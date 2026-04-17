#!/usr/bin/env python3
"""Generic integrity cleanup for trusted relation fields such as `sinonim` and `antonim`."""

from __future__ import annotations

import argparse
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


BACKLINK_MAP = {
    "sinonim": ("sinonim", "esanlamlilar"),
    "antonim": ("antonim", "zit_anlamlilar"),
}


def has_backlink(records: list[dict], target_indexes: list[int], source_lemma: str, field: str) -> bool:
    source_key = normalize_key(source_lemma)
    backlink_fields = BACKLINK_MAP.get(field, (field,))
    for target_idx in target_indexes:
        target = records[target_idx]
        for backlink_field in backlink_fields:
            values = {normalize_key(item) for item in to_list(target.get(backlink_field))}
            if source_key in values:
                return True
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_DIR / "relation_target_integrity.json",
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--apply-fixes", action="store_true")
    parser.add_argument("--fields", nargs="+", default=["sinonim", "antonim"])
    parser.add_argument("--require-existing-target", action="store_true")
    parser.add_argument("--require-reciprocal", action="store_true")
    parser.add_argument("--drop-self-loops", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=200)
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
        if not lemma:
            continue
        source_key = normalize_key(lemma)

        for field in args.fields:
            values = to_list(record.get(field))
            if not values:
                continue
            cleaned: list[str] = []
            removed: list[dict] = []
            for item in values:
                item_key = normalize_key(item)
                target_indexes = index.get(item_key, [])
                reasons: list[str] = []
                if item_key == source_key:
                    reasons.append("self_loop")
                    counters[f"{field}:self_loops"] += 1
                if not target_indexes:
                    reasons.append("missing_target")
                    counters[f"{field}:missing_targets"] += 1
                elif not has_backlink(records, target_indexes, lemma, field):
                    reasons.append("nonreciprocal")
                    counters[f"{field}:nonreciprocal"] += 1

                should_drop = False
                if "self_loop" in reasons and args.drop_self_loops:
                    should_drop = True
                if "missing_target" in reasons and args.require_existing_target:
                    should_drop = True
                if "nonreciprocal" in reasons and args.require_reciprocal:
                    should_drop = True

                if should_drop:
                    removed.append({"value": item, "reasons": reasons})
                    counters[f"{field}:removed"] += 1
                else:
                    cleaned.append(item)

            cleaned = unique_list(cleaned)
            if removed:
                samples.append(
                    {
                        "record_index": rec_idx,
                        "record": record_label(record, rec_idx),
                        "field": field,
                        "before": values,
                        "after": cleaned,
                        "removed": removed,
                    }
                )
            if args.apply_fixes:
                if cleaned:
                    record[field] = cleaned
                else:
                    record.pop(field, None)

    payload = {
        "dict_path": str(args.dict_path),
        "fields": args.fields,
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
