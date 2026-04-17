#!/usr/bin/env python3
"""Build a quality report for structured definitions (anlamlar)."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "definition_quality_report.json"


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


def iter_examples(record: dict) -> list[dict]:
    examples: list[dict] = []
    for item in record.get("ornekler") or []:
        if isinstance(item, dict) and compact_space(item.get("almanca") or ""):
            examples.append(item)
    top_de = compact_space(record.get("ornek_almanca") or "")
    top_tr = compact_space(record.get("ornek_turkce") or "")
    if top_de:
        key = top_de.casefold()
        if not any(compact_space(item.get("almanca") or "").casefold() == key for item in examples):
            examples.insert(0, {"almanca": top_de, "turkce": top_tr, "kaynak": "top-level"})
    return examples


def normalized_senses(record: dict) -> list[dict]:
    senses = record.get("anlamlar")
    if not isinstance(senses, list):
        return []
    result: list[dict] = []
    for index, sense in enumerate(senses, start=1):
        if not isinstance(sense, dict):
            continue
        item = {
            "sira": sense.get("sira") or index,
            "tanim_almanca": compact_space(sense.get("tanim_almanca") or ""),
            "turkce": compact_space(sense.get("turkce") or ""),
            "aciklama_turkce": compact_space(sense.get("aciklama_turkce") or ""),
            "etiketler": normalized_list(sense.get("etiketler")),
            "ornekler": [
                example for example in (sense.get("ornekler") or [])
                if isinstance(example, dict) and compact_space(example.get("almanca") or "")
            ],
        }
        if any(
            (
                item["tanim_almanca"],
                item["turkce"],
                item["aciklama_turkce"],
                item["etiketler"],
                item["ornekler"],
            )
        ):
            result.append(item)
    return result


def build_record_issues(record: dict) -> list[str]:
    issues: list[str] = []
    senses = normalized_senses(record)
    top_tr = compact_space(record.get("turkce") or "")
    top_desc = compact_space(record.get("aciklama_turkce") or "")
    top_de_def = compact_space(record.get("tanim_almanca") or "")
    examples = iter_examples(record)

    if not senses:
        if top_tr or top_desc or top_de_def:
            issues.append("structured-sense-missing")
        return issues

    if all(not sense["turkce"] for sense in senses):
        issues.append("sense-translation-missing")
    if all(not sense["aciklama_turkce"] for sense in senses):
        issues.append("sense-explanation-missing")
    if len(senses) > 1 and sum(1 for sense in senses if sense["turkce"] or sense["aciklama_turkce"]) < len(senses):
        issues.append("multi-sense-tr-coverage-low")
    if any(not sense["etiketler"] for sense in senses) and normalized_list(record.get("kategoriler")):
        issues.append("sense-label-missing")
    if examples and all(not sense["ornekler"] for sense in senses):
        issues.append("sense-example-missing")
    if top_desc and all(not sense["aciklama_turkce"] for sense in senses):
        issues.append("top-level-explanation-not-promoted")
    if top_tr and len(senses) == 1 and not senses[0]["turkce"]:
        issues.append("single-sense-translation-not-promoted")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Build definition quality report.")
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()

    records = json.loads(args.dictionary.read_text(encoding="utf-8"))

    counts = Counter()
    sample_records: list[dict] = []
    flagged = 0

    for record in records:
        issues = build_record_issues(record)
        if not issues:
            continue
        flagged += 1
        for issue in issues:
            counts[issue] += 1
        if len(sample_records) < max(0, args.limit):
            sample_records.append(
                {
                    "almanca": compact_space(record.get("almanca") or ""),
                    "turkce": compact_space(record.get("turkce") or ""),
                    "tur": compact_space(record.get("tur") or ""),
                    "issues": issues,
                    "sense_count": len(normalized_senses(record)),
                    "has_examples": bool(iter_examples(record)),
                    "storage_source": compact_space(record.get("_storage_source") or "base"),
                }
            )

    payload = {
        "dictionary_path": str(args.dictionary),
        "total_records": len(records),
        "flagged_records": flagged,
        "issue_counts": dict(sorted(counts.items())),
        "sample_records": sample_records,
    }
    args.report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Tanım kalite raporu yazıldı: {args.report_path}")
    print(f"İşaretlenen kayıt: {flagged}")
    for key, value in sorted(counts.items()):
        print(f"  - {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
