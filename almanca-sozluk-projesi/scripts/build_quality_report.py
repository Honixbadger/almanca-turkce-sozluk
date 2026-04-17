#!/usr/bin/env python3
"""Build a compact quality report for the current dictionary state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "dictionary_quality_report.json"


def compact(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def iter_examples(record: dict) -> list[tuple[str, str]]:
    examples: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in record.get("ornekler") or []:
        if not isinstance(item, dict):
            continue
        de = compact(item.get("almanca") or "")
        tr = compact(item.get("turkce") or "")
        if not de:
            continue
        key = (de, tr)
        if key not in seen:
            seen.add(key)
            examples.append(key)
    top_de = compact(record.get("ornek_almanca") or "")
    top_tr = compact(record.get("ornek_turkce") or "")
    if top_de:
        key = (top_de, top_tr)
        if key not in seen:
            examples.append(key)
    return examples


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    data = json.loads(args.dict_path.read_text(encoding="utf-8"))

    total_records = len(data)
    with_senses = 0
    multi_sense = 0
    with_baglamlar = 0
    grouped_images = 0
    verbs_total = 0
    verbs_missing_partizip2 = 0
    verbs_missing_prateritum = 0
    verbs_missing_perfekt = 0
    verbs_missing_cekimler = 0
    verbs_with_patterns = 0
    total_examples = 0
    translated_examples = 0
    records_missing_example_tr = 0

    for record in data:
        senses = record.get("anlamlar") or []
        if isinstance(senses, list) and senses:
            with_senses += 1
            if len(senses) > 1:
                multi_sense += 1

        baglamlar = record.get("baglamlar") or []
        if isinstance(baglamlar, list) and baglamlar:
            with_baglamlar += 1

        if compact(record.get("gorsel_grubu") or ""):
            grouped_images += 1

        if compact(record.get("tur") or "") == "fiil":
            verbs_total += 1
            if not compact(record.get("partizip2") or ""):
                verbs_missing_partizip2 += 1
            if not compact(record.get("prateritum") or ""):
                verbs_missing_prateritum += 1
            if not compact(record.get("perfekt_yardimci") or ""):
                verbs_missing_perfekt += 1
            if not isinstance(record.get("cekimler"), dict) or not record.get("cekimler"):
                verbs_missing_cekimler += 1
            if isinstance(record.get("fiil_kaliplari"), list) and record.get("fiil_kaliplari"):
                verbs_with_patterns += 1

        examples = iter_examples(record)
        total_examples += len(examples)
        translated = sum(1 for _de, tr in examples if compact(tr))
        translated_examples += translated
        if any(_de and not compact(tr) for _de, tr in examples):
            records_missing_example_tr += 1

    payload = {
        "total_records": total_records,
        "with_senses": with_senses,
        "multi_sense_records": multi_sense,
        "with_baglamlar": with_baglamlar,
        "grouped_images": grouped_images,
        "examples": {
            "total": total_examples,
            "translated": translated_examples,
            "missing": max(0, total_examples - translated_examples),
            "records_missing_translation": records_missing_example_tr,
        },
        "verbs": {
            "total": verbs_total,
            "missing_partizip2": verbs_missing_partizip2,
            "missing_prateritum": verbs_missing_prateritum,
            "missing_perfekt_yardimci": verbs_missing_perfekt,
            "missing_cekimler": verbs_missing_cekimler,
            "with_patterns": verbs_with_patterns,
        },
    }
    args.output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
