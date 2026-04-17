#!/usr/bin/env python3
"""Find and optionally strip stray English residues from Turkish text fields."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from quality_common import (
    DEFAULT_DICT_PATH,
    DEFAULT_REPORT_DIR,
    cjk_present,
    compact,
    configure_stdio,
    get_text_field_paths,
    iter_example_slots,
    normalize_key,
    read_records,
    record_label,
    write_json,
    write_records,
)


ENGLISH_RESIDUE_WORDS = {
    "already",
    "actually",
    "basically",
    "literally",
    "maybe",
    "the",
    "and",
    "with",
    "from",
    "into",
    "without",
    "then",
    "still",
}


def find_english_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z]+", text)
    hits: list[str] = []
    for token in tokens:
        lowered = normalize_key(token)
        if lowered in ENGLISH_RESIDUE_WORDS:
            hits.append(token)
    return hits


def strip_known_residue(text: str) -> str:
    cleaned = text
    cleaned = re.sub(
        r"^(already|actually|basically|literally|then|still)\b[\s,;:-]*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"[\s,;:-]*\b(already|actually|basically|literally|then|still)$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return compact(cleaned)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_DIR / "turkish_foreign_residue.json",
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--apply-fixes", action="store_true")
    parser.add_argument("--strip-known-fragments", action="store_true")
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
            hits = find_english_tokens(value)
            if not hits and not cjk_present(value):
                continue
            counters["flagged_fields"] += 1
            if cjk_present(value):
                counters["cjk_fields"] += 1
            if hits:
                counters["english_residue_fields"] += 1
            after = strip_known_residue(value) if args.strip_known_fragments else value
            samples.append(
                {
                    "record_index": rec_idx,
                    "record": record_label(record, rec_idx),
                    "field": field,
                    "before": value,
                    "after": after,
                    "english_hits": hits,
                    "contains_cjk": cjk_present(value),
                }
            )
            if args.apply_fixes and args.strip_known_fragments and after != value:
                record[field] = after
                counters["updated_fields"] += 1

        for slot in iter_example_slots(record):
            tr = compact(slot["turkce"])
            if not tr:
                continue
            hits = find_english_tokens(tr)
            has_cjk = cjk_present(tr)
            if not hits and not has_cjk:
                continue
            counters["flagged_example_translations"] += 1
            after = strip_known_residue(tr) if args.strip_known_fragments else tr
            samples.append(
                {
                    "record_index": rec_idx,
                    "record": record_label(record, rec_idx),
                    "field": "ornek_turkce" if slot["kind"] == "top" else f"ornekler[{slot['index']}].turkce",
                    "before": tr,
                    "after": after,
                    "english_hits": hits,
                    "contains_cjk": has_cjk,
                }
            )
            if args.apply_fixes and args.strip_known_fragments and after != tr:
                if slot["kind"] == "top":
                    record["ornek_turkce"] = after
                else:
                    record["ornekler"][slot["index"]]["turkce"] = after
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
