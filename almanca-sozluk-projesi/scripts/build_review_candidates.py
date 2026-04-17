#!/usr/bin/env python3
"""Build resumable review candidates from corpus-derived quality artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from corpus_quality_utils import CORPUS_OUTPUT_DIR, DEFAULT_DICT_PATH, compact_space, load_json, normalize_text, save_json


DEFAULT_USAGE_PATH = CORPUS_OUTPUT_DIR / "corpus_usage_index.json"
DEFAULT_CLUSTERS_PATH = CORPUS_OUTPUT_DIR / "corpus_sense_clusters.json"
DEFAULT_VALENCY_PATH = CORPUS_OUTPUT_DIR / "corpus_verb_valency.json"
DEFAULT_EXAMPLES_PATH = CORPUS_OUTPUT_DIR / "corpus_ranked_examples.json"
DEFAULT_OUTPUT_PATH = CORPUS_OUTPUT_DIR / "corpus_review_candidates.json"
DEFAULT_CHECKPOINT_PATH = CORPUS_OUTPUT_DIR / "corpus_review_candidates.checkpoint.json"
DEFAULT_REPORT_PATH = CORPUS_OUTPUT_DIR / "corpus_review_candidates_report.json"


def existing_example_count(record: dict) -> int:
    count = 0
    for item in record.get("ornekler") or []:
        if isinstance(item, dict) and compact_space(item.get("almanca") or ""):
            count += 1
    if compact_space(record.get("ornek_almanca") or ""):
        count += 1
    return count


def existing_valency_count(record: dict) -> int:
    return len([item for item in (record.get("valenz") or []) if compact_space(item if isinstance(item, str) else item.get("valenz", ""))])


def build_candidate(record: dict, usage_row: dict, cluster_row: dict | None, valency_row: dict | None, examples_row: dict | None) -> dict | None:
    candidate = {
        "almanca": compact_space(record.get("almanca") or ""),
        "tur": compact_space(record.get("tur") or ""),
        "turkce": compact_space(record.get("turkce") or ""),
        "review_reasons": [],
    }
    if not candidate["almanca"]:
        return None

    if cluster_row and len(cluster_row.get("clusters") or []) >= 2:
        candidate["sense_cluster_hints"] = cluster_row.get("clusters")[:4]
        candidate["review_reasons"].append("multi-sense-usage")

    if valency_row and candidate["tur"] == "fiil":
        if existing_valency_count(record) < 2 and (valency_row.get("valenz") or []):
            candidate["valency_candidates"] = valency_row.get("valenz")[:6]
            candidate["review_reasons"].append("valency-gap")
        if not (record.get("fiil_kaliplari") or []) and (valency_row.get("fiil_kaliplari") or []):
            candidate["pattern_candidates"] = valency_row.get("fiil_kaliplari")[:6]
            candidate["review_reasons"].append("pattern-gap")

    if examples_row and existing_example_count(record) < 2:
        candidate["example_candidates"] = (examples_row.get("examples") or [])[:3]
        if candidate["example_candidates"]:
            candidate["review_reasons"].append("example-gap")

    if usage_row and int(usage_row.get("hits_total", 0)) >= 8:
        candidate["usage_summary"] = {
            "hits_total": int(usage_row.get("hits_total", 0)),
            "source_counts": usage_row.get("source_counts", {}),
            "top_context_terms": list((usage_row.get("context_counts") or {}).keys())[:10],
        }

    if not candidate["review_reasons"]:
        return None
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Build resumable review candidates from corpus artifacts.")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--usage-path", type=Path, default=DEFAULT_USAGE_PATH)
    parser.add_argument("--clusters-path", type=Path, default=DEFAULT_CLUSTERS_PATH)
    parser.add_argument("--valency-path", type=Path, default=DEFAULT_VALENCY_PATH)
    parser.add_argument("--examples-path", type=Path, default=DEFAULT_EXAMPLES_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--checkpoint-path", type=Path, default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-records-per-run", type=int, default=1800)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if args.reset:
        for path in (args.output_path, args.checkpoint_path, args.report_path):
            if path.exists():
                path.unlink()

    dictionary = load_json(args.dict_path, [])
    usage_index = load_json(args.usage_path, {})
    clusters = load_json(args.clusters_path, {})
    valency = load_json(args.valency_path, {})
    examples = load_json(args.examples_path, {})
    output = load_json(args.output_path, {})
    checkpoint = load_json(args.checkpoint_path, {"offset": 0, "cycles": 0})

    start = int(checkpoint.get("offset", 0))
    end = min(len(dictionary), start + max(0, args.max_records_per_run))
    processed = 0
    updated = 0

    for record in dictionary[start:end]:
        processed += 1
        key = normalize_text(compact_space(record.get("almanca") or ""))
        if not key:
            continue
        candidate = build_candidate(record, usage_index.get(key, {}), clusters.get(key), valency.get(key), examples.get(key))
        if candidate is None:
            continue
        output[key] = candidate
        updated += 1

    checkpoint["offset"] = end
    checkpoint["cycles"] = int(checkpoint.get("cycles", 0)) + 1
    checkpoint["total"] = len(dictionary)

    save_json(args.output_path, output)
    save_json(args.checkpoint_path, checkpoint)
    save_json(
        args.report_path,
        {
            "processed": processed,
            "updated": updated,
            "offset": checkpoint["offset"],
            "total": checkpoint["total"],
            "cycles": checkpoint["cycles"],
            "candidate_count": len(output),
        },
    )
    print(json.dumps({"processed": processed, "updated": updated, "candidate_count": len(output), "offset": checkpoint["offset"], "total": checkpoint["total"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
