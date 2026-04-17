#!/usr/bin/env python3
"""Enrich German verb forms from deWiktionary with safe fallbacks.

Fills these fields for verb entries:
- partizip2
- prateritum
- perfekt_yardimci
- trennbar
- cekimler
- verb_typ (when missing)

Data sources:
- dewiktionary.gz forms/head data
- grammar_utils fallbacks for verb type, participle II and separable verbs
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import unicodedata
from pathlib import Path

from grammar_utils import STARK_VERBS, classify_verb_type, get_partizip_ii, is_trennbar


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEWIKT_PATH = PROJECT_ROOT / "data" / "raw" / "downloads" / "dewiktionary.gz"

PERSON_SLOTS = ("ich", "du", "er/sie/es", "wir", "ihr", "sie/Sie")
KNOWN_TRENNBAR_PREFIXES = (
    "ab", "an", "auf", "aus", "bei", "ein", "empor", "entgegen", "entzwei", "fest",
    "fort", "heim", "her", "hin", "los", "mit", "nach", "nieder", "statt", "teil",
    "um", "vor", "weg", "wieder", "zurecht", "zurueck", "zurück", "zusammen", "zu",
)
LIKELY_SEIN_VERBS = {
    "abfahren",
    "ankommen",
    "aufstehen",
    "aussteigen",
    "bleiben",
    "einsteigen",
    "entschlafen",
    "fallen",
    "fliegen",
    "folgen",
    "fahren",
    "gehen",
    "gelingen",
    "geschehen",
    "kommen",
    "laufen",
    "passieren",
    "reisen",
    "rennen",
    "schwimmen",
    "sein",
    "springen",
    "sterben",
    "steigen",
    "sinken",
    "umziehen",
    "verschwinden",
    "wachsen",
    "wandern",
    "werden",
}

KNOWN_UNTRENNBAR_PREFIXES = (
    "be", "emp", "ent", "er", "ge", "miss", "ver", "zer",
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().casefold()


def compact_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def clean_form(text: str, keep_bang: bool = False) -> str:
    text = compact_space(text)
    if not keep_bang:
        text = text.rstrip("!")
    return compact_space(text.strip(" ,;"))


def is_verb_obj(obj: dict) -> bool:
    pos_blob = " ".join(
        str(obj.get(key) or "") for key in ("pos", "pos_title", "word_class")
    ).casefold()
    tokens = set(re.findall(r"[a-zäöüß-]+", pos_blob))
    if "hilfsverb" in tokens:
        return True
    if "verb" in tokens:
        return True
    return False


def slot_from_pronouns(pronouns: list[str]) -> str:
    cleaned = {str(item).strip().casefold() for item in pronouns if str(item).strip()}
    if cleaned == {"ich"}:
        return "ich"
    if cleaned == {"du"}:
        return "du"
    if cleaned == {"er", "sie", "es"}:
        return "er/sie/es"
    if cleaned == {"wir"}:
        return "wir"
    if cleaned == {"ihr"}:
        return "ihr"
    if cleaned in ({"sie"}, {"sie", "sie/sie"}):
        return "sie/Sie"
    return ""


def slot_from_tags(tags: set[str]) -> str:
    if "first-person" in tags and "singular" in tags:
        return "ich"
    if "second-person" in tags and "singular" in tags:
        return "du"
    if "third-person" in tags and "singular" in tags:
        return "er/sie/es"
    if "first-person" in tags and "plural" in tags:
        return "wir"
    if "second-person" in tags and "plural" in tags:
        return "ihr"
    if "third-person" in tags and "plural" in tags:
        return "sie/Sie"
    if "honorific" in tags:
        return "sie/Sie"
    return ""


def strip_slot_prefix(slot: str, form: str) -> str:
    prefixes = {
        "ich": ("ich ",),
        "du": ("du ",),
        "er/sie/es": ("er/sie/es ", "er ", "sie ", "es "),
        "wir": ("wir ",),
        "ihr": ("ihr ",),
        "sie/Sie": ("sie ", "Sie ", "sie/Sie "),
    }
    result = compact_space(form)
    for prefix in prefixes.get(slot, ()):
        if result.startswith(prefix):
            result = result[len(prefix):]
            break
    return clean_form(result, keep_bang=True)


def prefer_score(tags: set[str], raw_tags: list[str], source: str, *, prefer_main: bool) -> int:
    score = 0
    raw_join = " ".join(raw_tags).casefold()
    if "indicative" in tags:
        score += 40
    if "active" in tags:
        score += 20
    if "present" in tags or "past" in tags:
        score += 10
    if source.startswith("Flexion:"):
        score += 10
    if prefer_main and "main-clause" in tags:
        score += 15
    if "subordinate-clause" in tags:
        score -= 10
    if "subjunctive-i" in tags or "subjunctive-ii" in tags:
        score -= 25
    if "archaic" in tags or "uncommon" in tags or "obsolete" in tags:
        score -= 20
    if "Finite Formen" in raw_join:
        score += 5
    return score


def merge_present(bucket: dict, slot: str, form: str, score: int) -> None:
    current = bucket.get(slot)
    if current is None or score > current["score"]:
        bucket[slot] = {"form": form, "score": score}


def choose_best_text(candidates: list[tuple[str, int]]) -> str:
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (item[1], len(item[0])), reverse=True)
    return candidates[0][0]


def normalize_helper_values(values: set[str], raw_hints: set[str], lemma: str) -> str:
    helper_values = {compact_space(value).casefold() for value in values if compact_space(value) in {"haben", "sein"}}
    helper_values.update(raw_hints)
    if len(helper_values) == 1:
        return next(iter(helper_values))
    if len(helper_values) >= 2:
        return "haben/sein"
    if normalize(lemma) in LIKELY_SEIN_VERBS:
        return "sein"
    return "haben"


def build_perfekt_phrase(helper: str, partizip2: str) -> str:
    if not helper or not partizip2:
        return ""
    if helper == "sein":
        return f"ist {partizip2}"
    if helper == "haben":
        return f"hat {partizip2}"
    if helper == "haben/sein":
        return f"hat/ist {partizip2}"
    return f"{helper} {partizip2}"


def default_verb_info() -> dict:
    return {
        "partizip2_candidates": [],
        "prateritum_candidates": [],
        "helper_values": set(),
        "helper_hints": set(),
        "present_forms": {},
        "imperative_forms": {},
    }


def has_real_verb_signal(info: dict) -> bool:
    return bool(
        info.get("present_forms")
        or info.get("imperative_forms")
        or info.get("prateritum_candidates")
        or info.get("helper_values")
        or info.get("helper_hints")
    )


def extract_helper_hint(raw_tags: list[str]) -> set[str]:
    hints = set()
    for raw in raw_tags:
        lowered = str(raw).casefold()
        if "hilfsverb sein" in lowered:
            hints.add("sein")
        if "hilfsverb haben" in lowered:
            hints.add("haben")
    return hints


def extract_verb_index(target_keys: set[str]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    processed = 0
    matched = 0

    with gzip.open(DEWIKT_PATH, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            processed += 1
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("lang_code") != "de" or not is_verb_obj(obj):
                continue

            word = compact_space(obj.get("word") or "")
            key = normalize(word)
            if key not in target_keys:
                continue

            matched += 1
            info = index.setdefault(key, default_verb_info())
            for form_data in obj.get("forms") or []:
                form = clean_form(form_data.get("form") or "", keep_bang=True)
                if not form:
                    continue
                tags = {str(tag).casefold() for tag in (form_data.get("tags") or [])}
                raw_tags = [str(tag) for tag in (form_data.get("raw_tags") or [])]
                source = str(form_data.get("source") or "")
                pronouns = [str(item) for item in (form_data.get("pronouns") or [])]

                if "participle-2" in tags and "perfect" in tags:
                    score = 10
                    if " " not in form:
                        score += 20
                    if normalize(form) != "worden":
                        score += 10
                    if "passive" not in tags:
                        score += 5
                    info["partizip2_candidates"].append((clean_form(form), score))

                if "past" in tags:
                    slot = slot_from_pronouns(pronouns) or slot_from_tags(tags)
                    if slot == "ich":
                        stripped = strip_slot_prefix(slot, form)
                        score = prefer_score(tags, raw_tags, source, prefer_main=True)
                        info["prateritum_candidates"].append((clean_form(stripped), score))

                if "auxiliary" in tags and "perfect" in tags:
                    helper = normalize(clean_form(form))
                    if helper in {"haben", "sein"}:
                        info["helper_values"].add(helper)
                    info["helper_hints"].update(extract_helper_hint(raw_tags))

                if "present" in tags:
                    slot = slot_from_pronouns(pronouns) or slot_from_tags(tags)
                    if slot:
                        stripped = strip_slot_prefix(slot, form)
                        if stripped:
                            score = prefer_score(tags, raw_tags, source, prefer_main=True)
                            merge_present(info["present_forms"], slot, stripped, score)

                if "imperative" in tags:
                    imp_slot = ""
                    if "singular" in tags:
                        imp_slot = "singular"
                    elif "plural" in tags:
                        imp_slot = "plural"
                    elif "honorific" in tags:
                        imp_slot = "honorific"
                    if imp_slot:
                        stripped = clean_form(form, keep_bang=False)
                        score = prefer_score(tags, raw_tags, source, prefer_main=False)
                        current = info["imperative_forms"].get(imp_slot)
                        if current is None or score > current["score"]:
                            info["imperative_forms"][imp_slot] = {"form": stripped, "score": score}

    print(f"dewiktionary verb scan: {matched} matched entries from {processed} rows", flush=True)
    return index


def merge_cekimler(existing: dict | None, *, present: dict[str, str], prateritum: str, perfekt: str, imperative: str) -> tuple[dict, int]:
    merged = dict(existing or {})
    changes = 0

    current_present = dict(merged.get("präsens") or {})
    for slot in PERSON_SLOTS:
        value = present.get(slot, "")
        if value and not compact_space(current_present.get(slot) or ""):
            current_present[slot] = value
            changes += 1
    if current_present and current_present != merged.get("präsens"):
        merged["präsens"] = current_present

    for key, value in (("präteritum", prateritum), ("perfekt", perfekt), ("imperativ", imperative)):
        if value and not compact_space(merged.get(key) or ""):
            merged[key] = value
            changes += 1
    return merged, changes


def helper_from_lemma(lemma: str) -> str:
    return "sein" if normalize(lemma) in LIKELY_SEIN_VERBS else "haben"


def extract_trennbar_prefix(lemma: str) -> str:
    word = compact_space(lemma).casefold()
    for prefix in sorted(KNOWN_TRENNBAR_PREFIXES, key=len, reverse=True):
        if word.startswith(prefix) and len(word) > len(prefix) + 2:
            return prefix
    return ""


def split_known_prefix(lemma: str) -> tuple[str, str, str]:
    word = compact_space(lemma).casefold()
    for prefix in sorted(KNOWN_TRENNBAR_PREFIXES, key=len, reverse=True):
        if word.startswith(prefix) and len(word) > len(prefix) + 2:
            return prefix, word[len(prefix):], "trennbar"
    for prefix in sorted(KNOWN_UNTRENNBAR_PREFIXES, key=len, reverse=True):
        if word.startswith(prefix) and len(word) > len(prefix) + 2:
            return prefix, word[len(prefix):], "untrennbar"
    return "", word, ""


def weak_prateritum_form(lemma: str) -> str:
    word = compact_space(lemma).casefold()
    if not word:
        return ""
    if word.endswith(("eln", "ern")) and len(word) > 4:
        stem = word[:-1]
    elif word.endswith("en") and len(word) > 3:
        stem = word[:-2]
    else:
        stem = word
    if not stem:
        return ""
    if re.search(r"(d|t|[^aeiouäöü]m|[^aeiouäöü]n)$", stem):
        return f"{stem}ete"
    return f"{stem}te"


def build_prefixed_prateritum(prefix: str, base_prateritum: str, prefix_kind: str) -> str:
    base_prateritum = compact_space(base_prateritum)
    if not prefix or not base_prateritum:
        return base_prateritum
    if prefix_kind == "trennbar":
        return base_prateritum if base_prateritum.endswith(f" {prefix}") else f"{base_prateritum} {prefix}"
    return f"{prefix}{base_prateritum}"


def infer_prateritum_fallback(lemma: str) -> str:
    word = compact_space(lemma)
    if not word:
        return ""

    norm = normalize(word)
    if norm in STARK_VERBS:
        return compact_space(STARK_VERBS[norm][0])

    prefix, base, prefix_kind = split_known_prefix(word)
    if base in STARK_VERBS:
        return build_prefixed_prateritum(prefix, STARK_VERBS[base][0], prefix_kind)

    verb_type = compact_space(classify_verb_type(word))
    target = base if prefix_kind == "trennbar" and base else word.casefold()
    if verb_type in {"schwach", "gemischt"}:
        inferred = weak_prateritum_form(target)
        return build_prefixed_prateritum(prefix, inferred, prefix_kind)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dict-path", default=str(DEFAULT_DICT_PATH))
    parser.add_argument("--report-path", default="")
    args = parser.parse_args()
    dict_path = Path(args.dict_path)

    if not dict_path.exists():
        print(f"dictionary.json not found: {dict_path}", flush=True)
        return 2
    if not DEWIKT_PATH.exists():
        print(f"dewiktionary.gz not found: {DEWIKT_PATH}", flush=True)
        return 2

    data = json.loads(dict_path.read_text(encoding="utf-8"))
    verbs = [row for row in data if compact_space(row.get("tur") or "").casefold() == "fiil" and compact_space(row.get("almanca") or "")]
    if args.limit:
        verbs = verbs[: args.limit]
    target_keys = {normalize(row["almanca"]) for row in verbs}

    print(f"target verbs: {len(verbs)}", flush=True)
    verb_index = extract_verb_index(target_keys)

    updated_entries = 0
    partizip2_added = 0
    prateritum_added = 0
    prateritum_fallback_added = 0
    helper_added = 0
    trennbar_added = 0
    trennbar_prefix_added = 0
    cekimler_added = 0
    verb_typ_added = 0

    for row in verbs:
        lemma = compact_space(row.get("almanca") or "")
        lemma_key = normalize(lemma)
        info = verb_index.get(lemma_key, default_verb_info())
        has_index_entry = lemma_key in verb_index
        changed = False

        partizip2 = choose_best_text(list(info["partizip2_candidates"]))
        if not partizip2:
            partizip2 = compact_space(get_partizip_ii(lemma))
        if partizip2 and (args.overwrite or not compact_space(row.get("partizip2") or "")):
            if compact_space(row.get("partizip2") or "") != partizip2:
                row["partizip2"] = partizip2
                partizip2_added += 1
                changed = True

        prateritum = choose_best_text(list(info["prateritum_candidates"]))
        if not prateritum and lemma_key in STARK_VERBS:
            prateritum = compact_space(STARK_VERBS[lemma_key][0])
        used_prateritum_fallback = False
        if not prateritum and has_index_entry and has_real_verb_signal(info):
            prateritum = infer_prateritum_fallback(lemma)
            used_prateritum_fallback = bool(prateritum)
        if prateritum and (args.overwrite or not compact_space(row.get("prateritum") or "")):
            if compact_space(row.get("prateritum") or "") != prateritum:
                row["prateritum"] = prateritum
                prateritum_added += 1
                if used_prateritum_fallback:
                    prateritum_fallback_added += 1
                changed = True

        helper = normalize_helper_values(info["helper_values"], info["helper_hints"], lemma)
        helper_output = helper if helper else helper_from_lemma(lemma)
        if helper_output and (args.overwrite or not compact_space(row.get("perfekt_yardimci") or "")):
            if compact_space(row.get("perfekt_yardimci") or "") != helper_output:
                row["perfekt_yardimci"] = helper_output
                helper_added += 1
                changed = True

        trennbar_value = "trennbar" if is_trennbar(lemma) else ""
        if trennbar_value and (args.overwrite or not compact_space(row.get("trennbar") or "")):
            if compact_space(row.get("trennbar") or "") != trennbar_value:
                row["trennbar"] = trennbar_value
                trennbar_added += 1
                changed = True
        if trennbar_value:
            prefix_value = extract_trennbar_prefix(lemma)
            if prefix_value and (args.overwrite or not compact_space(row.get("trennbar_prefix") or "")):
                if compact_space(row.get("trennbar_prefix") or "") != prefix_value:
                    row["trennbar_prefix"] = prefix_value
                    trennbar_prefix_added += 1
                    changed = True

        verb_typ = compact_space(row.get("verb_typ") or "")
        if not verb_typ or args.overwrite:
            inferred_type = compact_space(classify_verb_type(lemma))
            if inferred_type and inferred_type != verb_typ:
                row["verb_typ"] = inferred_type
                verb_typ_added += 1
                changed = True

        present = {
            slot: info["present_forms"][slot]["form"]
            for slot in PERSON_SLOTS
            if slot in info["present_forms"] and compact_space(info["present_forms"][slot]["form"])
        }
        imperative_parts = []
        for imp_slot in ("singular", "plural", "honorific"):
            item = info["imperative_forms"].get(imp_slot)
            if item and compact_space(item["form"]):
                imperative_parts.append(compact_space(item["form"]))
        imperative = ", ".join(dict.fromkeys(imperative_parts))
        effektive_partizip2 = compact_space(row.get("partizip2") or partizip2)
        effektive_helper = compact_space(row.get("perfekt_yardimci") or helper_output)
        perfekt = build_perfekt_phrase(effektive_helper, effektive_partizip2)

        merged_cekimler, local_changes = merge_cekimler(
            row.get("cekimler") or {},
            present=present,
            prateritum=compact_space(row.get("prateritum") or prateritum),
            perfekt=perfekt,
            imperative=imperative,
        )
        if local_changes and (args.overwrite or not (row.get("cekimler") or {})):
            row["cekimler"] = merged_cekimler
            cekimler_added += 1
            changed = True
        elif local_changes and row.get("cekimler"):
            row["cekimler"] = merged_cekimler
            cekimler_added += 1
            changed = True

        if changed:
            updated_entries += 1
            kaynak = compact_space(row.get("kaynak") or "")
            if "Wiktionary DE (CC BY-SA 3.0)" not in kaynak:
                row["kaynak"] = (kaynak + "; Wiktionary DE (CC BY-SA 3.0)").strip("; ")

    report = {
        "target_verbs": len(verbs),
        "matched_in_dump": len(verb_index),
        "updated_entries": updated_entries,
        "partizip2_added": partizip2_added,
        "prateritum_added": prateritum_added,
        "prateritum_fallback_added": prateritum_fallback_added,
        "perfekt_yardimci_added": helper_added,
        "trennbar_added": trennbar_added,
        "trennbar_prefix_added": trennbar_prefix_added,
        "cekimler_added": cekimler_added,
        "verb_typ_added": verb_typ_added,
        "dry_run": args.dry_run,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if args.report_path:
        Path(args.report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.dry_run:
        dict_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"saved: {dict_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
