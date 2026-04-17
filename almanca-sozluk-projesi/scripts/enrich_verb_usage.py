#!/usr/bin/env python3
"""Enrich verb usage with safer patterns, context groups, and examples from deWiktionary."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "verb_usage_report.json"
DEWIKT_PATH = PROJECT_ROOT / "data" / "raw" / "downloads" / "dewiktionary.gz"

VERB_POS = "fiil"
PREPOSITIONS = {
    "an": "an",
    "ans": "an",
    "am": "an",
    "auf": "auf",
    "aufs": "auf",
    "aus": "aus",
    "bei": "bei",
    "beim": "bei",
    "für": "für",
    "fur": "für",
    "gegen": "gegen",
    "in": "in",
    "im": "in",
    "ins": "in",
    "mit": "mit",
    "nach": "nach",
    "über": "über",
    "uber": "über",
    "ums": "um",
    "um": "um",
    "unter": "unter",
    "von": "von",
    "vom": "von",
    "vor": "vor",
    "zu": "zu",
    "zum": "zu",
    "zur": "zu",
}
CASE_WORDS = ("Akkusativ", "Dativ", "Genitiv")
REFLEXIVE_PRONOUNS = {"mich", "dich", "sich", "uns", "euch"}
TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß-]+")
CASE_RE = re.compile(r"\bmit\s+(Dativ|Akkusativ|Genitiv)\b", re.IGNORECASE)
PLUS_CASE_RE = re.compile(r"\b([A-Za-zÄÖÜäöüß]+)\s*\+\s*(Akkusativ|Dativ|Genitiv)\b", re.IGNORECASE)


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().casefold()


def tokenize(text: str) -> list[str]:
    return [normalize(token) for token in TOKEN_RE.findall(str(text or "")) if normalize(token)]


def is_true_verb_entry(obj: dict) -> bool:
    if obj.get("lang_code") != "de":
        return False
    if str(obj.get("pos") or "").casefold() != "verb":
        return False
    word = compact(obj.get("word") or "")
    if not word:
        return False
    signals = 0
    for form in obj.get("forms") or []:
        tags = {str(tag).casefold() for tag in (form.get("tags") or [])}
        if "present" in tags or "imperative" in tags or "past" in tags:
            signals += 1
            break
        if "auxiliary" in tags and "perfect" in tags:
            signals += 1
            break
    if signals:
        return True
    for sense in obj.get("senses") or []:
        tags = {str(tag).casefold() for tag in (sense.get("tags") or [])}
        if "reflexive" in tags or "transitive" in tags or "intransitive" in tags:
            return True
        if sense.get("examples"):
            return True
    return False


def load_dewiktionary_verbs(target_lemmas: set[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    with gzip.open(DEWIKT_PATH, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not is_true_verb_entry(obj):
                continue
            lemma = compact(obj.get("word") or "")
            key = normalize(lemma)
            if key in target_lemmas and key not in result:
                result[key] = obj
    return result


def existing_example_map(record: dict) -> dict[str, str]:
    pairs: dict[str, str] = {}
    top_de = compact(record.get("ornek_almanca") or "")
    top_tr = compact(record.get("ornek_turkce") or "")
    if top_de and top_tr:
        pairs[normalize(top_de)] = top_tr
    for example in record.get("ornekler") or []:
        if not isinstance(example, dict):
            continue
        de = compact(example.get("almanca") or "")
        tr = compact(example.get("turkce") or "")
        if de and tr and normalize(de) not in pairs:
            pairs[normalize(de)] = tr
    return pairs


def collect_known_forms(record: dict) -> set[str]:
    forms = set()
    for field in ("almanca", "partizip2", "prateritum"):
        value = compact(record.get(field) or "")
        if value:
            tokens = tokenize(value)
            if len(tokens) == 1:
                forms.add(tokens[0])
    cekimler = record.get("cekimler") or {}
    if isinstance(cekimler, dict):
        for value in cekimler.values():
            if isinstance(value, dict):
                iterable = value.values()
            else:
                iterable = (value,)
            for item in iterable:
                tokens = tokenize(item)
                if len(tokens) == 1:
                    forms.add(tokens[0])
    return forms


def split_prefix_root(lemma: str) -> str:
    for prefix in (
        "ab", "an", "auf", "aus", "bei", "ein", "fort", "her", "hin", "los",
        "mit", "nach", "nieder", "um", "vor", "weg", "wieder", "zu", "zurück",
        "zurueck", "zusammen",
    ):
        if lemma.startswith(prefix) and len(lemma) > len(prefix) + 3:
            return lemma[len(prefix):]
    return lemma


def keep_existing_pattern(record: dict, pattern_row: dict) -> bool:
    phrase = compact(pattern_row.get("kalip") or "")
    if not phrase:
        return False
    phrase_norm = normalize(phrase)
    if "+" in phrase or phrase_norm.startswith("sich "):
        return True
    tokens = tokenize(phrase)
    raw_tokens = TOKEN_RE.findall(phrase)
    forms = collect_known_forms(record)
    lemma = normalize(record.get("almanca") or "")
    root = split_prefix_root(lemma)
    for raw, token in zip(raw_tokens, tokens):
        if token == lemma and raw[:1].islower():
            return True
        if token in forms and raw[:1].islower():
            return True
        if root == token and root == lemma and raw[:1].islower():
            return True
    return False


def sense_translation(record: dict, sense_index: int) -> str:
    senses = record.get("anlamlar") or []
    if isinstance(senses, list) and sense_index < len(senses):
        candidate = senses[sense_index]
        if isinstance(candidate, dict):
            text = compact(candidate.get("turkce") or "")
            if text:
                return text
    return compact(record.get("turkce") or "")


def sense_explanation(record: dict, sense_index: int) -> str:
    senses = record.get("anlamlar") or []
    if isinstance(senses, list) and sense_index < len(senses):
        candidate = senses[sense_index]
        if isinstance(candidate, dict):
            text = compact(candidate.get("aciklama_turkce") or "")
            if text:
                return text
    return compact(record.get("aciklama_turkce") or "")


def extract_case_patterns(lemma: str, reflexive: bool, texts: list[str]) -> list[str]:
    patterns: list[str] = []
    prefix = f"sich {lemma}" if reflexive else lemma
    for text in texts:
        for match in CASE_RE.finditer(text):
            patterns.append(f"{prefix} + {match.group(1).capitalize()}")
        for match in PLUS_CASE_RE.finditer(text):
            prep = compact(match.group(1))
            case = compact(match.group(2)).capitalize()
            patterns.append(f"{prefix} {prep} + {case}")
    return patterns


def extract_prep_patterns(lemma: str, forms: set[str], examples: list[str], reflexive: bool) -> list[str]:
    counts: Counter[str] = Counter()
    for text in examples:
        tokens = tokenize(text)
        for idx, token in enumerate(tokens):
            if token not in forms:
                continue
            saw_reflexive = reflexive or any(prev in REFLEXIVE_PRONOUNS for prev in tokens[max(0, idx - 3):idx])
            for probe in tokens[idx + 1: idx + 5]:
                mapped = PREPOSITIONS.get(probe)
                if mapped:
                    phrase = f"{'sich ' if saw_reflexive else ''}{lemma} {mapped}"
                    counts[phrase] += 1
                    break
    minimum = 1 if reflexive else 99
    return [phrase for phrase, count in counts.most_common(3) if count >= minimum]


def extract_translation_note_patterns(record: dict, lemma: str, reflexive: bool) -> list[str]:
    text = " ".join(
        compact(record.get(field) or "")
        for field in ("turkce", "aciklama_turkce")
        if compact(record.get(field) or "")
    )
    patterns: list[str] = []
    prefix = f"sich {lemma}" if reflexive else lemma
    for prep in re.findall(r"\+\s*([A-Za-zÄÖÜäöüß]+)", text):
        prep_norm = PREPOSITIONS.get(normalize(prep))
        if prep_norm:
            patterns.append(f"{prefix} {prep_norm}")
    return patterns


def make_context_category(sense: dict) -> str:
    topics = sense.get("topics") or []
    if topics:
        return compact(topics[0] or "") or "genel"
    tags = {str(tag).casefold() for tag in (sense.get("tags") or [])}
    if "reflexive" in tags:
        return "refleksif"
    if "transitive" in tags or "intransitive" in tags:
        return "valenz"
    return "genel"


def merge_contexts(existing: list, staged: list) -> list[dict]:
    by_cat: dict[str, dict] = {}
    merged = []
    for item in existing or []:
        if isinstance(item, dict):
            cat = compact(item.get("kategori") or "")
            if cat:
                by_cat[normalize(cat)] = item
                merged.append(item)
    for item in staged:
        cat = compact(item.get("kategori") or "")
        if not cat:
            continue
        target = by_cat.get(normalize(cat))
        if target is None:
            merged.append(item)
            by_cat[normalize(cat)] = item
            continue
        live_examples = list(target.get("cumleler") or [])
        seen = {(normalize(ex.get("de") or ""), normalize(ex.get("tr") or "")) for ex in live_examples if isinstance(ex, dict)}
        for example in item.get("cumleler") or []:
            if not isinstance(example, dict):
                continue
            key = (normalize(example.get("de") or ""), normalize(example.get("tr") or ""))
            if not key[0] or key in seen:
                continue
            live_examples.append({"de": compact(example.get("de") or ""), "tr": compact(example.get("tr") or "")})
            seen.add(key)
        target["cumleler"] = live_examples
    return merged


def dedupe_patterns(rows: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        phrase = compact(row.get("kalip") or "")
        key = normalize(phrase)
        if not phrase or key in seen:
            continue
        seen.add(key)
        deduped.append(
            {
                "kalip": phrase,
                "turkce": compact(row.get("turkce") or ""),
                "aciklama_turkce": compact(row.get("aciklama_turkce") or ""),
                "ornek_almanca": compact(row.get("ornek_almanca") or ""),
                "ornek_turkce": compact(row.get("ornek_turkce") or ""),
                "kaynak": compact(row.get("kaynak") or ""),
            }
        )
    return deduped


def dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        clean = compact(item)
        key = normalize(clean)
        if not clean or key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-sense-examples", type=int, default=2)
    args = parser.parse_args()

    dict_path = args.dict_path
    output_path = args.output_path or dict_path
    data = json.loads(dict_path.read_text(encoding="utf-8"))

    target_lemmas = {
        normalize(compact(record.get("almanca") or ""))
        for record in data
        if compact(record.get("tur") or "").casefold() == VERB_POS and compact(record.get("almanca") or "")
    }
    dewiktionary_index = load_dewiktionary_verbs(target_lemmas)

    counters = Counter()
    sample: list[dict] = []

    for record in data:
        if compact(record.get("tur") or "").casefold() != VERB_POS:
            continue

        lemma = compact(record.get("almanca") or "")
        if not lemma:
            continue
        lemma_key = normalize(lemma)
        source_entry = dewiktionary_index.get(lemma_key)
        if source_entry is None:
            continue

        existing_map = existing_example_map(record)
        forms = collect_known_forms(record)
        forms.add(lemma_key)

        new_contexts: list[dict] = []
        new_examples: list[dict] = list(record.get("ornekler") or [])
        seen_example_keys = {
            normalize(example.get("almanca") or "")
            for example in new_examples
            if isinstance(example, dict) and compact(example.get("almanca") or "")
        }
        pattern_rows: list[dict] = [
            row for row in (record.get("fiil_kaliplari") or []) if isinstance(row, dict) and keep_existing_pattern(record, row)
        ]
        valenz_rows: list[str] = list(record.get("valenz") or [])
        related = list(record.get("ilgili_kayitlar") or [])
        related_seen = {normalize(item) for item in related}

        for sense_index, sense in enumerate(source_entry.get("senses") or []):
            gloss_texts = [compact(text) for text in (sense.get("glosses") or []) + (sense.get("raw_glosses") or []) if compact(text)]
            example_dicts = [item for item in (sense.get("examples") or []) if isinstance(item, dict) and compact(item.get("text") or "")]
            example_texts = [compact(item.get("text") or "") for item in example_dicts]
            if not gloss_texts and not example_texts:
                continue

            tags = {str(tag).casefold() for tag in (sense.get("tags") or [])}
            example_tokens = [tokenize(text) for text in example_texts]
            reflexive = "reflexive" in tags
            has_reflexive_example = any(any(token in REFLEXIVE_PRONOUNS for token in tokens) for tokens in example_tokens)
            turkish = sense_translation(record, sense_index)
            explanation = sense_explanation(record, sense_index)

            case_patterns = extract_case_patterns(lemma, reflexive and has_reflexive_example, gloss_texts)
            prep_patterns = extract_prep_patterns(lemma, forms, example_texts, reflexive)
            prep_patterns.extend(extract_translation_note_patterns(record, lemma, reflexive))
            valenz_rows.extend(case_patterns)
            valenz_rows.extend(prep_patterns)
            if reflexive and has_reflexive_example:
                case_patterns.insert(0, f"sich {lemma}")

            first_example_de = ""
            first_example_tr = ""
            context_examples: list[dict] = []
            for example_text in example_texts[: args.max_sense_examples]:
                translated = compact(existing_map.get(normalize(example_text), ""))
                context_examples.append({"de": example_text, "tr": translated})
                if normalize(example_text) not in seen_example_keys:
                    new_examples.append({"almanca": example_text, "turkce": translated, "kaynak": "deWiktionary"})
                    seen_example_keys.add(normalize(example_text))
                    counters["examples_added"] += 1
                if not first_example_de:
                    first_example_de = example_text
                    first_example_tr = translated

            if context_examples:
                new_contexts.append(
                    {
                        "kategori": make_context_category(sense),
                        "cumleler": context_examples,
                    }
                )

            for phrase in case_patterns + prep_patterns:
                pattern_rows.append(
                    {
                        "kalip": phrase,
                        "turkce": turkish,
                        "aciklama_turkce": explanation,
                        "ornek_almanca": first_example_de,
                        "ornek_turkce": first_example_tr,
                        "kaynak": "deWiktionary",
                    }
                )

        cleaned_patterns = dedupe_patterns(pattern_rows)
        for row_item in cleaned_patterns:
            phrase = compact(row_item.get("kalip") or "")
            if phrase and normalize(phrase).startswith(f"sich {lemma_key}"):
                valenz_rows.append(phrase)
        cleaned_valenz = dedupe_strings(valenz_rows)
        if cleaned_patterns and json.dumps(cleaned_patterns, ensure_ascii=False, sort_keys=True) != json.dumps(record.get("fiil_kaliplari") or [], ensure_ascii=False, sort_keys=True):
            record["fiil_kaliplari"] = cleaned_patterns
            counters["verbs_patterns_updated"] += 1
            counters["patterns_total"] += len(cleaned_patterns)
            for row in cleaned_patterns:
                phrase = compact(row.get("kalip") or "")
                if phrase and normalize(phrase) not in related_seen:
                    related.append(phrase)
                    related_seen.add(normalize(phrase))
                    counters["related_links_added"] += 1
            record["ilgili_kayitlar"] = related

        if cleaned_valenz and json.dumps(cleaned_valenz, ensure_ascii=False) != json.dumps(record.get("valenz") or [], ensure_ascii=False):
            record["valenz"] = cleaned_valenz
            counters["verbs_valenz_updated"] += 1
            counters["valenz_total"] += len(cleaned_valenz)

        merged_contexts = merge_contexts(record.get("baglamlar") or [], new_contexts)
        if merged_contexts and json.dumps(merged_contexts, ensure_ascii=False, sort_keys=True) != json.dumps(record.get("baglamlar") or [], ensure_ascii=False, sort_keys=True):
            record["baglamlar"] = merged_contexts
            counters["verbs_contexts_updated"] += 1

        if json.dumps(new_examples, ensure_ascii=False, sort_keys=True) != json.dumps(record.get("ornekler") or [], ensure_ascii=False, sort_keys=True):
            record["ornekler"] = new_examples
            counters["verbs_examples_updated"] += 1
            if not compact(record.get("ornek_almanca") or "") and new_contexts:
                first_group = new_contexts[0].get("cumleler") or []
                if first_group:
                    record["ornek_almanca"] = compact(first_group[0].get("de") or "")
                    if compact(first_group[0].get("tr") or ""):
                        record["ornek_turkce"] = compact(first_group[0].get("tr") or "")

        if len(sample) < 20 and (new_contexts or cleaned_patterns):
            sample.append(
                {
                    "verb": lemma,
                    "patterns": [row.get("kalip") for row in cleaned_patterns[:4]],
                    "valenz": cleaned_valenz[:4],
                    "context_categories": [item.get("kategori") for item in merged_contexts[:3]],
                }
            )

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "dict_path": str(dict_path),
        "output_path": str(output_path),
        "dewiktionary_exact_verbs": len(dewiktionary_index),
        "counters": dict(counters),
        "sample": sample,
    }
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
