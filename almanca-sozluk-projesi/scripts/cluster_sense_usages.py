#!/usr/bin/env python3
"""Cluster corpus usage samples into sense-like groups for review."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from corpus_quality_utils import CORPUS_OUTPUT_DIR, DEFAULT_DICT_PATH, compact_space, keyword_tokens, load_json, normalize_text, save_json


DEFAULT_USAGE_PATH = CORPUS_OUTPUT_DIR / "corpus_usage_index.json"
DEFAULT_OUTPUT_PATH = CORPUS_OUTPUT_DIR / "corpus_sense_clusters.json"
DEFAULT_CHECKPOINT_PATH = CORPUS_OUTPUT_DIR / "corpus_sense_clusters.checkpoint.json"
DEFAULT_REPORT_PATH = CORPUS_OUTPUT_DIR / "corpus_sense_clusters_report.json"


def build_cluster_record(sample: dict, lemma: str) -> dict:
    blocked = {normalize_text(lemma)}
    tokens = keyword_tokens(sample.get("sentence", ""), blocked=blocked)
    return {
        "sample_count": 1,
        "keywords": Counter(tokens),
        "sources": Counter({sample.get("source", "unknown"): 1}),
        "samples": [{"sentence": sample.get("sentence", ""), "source": sample.get("source", ""), "score": sample.get("score", 0.0)}],
        "token_set": set(tokens),
    }


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def finalize_clusters(clusters: list[dict]) -> list[dict]:
    result: list[dict] = []
    for cluster in clusters:
        keywords = [token for token, _count in cluster["keywords"].most_common(8)]
        samples = sorted(cluster["samples"], key=lambda item: (-float(item.get("score", 0.0)), len(item.get("sentence", ""))))[:3]
        result.append(
            {
                "sample_count": cluster["sample_count"],
                "keywords": keywords,
                "sources": dict(cluster["sources"]),
                "samples": samples,
            }
        )
    result.sort(key=lambda item: (-item["sample_count"], len(item["keywords"])))
    return result


def cluster_samples(lemma: str, samples: list[dict], threshold: float) -> list[dict]:
    clusters: list[dict] = []
    for sample in samples:
        sample_tokens = set(keyword_tokens(sample.get("sentence", ""), blocked={normalize_text(lemma)}))
        if not sample_tokens:
            sample_tokens = set(keyword_tokens(sample.get("sentence", "")))
        best_index = -1
        best_score = 0.0
        for index, cluster in enumerate(clusters):
            overlap = jaccard(sample_tokens, cluster["token_set"])
            if overlap > best_score:
                best_score = overlap
                best_index = index
        if best_index >= 0 and best_score >= threshold:
            target = clusters[best_index]
            target["sample_count"] += 1
            target["keywords"].update(sample_tokens)
            target["sources"].update([sample.get("source", "unknown")])
            target["samples"].append({"sentence": sample.get("sentence", ""), "source": sample.get("source", ""), "score": sample.get("score", 0.0)})
            target["token_set"].update(sample_tokens)
        else:
            clusters.append(build_cluster_record(sample, lemma))
    return finalize_clusters(clusters)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cluster corpus usage samples into sense-like groups.")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--usage-path", type=Path, default=DEFAULT_USAGE_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--checkpoint-path", type=Path, default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-lemmas-per-run", type=int, default=900)
    parser.add_argument("--min-samples", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.34)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if args.reset:
        for path in (args.output_path, args.checkpoint_path, args.report_path):
            if path.exists():
                path.unlink()

    usage_index = load_json(args.usage_path, {})
    output = load_json(args.output_path, {})
    checkpoint = load_json(args.checkpoint_path, {"offset": 0, "cycles": 0})
    items = sorted(usage_index.items(), key=lambda item: item[1].get("almanca", item[0]))
    start = int(checkpoint.get("offset", 0))
    end = min(len(items), start + max(0, args.max_lemmas_per_run))
    processed = 0
    clustered = 0

    for key, row in items[start:end]:
        processed += 1
        samples = [item for item in (row.get("samples") or []) if compact_space(item.get("sentence") or "")]
        if len(samples) < args.min_samples:
            continue
        output[key] = {
            "almanca": row.get("almanca", ""),
            "tur": row.get("tur", ""),
            "turkce": row.get("turkce", ""),
            "clusters": cluster_samples(row.get("almanca", ""), samples, args.threshold),
        }
        clustered += 1

    checkpoint["offset"] = end
    checkpoint["cycles"] = int(checkpoint.get("cycles", 0)) + 1
    checkpoint["total"] = len(items)

    save_json(args.output_path, output)
    save_json(args.checkpoint_path, checkpoint)
    save_json(
        args.report_path,
        {
            "processed": processed,
            "clustered": clustered,
            "offset": checkpoint["offset"],
            "total": checkpoint["total"],
            "cycles": checkpoint["cycles"],
        },
    )
    print(json.dumps({"processed": processed, "clustered": clustered, "offset": checkpoint["offset"], "total": checkpoint["total"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
