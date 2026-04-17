#!/usr/bin/env python3
"""Conservatively improve structured definition quality from local fields only."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output" / "dictionary_definition_stage.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "definition_enrichment_report.json"


def compact_space(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def normalized_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = compact_space(value)
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def split_meanings(text: str) -> list[str]:
    return normalized_list(str(text or "").replace("|", ";").split(";"))


def is_safe_explanation_text(text: str) -> bool:
    value = compact_space(text)
    if not value:
        return False
    if "->" in value:
        return False
    if len(value) < 8:
        return False
    return True


def build_examples(record: dict) -> list[dict]:
    examples: list[dict] = []
    for item in record.get("ornekler") or []:
        if isinstance(item, dict) and compact_space(item.get("almanca") or ""):
            payload = {
                "almanca": compact_space(item.get("almanca") or ""),
                "turkce": compact_space(item.get("turkce") or ""),
                "kaynak": compact_space(item.get("kaynak") or ""),
                "not": compact_space(item.get("not") or ""),
            }
            examples.append(payload)
    top_de = compact_space(record.get("ornek_almanca") or "")
    top_tr = compact_space(record.get("ornek_turkce") or "")
    if top_de:
        key = top_de.casefold()
        if not any(compact_space(item.get("almanca") or "").casefold() == key for item in examples):
            examples.insert(0, {"almanca": top_de, "turkce": top_tr, "kaynak": "top-level"})
    return examples


def normalize_senses(record: dict) -> list[dict]:
    senses = record.get("anlamlar")
    if not isinstance(senses, list):
        return []
    result: list[dict] = []
    for index, sense in enumerate(senses, start=1):
        if not isinstance(sense, dict):
            continue
        normalized = deepcopy(sense)
        normalized["sira"] = normalized.get("sira") or index
        normalized["tanim_almanca"] = compact_space(normalized.get("tanim_almanca") or "")
        normalized["turkce"] = compact_space(normalized.get("turkce") or "")
        normalized["aciklama_turkce"] = compact_space(normalized.get("aciklama_turkce") or "")
        normalized["kaynak"] = compact_space(normalized.get("kaynak") or "")
        normalized["etiketler"] = normalized_list(normalized.get("etiketler"))
        normalized_examples = []
        for example in normalized.get("ornekler") or []:
            if not isinstance(example, dict):
                continue
            de_text = compact_space(example.get("almanca") or "")
            if not de_text:
                continue
            normalized_examples.append(
                {
                    "almanca": de_text,
                    "turkce": compact_space(example.get("turkce") or ""),
                    "kaynak": compact_space(example.get("kaynak") or ""),
                    "not": compact_space(example.get("not") or ""),
                }
            )
        normalized["ornekler"] = normalized_examples
        if any(
            (
                normalized["tanim_almanca"],
                normalized["turkce"],
                normalized["aciklama_turkce"],
                normalized["etiketler"],
                normalized["ornekler"],
            )
        ):
            result.append(normalized)
    return result


def build_fallback_sense(record: dict) -> dict | None:
    sense = {
        "sira": 1,
        "tanim_almanca": compact_space(record.get("tanim_almanca") or ""),
        "turkce": split_meanings(record.get("turkce") or "")[:1],
        "aciklama_turkce": (
            compact_space(record.get("aciklama_turkce") or "")
            if is_safe_explanation_text(record.get("aciklama_turkce") or "")
            else ""
        ),
        "etiketler": [
            item for item in normalized_list(record.get("kategoriler"))
            if item.casefold() not in {"genel", "general"}
        ],
        "ornekler": build_examples(record)[:1],
        "kaynak": compact_space(record.get("kaynak") or "") or "local-definition-quality",
        "guven": 0.72,
    }
    if isinstance(sense["turkce"], list):
        sense["turkce"] = sense["turkce"][0] if sense["turkce"] else ""
    if not any((sense["tanim_almanca"], sense["turkce"], sense["aciklama_turkce"], sense["ornekler"])):
        return None
    return sense


def promote_sense_fields(record: dict, counters: Counter) -> int:
    changes = 0
    senses = normalize_senses(record)
    top_tr_values = split_meanings(record.get("turkce") or "")
    top_desc = compact_space(record.get("aciklama_turkce") or "")
    top_labels = [
        item for item in normalized_list(record.get("kategoriler"))
        if item.casefold() not in {"genel", "general"}
    ]
    examples = build_examples(record)

    if not senses:
        fallback = build_fallback_sense(record)
        if fallback:
            record["anlamlar"] = [fallback]
            counters["created_fallback_senses"] += 1
            senses = normalize_senses(record)
            changes += 1
        else:
            return changes

    if len(senses) == 1:
        sense = senses[0]
        if not sense.get("turkce") and top_tr_values:
            sense["turkce"] = top_tr_values[0]
            counters["promoted_single_translation"] += 1
            changes += 1
        if not sense.get("aciklama_turkce") and is_safe_explanation_text(top_desc):
            sense["aciklama_turkce"] = top_desc
            counters["promoted_single_explanation"] += 1
            changes += 1
    else:
        sense_tr_values = [compact_space(item.get("turkce") or "") for item in senses]
        missing_tr_count = sum(1 for item in sense_tr_values if not item)
        if top_tr_values and len(top_tr_values) == len(senses) and missing_tr_count:
            for sense, value in zip(senses, top_tr_values):
                if value and not sense.get("turkce"):
                    sense["turkce"] = value
                    counters["promoted_multi_translation"] += 1
                    changes += 1
        explanation_parts = [item for item in split_meanings(top_desc) if is_safe_explanation_text(item)]
        if explanation_parts and len(explanation_parts) == len(senses):
            for sense, value in zip(senses, explanation_parts):
                if value and not sense.get("aciklama_turkce"):
                    sense["aciklama_turkce"] = value
                    counters["promoted_multi_explanation"] += 1
                    changes += 1

    if top_labels:
        for sense in senses:
            if not normalized_list(sense.get("etiketler")):
                sense["etiketler"] = list(top_labels)
                counters["promoted_labels"] += 1
                changes += 1

    unused_examples = list(examples)
    for sense in senses:
        sense_examples = sense.get("ornekler") or []
        if sense_examples:
            for used in sense_examples:
                used_key = compact_space(used.get("almanca") or "").casefold()
                unused_examples = [
                    item for item in unused_examples
                    if compact_space(item.get("almanca") or "").casefold() != used_key
                ]
        if not sense_examples and unused_examples:
            candidate = unused_examples.pop(0)
            sense["ornekler"] = [candidate]
            counters["promoted_examples"] += 1
            changes += 1

    if senses:
        if not compact_space(record.get("aciklama_turkce") or ""):
            first_desc = compact_space(senses[0].get("aciklama_turkce") or "")
            if first_desc:
                record["aciklama_turkce"] = first_desc
                counters["backfilled_top_explanation"] += 1
                changes += 1
        record["anlamlar"] = senses

    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Improve definition quality conservatively.")
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    records = json.loads(args.dictionary.read_text(encoding="utf-8"))
    counters = Counter()
    touched_records: list[dict] = []

    for index, record in enumerate(records):
        if args.limit and index >= args.limit:
            break
        before = json.dumps(record.get("anlamlar") or [], ensure_ascii=False, sort_keys=True)
        before_desc = compact_space(record.get("aciklama_turkce") or "")
        changes = promote_sense_fields(record, counters)
        after = json.dumps(record.get("anlamlar") or [], ensure_ascii=False, sort_keys=True)
        after_desc = compact_space(record.get("aciklama_turkce") or "")
        if changes or before != after or before_desc != after_desc:
            counters["records_updated"] += 1
            touched_records.append(
                {
                    "almanca": compact_space(record.get("almanca") or ""),
                    "turkce": compact_space(record.get("turkce") or ""),
                    "tur": compact_space(record.get("tur") or ""),
                    "change_count": changes,
                }
            )

    report = {
        "dictionary_path": str(args.dictionary),
        "dry_run": bool(args.dry_run),
        "records_updated": counters.get("records_updated", 0),
        "change_counts": dict(sorted(counters.items())),
        "sample_records": touched_records[:300],
    }
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.dry_run:
        args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Tanım kalite stage çıktısı yazıldı: {args.output}")
    print(f"Tanım kalite raporu yazıldı: {args.report_path}")
    print(f"Güncellenen kayıt: {counters.get('records_updated', 0)}")
    for key, value in sorted(counters.items()):
        print(f"  - {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
