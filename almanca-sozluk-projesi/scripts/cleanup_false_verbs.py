#!/usr/bin/env python3
"""Reclassify high-confidence false verb entries using exact deWiktionary POS matches."""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from enrich_verb_usage import VERB_POS, compact, normalize
from merge_stage_dictionary_safe import InterProcessFileLock, LOCK_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "cleanup_false_verbs_report.json"
DEWIKT_PATH = PROJECT_ROOT / "data" / "raw" / "downloads" / "dewiktionary.gz"

POS_MAP = {
    "adjective": "sıfat",
    "adj": "sıfat",
    "adverb": "zarf",
    "adv": "zarf",
    "conjunction": "bağlaç",
    "conj": "bağlaç",
    "pronoun": "zamir",
    "pron": "zamir",
    "preposition": "edat",
    "prep": "edat",
    "interjection": "ünlem",
    "intj": "ünlem",
    "phrase": "ifade",
    "proverb": "deyim",
    "idiom": "deyim",
    "abbrev": "kısaltma",
}
VERB_SPECIFIC_FIELDS = (
    "partizip2",
    "prateritum",
    "perfekt_yardimci",
    "verb_typ",
    "trennbar",
    "trennbar_prefix",
    "cekimler",
    "valenz",
    "fiil_kaliplari",
)


def looks_turkish_infinitive(row: dict) -> bool:
    blob = " ".join(
        compact(row.get(field) or "")
        for field in ("turkce", "aciklama_turkce")
        if compact(row.get(field) or "")
    )
    for token in blob.replace(";", " ").replace(",", " ").split():
        stripped = token.strip("()[]'\"“”.,:;!?").casefold()
        if stripped.endswith(("mek", "mak")):
            return True
    return False


def build_exact_pos_index(target_keys: set[str]) -> dict[str, dict[str, set[str]]]:
    index: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"mapped": set(), "raw": set()})
    with gzip.open(DEWIKT_PATH, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("lang_code") != "de":
                continue
            word = compact(obj.get("word") or "")
            if not word:
                continue
            key = normalize(word)
            if key not in target_keys:
                continue
            pos = str(obj.get("pos") or "").casefold()
            if not pos:
                continue
            index[key]["raw"].add(pos)
            mapped = POS_MAP.get(pos)
            if mapped:
                index[key]["mapped"].add(mapped)
    return index


def should_reclassify(row: dict, exact_pos: dict[str, set[str]], *, include_mixed_pos: bool) -> tuple[bool, str, str]:
    mapped = set(exact_pos.get("mapped") or set())
    raw = {str(item).casefold() for item in (exact_pos.get("raw") or set())}
    if len(mapped) != 1:
        return False, "", "ambiguous-or-missing-nonverb-pos"
    has_verb_entry = "verb" in raw or "auxiliary-verb" in raw or "verb form" in raw
    if compact(row.get("prateritum") or ""):
        return False, "", "has-prateritum"
    if row.get("fiil_kaliplari") or row.get("valenz"):
        return False, "", "has-verb-usage-data"
    target_tur = next(iter(mapped))
    if not has_verb_entry:
        return True, target_tur, "exact-nonverb-pos"
    if target_tur in {"bağlaç", "zamir", "edat", "ünlem", "ifade"}:
        return True, target_tur, "mixed-pos-but-function-word"
    if include_mixed_pos and target_tur in {"zarf", "sıfat"} and not looks_turkish_infinitive(row):
        return True, target_tur, "mixed-pos-nonverb-gloss"
    return False, "", "mixed-pos-with-verb-gloss"


def clear_verb_fields(row: dict) -> int:
    changes = 0
    for field in VERB_SPECIFIC_FIELDS:
        existing = row.get(field)
        if field in {"valenz", "fiil_kaliplari"}:
            if existing:
                row[field] = []
                changes += 1
        elif field == "cekimler":
            if existing:
                row[field] = {}
                changes += 1
        else:
            if existing not in (None, "", False):
                row[field] = None
                changes += 1
    return changes


def append_cleanup_note(row: dict, target_tur: str, reason: str) -> None:
    note = compact(row.get("not") or "")
    addition = f"[cleanup_false_verbs] Exact deWiktionary POS nedeniyle tür '{target_tur}' olarak düzeltildi ({reason})."
    if addition not in note:
        row["not"] = addition if not note else f"{note}\n{addition}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup high-confidence false verbs.")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--keep-verb-fields", action="store_true")
    parser.add_argument("--include-mixed-pos", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.dict_path.read_text(encoding="utf-8"))
    target_keys = {
        normalize(row.get("almanca") or "")
        for row in data
        if compact(row.get("tur") or "").casefold() == VERB_POS and compact(row.get("almanca") or "")
    }
    exact_pos_index = build_exact_pos_index(target_keys)

    counters = Counter()
    samples: list[dict] = []

    for row in data:
        if compact(row.get("tur") or "").casefold() != VERB_POS:
            continue
        lemma = compact(row.get("almanca") or "")
        if not lemma:
            continue
        lemma_key = normalize(lemma)
        should_apply, target_tur, reason = should_reclassify(
            row,
            exact_pos_index.get(lemma_key) or {},
            include_mixed_pos=args.include_mixed_pos,
        )
        if not should_apply or not target_tur:
            continue

        previous_tur = compact(row.get("tur") or "")
        row["tur"] = target_tur
        counters["reclassified_entries"] += 1
        counters[f"target::{target_tur}"] += 1
        if not args.keep_verb_fields:
            counters["cleared_verb_fields"] += clear_verb_fields(row)
        append_cleanup_note(row, target_tur, reason)
        if len(samples) < 120:
            samples.append(
                {
                    "lemma": lemma,
                    "from": previous_tur,
                    "to": target_tur,
                    "reason": reason,
                }
            )

    output_path = args.output_path or args.dict_path
    report = {
        "dict_path": str(args.dict_path),
        "output_path": str(output_path),
        "apply": bool(args.apply),
        "counters": dict(counters),
        "sample": samples,
    }

    if args.apply:
        with InterProcessFileLock(LOCK_PATH):
            output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
