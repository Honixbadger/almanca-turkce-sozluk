#!/usr/bin/env python3
"""Enrich verb records with frequent phrase patterns and verb-centric examples."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from enrich_phrase_patterns import (
    build_translation_index,
    extract_candidates,
    load_manual_phrase_records,
    load_wikdict_index,
    mine_bulk_candidates,
    normalize_key,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "verb_patterns_report.json"
VERB_POS = "fiil"
PHRASE_POS_VALUES = {"kalıp", "ifade", "deyim"}
TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüßÇĞİIÖŞÜçğıöşü-]{3,}")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().casefold()


def token_list(text: str) -> list[str]:
    return [normalize(item) for item in TOKEN_RE.findall(str(text or "")) if normalize(item)]


def collect_entry_examples(record: dict) -> list[dict]:
    examples: list[dict] = []
    seen: set[tuple[str, str]] = set()
    top_de = compact(record.get("ornek_almanca") or "")
    top_tr = compact(record.get("ornek_turkce") or "")
    if top_de:
        examples.append({"almanca": top_de, "turkce": top_tr, "kaynak": compact(record.get("kaynak") or "")})
        seen.add((normalize(top_de), normalize(top_tr)))

    for item in record.get("ornekler") or []:
        if not isinstance(item, dict):
            continue
        de = compact(item.get("almanca") or "")
        tr = compact(item.get("turkce") or "")
        if not de:
            continue
        key = (normalize(de), normalize(tr))
        if key in seen:
            continue
        seen.add(key)
        examples.append({"almanca": de, "turkce": tr, "kaynak": compact(item.get("kaynak") or "")})
    return examples


def collect_known_forms(record: dict) -> set[str]:
    forms = {
        normalize(record.get("almanca") or ""),
        normalize(record.get("partizip2") or ""),
        normalize(record.get("prateritum") or ""),
    }
    cekimler = record.get("cekimler") or {}
    if isinstance(cekimler, dict):
        for value in cekimler.values():
            if isinstance(value, dict):
                for slot_value in value.values():
                    clean = compact(slot_value or "")
                    if clean:
                        tokens = token_list(clean)
                        if len(tokens) == 1:
                            forms.add(tokens[0])
            else:
                clean = compact(value or "")
                if clean:
                    tokens = token_list(clean)
                    if len(tokens) == 1:
                        forms.add(tokens[0])
    return {item for item in forms if item}


def phrase_contains_verb(phrase: str, forms: set[str]) -> bool:
    tokens = token_list(phrase)
    return any(token in forms for token in tokens)


def build_phrase_index(data: list[dict]) -> dict[str, dict]:
    phrase_index: dict[str, dict] = {}
    for record in data:
        pos = compact(record.get("tur") or "")
        phrase = compact(record.get("almanca") or "")
        if not phrase:
            continue
        if pos in PHRASE_POS_VALUES or (" " in phrase and pos != VERB_POS):
            phrase_index[normalize_key(phrase)] = record
    return phrase_index


def dedupe_phrase_rows(rows: list[dict], limit: int) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        phrase = compact(row.get("kalip") or "")
        key = normalize_key(phrase)
        if not phrase or key in seen:
            continue
        seen.add(key)
        result.append(row)
        if len(result) >= limit:
            break
    return result


def maybe_add_example(record: dict, phrase_row: dict, max_added_examples: int) -> int:
    de = compact(phrase_row.get("ornek_almanca") or "")
    tr = compact(phrase_row.get("ornek_turkce") or "")
    if not de:
        return 0

    examples = list(record.get("ornekler") or [])
    existing = {
        normalize(compact(item.get("almanca") or ""))
        for item in examples
        if isinstance(item, dict) and compact(item.get("almanca") or "")
    }
    if normalize(de) in existing:
        return 0

    added_so_far = sum(
        1
        for item in examples
        if isinstance(item, dict) and compact(item.get("kaynak") or "").startswith("verb-pattern")
    )
    if added_so_far >= max_added_examples:
        return 0

    payload = {"almanca": de, "turkce": tr, "kaynak": compact(phrase_row.get("kaynak") or "verb-pattern")}
    examples.append(payload)
    record["ornekler"] = examples

    if not compact(record.get("ornek_almanca") or ""):
        record["ornek_almanca"] = de
        if tr:
            record["ornek_turkce"] = tr
    elif not compact(record.get("ornek_turkce") or "") and tr:
        record["ornek_turkce"] = tr
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-patterns-per-verb", type=int, default=8)
    parser.add_argument("--max-extra-examples", type=int, default=3)
    args = parser.parse_args()

    dict_path = args.dict_path
    output_path = args.output_path or dict_path
    data = json.loads(dict_path.read_text(encoding="utf-8"))

    phrase_index = build_phrase_index(data)
    manual_records = load_manual_phrase_records()
    wikdict_index = load_wikdict_index()
    translation_index = build_translation_index(data, manual_records, wikdict_index)
    curated_map = {}

    counters = Counter()
    sample: list[dict] = []

    for record in data:
        if compact(record.get("tur") or "") != VERB_POS:
            continue

        lemma = compact(record.get("almanca") or "")
        if not lemma:
            continue

        forms = collect_known_forms(record)
        phrase_rows: list[dict] = []

        for phrase_record in phrase_index.values():
            phrase = compact(phrase_record.get("almanca") or "")
            if phrase_contains_verb(phrase, forms):
                phrase_rows.append(
                    {
                        "kalip": phrase,
                        "turkce": compact(phrase_record.get("turkce") or translation_index.get(normalize_key(phrase), "")),
                        "aciklama_turkce": compact(phrase_record.get("aciklama_turkce") or ""),
                        "ornek_almanca": compact(phrase_record.get("ornek_almanca") or ""),
                        "ornek_turkce": compact(phrase_record.get("ornek_turkce") or ""),
                        "kaynak": compact(phrase_record.get("kaynak") or "phrase-entry"),
                    }
                )

        for example in collect_entry_examples(record):
            sentence = compact(example.get("almanca") or "")
            if not sentence:
                continue
            for phrase, _pos, source_kind in extract_candidates(sentence, curated_map) + mine_bulk_candidates(sentence):
                if not phrase_contains_verb(phrase, forms):
                    continue
                phrase_rows.append(
                    {
                        "kalip": compact(phrase),
                        "turkce": compact(translation_index.get(normalize_key(phrase), "")),
                        "aciklama_turkce": "",
                        "ornek_almanca": sentence,
                        "ornek_turkce": compact(example.get("turkce") or ""),
                        "kaynak": f"verb-pattern:{source_kind}",
                    }
                )

        phrase_rows.sort(
            key=lambda item: (
                1 if compact(item.get("turkce") or "") else 0,
                1 if compact(item.get("ornek_turkce") or "") else 0,
                len(compact(item.get("kalip") or "")),
            ),
            reverse=True,
        )
        merged_rows = dedupe_phrase_rows(phrase_rows, args.max_patterns_per_verb)
        if not merged_rows:
            continue

        previous = {normalize_key(str(item.get("kalip") or "")) for item in (record.get("fiil_kaliplari") or []) if isinstance(item, dict)}
        if merged_rows:
            record["fiil_kaliplari"] = merged_rows
            counters["verbs_with_patterns"] += 1
            counters["patterns_attached"] += len(merged_rows)
            if len(previous) != len({normalize_key(row["kalip"]) for row in merged_rows}):
                counters["pattern_sets_changed"] += 1

        related = list(record.get("ilgili_kayitlar") or [])
        related_seen = {normalize(item) for item in related}
        for row in merged_rows[: args.max_patterns_per_verb]:
            phrase = compact(row.get("kalip") or "")
            if phrase and normalize(phrase) not in related_seen:
                related.append(phrase)
                related_seen.add(normalize(phrase))
                counters["related_links_added"] += 1
        if related:
            record["ilgili_kayitlar"] = related

        added_examples = 0
        for row in merged_rows:
            added_examples += maybe_add_example(record, row, args.max_extra_examples)
        counters["examples_added"] += added_examples

        if len(sample) < 20:
            sample.append(
                {
                    "verb": lemma,
                    "patterns": [item["kalip"] for item in merged_rows[:4]],
                }
            )

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "dict_path": str(dict_path),
        "output_path": str(output_path),
        "counters": dict(counters),
        "sample": sample,
    }
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
