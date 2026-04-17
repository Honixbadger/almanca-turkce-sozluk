#!/usr/bin/env python3
"""Report likely noun<->verb derivational pairs using deWiktionary and DWDS.

This script is intentionally report-only:
- it does not modify dictionary entries
- it only surfaces conservative candidate pairs for user review

Primary source:
- local deWiktionary/Kaikki dump (`data/raw/downloads/dewiktionary.gz`)

Validation source:
- DWDS lemma pages
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from enrich_verb_usage import is_true_verb_entry
from validate_verb_patterns_dwds import fetch_dwds_html, strip_html_markup


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_DUMP_PATH = PROJECT_ROOT / "data" / "raw" / "downloads" / "dewiktionary.gz"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "output" / "dwds_derivation_cache"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "derivational_pairs_report.json"

NOUN_POS = "isim"
VERB_POS = "fiil"
TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß-]+")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().casefold()


def titlecase_token(text: str) -> str:
    value = compact(text)
    if not value:
        return ""
    return value[:1].upper() + value[1:]


def tokenize(text: str) -> list[str]:
    return [normalize(token) for token in TOKEN_RE.findall(str(text or "")) if normalize(token)]


def extract_link_words(payload: object) -> list[str]:
    if not payload:
        return []
    values: list[str] = []
    for item in payload:
        if isinstance(item, dict):
            word = compact(item.get("word") or "")
        else:
            word = compact(item)
        if word:
            values.append(word)
    return values


def build_dump_indexes(dump_path: Path) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]], dict[str, set[str]]]:
    """Return:
    - pos_index[word] -> {"noun","verb",...}
    - noun_to_verbs[word] -> {verb lemma}
    - noun_from_verbs[word] -> {verb lemma}
    - dump_caseforms[word] -> surface forms seen in dump
    """
    pos_index: dict[str, set[str]] = defaultdict(set)
    noun_to_verbs: dict[str, set[str]] = defaultdict(set)
    noun_from_verbs: dict[str, set[str]] = defaultdict(set)
    dump_caseforms: dict[str, set[str]] = defaultdict(set)

    records: list[tuple[str, str, list[str], list[str]]] = []
    with gzip.open(dump_path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("lang_code") != "de":
                continue
            word = compact(obj.get("word") or "")
            pos = compact(obj.get("pos") or "").casefold()
            if not word or not pos:
                continue
            if pos == "verb" and not is_true_verb_entry(obj):
                continue
            key = normalize(word)
            pos_index[key].add(pos)
            dump_caseforms[key].add(word)
            derived_words = extract_link_words(obj.get("derived") or [])
            related_words = extract_link_words(obj.get("related") or [])
            records.append((word, pos, derived_words, related_words))

    for word, pos, derived_words, related_words in records:
        word_key = normalize(word)
        links = derived_words + related_words
        if pos == "noun":
            for linked in links:
                linked_key = normalize(linked)
                if "verb" in pos_index.get(linked_key, set()):
                    noun_to_verbs[word_key].add(compact(linked))
        elif pos == "verb":
            for linked in links:
                linked_key = normalize(linked)
                if "noun" in pos_index.get(linked_key, set()):
                    noun_from_verbs[linked_key].add(compact(word))

    return dict(pos_index), dict(noun_to_verbs), dict(noun_from_verbs), dict(dump_caseforms)


def validate_dwds_lemma(lemma: str, cache_dir: Path, refresh: bool, delay: float) -> dict:
    html_text, used_cache = fetch_dwds_html(lemma, cache_dir, refresh, delay)
    visible = strip_html_markup(html_text)
    visible_norm = normalize(visible)
    lemma_norm = normalize(lemma)
    miss_markers = (
        "kein eintrag",
        "keine treffer",
        "wurde nicht gefunden",
        "es tut uns leid",
    )
    signals: list[str] = []
    if lemma_norm and lemma_norm in visible_norm:
        signals.append("lemma-text")
    if "wortprofil" in visible_norm:
        signals.append("wortprofil")
    supported = bool(signals) and not any(marker in visible_norm for marker in miss_markers)
    return {
        "supported": supported,
        "signals": signals,
        "used_cache": used_cache,
        "url": f"https://www.dwds.de/wb/{lemma}",
    }


def build_report_rows(
    data: list[dict],
    pos_index: dict[str, set[str]],
    noun_to_verbs: dict[str, set[str]],
    noun_from_verbs: dict[str, set[str]],
    dump_caseforms: dict[str, set[str]],
    *,
    lemma_filter: str,
    missing_only: bool,
    limit: int,
    cache_dir: Path,
    refresh_cache: bool,
    delay: float,
) -> tuple[list[dict], Counter]:
    dict_index: dict[str, list[dict]] = defaultdict(list)
    for row in data:
        dict_index[normalize(row.get("almanca") or "")].append(row)

    nouns = [
        row for row in data
        if compact(row.get("tur") or "").casefold() == NOUN_POS
        and compact(row.get("almanca") or "")
        and len(tokenize(row.get("almanca") or "")) == 1
    ]
    if lemma_filter:
        target = normalize(lemma_filter)
        nouns = [row for row in nouns if normalize(row.get("almanca") or "") == target]

    counters: Counter = Counter()
    rows: list[dict] = []
    dwds_cache: dict[str, dict] = {}

    for row in nouns:
        noun = compact(row.get("almanca") or "")
        article = compact(row.get("artikel") or "")
        noun_key = normalize(noun)
        counters["nouns_checked"] += 1

        candidate_sources: dict[str, list[str]] = defaultdict(list)
        lower_candidate = compact(noun.lower())
        lower_key = normalize(lower_candidate)
        if (
            article.casefold() == "das"
            and lower_candidate != noun
            and titlecase_token(lower_candidate) == noun
            and "verb" in pos_index.get(lower_key, set())
        ):
            candidate_sources[lower_candidate].append("exact-lowercase-verb-in-dewiktionary")

        for linked in noun_to_verbs.get(noun_key, set()):
            candidate_sources[compact(linked)].append("noun-derived-or-related-links-to-verb")
        for linked in noun_from_verbs.get(noun_key, set()):
            candidate_sources[compact(linked)].append("verb-derived-or-related-links-back-to-noun")

        if not candidate_sources:
            continue

        counters["nouns_with_candidates"] += 1
        noun_dump_supported = "noun" in pos_index.get(noun_key, set())
        noun_dump_forms = sorted(dump_caseforms.get(noun_key, set()))

        for candidate, reasons in sorted(candidate_sources.items()):
            candidate_key = normalize(candidate)
            verb_in_dict = any(compact(item.get("tur") or "").casefold() == VERB_POS for item in dict_index.get(candidate_key, []))
            if missing_only and verb_in_dict:
                continue
            if limit > 0 and len(rows) >= limit:
                return rows, counters

            if candidate_key not in dwds_cache:
                dwds_cache[candidate_key] = validate_dwds_lemma(candidate, cache_dir, refresh_cache, delay)
            dwds_result = dwds_cache[candidate_key]
            counters["dwds_pages_cached" if dwds_result["used_cache"] else "dwds_pages_fetched"] += 1

            verb_dump_supported = "verb" in pos_index.get(candidate_key, set())
            status = "review_missing_verb" if not verb_in_dict else "review_existing_pair"
            if noun_dump_supported and verb_dump_supported and dwds_result["supported"] and not verb_in_dict:
                status = "high_confidence_missing_verb"

            rows.append(
                {
                    "noun": noun,
                    "article": article,
                    "noun_turkce": compact(row.get("turkce") or ""),
                    "noun_exists_in_dictionary": True,
                    "verb_candidate": candidate,
                    "verb_exists_in_dictionary": verb_in_dict,
                    "dewiktionary_support": {
                        "noun_entry": noun_dump_supported,
                        "noun_forms": noun_dump_forms,
                        "verb_entry": verb_dump_supported,
                        "verb_forms": sorted(dump_caseforms.get(candidate_key, set())),
                        "signals": sorted(set(reasons)),
                    },
                    "dwds_support": {
                        "supported": dwds_result["supported"],
                        "signals": dwds_result["signals"],
                        "url": dwds_result["url"],
                    },
                    "status": status,
                }
            )
            counters["pairs_reported"] += 1
            counters["pairs_missing_verb"] += int(not verb_in_dict)
            counters["pairs_supported_by_dwds"] += int(dwds_result["supported"])
            counters["pairs_supported_by_dump"] += int(noun_dump_supported and verb_dump_supported)

    return rows, counters


def main() -> int:
    parser = argparse.ArgumentParser(description="Report likely noun<->verb derivational pairs for review.")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--dump-path", type=Path, default=DEFAULT_DUMP_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--lemma", default="", help="Only report candidates for this noun lemma.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--missing-only", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--delay", type=float, default=0.35)
    args = parser.parse_args()

    data = json.loads(args.dict_path.read_text(encoding="utf-8"))
    pos_index, noun_to_verbs, noun_from_verbs, dump_caseforms = build_dump_indexes(args.dump_path)
    rows, counters = build_report_rows(
        data,
        pos_index,
        noun_to_verbs,
        noun_from_verbs,
        dump_caseforms,
        lemma_filter=args.lemma,
        missing_only=args.missing_only,
        limit=args.limit,
        cache_dir=args.cache_dir,
        refresh_cache=args.refresh_cache,
        delay=args.delay,
    )

    rows.sort(
        key=lambda item: (
            item["status"] != "high_confidence_missing_verb",
            item["status"] != "review_missing_verb",
            not item["dwds_support"]["supported"],
            item["noun"].casefold(),
            item["verb_candidate"].casefold(),
        )
    )

    report = {
        "dict_path": str(args.dict_path),
        "dump_path": str(args.dump_path),
        "cache_dir": str(args.cache_dir),
        "counters": dict(counters),
        "rows": rows,
    }
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
