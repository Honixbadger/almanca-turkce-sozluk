#!/usr/bin/env python3
"""Extract conservative verb valency hints from corpus usage samples."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from corpus_quality_utils import CORPUS_OUTPUT_DIR, DEFAULT_DICT_PATH, compact_space, load_json, normalize_text, save_json, tokenize


DEFAULT_USAGE_PATH = CORPUS_OUTPUT_DIR / "corpus_usage_index.json"
DEFAULT_OUTPUT_PATH = CORPUS_OUTPUT_DIR / "corpus_verb_valency.json"
DEFAULT_CHECKPOINT_PATH = CORPUS_OUTPUT_DIR / "corpus_verb_valency.checkpoint.json"
DEFAULT_REPORT_PATH = CORPUS_OUTPUT_DIR / "corpus_verb_valency_report.json"

PREPOSITIONS = {"an", "auf", "aus", "bei", "für", "gegen", "in", "mit", "nach", "über", "um", "unter", "von", "vor", "zu"}
REFLEXIVE = {"mich", "dich", "sich", "uns", "euch"}
CASE_HINTS = {
    "Akk": {"den", "die", "das", "einen", "eine", "einen", "ihn", "sie", "es", "mich", "dich", "uns", "euch"},
    "Dat": {"dem", "der", "einem", "einer", "ihm", "ihr", "ihnen", "mir", "dir", "uns", "euch"},
    "Gen": {"des", "eines", "einer", "dessen", "deren"},
}
PUNCT_RE = re.compile(r"[.,;:!?()\[\]\"„“]")


def normalize_tokens(sentence: str) -> list[str]:
    cleaned = PUNCT_RE.sub(" ", str(sentence or ""))
    return [normalize_text(token) for token in tokenize(cleaned) if normalize_text(token)]


def detect_case(tokens: list[str], prep_pos: int) -> str:
    window = tokens[prep_pos + 1: prep_pos + 5]
    for label, hints in CASE_HINTS.items():
        if any(token in hints for token in window):
            return label
    return ""


def extract_patterns(lemma: str, samples: list[dict]) -> tuple[list[dict], list[dict]]:
    lemma_key = normalize_text(lemma)
    valency_counter = Counter()
    pattern_counter = Counter()
    for sample in samples:
        tokens = normalize_tokens(sample.get("sentence", ""))
        if lemma_key not in tokens:
            continue
        positions = [idx for idx, token in enumerate(tokens) if token == lemma_key]
        for pos in positions:
            window = tokens[max(0, pos - 3): min(len(tokens), pos + 6)]
            if any(token in REFLEXIVE for token in window):
                valency_counter["sich + Verb"] += 1
                pattern_counter[f"sich {lemma}"] += 1
            for idx in range(pos, min(len(tokens), pos + 5)):
                token = tokens[idx]
                if token in PREPOSITIONS:
                    case_label = detect_case(tokens, idx)
                    valency = f"{token} + {case_label}" if case_label else token
                    valency_counter[valency] += 1
                    pattern_counter[f"{lemma} {token}"] += 1
    valency = [{"valenz": key, "count": count} for key, count in valency_counter.most_common(10) if count >= 2]
    patterns = [{"kalip": key, "count": count} for key, count in pattern_counter.most_common(10) if count >= 2]
    return valency, patterns


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract conservative verb valency hints from corpus usage.")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--usage-path", type=Path, default=DEFAULT_USAGE_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--checkpoint-path", type=Path, default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-verbs-per-run", type=int, default=600)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if args.reset:
        for path in (args.output_path, args.checkpoint_path, args.report_path):
            if path.exists():
                path.unlink()

    dictionary = load_json(args.dict_path, [])
    usage_index = load_json(args.usage_path, {})
    output = load_json(args.output_path, {})
    checkpoint = load_json(args.checkpoint_path, {"offset": 0, "cycles": 0})

    verbs = []
    for row in dictionary:
        if compact_space(row.get("tur") or "").casefold() != "fiil":
            continue
        lemma = compact_space(row.get("almanca") or "")
        if not lemma:
            continue
        verbs.append((normalize_text(lemma), lemma))
    verbs.sort(key=lambda item: item[1])

    start = int(checkpoint.get("offset", 0))
    end = min(len(verbs), start + max(0, args.max_verbs_per_run))
    processed = 0
    updated = 0

    for key, lemma in verbs[start:end]:
        processed += 1
        usage_row = usage_index.get(key)
        if not usage_row:
            continue
        samples = usage_row.get("samples") or []
        if not samples:
            continue
        valency, patterns = extract_patterns(lemma, samples)
        if not valency and not patterns:
            continue
        output[key] = {
            "almanca": lemma,
            "valenz": valency,
            "fiil_kaliplari": patterns,
        }
        updated += 1

    checkpoint["offset"] = end
    checkpoint["cycles"] = int(checkpoint.get("cycles", 0)) + 1
    checkpoint["total"] = len(verbs)

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
        },
    )
    print(json.dumps({"processed": processed, "updated": updated, "offset": checkpoint["offset"], "total": checkpoint["total"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
