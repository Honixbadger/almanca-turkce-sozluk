#!/usr/bin/env python3
"""Build a broad snapshot of remaining dictionary quality problems."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from fix_example_translation_drift import suspicious_translation
from fix_fragment_examples import detect_fragment
from fix_non_german_examples import score_language
from fix_top_example_lemma_mismatch import example_matches_lemma
from quality_common import (
    DEFAULT_DICT_PATH,
    DEFAULT_REPORT_DIR,
    compact,
    configure_stdio,
    contains_mojibake,
    get_text_field_paths,
    iter_example_slots,
    normalize_key,
    read_records,
    relation_index,
    to_list,
    write_json,
)


BACKLINK_MAP = {
    "esanlamlilar": ("esanlamlilar", "sinonim"),
    "sinonim": ("sinonim", "esanlamlilar"),
    "zit_anlamlilar": ("zit_anlamlilar", "antonim"),
    "antonim": ("antonim", "zit_anlamlilar"),
}


def has_backlink(records: list[dict], target_indexes: list[int], source_lemma: str, field: str) -> bool:
    source_key = normalize_key(source_lemma)
    for target_idx in target_indexes:
        target = records[target_idx]
        for backlink_field in BACKLINK_MAP[field]:
            values = {normalize_key(item) for item in to_list(target.get(backlink_field))}
            if source_key in values:
                return True
    return False


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_DIR / "quality_snapshot.json",
    )
    parser.add_argument("--sample-limit", type=int, default=100)
    args = parser.parse_args()

    records = read_records(args.dict_path)
    index = relation_index(records)
    counters = Counter()
    samples: dict[str, list[dict]] = {
        "non_german_examples": [],
        "fragment_examples": [],
        "lemma_mismatch_top_examples": [],
        "translation_drift_examples": [],
        "encoding_artifacts": [],
    }

    field_names = [field for field, _path in get_text_field_paths()]

    for rec_idx, record in enumerate(records):
        counters["total_records"] += 1
        if len(record.get("anlamlar") or []) > 1 and len(record.get("kategoriler") or []) <= 1:
            counters["multi_sense_single_category"] += 1

        top_de = compact(record.get("ornek_almanca") or "")
        top_tr = compact(record.get("ornek_turkce") or "")
        if top_de and top_tr:
            top_matches = False
            for item in record.get("ornekler") or []:
                if not isinstance(item, dict):
                    continue
                if compact(item.get("almanca") or "") == top_de and compact(item.get("turkce") or "") == top_tr:
                    top_matches = True
                    break
            if record.get("ornekler") and not top_matches:
                counters["top_pair_not_repeated_in_nested_examples"] += 1

        for field in field_names:
            value = compact(record.get(field) or "")
            if not value:
                continue
            if "??" in value or contains_mojibake(value):
                counters["encoding_placeholder_turkish"] += 1
                if len(samples["encoding_artifacts"]) < args.sample_limit:
                    samples["encoding_artifacts"].append(
                        {
                            "record_index": rec_idx,
                            "lemma": compact(record.get("almanca") or ""),
                            "field": field,
                            "value": value,
                        }
                    )

        lemma = compact(record.get("almanca") or "")
        if lemma and top_de:
            ok, reason = example_matches_lemma(lemma, top_de, compact(record.get("tur") or ""))
            if not ok:
                counters["top_example_lemma_mismatch"] += 1
                if len(samples["lemma_mismatch_top_examples"]) < args.sample_limit:
                    samples["lemma_mismatch_top_examples"].append(
                        {
                            "record_index": rec_idx,
                            "lemma": lemma,
                            "reason": reason,
                            "top_almanca": top_de,
                        }
                    )

        for slot in iter_example_slots(record):
            de = compact(slot["almanca"])
            tr = compact(slot["turkce"])
            if not de:
                continue
            language, counts = score_language(de)
            if language:
                counters["non_german_examples"] += 1
                if len(samples["non_german_examples"]) < args.sample_limit:
                    samples["non_german_examples"].append(
                        {
                            "record_index": rec_idx,
                            "lemma": lemma,
                            "slot": slot["kind"],
                            "language": language,
                            "counts": counts,
                            "almanca": de,
                        }
                    )
            reasons = detect_fragment(de, min_words=4)
            if reasons:
                counters["fragment_examples"] += 1
                if len(samples["fragment_examples"]) < args.sample_limit:
                    samples["fragment_examples"].append(
                        {
                            "record_index": rec_idx,
                            "lemma": lemma,
                            "slot": slot["kind"],
                            "reasons": reasons,
                            "almanca": de,
                        }
                    )
            if tr:
                bad, details = suspicious_translation(record, de, tr)
                if bad:
                    counters["translation_drift_examples"] += 1
                    if len(samples["translation_drift_examples"]) < args.sample_limit:
                        samples["translation_drift_examples"].append(
                            {
                                "record_index": rec_idx,
                                "lemma": lemma,
                                "slot": slot["kind"],
                                "almanca": de,
                                "turkce": tr,
                                "details": details,
                            }
                        )

    for field in ("esanlamlilar", "sinonim", "zit_anlamlilar", "antonim"):
        total = 0
        missing = 0
        self_loops = 0
        reciprocal = 0
        for record in records:
            lemma = compact(record.get("almanca") or "")
            source_key = normalize_key(lemma)
            values = to_list(record.get(field))
            if values:
                counters[f"{field}_entries"] += 1
            for value in values:
                total += 1
                item_key = normalize_key(value)
                targets = index.get(item_key, [])
                if item_key == source_key:
                    self_loops += 1
                if not targets:
                    missing += 1
                elif has_backlink(records, targets, lemma, field):
                    reciprocal += 1
        counters[f"{field}_total"] = total
        counters[f"{field}_target_missing"] = missing
        counters[f"{field}_self_loops"] = self_loops
        counters[f"{field}_target_exists"] = max(0, total - missing)
        counters[f"{field}_reciprocal"] = reciprocal

    payload = {
        "dict_path": str(args.dict_path),
        "counters": dict(counters),
        "samples": samples,
    }
    write_json(args.report_path, payload)
    print(payload["counters"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
