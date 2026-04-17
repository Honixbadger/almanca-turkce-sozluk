#!/usr/bin/env python3
"""Detect and optionally remove example sentences that are probably not German."""

from __future__ import annotations

import argparse
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
    normalize_key,
    record_label,
    stem_tokens,
    write_json,
    write_records,
    read_records,
)


ENGLISH_MARKERS = {
    "the",
    "and",
    "with",
    "for",
    "from",
    "into",
    "already",
    "because",
    "without",
    "there",
    "these",
    "those",
    "would",
    "could",
    "should",
    "very",
}
FRENCH_MARKERS = {
    "avec",
    "pour",
    "dans",
    "mais",
    "sans",
    "elle",
    "nous",
    "vous",
    "plus",
    "tout",
    "cette",
    "comme",
}
DUTCH_MARKERS = {
    "een",
    "het",
    "van",
    "niet",
    "voor",
    "zijn",
    "wordt",
    "meer",
    "deze",
    "over",
}
GERMAN_MARKERS = {
    "der",
    "die",
    "das",
    "und",
    "mit",
    "für",
    "ist",
    "sind",
    "wird",
    "werden",
    "nicht",
    "ein",
    "eine",
    "einer",
    "im",
    "am",
    "auf",
    "zu",
    "von",
    "den",
    "dem",
    "des",
}


def score_language(text: str) -> tuple[str | None, dict[str, int]]:
    lowered = normalize_key(text)
    tokens = stem_tokens(lowered, min_len=2)
    english = sum(1 for token in tokens if token in ENGLISH_MARKERS)
    french = sum(1 for token in tokens if token in FRENCH_MARKERS)
    dutch = sum(1 for token in tokens if token in DUTCH_MARKERS)
    german = sum(1 for token in tokens if token in GERMAN_MARKERS)
    if any(ch in text for ch in "äöüßÄÖÜ"):
        german += 1
    counts = {"english": english, "french": french, "dutch": dutch, "german": german}
    dominant = None
    if english >= 2 and english > german:
        dominant = "english"
    elif french >= 2 and french > german:
        dominant = "french"
    elif dutch >= 2 and dutch > german:
        dominant = "dutch"
    elif english >= 1 and german == 0 and " the " in f" {lowered} ":
        dominant = "english"
    return dominant, counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_DIR / "non_german_examples.json",
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--apply-fixes", action="store_true")
    parser.add_argument("--drop-nested", action="store_true")
    parser.add_argument("--clear-top", action="store_true")
    parser.add_argument("--min-words", type=int, default=4)
    parser.add_argument("--sample-limit", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    records = read_records(args.dict_path)

    counters = Counter()
    report_examples: list[dict] = []

    for rec_idx, record in enumerate(records):
        nested_to_drop: set[int] = set()
        top_bad = False
        for slot in iter_example_slots(record):
            text = compact(slot["almanca"])
            if not text:
                continue
            if len(text.split()) < args.min_words:
                continue
            language, counts = score_language(text)
            if not language:
                continue
            counters["flagged_examples"] += 1
            counters[f"{language}_examples"] += 1
            report_examples.append(
                {
                    "record_index": rec_idx,
                    "record": record_label(record, rec_idx),
                    "slot": slot["kind"],
                    "nested_index": slot["index"],
                    "language": language,
                    "counts": counts,
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
        "samples": report_examples[: args.sample_limit],
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
