#!/usr/bin/env python3
"""Detect and optionally remove fragmented or truncated example sentences."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from quality_common import (
    DEFAULT_DICT_PATH,
    DEFAULT_REPORT_DIR,
    clear_top_example,
    compact,
    configure_stdio,
    drop_nested_examples,
    iter_example_slots,
    record_label,
    write_json,
    write_records,
    read_records,
)


BAD_ENDINGS = {
    "der",
    "die",
    "das",
    "den",
    "dem",
    "des",
    "ein",
    "eine",
    "einen",
    "einem",
    "einer",
    "und",
    "oder",
    "aber",
    "weil",
    "dass",
    "wenn",
    "mit",
    "für",
    "ohne",
    "gegen",
    "an",
    "auf",
    "im",
    "am",
    "von",
    "zu",
    "zum",
    "zur",
}


def detect_fragment(text: str, min_words: int) -> list[str]:
    reasons: list[str] = []
    if not text:
        return reasons

    words = text.split()
    if re.search(r"[,;:\-–—]$", text):
        reasons.append("trailing_punctuation")

    last_token = re.sub(r"[^\wäöüÄÖÜß-]", "", words[-1]).casefold() if words else ""
    if len(words) >= min_words and last_token in BAD_ENDINGS:
        reasons.append("ends_with_function_word")

    if text.count("(") != text.count(")"):
        reasons.append("unbalanced_parentheses")

    if "..." in text or "…" in text:
        reasons.append("ellipsis_like_truncation")

    return reasons


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_DIR / "fragment_examples.json",
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--apply-fixes", action="store_true")
    parser.add_argument("--drop-nested", action="store_true")
    parser.add_argument("--clear-top", action="store_true")
    parser.add_argument("--min-words", type=int, default=4)
    parser.add_argument("--sample-limit", type=int, default=250)
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    records = read_records(args.dict_path)

    counters = Counter()
    samples: list[dict] = []

    for rec_idx, record in enumerate(records):
        nested_to_drop: set[int] = set()
        top_bad = False
        for slot in iter_example_slots(record):
            text = compact(slot["almanca"])
            if not text:
                continue
            reasons = detect_fragment(text, args.min_words)
            if not reasons:
                continue
            counters["flagged_examples"] += 1
            for reason in reasons:
                counters[f"reason:{reason}"] += 1
            samples.append(
                {
                    "record_index": rec_idx,
                    "record": record_label(record, rec_idx),
                    "slot": slot["kind"],
                    "nested_index": slot["index"],
                    "reasons": reasons,
                    "almanca": text,
                    "turkce": compact(slot["turkce"]),
                }
            )
            if slot["kind"] == "top":
                top_bad = True
            elif slot["index"] is not None:
                nested_to_drop.add(slot["index"])

        if args.apply_fixes:
            if args.clear_top and top_bad and clear_top_example(record):
                counters["top_examples_cleared"] += 1
            if args.drop_nested:
                removed = drop_nested_examples(record, nested_to_drop)
                counters["nested_examples_removed"] += removed

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
