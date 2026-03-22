#!/usr/bin/env python
"""Build lightweight offline definition indexes for frontend lookups."""

from __future__ import annotations

import gzip
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "downloads"
DICTIONARY_PATH = OUTPUT_DIR / "dictionary.json"
DEWIKTIONARY_PATH = RAW_DIR / "dewiktionary.gz"
TRWIKTIONARY_PATH = RAW_DIR / "trwiktionary.gz"
DEFINITION_INDEX_DE_PATH = OUTPUT_DIR / "definition_index_de.json"
DEFINITION_INDEX_TR_PATH = OUTPUT_DIR / "definition_index_tr.json"
DEFINITION_AVAILABILITY_PATH = OUTPUT_DIR / "definition_availability.json"


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = text.replace("ß", "ss")
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return normalize_whitespace(text)


def strip_article(term: str) -> str:
    pieces = normalize_whitespace(term).split(" ", 1)
    if len(pieces) == 2 and pieces[0].casefold() in {"der", "die", "das"}:
        return pieces[1]
    return normalize_whitespace(term)


def turkish_candidates(term: str) -> list[str]:
    normalized = normalize_whitespace(term)
    candidates = [normalized]
    parts = [part for part in normalized.split(" ") if part]
    if len(parts) > 1:
        candidates.append(" ".join(parts[-2:]))
        candidates.append(parts[-1])

    seen = set()
    results = []
    for item in candidates:
        key = normalize_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


def unique_definitions(values: list[str], limit: int = 3) -> list[str]:
    seen = set()
    results = []
    for value in values:
        cleaned = normalize_whitespace(value)
        if not cleaned:
            continue
        key = normalize_key(cleaned)
        if key in seen:
            continue
        seen.add(key)
        results.append(cleaned)
        if len(results) >= limit:
            break
    return results


def load_targets() -> tuple[dict[str, str], dict[str, str]]:
    rows = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
    german_terms: dict[str, str] = {}
    turkish_terms: dict[str, str] = {}

    for row in rows:
        almanca = normalize_whitespace(row.get("almanca", ""))
        turkce = normalize_whitespace(row.get("turkce", ""))
        if almanca:
            german_terms.setdefault(normalize_key(almanca), almanca)
        if turkce:
            turkish_terms.setdefault(normalize_key(turkce), turkce)

    return german_terms, turkish_terms


def build_de_index(targets: dict[str, str]) -> tuple[dict[str, dict], Counter]:
    index: dict[str, dict] = {}
    counters = Counter()

    with gzip.open(DEWIKTIONARY_PATH, "rt", encoding="utf-8") as fh:
        for line in fh:
            entry = json.loads(line)
            word = normalize_whitespace(entry.get("word", ""))
            key = normalize_key(word)
            if not word or key not in targets or key in index:
                continue

            glosses = []
            for sense in entry.get("senses") or []:
                glosses.extend(sense.get("glosses") or [])

            definitions = unique_definitions(glosses)
            if not definitions:
                continue

            index[key] = {
                "term": targets[key],
                "source": "dewiktionary (Kaikki open data)",
                "definitions": definitions,
                "url": "https://kaikki.org/dewiktionary/rawdata.html",
            }
            counters["de_found"] += 1

    counters["de_missing"] = max(0, len(targets) - len(index))
    return index, counters


def build_tr_index(targets: dict[str, str]) -> tuple[dict[str, dict], Counter]:
    index: dict[str, dict] = {}
    counters = Counter()

    with gzip.open(TRWIKTIONARY_PATH, "rt", encoding="utf-8") as fh:
        for line in fh:
            entry = json.loads(line)
            if entry.get("lang_code") != "tr":
                continue

            word = normalize_whitespace(entry.get("word", ""))
            key = normalize_key(word)
            if not word or key not in targets or key in index:
                continue

            glosses = []
            for sense in entry.get("senses") or []:
                glosses.extend(sense.get("glosses") or [])

            definitions = unique_definitions(glosses)
            if not definitions:
                continue

            index[key] = {
                "term": targets[key],
                "source": "trwiktionary (Kaikki open data)",
                "definitions": definitions,
                "url": "https://kaikki.org/trwiktionary/rawdata.html",
            }
            counters["tr_found"] += 1

    counters["tr_missing"] = max(0, len(targets) - len(index))
    return index, counters


def lookup_german_offline(index: dict[str, dict], term: str) -> dict | None:
    candidates = [
        normalize_key(term),
        normalize_key(strip_article(term)),
        normalize_key(term.replace("-", " ")),
    ]
    seen = set()
    for key in candidates:
        if not key or key in seen:
            continue
        seen.add(key)
        if key in index:
            return index[key]
    return None


def lookup_turkish_offline(index: dict[str, dict], term: str) -> dict | None:
    for candidate in turkish_candidates(term):
        key = normalize_key(candidate)
        if key in index:
            return index[key]
    return None


def build_availability(
    german_targets: dict[str, str],
    turkish_targets: dict[str, str],
    de_index: dict[str, dict],
    tr_index: dict[str, dict],
) -> dict[str, dict[str, bool]]:
    availability = {"de": {}, "tr": {}}

    for term in german_targets.values():
        availability["de"][term] = lookup_german_offline(de_index, term) is not None

    for term in turkish_targets.values():
        availability["tr"][term] = lookup_turkish_offline(tr_index, term) is not None

    return availability


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    german_targets, turkish_targets = load_targets()
    de_index, de_counters = build_de_index(german_targets)
    tr_index, tr_counters = build_tr_index(turkish_targets)
    availability = build_availability(german_targets, turkish_targets, de_index, tr_index)

    write_json(DEFINITION_INDEX_DE_PATH, de_index)
    write_json(DEFINITION_INDEX_TR_PATH, tr_index)
    write_json(DEFINITION_AVAILABILITY_PATH, availability)

    summary = {
        "german_targets": len(german_targets),
        "turkish_targets": len(turkish_targets),
        "de_index_size": len(de_index),
        "tr_index_size": len(tr_index),
        "de_available": sum(1 for value in availability["de"].values() if value),
        "tr_available": sum(1 for value in availability["tr"].values() if value),
        "counters": de_counters + tr_counters,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
