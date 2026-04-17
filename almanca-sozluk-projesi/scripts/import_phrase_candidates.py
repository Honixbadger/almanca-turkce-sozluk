#!/usr/bin/env python3
"""Import reviewed German phrase candidates into the dictionary."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from enrich_phrase_patterns import (
    DICT_PATH,
    build_entry,
    build_translation_index,
    load_manual_phrase_records,
    load_wikdict_index,
    normalize_key,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "manual" / "phrase_candidates_review.json"
REPORT_PATH = PROJECT_ROOT / "data" / "manual" / "phrase_candidates_import_report.json"
SOURCE_TAG = "phrase-candidates-review"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DICT_PATH)
    parser.add_argument("--input-path", type=Path, default=INPUT_PATH)
    parser.add_argument("--report-path", type=Path, default=REPORT_PATH)
    return parser.parse_args()


def load_candidates(input_path: Path) -> list[dict]:
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    return [row for row in payload.get("candidates") or [] if isinstance(row, dict)]


def main() -> None:
    args = parse_args()
    data = json.loads(args.dict_path.read_text(encoding="utf-8"))
    existing_keys = {normalize_key(str(row.get("almanca") or "")) for row in data if row.get("almanca")}

    manual_records = load_manual_phrase_records()
    wikdict_index = load_wikdict_index()
    translation_index = build_translation_index(data, manual_records, wikdict_index)

    imported: list[dict] = []
    skipped_existing = 0
    skipped_invalid = 0
    skipped_not_ready = 0

    candidates = load_candidates(args.input_path)

    for candidate in candidates:
        if candidate.get("import_ready") is False:
            skipped_not_ready += 1
            continue
        phrase = str(candidate.get("almanca") or "").strip()
        key = normalize_key(phrase)
        if not key:
            skipped_invalid += 1
            continue
        if key in existing_keys:
            skipped_existing += 1
            continue

        sources = [str(src).strip() for src in candidate.get("kaynaklar") or [] if str(src).strip()]
        example = str(candidate.get("ornek") or "").strip()
        meta = {
            "almanca": phrase,
            "tur": str(candidate.get("tur") or "kalıp").strip() or "kalıp",
            "translation": "",
            "freq": int(candidate.get("frekans") or 0),
            "seeded": False,
            "generic_hits": 0,
            "mined_hits": int(candidate.get("frekans") or 0),
            "categories": Counter(),
            "sources": set([SOURCE_TAG, *sources]),
            "source_urls": set(),
            "examples": [{"almanca": example, "turkce": ""}] if example else [],
            "source_kinds": set(sources),
        }
        entry = build_entry(meta, translation_index)
        imported.append(entry)
        existing_keys.add(key)

    if imported:
        data.extend(sorted(imported, key=lambda row: normalize_key(str(row.get("almanca") or ""))))
        args.dict_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    report = {
        "input_candidates": len(candidates),
        "imported_count": len(imported),
        "skipped_existing": skipped_existing,
        "skipped_invalid": skipped_invalid,
        "skipped_not_ready": skipped_not_ready,
        "sample": [
            {
                "almanca": row["almanca"],
                "turkce": row["turkce"],
                "kaynak": row["kaynak"],
            }
            for row in imported[:20]
        ],
    }
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
