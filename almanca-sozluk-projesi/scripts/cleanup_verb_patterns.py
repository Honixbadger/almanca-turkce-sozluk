#!/usr/bin/env python3
"""Conservatively clean noisy verb patterns using structure and DWDS validation."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from enrich_verb_usage import VERB_POS, compact, keep_existing_pattern
from merge_stage_dictionary_safe import InterProcessFileLock, LOCK_PATH
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "cleanup_verb_patterns_report.json"


def should_keep_pattern(record: dict, row: dict) -> tuple[bool, str]:
    phrase = compact(row.get("kalip") or "")
    if not phrase:
        return False, "empty"
    structural_keep = keep_existing_pattern(record, row)
    if structural_keep:
        return True, "structural"
    return False, "unsupported"


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean noisy verb patterns conservatively.")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    data = json.loads(args.dict_path.read_text(encoding="utf-8"))
    counters = Counter()
    sample: list[dict] = []

    for row in data:
        if compact(row.get("tur") or "").casefold() != VERB_POS:
            continue
        patterns = [item for item in (row.get("fiil_kaliplari") or []) if isinstance(item, dict) and compact(item.get("kalip") or "")]
        if not patterns:
            continue
        if args.limit > 0 and counters["verbs_seen"] >= args.limit:
            break
        counters["verbs_seen"] += 1

        kept: list[dict] = []
        removed: list[str] = []
        for pattern_row in patterns:
            keep, reason = should_keep_pattern(row, pattern_row)
            if keep:
                kept.append(pattern_row)
            else:
                removed.append(compact(pattern_row.get("kalip") or ""))
                counters[f"removed::{reason}"] += 1

        if len(kept) != len(patterns):
            row["fiil_kaliplari"] = kept
            counters["verbs_updated"] += 1
            counters["patterns_removed"] += len(patterns) - len(kept)
            if len(sample) < 120:
                sample.append(
                    {
                        "verb": compact(row.get("almanca") or ""),
                        "removed": removed[:8],
                        "kept": [compact(item.get("kalip") or "") for item in kept[:8]],
                    }
                )

    output_path = args.output_path or args.dict_path
    report = {
        "dict_path": str(args.dict_path),
        "output_path": str(output_path),
        "apply": bool(args.apply),
        "counters": dict(counters),
        "sample": sample,
    }
    if args.apply:
        with InterProcessFileLock(LOCK_PATH):
            output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
