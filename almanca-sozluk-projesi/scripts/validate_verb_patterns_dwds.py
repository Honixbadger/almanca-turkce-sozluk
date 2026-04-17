#!/usr/bin/env python3
"""Validate verb patterns and valency hints against DWDS pages."""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from enrich_verb_usage import VERB_POS, collect_known_forms, compact, normalize


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "output" / "dwds_validation_cache"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "dwds_verb_validation_report.json"

TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß-]+")
PREPOSITIONS = {
    "an", "auf", "aus", "bei", "fuer", "für", "gegen", "in", "mit", "nach",
    "ueber", "über", "um", "unter", "von", "vor", "zu",
}
REFLEXIVE_PRONOUNS = {"mich", "dich", "sich", "uns", "euch"}
DATIV_HINTS = {"mir", "dir", "ihm", "ihr", "ihnen", "uns", "euch", "dem", "der"}
AKKUSATIV_HINTS = {"mich", "dich", "ihn", "sie", "es", "uns", "euch", "den", "die", "das"}
GENITIV_HINTS = {"dessen", "deren", "jemandes", "eines"}
CASE_HINTS = {
    "Dativ": DATIV_HINTS,
    "Akkusativ": AKKUSATIV_HINTS,
    "Genitiv": GENITIV_HINTS,
}


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().casefold()


def tokenize(text: str) -> list[str]:
    return [normalize_text(token) for token in TOKEN_RE.findall(str(text or "")) if normalize_text(token)]


def strip_html_markup(text: str) -> str:
    cleaned = re.sub(r"<script.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<style.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return " ".join(html.unescape(cleaned).split())


def fetch_dwds_html(lemma: str, cache_dir: Path, refresh: bool, delay: float) -> tuple[str, bool]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{urllib.parse.quote(lemma, safe='')}.html"
    if cache_path.exists() and not refresh:
        return cache_path.read_text(encoding="utf-8", errors="replace"), True
    url = f"https://www.dwds.de/wb/{urllib.parse.quote(lemma, safe='')}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8", errors="replace")
    cache_path.write_text(payload, encoding="utf-8")
    if delay > 0:
        time.sleep(delay)
    return payload, False


def find_form_positions(tokens: list[str], forms: set[str]) -> list[int]:
    return [idx for idx, token in enumerate(tokens) if token in forms]


def has_reflexive_signal(tokens: list[str], positions: list[int]) -> bool:
    for pos in positions:
        window = tokens[max(0, pos - 3): min(len(tokens), pos + 4)]
        if any(token in REFLEXIVE_PRONOUNS for token in window):
            return True
    return False


def has_case_signal(tokens: list[str], positions: list[int], case_name: str) -> bool:
    hints = CASE_HINTS.get(case_name, set())
    if not hints:
        return False
    for pos in positions:
        window = tokens[max(0, pos - 4): min(len(tokens), pos + 5)]
        if any(token in hints for token in window):
            return True
    return False


def has_prep_signal(tokens: list[str], positions: list[int], prep: str) -> bool:
    target = normalize_text(prep)
    for pos in positions:
        window = tokens[pos + 1: min(len(tokens), pos + 5)]
        if target in window:
            return True
    return False


def classify_candidate(candidate: str, lemma: str) -> dict:
    text = compact(candidate)
    tokens = tokenize(text)
    reflexive = bool(tokens and tokens[0] == "sich")
    case_name = ""
    prep = ""
    if "+" in text:
        left, right = [compact(part) for part in text.split("+", 1)]
        right_title = right.capitalize()
        if right_title in CASE_HINTS:
            case_name = right_title
        left_tokens = tokenize(left)
        core = [token for token in left_tokens if token not in {"sich", normalize_text(lemma)}]
        if core:
            maybe_prep = core[-1]
            if maybe_prep in PREPOSITIONS:
                prep = maybe_prep
    elif len(tokens) >= 2:
        maybe_prep = tokens[-1]
        if maybe_prep in PREPOSITIONS:
            prep = maybe_prep
    return {
        "text": text,
        "normalized": normalize_text(text),
        "reflexive": reflexive,
        "prep": prep,
        "case": case_name,
    }


