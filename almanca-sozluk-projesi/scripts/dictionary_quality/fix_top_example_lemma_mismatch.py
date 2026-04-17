#!/usr/bin/env python3
"""Find top examples that do not actually exemplify the current lemma."""

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
    normalize_key,
    read_records,
    record_label,
    write_json,
    write_records,
)


def tokenize_example(text: str) -> list[str]:
    return [token for token in re.findall(r"[A-Za-zÄÖÜäöüß-]+", text)]


def example_matches_lemma(lemma: str, example: str, word_type: str) -> tuple[bool, str]:
    lemma_key = normalize_key(lemma)
    original_tokens = tokenize_example(example)
    tokens = [normalize_key(token) for token in original_tokens]
    if not lemma_key or not tokens:
        return True, "empty"

    if lemma_key in tokens:
        return True, "exact_token"

    if "-" in lemma_key and lemma_key.replace("-", "") in {token.replace("-", "") for token in tokens}:
        return True, "hyphen_variant"

    if word_type == "fiil":
        root = lemma_key[:-2] if lemma_key.endswith("en") else lemma_key
        root = root[: max(4, len(root))]
        if any(token.startswith(root[:4]) for token in tokens):
            return True, "verb_root_match"
    else:
        noun_suffixes = ("e", "en", "er", "n", "s", "es")
        for original, token in zip(original_tokens, tokens):
            if not original[:1].isupper():
                continue
            if token == lemma_key:
                return True, "noun_exact"
            if any(token == f"{lemma_key}{suffix}" for suffix in noun_suffixes):
                return True, "noun_inflection"

    substring_tokens = [token for token in tokens if lemma_key in token and token != lemma_key]
    if substring_tokens:
        return False, "substring_only"

    return False, "lemma_missing"


def first_matching_nested(record: dict, lemma: str, word_type: str) -> dict | None:
    for item in record.get("ornekler") or []:
        if not isinstance(item, dict):
            continue
        example = compact(item.get("almanca") or "")
        if not example:
            continue
        ok, _reason = example_matches_lemma(lemma, example, word_type)
        if ok:
            return {
                "almanca": compact(item.get("almanca") or ""),
                "turkce": compact(item.get("turkce") or ""),
            }
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_DIR / "top_example_lemma_mismatch.json",
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--apply-fixes", action="store_true")
    parser.add_argument("--clear-top", action="store_true")
    parser.add_argument("--promote-matching-nested", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    records = read_records(args.dict_path)
    counters = Counter()
    samples: list[dict] = []

    for rec_idx, record in enumerate(records):
        lemma = compact(record.get("almanca") or "")
        top_de = compact(record.get("ornek_almanca") or "")
        if not lemma or not top_de:
            continue

        ok, reason = example_matches_lemma(lemma, top_de, compact(record.get("tur") or ""))
        if ok:
            continue

        counters["flagged_records"] += 1
        counters[f"reason:{reason}"] += 1
        sample = {
            "record_index": rec_idx,
            "record": record_label(record, rec_idx),
            "lemma": lemma,
            "top_almanca": top_de,
            "top_turkce": compact(record.get("ornek_turkce") or ""),
            "reason": reason,
        }

        if args.apply_fixes and args.promote_matching_nested:
            replacement = first_matching_nested(record, lemma, compact(record.get("tur") or ""))
            if replacement:
                record["ornek_almanca"] = replacement["almanca"]
                record["ornek_turkce"] = replacement["turkce"]
                counters["promoted_nested_examples"] += 1
                sample["replacement"] = replacement
            elif args.clear_top and clear_top_example(record):
                counters["cleared_top_examples"] += 1
        elif args.apply_fixes and args.clear_top and clear_top_example(record):
            counters["cleared_top_examples"] += 1

        samples.append(sample)

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
