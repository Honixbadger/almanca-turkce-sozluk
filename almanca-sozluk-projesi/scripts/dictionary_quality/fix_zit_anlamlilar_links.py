#!/usr/bin/env python3
"""Clean `zit_anlamlilar` entries with weak or broken antonym links."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from quality_common import (
    DEFAULT_DICT_PATH,
    DEFAULT_REPORT_DIR,
    compact,
    configure_stdio,
    normalize_key,
    read_records,
    record_label,
    relation_index,
    to_list,
    unique_list,
    write_json,
    write_records,
)


BACKLINK_FIELDS = ("zit_anlamlilar", "antonim")
DERIVED_NEGATIVE_RE = re.compile(r"^(nicht|un)[a-zäöüß]", re.IGNORECASE)


def has_backlink(records: list[dict], target_indexes: list[int], source_lemma: str) -> bool:
    source_key = normalize_key(source_lemma)
    for target_idx in target_indexes:
        target = records[target_idx]
        for field in BACKLINK_FIELDS:
            values = {normalize_key(item) for item in to_list(target.get(field))}
            if source_key in values:
                return True
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_DIR / "zit_anlamlilar_links.json",
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--apply-fixes", action="store_true")
    parser.add_argument("--require-existing-target", action="store_true")
    parser.add_argument("--require-reciprocal", action="store_true")
    parser.add_argument("--drop-self-loops", action="store_true")
    parser.add_argument("--drop-derived-negatives", action="store_true")
    parser.add_argument("--keep-max", type=int, default=12)
    parser.add_argument("--sample-limit", type=int, default=300)
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    records = read_records(args.dict_path)
    index = relation_index(records)
    counters = Counter()
    samples: list[dict] = []

    for rec_idx, record in enumerate(records):
        lemma = compact(record.get("almanca") or "")
        values = to_list(record.get("zit_anlamlilar"))
        if not lemma or not values:
            continue

        cleaned: list[str] = []
        seen_reasons: list[dict] = []
        source_key = normalize_key(lemma)
        for item in values:
            item_key = normalize_key(item)
            reasons: list[str] = []
            target_indexes = index.get(item_key, [])

            if item_key == source_key:
                counters["self_loops"] += 1
                reasons.append("self_loop")
            if not target_indexes:
                counters["missing_targets"] += 1
                reasons.append("missing_target")
            elif not has_backlink(records, target_indexes, lemma):
                counters["nonreciprocal_targets"] += 1
                reasons.append("nonreciprocal")
            if DERIVED_NEGATIVE_RE.match(item_key):
                counters["derived_negative_candidates"] += 1
                reasons.append("derived_negative")

            should_drop = False
            if "self_loop" in reasons and args.drop_self_loops:
                should_drop = True
            if "missing_target" in reasons and args.require_existing_target:
                should_drop = True
            if "nonreciprocal" in reasons and args.require_reciprocal:
                should_drop = True
            if "derived_negative" in reasons and args.drop_derived_negatives:
                should_drop = True

            if should_drop:
                counters["removed_links"] += 1
                seen_reasons.append({"value": item, "reasons": reasons})
            else:
                cleaned.append(item)

        cleaned = unique_list(cleaned)[: args.keep_max]
        if seen_reasons:
            counters["flagged_records"] += 1
            samples.append(
                {
                    "record_index": rec_idx,
                    "record": record_label(record, rec_idx),
                    "removed_or_flagged": seen_reasons,
                    "before": values,
                    "after": cleaned,
                }
            )

        if args.apply_fixes:
            if cleaned:
                record["zit_anlamlilar"] = cleaned
            else:
                record.pop("zit_anlamlilar", None)

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