def validate_candidate(candidate: str, lemma: str, tokens: list[str], forms: set[str], visible_text: str) -> dict:
    parsed = classify_candidate(candidate, lemma)
    positions = find_form_positions(tokens, forms)
    supported_by = []
    visible_norm = normalize_text(visible_text)

    if parsed["normalized"] and parsed["normalized"] in visible_norm:
        supported_by.append("exact-text")
    if positions:
        if parsed["reflexive"] and has_reflexive_signal(tokens, positions):
            supported_by.append("reflexive-window")
        if parsed["prep"] and has_prep_signal(tokens, positions, parsed["prep"]):
            supported_by.append(f"prep:{parsed['prep']}")
        if parsed["case"] and has_case_signal(tokens, positions, parsed["case"]):
            supported_by.append(f"case:{parsed['case']}")
        if not parsed["prep"] and not parsed["case"] and not parsed["reflexive"]:
            supported_by.append("lemma-page")

    return {
        "candidate": candidate,
        "supported": bool(supported_by),
        "signals": supported_by,
    }


def gather_dwds_suggestions(tokens: list[str], forms: set[str], lemma: str) -> dict[str, int]:
    suggestions: Counter[str] = Counter()
    positions = find_form_positions(tokens, forms)
    for pos in positions:
        prev_window = tokens[max(0, pos - 3): pos]
        next_window = tokens[pos + 1: min(len(tokens), pos + 5)]
        full_window = tokens[max(0, pos - 4): min(len(tokens), pos + 5)]
        if any(token in REFLEXIVE_PRONOUNS for token in prev_window):
            suggestions[f"sich {lemma}"] += 1
        for prep in PREPOSITIONS:
            if prep in next_window:
                suggestions[f"{lemma} {prep}"] += 1
        for case_name, hints in CASE_HINTS.items():
            if any(token in hints for token in full_window):
                suggestions[f"{lemma} + {case_name}"] += 1
    return dict(suggestions)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate verb usage hints against DWDS pages.")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--include-supported", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.dict_path.read_text(encoding="utf-8"))
    verbs = [
        row for row in data
        if compact(row.get("tur") or "").casefold() == VERB_POS
        and (
            any(isinstance(item, dict) and compact(item.get("kalip") or "") for item in (row.get("fiil_kaliplari") or []))
            or any(compact(item) for item in (row.get("valenz") or []))
        )
    ]
    if args.limit > 0:
        verbs = verbs[: args.limit]

    counters = Counter()
    flagged: list[dict] = []
    supported_rows: list[dict] = []

    for row in verbs:
        lemma = compact(row.get("almanca") or "")
        if not lemma:
            continue
        html_text, used_cache = fetch_dwds_html(lemma, args.cache_dir, args.refresh_cache, args.delay)
        counters["pages_cached" if used_cache else "pages_fetched"] += 1
        visible = strip_html_markup(html_text)
        tokens = tokenize(visible)
        forms = collect_known_forms(row)
        forms.add(normalize_text(lemma))
        positions = find_form_positions(tokens, forms)
        if "wortprofil" in normalize_text(visible):
            counters["pages_with_wortprofil"] += 1

        valenz_results = [
            validate_candidate(item, lemma, tokens, forms, visible)
            for item in (row.get("valenz") or [])
            if compact(item)
        ]
        pattern_candidates = [
            compact(item.get("kalip") or "")
            for item in (row.get("fiil_kaliplari") or [])
            if isinstance(item, dict) and compact(item.get("kalip") or "")
        ]
        pattern_results = [
            validate_candidate(item, lemma, tokens, forms, visible)
            for item in pattern_candidates
        ]

        counters["verbs_checked"] += 1
        counters["verbs_with_form_hits"] += int(bool(positions))
        counters["valenz_total"] += len(valenz_results)
        counters["patterns_total"] += len(pattern_results)
        counters["valenz_supported"] += sum(1 for item in valenz_results if item["supported"])
        counters["patterns_supported"] += sum(1 for item in pattern_results if item["supported"])

        unsupported_valenz = [item for item in valenz_results if not item["supported"]]
        unsupported_patterns = [item for item in pattern_results if not item["supported"]]
        supported_valenz = [item for item in valenz_results if item["supported"]]
        supported_patterns = [item for item in pattern_results if item["supported"]]

        row_payload = {
            "verb": lemma,
            "dwds_url": f"https://www.dwds.de/wb/{urllib.parse.quote(lemma, safe='')}",
            "supported_valenz": supported_valenz,
            "unsupported_valenz": unsupported_valenz,
            "supported_patterns": supported_patterns,
            "unsupported_patterns": unsupported_patterns,
            "dwds_suggestions": gather_dwds_suggestions(tokens, forms, lemma),
        }
        if unsupported_valenz or unsupported_patterns:
            flagged.append(row_payload)
        elif args.include_supported and (supported_valenz or supported_patterns):
            supported_rows.append(row_payload)

    report = {
        "dict_path": str(args.dict_path),
        "cache_dir": str(args.cache_dir),
        "counters": dict(counters),
        "flagged": flagged[:200],
        "supported_sample": supported_rows[:80],
    }
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
