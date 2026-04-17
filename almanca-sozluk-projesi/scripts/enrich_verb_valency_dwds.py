#!/usr/bin/env python3
"""Grow verb valency data using conservative DWDS-supported signals."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from enrich_verb_usage import (
    PREPOSITIONS,
    VERB_POS,
    collect_known_forms,
    compact,
    dedupe_strings,
    extract_translation_note_patterns,
    keep_existing_pattern,
    normalize,
)
from validate_verb_patterns_dwds import (
    fetch_dwds_html,
    find_form_positions,
    strip_html_markup,
    tokenize,
    validate_candidate,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output" / "dictionary_verb_valency_dwds_stage.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "verb_valency_dwds_report.json"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "output" / "dwds_validation_cache"


def pattern_to_valency(record: dict, lemma: str, tokens: list[str], forms: set[str], visible: str) -> list[str]:
    suggestions: list[str] = []
    for row in record.get("fiil_kaliplari") or []:
        if not isinstance(row, dict):
            continue
        phrase = compact(row.get("kalip") or "")
        if not phrase:
            continue
        if not ("+" in phrase or phrase.startswith("sich ") or phrase.split()[-1].casefold() in PREPOSITIONS):
            continue
        if not keep_existing_pattern(record, row):
            continue
        validation = validate_candidate(phrase, lemma, tokens, forms, visible)
        if validation["supported"]:
            suggestions.append(phrase)
    return suggestions


def has_valency_candidates(record: dict, lemma: str) -> bool:
    if record.get("valenz"):
        return True
    for row in record.get("fiil_kaliplari") or []:
        if not isinstance(row, dict):
            continue
        phrase = compact(row.get("kalip") or "")
        if not phrase:
            continue
        if "+" in phrase or phrase.startswith("sich ") or phrase.split()[-1].casefold() in PREPOSITIONS:
            return True
    if extract_translation_note_patterns(record, lemma, reflexive=False):
        return True
    if extract_translation_note_patterns(record, lemma, reflexive=True):
        return True
    return False


def note_to_valency(record: dict, lemma: str, tokens: list[str], forms: set[str], visible: str) -> list[str]:
    suggestions: list[str] = []
    for phrase in extract_translation_note_patterns(record, lemma, reflexive=False):
        validation = validate_candidate(phrase, lemma, tokens, forms, visible)
        if validation["supported"]:
            suggestions.append(phrase)
    has_reflexive_signal = any(
        compact(item).startswith("sich ")
        for item in (record.get("valenz") or [])
    ) or any(
        isinstance(item, dict) and compact(item.get("kalip") or "").startswith("sich ")
        for item in (record.get("fiil_kaliplari") or [])
    ) or "reflexiv" in normalize(record.get("aciklama_turkce") or "")
    if has_reflexive_signal:
        for phrase in extract_translation_note_patterns(record, lemma, reflexive=True):
            validation = validate_candidate(phrase, lemma, tokens, forms, visible)
            if validation["supported"]:
                suggestions.append(phrase)
    return suggestions


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich verb valency data with conservative DWDS signals.")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--refresh-cache", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.dict_path.read_text(encoding="utf-8"))
    counters = Counter()
    sample: list[dict] = []

    for row in data:
        if compact(row.get("tur") or "").casefold() != VERB_POS:
            continue
        lemma = compact(row.get("almanca") or "")
        if not lemma:
            continue
        if args.limit > 0 and counters["verbs_seen"] >= args.limit:
            break
        if not has_valency_candidates(row, lemma):
            continue
        counters["verbs_seen"] += 1

        try:
            html_text, used_cache = fetch_dwds_html(lemma, args.cache_dir, args.refresh_cache, args.delay)
        except Exception:
            counters["dwds_fetch_errors"] += 1
            continue
        counters["pages_cached" if used_cache else "pages_fetched"] += 1
        visible = strip_html_markup(html_text)
        tokens = tokenize(visible)
        forms = collect_known_forms(row)
        forms.add(normalize(lemma))
        positions = find_form_positions(tokens, forms)
        if not positions:
            continue

        current = list(row.get("valenz") or [])
        suggestions = list(current)
        suggestions.extend(pattern_to_valency(row, lemma, tokens, forms, visible))
        suggestions.extend(note_to_valency(row, lemma, tokens, forms, visible))

        cleaned = dedupe_strings(suggestions)
        if json.dumps(cleaned, ensure_ascii=False) != json.dumps(current, ensure_ascii=False):
            row["valenz"] = cleaned
            counters["verbs_updated"] += 1
            counters["valenz_added_total"] += max(0, len(cleaned) - len(current))
            if len(sample) < 80:
                sample.append(
                    {
                        "verb": lemma,
                        "before": current[:4],
                        "after": cleaned[:6],
                    }
                )

    args.output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "dict_path": str(args.dict_path),
        "output_path": str(args.output_path),
        "cache_dir": str(args.cache_dir),
        "counters": dict(counters),
        "sample": sample,
    }
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
