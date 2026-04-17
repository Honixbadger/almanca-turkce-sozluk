#!/usr/bin/env python3
"""Flag example translations that drift too far away from the entry's main translation."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from quality_common import (
    DEFAULT_DICT_PATH,
    DEFAULT_REPORT_DIR,
    compact,
    configure_stdio,
    iter_example_slots,
    read_records,
    record_label,
    stem_tokens,
    write_json,
    write_records,
)
from fix_top_example_lemma_mismatch import example_matches_lemma


def head_translation_stems(record: dict) -> set[str]:
    stems = stem_tokens(record.get("turkce") or "", min_len=4)
    if stems:
        return stems
    return stem_tokens(record.get("aciklama_turkce") or "", min_len=4)


def overlapping_stems(left: set[str], right: set[str]) -> set[str]:
    overlaps: set[str] = set()
    for a in left:
        for b in right:
            shared = min(len(a), len(b))
            if shared >= 5 and (a.startswith(b[:5]) or b.startswith(a[:5])):
                overlaps.add(a if len(a) <= len(b) else b)
    return overlaps


def suspicious_translation(record: dict, de_text: str, tr_text: str) -> tuple[bool, dict]:
    head_stems = head_translation_stems(record)
    tr_stems = stem_tokens(tr_text, min_len=4)
    lemma = compact(record.get("almanca") or "")
    word_type = compact(record.get("tur") or "")
    if not head_stems or len(tr_stems) < 3 or len(head_stems) > 4:
        return False, {}
    if not any(len(stem) >= 6 for stem in head_stems):
        return False, {}
    if lemma:
        matches_lemma, _reason = example_matches_lemma(lemma, de_text, word_type)
        if not matches_lemma:
            return False, {}
    overlap = sorted(overlapping_stems(head_stems, tr_stems))
    if overlap:
        return False, {"overlap": overlap}
    return True, {
        "head_stems": sorted(head_stems),
        "translation_stems": sorted(tr_stems),
        "overlap": overlap,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_DIR / "example_translation_drift.json",
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--apply-fixes", action="store_true")
    parser.add_argument("--clear-top-tr", action="store_true")
    parser.add_argument("--clear-nested-tr", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=250)
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    records = read_records(args.dict_path)
    counters = Counter()
    samples: list[dict] = []

    for rec_idx, record in enumerate(records):
        for slot in iter_example_slots(record):
            tr_text = compact(slot["turkce"])
            de_text = compact(slot["almanca"])
            if not de_text or not tr_text:
                continue
            bad, info = suspicious_translation(record, de_text, tr_text)
            if not bad:
                continue
            counters["flagged_examples"] += 1
            sample = {
                "record_index": rec_idx,
                "record": record_label(record, rec_idx),
                "slot": slot["kind"],
                "nested_index": slot["index"],
                "almanca": de_text,
                "turkce": tr_text,
                "details": info,
            }
            samples.append(sample)

            if not args.apply_fixes:
                continue
            if slot["kind"] == "top" and args.clear_top_tr:
                record["ornek_turkce"] = ""
                counters["cleared_top_translations"] += 1
            elif slot["kind"] == "nested" and args.clear_nested_tr:
                record["ornekler"][slot["index"]]["turkce"] = ""
                counters["cleared_nested_translations"] += 1

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
