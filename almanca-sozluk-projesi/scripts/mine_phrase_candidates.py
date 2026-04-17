#!/usr/bin/env python3
"""Mine German phrase candidates from Wikipedia/Gutenberg example sentences."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from enrich_phrase_patterns import (
    DICT_PATH,
    BOOK_WIKI_MARKERS,
    FUNCTION_STARTERS,
    MINED_SUPPORT_NOUNS,
    MINING_END_VERBS,
    extract_candidates,
    mine_bulk_candidates,
    normalize_key,
    split_semicolon_sources,
    tokenize_german,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "manual" / "phrase_candidates_review.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DICT_PATH)
    parser.add_argument("--output-path", type=Path, default=OUTPUT_PATH)
    return parser.parse_args()


def source_allows_mining(source_names: list[str]) -> bool:
    joined = "; ".join(source_names)
    return any(marker in joined for marker in BOOK_WIKI_MARKERS)


def classify_candidate(phrase: str, source_kinds: set[str], freq: int) -> tuple[str, bool]:
    tokens = tokenize_german(phrase)
    norm_tokens = [normalize_key(token) for token in tokens]
    if not norm_tokens:
        return "low", False

    has_support_noun = any(token in MINED_SUPPORT_NOUNS for token in norm_tokens[:-1])
    starts_function = norm_tokens[0] in FUNCTION_STARTERS
    ends_support_verb = norm_tokens[-1] in MINING_END_VERBS
    contains_zu = "zu" in norm_tokens[:-1]
    preposition_led = norm_tokens[0] in {"in", "im", "am", "an", "auf", "unter", "mit", "nach", "vor", "zu", "zum", "zur", "vom", "beim"}
    article_led = norm_tokens[0] in {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "eines"}

    if freq >= 2:
        return "high", True
    if starts_function and ends_support_verb and has_support_noun:
        if preposition_led and 2 <= len(norm_tokens) <= 4:
            return "high", True
        if article_led and contains_zu and 3 <= len(norm_tokens) <= 4:
            return "high", True
        if len(norm_tokens) <= 4 and ("generic" in source_kinds):
            return "medium", False
    return "low", False


def main() -> None:
    args = parse_args()
    data = json.loads(args.dict_path.read_text(encoding="utf-8"))
    existing = {normalize_key(str(row.get("almanca") or "")) for row in data if row.get("almanca")}
    candidate_counts: Counter[str] = Counter()
    candidate_examples: dict[str, str] = {}
    candidate_sources: defaultdict[str, set[str]] = defaultdict(set)

    curated_map = {}

    for row in data:
        source_names = split_semicolon_sources(row.get("kaynak") or "")
        if not source_allows_mining(source_names):
            continue

        sentences = []
        if (row.get("ornek_almanca") or "").strip():
            sentences.append(str(row.get("ornek_almanca") or "").strip())
        for ex in row.get("ornekler") or []:
            if isinstance(ex, dict) and (ex.get("almanca") or "").strip():
                sentences.append(str(ex.get("almanca") or "").strip())

        for sentence in sentences:
            matches = extract_candidates(sentence, curated_map) + mine_bulk_candidates(sentence)
            for phrase, _pos, source_kind in matches:
                key = normalize_key(phrase)
                if not key or key in existing:
                    continue
                candidate_counts[phrase] += 1
                candidate_sources[phrase].update(source_names)
                candidate_sources[phrase].add(source_kind)
                candidate_examples.setdefault(phrase, sentence)

    ranked = []
    for phrase, freq in candidate_counts.most_common(300):
        confidence, import_ready = classify_candidate(phrase, candidate_sources[phrase], freq)
        if freq < 2 and not import_ready:
            continue
        ranked.append(
            {
                "almanca": phrase,
                "frekans": freq,
                "ornek": candidate_examples.get(phrase, ""),
                "kaynaklar": sorted(candidate_sources[phrase]),
                "confidence": confidence,
                "import_ready": import_ready,
            }
        )

    payload = {
        "candidate_count": len(ranked),
        "candidates": ranked,
    }
    args.output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"candidate_count": len(ranked), "output": str(args.output_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
