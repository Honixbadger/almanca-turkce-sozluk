#!/usr/bin/env python3
"""Build a resumable usage index from local corpora for dictionary quality work."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from corpus_quality_utils import (
    DEFAULT_DICT_PATH,
    build_dictionary_lemma_index,
    candidate_lemmas_for_token,
    compact_space,
    ensure_corpus_output_dir,
    html_files_sorted,
    iter_dewiktionary_example_sentences,
    iter_html_sentences,
    iter_tatoeba_sentences,
    load_json,
    normalize_text,
    save_json,
    tokenize,
    update_usage_entry,
)


OUTPUT_DIR = ensure_corpus_output_dir()
DEFAULT_OUTPUT_PATH = OUTPUT_DIR / "corpus_usage_index.json"
DEFAULT_CHECKPOINT_PATH = OUTPUT_DIR / "corpus_usage_index.checkpoint.json"
DEFAULT_REPORT_PATH = OUTPUT_DIR / "corpus_usage_index_report.json"


def process_payloads(
    payloads: list[dict],
    lemma_index: dict[str, dict],
    usage_index: dict[str, dict],
    counters: Counter,
) -> None:
    for item in payloads:
        sentence = compact_space(item.get("sentence") or "")
        if not sentence:
            continue
        matched: set[str] = set()
        for token in tokenize(sentence):
            for candidate in candidate_lemmas_for_token(token):
                if candidate in lemma_index:
                    matched.add(candidate)
                    break
        if not matched:
            counters["sentences_without_match"] += 1
            continue
        counters["sentences_with_match"] += 1
        for candidate in matched:
            meta = lemma_index[candidate]
            entry = usage_index.setdefault(
                candidate,
                {
                    "almanca": meta.get("almanca", ""),
                    "tur": meta.get("tur", ""),
                    "turkce": meta.get("turkce", ""),
                    "hits_total": 0,
                    "source_counts": {},
                    "context_counts": {},
                    "samples": [],
                },
            )
            update_usage_entry(entry, sentence, item.get("source", "unknown"), meta.get("almanca", ""))
            counters["lemma_hits"] += 1


def finalize_usage_index(usage_index: dict[str, dict]) -> dict[str, dict]:
    finalized: dict[str, dict] = {}
    for key, row in sorted(usage_index.items(), key=lambda item: item[1].get("almanca", item[0])):
        finalized[key] = {
            "almanca": row.get("almanca", ""),
            "tur": row.get("tur", ""),
            "turkce": row.get("turkce", ""),
            "hits_total": int(row.get("hits_total", 0)),
            "source_counts": dict(sorted((row.get("source_counts") or {}).items())),
            "context_counts": dict(sorted((row.get("context_counts") or {}).items(), key=lambda item: (-item[1], item[0]))[:40]),
            "samples": [
                {
                    "sentence": item.get("sentence", ""),
                    "source": item.get("source", ""),
                    "score": item.get("score", 0.0),
                }
                for item in sorted(
                    row.get("samples") or [],
                    key=lambda item: (-float(item.get("score", 0.0)), len(item.get("sentence", ""))),
                )[:10]
            ],
        }
    return finalized


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a resumable corpus usage index.")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--checkpoint-path", type=Path, default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-html-files-per-run", type=int, default=12)
    parser.add_argument("--max-tatoeba-lines-per-run", type=int, default=25000)
    parser.add_argument("--max-dewiktionary-lines-per-run", type=int, default=40000)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if args.reset:
        for path in (args.output_path, args.checkpoint_path, args.report_path):
            if path.exists():
                path.unlink()

    lemma_index = build_dictionary_lemma_index(args.dict_path)
    usage_index = load_json(args.output_path, {})
    checkpoint = load_json(
        args.checkpoint_path,
        {
            "html_index": 0,
            "tatoeba_lines": 0,
            "dewiktionary_lines": 0,
            "cycles": 0,
        },
    )
    counters = Counter()

    html_files = html_files_sorted()
    current_html_index = int(checkpoint.get("html_index", 0))
    next_html_index, html_payloads = iter_html_sentences(
        html_files,
        current_html_index,
        max(0, args.max_html_files_per_run),
    )
    process_payloads(html_payloads, lemma_index, usage_index, counters)
    checkpoint["html_index"] = next_html_index
    counters["html_files_processed"] = max(0, next_html_index - current_html_index)
    counters["html_sentences_seen"] = len(html_payloads)

    current_tatoeba_lines = int(checkpoint.get("tatoeba_lines", 0))
    next_tatoeba_line, tatoeba_payloads = iter_tatoeba_sentences(
        current_tatoeba_lines,
        max(0, args.max_tatoeba_lines_per_run),
    )
    process_payloads(tatoeba_payloads, lemma_index, usage_index, counters)
    counters["tatoeba_sentences_seen"] = len(tatoeba_payloads)
    counters["tatoeba_lines_advanced"] = max(0, next_tatoeba_line - current_tatoeba_lines)
    checkpoint["tatoeba_lines"] = next_tatoeba_line

    current_dewiktionary_lines = int(checkpoint.get("dewiktionary_lines", 0))
    next_dewiktionary_line, dewiktionary_payloads = iter_dewiktionary_example_sentences(
        current_dewiktionary_lines,
        max(0, args.max_dewiktionary_lines_per_run),
    )
    process_payloads(dewiktionary_payloads, lemma_index, usage_index, counters)
    counters["dewiktionary_examples_seen"] = len(dewiktionary_payloads)
    counters["dewiktionary_lines_advanced"] = max(0, next_dewiktionary_line - current_dewiktionary_lines)
    checkpoint["dewiktionary_lines"] = next_dewiktionary_line

    checkpoint["cycles"] = int(checkpoint.get("cycles", 0)) + 1
    checkpoint["lemma_count"] = len(lemma_index)
    checkpoint["indexed_lemma_count"] = len(usage_index)

    finalized = finalize_usage_index(usage_index)
    save_json(args.output_path, finalized)
    save_json(args.checkpoint_path, checkpoint)
    save_json(
        args.report_path,
        {
            "output_path": str(args.output_path),
            "checkpoint_path": str(args.checkpoint_path),
            "cycles": checkpoint["cycles"],
            "indexed_lemma_count": len(finalized),
            "counters": dict(counters),
            "progress": {
                "html_index": checkpoint["html_index"],
                "html_total_files": len(html_files),
                "tatoeba_lines": checkpoint["tatoeba_lines"],
                "dewiktionary_lines": checkpoint["dewiktionary_lines"],
            },
        },
    )
    print(json.dumps({"indexed_lemma_count": len(finalized), "counters": dict(counters), "progress": checkpoint}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
