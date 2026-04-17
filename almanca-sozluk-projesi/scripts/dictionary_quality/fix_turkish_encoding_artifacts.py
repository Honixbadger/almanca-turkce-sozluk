#!/usr/bin/env python3
"""Repair obvious mojibake and placeholder artifacts in Turkish text fields."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from quality_common import (
    DEFAULT_DICT_PATH,
    DEFAULT_REPORT_DIR,
    compact,
    configure_stdio,
    contains_mojibake,
    get_text_field_paths,
    iter_example_slots,
    read_records,
    record_label,
    write_json,
    write_records,
)


MOJIBAKE_MAP = {
    "Ã§": "ç",
    "Ã‡": "Ç",
    "Ã¶": "ö",
    "Ã–": "Ö",
    "Ã¼": "ü",
    "Ãœ": "Ü",
    "Ä±": "ı",
    "Ä°": "İ",
    "ÄŸ": "ğ",
    "Äž": "Ğ",
    "ÅŸ": "ş",
    "Åž": "Ş",
    "â€™": "'",
    "â€˜": "'",
    "â€œ": '"',
    "â€": '"',
    "â€“": "-",
    "â€”": "-",
    "â€¦": "...",
}


def repair_text(text: str) -> tuple[str, list[str]]:
    repaired = text
    reasons: list[str] = []
    for bad, good in MOJIBAKE_MAP.items():
        if bad in repaired:
            repaired = repaired.replace(bad, good)
            reasons.append(f"replace:{bad}")

    if "�" in repaired:
        repaired = repaired.replace("�", "")
        reasons.append("remove_replacement_character")

    if "??" in repaired:
        repaired = repaired.replace("??", "?")
        reasons.append("collapse_double_question")

    repaired = compact(repaired)
    return repaired, reasons


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_DIR / "turkish_encoding_artifacts.json",
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--apply-fixes", action="store_true")
    parser.add_argument("--clear-unresolved", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    records = read_records(args.dict_path)
    counters = Counter()
    samples: list[dict] = []

    field_names = [field for field, _path in get_text_field_paths()]

    for rec_idx, record in enumerate(records):
        for field in field_names:
            value = compact(record.get(field) or "")
            if not value:
                continue
            if "??" not in value and not contains_mojibake(value):
                continue
            repaired, reasons = repair_text(value)
            unresolved = "?" in repaired and "??" not in value and repaired.count("?") >= value.count("?")
            counters["flagged_fields"] += 1
            samples.append(
                {
                    "record_index": rec_idx,
                    "record": record_label(record, rec_idx),
                    "field": field,
                    "before": value,
                    "after": repaired,
                    "reasons": reasons,
                    "unresolved": unresolved,
                }
            )
            if args.apply_fixes:
                if unresolved and args.clear_unresolved:
                    record[field] = ""
                    counters["cleared_unresolved_fields"] += 1
                else:
                    record[field] = repaired
                    counters["updated_fields"] += 1

        for slot in iter_example_slots(record):
            tr = compact(slot["turkce"])
            if not tr or ("??" not in tr and not contains_mojibake(tr)):
                continue
            repaired, reasons = repair_text(tr)
            unresolved = "?" in repaired and "??" not in tr and repaired.count("?") >= tr.count("?")
            counters["flagged_example_translations"] += 1
            samples.append(
                {
                    "record_index": rec_idx,
                    "record": record_label(record, rec_idx),
                    "field": "ornek_turkce" if slot["kind"] == "top" else f"ornekler[{slot['index']}].turkce",
                    "before": tr,
                    "after": repaired,
                    "reasons": reasons,
                    "unresolved": unresolved,
                }
            )
            if not args.apply_fixes:
                continue
            if slot["kind"] == "top":
                record["ornek_turkce"] = "" if unresolved and args.clear_unresolved else repaired
            else:
                record["ornekler"][slot["index"]]["turkce"] = "" if unresolved and args.clear_unresolved else repaired
            counters["updated_example_translations"] += 1

    payload = {
        "dict_path": str(args.dict_path),
        "apply_fixes": args.apply_fixes,
        "counters": dict(counters),
        "samples": samples[: args.sample_limit],
    }
    write_json(args.report_path, payload)

    if args.apply_fixes:
        target = write_records(
            records=records,
            dict_path=args.dict_path,
            output_path=args.output_path,
            in_place=args.in_place,
        )
        payload["output_path"] = str(target)
        write_json(args.report_path, payload)

    print(payload["counters"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
