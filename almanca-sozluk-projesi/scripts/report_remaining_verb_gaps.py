#!/usr/bin/env python3
"""Report remaining verb gaps with a focus on missing prateritum and usage data."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from enrich_verb_forms import extract_verb_index, has_real_verb_signal
from enrich_verb_usage import VERB_POS, compact, normalize


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "remaining_verb_gaps_report.json"


def looks_suspicious_lemma(lemma: str) -> bool:
    normalized = normalize(lemma)
    if not normalized or " " in normalized:
        return True
    suspicious_suffixes = (
        "end",
        "ierende",
        "ierenden",
        "iertes",
        "ierte",
        "iert",
    )
    return normalized.endswith(suspicious_suffixes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Report remaining verb gaps in the dictionary.")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--sample-limit", type=int, default=80)
    args = parser.parse_args()

    data = json.loads(args.dict_path.read_text(encoding="utf-8"))
    verbs = [row for row in data if compact(row.get("tur") or "").casefold() == VERB_POS and compact(row.get("almanca") or "")]
    target_keys = {normalize(row.get("almanca") or "") for row in verbs}
    source_index = extract_verb_index(target_keys)

    counters = Counter()
    categories: defaultdict[str, list[dict]] = defaultdict(list)

    for row in verbs:
        lemma = compact(row.get("almanca") or "")
        key = normalize(lemma)
        if not compact(row.get("prateritum") or ""):
            source_info = source_index.get(key)
            if source_info is None:
                category = "no_exact_dewiktionary_match"
            elif source_info.get("prateritum_candidates"):
                category = "extractor_gap"
            elif has_real_verb_signal(source_info):
                category = "source_has_no_past_form"
            else:
                category = "weak_source_signal"
            if looks_suspicious_lemma(lemma):
                category = f"suspicious::{category}"
            categories[category].append(
                {
                    "verb": lemma,
                    "partizip2": compact(row.get("partizip2") or ""),
                    "perfekt_yardimci": compact(row.get("perfekt_yardimci") or ""),
                    "verb_typ": compact(row.get("verb_typ") or ""),
                    "trennbar": row.get("trennbar"),
                    "patterns": len(row.get("fiil_kaliplari") or []),
                    "valenz": len(row.get("valenz") or []),
                    "baglamlar": len(row.get("baglamlar") or []),
                    "translated_examples": sum(
                        1
                        for example in (row.get("ornekler") or [])
                        if isinstance(example, dict) and compact(example.get("almanca") or "") and compact(example.get("turkce") or "")
                    ),
                }
            )
            counters["missing_prateritum"] += 1

        counters["missing_patterns"] += int(not bool(row.get("fiil_kaliplari")))
        counters["missing_valenz"] += int(not bool(row.get("valenz")))
        counters["missing_baglamlar"] += int(not bool(row.get("baglamlar")))
        translated_examples = sum(
            1
            for example in (row.get("ornekler") or [])
            if isinstance(example, dict) and compact(example.get("almanca") or "") and compact(example.get("turkce") or "")
        )
        has_de_example = bool(compact(row.get("ornek_almanca") or "")) or any(
            isinstance(example, dict) and compact(example.get("almanca") or "")
            for example in (row.get("ornekler") or [])
        )
        counters["missing_translated_examples"] += int(has_de_example and translated_examples == 0)

    report = {
        "dict_path": str(args.dict_path),
        "verbs_total": len(verbs),
        "source_index_size": len(source_index),
        "counters": dict(counters),
        "missing_prateritum_categories": {
            category: {
                "count": len(items),
                "sample": items[: args.sample_limit],
            }
            for category, items in sorted(categories.items(), key=lambda item: (-len(item[1]), item[0]))
        },
    }
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
