#!/usr/bin/env python3
"""Rank corpus examples per lemma for later review/import."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from corpus_quality_utils import CORPUS_OUTPUT_DIR, sentence_score, load_json, save_json


DEFAULT_USAGE_PATH = CORPUS_OUTPUT_DIR / "corpus_usage_index.json"
DEFAULT_OUTPUT_PATH = CORPUS_OUTPUT_DIR / "corpus_ranked_examples.json"
DEFAULT_CHECKPOINT_PATH = CORPUS_OUTPUT_DIR / "corpus_ranked_examples.checkpoint.json"
DEFAULT_REPORT_PATH = CORPUS_OUTPUT_DIR / "corpus_ranked_examples_report.json"


def rerank_samples(samples: list[dict]) -> list[dict]:
    ranked = []
    for item in samples:
        sentence = item.get("sentence", "")
        source = item.get("source", "")
        score = float(item.get("score", 0.0)) + sentence_score(sentence, preferred_source=source)
        ranked.append({"sentence": sentence, "source": source, "score": round(score, 3)})
    ranked.sort(key=lambda item: (-item["score"], len(item["sentence"])))
    return ranked[:5]


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank corpus examples per lemma.")
    parser.add_argument("--usage-path", type=Path, default=DEFAULT_USAGE_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--checkpoint-path", type=Path, default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-lemmas-per-run", type=int, default=1400)
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
    updated = 0

    for key, row in items[start:end]:
        processed += 1
        samples = row.get("samples") or []
        if not samples:
            continue
        output[key] = {
            "almanca": row.get("almanca", ""),
            "tur": row.get("tur", ""),
            "examples": rerank_samples(samples),
        }
        updated += 1

    checkpoint["offset"] = end
    checkpoint["cycles"] = int(checkpoint.get("cycles", 0)) + 1
    checkpoint["total"] = len(items)

    save_json(args.output_path, output)
    save_json(args.checkpoint_path, checkpoint)
    save_json(
        args.report_path,
        {"processed": processed, "updated": updated, "offset": checkpoint["offset"], "total": checkpoint["total"], "cycles": checkpoint["cycles"]},
    )
    print(json.dumps({"processed": processed, "updated": updated, "offset": checkpoint["offset"], "total": checkpoint["total"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
