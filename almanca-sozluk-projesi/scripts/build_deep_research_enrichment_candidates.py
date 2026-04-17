#!/usr/bin/env python3
"""Build non-destructive deep-research enrichment candidates for dictionary review.

Outputs:
- lemma-grouped JSON for human review
- flat JSONL/CSV-friendly rows
- summary report

This script does not modify dictionary.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from corpus_quality_utils import (
    CORPUS_OUTPUT_DIR,
    DEFAULT_DICT_PATH,
    compact_space,
    load_json,
    normalize_text,
    save_json,
)
from enrich_verb_usage import collect_known_forms


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_USAGE_PATH = CORPUS_OUTPUT_DIR / "corpus_usage_index.json"
DEFAULT_CLUSTERS_PATH = CORPUS_OUTPUT_DIR / "corpus_sense_clusters.json"
DEFAULT_EXAMPLES_PATH = CORPUS_OUTPUT_DIR / "corpus_ranked_examples.json"
DEFAULT_VALENCY_PATH = CORPUS_OUTPUT_DIR / "corpus_verb_valency.json"
DEFAULT_DWDS_REPORT_PATH = PROJECT_ROOT / "output" / "dwds_verb_validation_report_live_20260331.json"

DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "output" / "deep_research_enrichment_candidates.json"
DEFAULT_OUTPUT_JSONL = PROJECT_ROOT / "output" / "deep_research_enrichment_candidates.jsonl"
DEFAULT_OUTPUT_CSV = PROJECT_ROOT / "output" / "deep_research_enrichment_candidates.csv"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "deep_research_enrichment_report.json"

GENERIC_TRANSLATIONS = {
    "etmek",
    "yapmak",
    "gitmek",
    "gelmek",
    "olmak",
    "durum",
    "olgu",
    "fenomen",
}
DOMAIN_HINTS = {
    "teknik": {"motor", "maschine", "technik", "gerät", "druck", "signal", "system", "elektr"},
    "hukuk": {"gesetz", "vertrag", "gericht", "klage", "recht", "anwalt"},
    "ekonomi": {"geld", "markt", "preis", "produktion", "bank", "währung", "steuer"},
    "askeri": {"militär", "krieg", "soldat", "waffe", "armee"},
    "tıp": {"arzt", "medizin", "krank", "patient", "therapie", "diagnose"},
    "günlük": {"haus", "essen", "familie", "schule", "kind", "zimmer"},
}
REGISTER_HINTS = {
    "argo": {"slang", "derb", "vulgär", "umgangssprachlich"},
    "resmi": {"amtlich", "förmlich", "offiziell"},
    "edebi": {"literarisch", "poetisch"},
}
TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß-]+")


def normalize_list(items) -> list[str]:
    result: list[str] = []
    for item in items or []:
        if isinstance(item, dict):
            text = compact_space(item.get("kalip") or item.get("valenz") or item.get("text") or "")
        else:
            text = compact_space(item)
        if text:
            result.append(text)
    return result


def existing_example_count(record: dict) -> int:
    count = 0
    if compact_space(record.get("ornek_almanca") or ""):
        count += 1
    for item in record.get("ornekler") or []:
        if isinstance(item, dict) and compact_space(item.get("almanca") or ""):
            count += 1
    return count


def infer_domain(keywords: list[str], examples: list[dict]) -> str:
    bag = set(normalize_text(word) for word in keywords)
    for sample in examples or []:
        bag.update(normalize_text(token) for token in compact_space(sample.get("sentence") or "").split())
    best_label = ""
    best_score = 0
    for label, hints in DOMAIN_HINTS.items():
        score = sum(1 for token in bag for hint in hints if hint in token)
        if score > best_score:
            best_label = label
            best_score = score
    return best_label if best_score >= 2 else ""


def infer_register(record: dict, keywords: list[str]) -> str:
    haystack = " ".join(
        [
            compact_space(record.get("aciklama_turkce") or ""),
            compact_space(record.get("turkce") or ""),
            " ".join(keywords or []),
        ]
    )
    haystack_norm = normalize_text(haystack)
    for label, hints in REGISTER_HINTS.items():
        if any(normalize_text(hint) in haystack_norm for hint in hints):
            return label
    return ""


def detect_missing_fields(record: dict) -> list[str]:
    missing: list[str] = []
    if not (record.get("baglamlar") or []):
        missing.append("usage_label")
    if existing_example_count(record) == 0:
        missing.append("example_sentence")
    if not normalize_list(record.get("fiil_kaliplari") or []):
        missing.append("collocation")
        missing.append("idiomatic_usage")
    if not normalize_list(record.get("valenz") or []):
        missing.append("usage_pattern")
    if not (record.get("kategoriler") or []):
        missing.append("register_or_domain")
    if compact_space(record.get("tur") or "").casefold() == "fiil":
        if not compact_space(record.get("partizip2") or ""):
            missing.append("partizip2")
        if not compact_space(record.get("prateritum") or ""):
            missing.append("prateritum")
        if not compact_space(record.get("perfekt_yardimci") or ""):
            missing.append("perfekt_auxiliary")
        if not (record.get("cekimler") or {}):
            missing.append("conjugation")
    return missing


def build_dwds_flag_map(dwds_report: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for item in dwds_report.get("flagged") or []:
        lemma = normalize_text(item.get("verb") or "")
        if lemma:
            result[lemma] = item
    return result


def sentence_supports_record(record: dict, sentence: str) -> bool:
    pos = compact_space(record.get("tur") or "").casefold()
    if pos != "fiil":
        return True
    known_forms = {normalize_text(item) for item in collect_known_forms(record)}
    lemma = normalize_text(record.get("almanca") or "")
    if lemma:
        known_forms.add(lemma)
    raw_tokens = TOKEN_RE.findall(compact_space(sentence))
    for idx, raw in enumerate(raw_tokens):
        norm = normalize_text(raw)
        if norm not in known_forms:
            continue
        # Mid-sentence uppercase tokens are usually noun/adjective homographs, not verb uses.
        if idx > 0 and raw[:1].isupper():
            continue
        return True
    return False


def filtered_top_examples(record: dict, examples_row: dict | None) -> list[dict]:
    candidates = []
    for item in (examples_row or {}).get("examples") or []:
        sentence = compact_space(item.get("sentence") or "")
        if not sentence:
            continue
        if not sentence_supports_record(record, sentence):
            continue
        candidates.append(item)
    return candidates


def filtered_clusters(record: dict, cluster_row: dict | None) -> list[dict]:
    result: list[dict] = []
    for cluster in (cluster_row or {}).get("clusters") or []:
        samples = [
            item for item in (cluster.get("samples") or [])
            if sentence_supports_record(record, compact_space(item.get("sentence") or ""))
        ]
        cluster_sources = cluster.get("sources") or {}
        if not samples:
            continue
        sample_count = int(cluster.get("sample_count") or 0)
        source_count = len([name for name, count in cluster_sources.items() if int(count or 0) > 0])
        if sample_count < 2:
            continue
        if sample_count < 3 and source_count < 2:
            continue
        cloned = dict(cluster)
        cloned["samples"] = samples
        result.append(cloned)
    return result


def confidence_score(source_types: set[str], conflicts: list[str], support_count: int) -> float:
    score = 0.35
    if "dewiktionary" in source_types:
        score += 0.22
    if "tatoeba" in source_types:
        score += 0.14
    if "corpus-derived" in source_types:
        score += 0.12
    if "dwds-validation" in source_types:
        score += 0.18
    if len(source_types) >= 2:
        score += 0.08
    if support_count >= 2:
        score += 0.05
    score -= min(0.30, len(conflicts) * 0.12)
    return round(max(0.15, min(0.97, score)), 2)


def build_flat_rows_for_record(
    record: dict,
    usage_row: dict,
    cluster_row: dict | None,
    valency_row: dict | None,
    examples_row: dict | None,
    dwds_flag: dict | None,
) -> tuple[list[dict], list[str]]:
    lemma = compact_space(record.get("almanca") or "")
    pos = compact_space(record.get("tur") or "")
    missing_fields = detect_missing_fields(record)
    rows: list[dict] = []
    conflicts_summary: list[str] = []

    source_counts = usage_row.get("source_counts") or {}
    top_examples = filtered_top_examples(record, examples_row)
    top_keywords = []
    filtered_cluster_rows = filtered_clusters(record, cluster_row)
    if filtered_cluster_rows:
        top_keywords = list((filtered_cluster_rows[0] or {}).get("keywords") or [])
    domain = infer_domain(top_keywords, top_examples)
    register = infer_register(record, top_keywords)
    existing_senses = record.get("anlamlar") or []
    cluster_count = len(filtered_cluster_rows)
    if cluster_count >= 2 and len(existing_senses) < cluster_count:
        conflicts_summary.append("polysemy_may_be_collapsed")
    if compact_space(record.get("turkce") or "").casefold() in GENERIC_TRANSLATIONS:
        conflicts_summary.append("generic_top_translation")
    if dwds_flag and ((dwds_flag.get("unsupported_patterns") or []) or (dwds_flag.get("unsupported_valenz") or [])):
        conflicts_summary.append("dwds_conflict_detected")

    source_types = set()
    for source_name, count in source_counts.items():
        if count:
            if source_name in {"dewiktionary", "tatoeba", "html"}:
                source_types.add("corpus-derived" if source_name == "html" else source_name)

    if filtered_cluster_rows:
        for cluster in filtered_cluster_rows[:2]:
            cluster_keywords = [compact_space(item) for item in (cluster.get("keywords") or [])[:6] if compact_space(item)]
            cluster_sources = list((cluster.get("sources") or {}).keys())
            row_sources = set(source_types)
            row_sources.update(cluster_sources)
            reasons = [
                f"Cluster {cluster_keywords[:4]} baglaminda ayri kullanim sinyali goruldu.",
                f"Kaynak dagilimi: {cluster.get('sources') or {}}",
            ]
            conflicts = list(conflicts_summary)
            confidence = confidence_score(row_sources, conflicts, len(cluster_sources))
            rows.append(
                {
                    "lemma": lemma,
                    "pos": pos,
                    "missing_fields": missing_fields,
                    "candidate_sense": "; ".join(cluster_keywords),
                    "pattern": "",
                    "example": compact_space(((cluster.get("samples") or [{}])[0]).get("sentence") or ""),
                    "register": register,
                    "domain": domain,
                    "source_type": sorted(row_sources),
                    "confidence": confidence,
                    "why": reasons,
                    "source_basis": {
                        "cluster_sources": cluster.get("sources") or {},
                        "sample_count": int(cluster.get("sample_count") or 0),
                    },
                    "conflicts_with_existing": conflicts,
                    "review_required": True,
                    "human_review_reason": "sense_candidate",
                }
            )

    if valency_row:
        existing_valenz = set(normalize_text(item) for item in normalize_list(record.get("valenz") or []))
        existing_patterns = set(normalize_text(item) for item in normalize_list(record.get("fiil_kaliplari") or []))
        for candidate in (valency_row.get("valenz") or [])[:4]:
            val = compact_space(candidate.get("valenz") or "")
            if not val:
                continue
            conflicts = list(conflicts_summary)
            if normalize_text(val) in existing_valenz:
                continue
            if dwds_flag and any(normalize_text(val) == normalize_text(item.get("candidate") or "") for item in (dwds_flag.get("unsupported_valenz") or [])):
                conflicts.append("candidate_conflicts_with_dwds")
            row_sources = set(source_types) | {"corpus-derived"}
            if dwds_flag:
                row_sources.add("dwds-validation")
            rows.append(
                {
                    "lemma": lemma,
                    "pos": pos,
                    "missing_fields": missing_fields,
                    "candidate_sense": "",
                    "pattern": val,
                    "example": compact_space(((top_examples or [{}])[0]).get("sentence") or ""),
                    "register": register,
                    "domain": domain,
                    "source_type": sorted(row_sources),
                    "confidence": confidence_score(row_sources, conflicts, 2 if dwds_flag else 1),
                    "why": [
                        "Korpus kullanimindan valenz adayi cikti.",
                        f"Frekans: {int(candidate.get('count') or 0)}",
                    ],
                    "source_basis": {
                        "corpus_count": int(candidate.get("count") or 0),
                        "dwds_supported": not any("dwds" in item for item in conflicts),
                    },
                    "conflicts_with_existing": conflicts,
                    "review_required": True,
                    "human_review_reason": "valency_candidate",
                }
            )
        for candidate in (valency_row.get("fiil_kaliplari") or [])[:4]:
            kalip = compact_space(candidate.get("kalip") or "")
            if not kalip or normalize_text(kalip) in existing_patterns:
                continue
            conflicts = list(conflicts_summary)
            if dwds_flag and any(normalize_text(kalip) == normalize_text(item.get("candidate") or "") for item in (dwds_flag.get("unsupported_patterns") or [])):
                conflicts.append("candidate_conflicts_with_dwds")
            row_sources = set(source_types) | {"corpus-derived"}
            if dwds_flag:
                row_sources.add("dwds-validation")
            rows.append(
                {
                    "lemma": lemma,
                    "pos": pos,
                    "missing_fields": missing_fields,
                    "candidate_sense": "",
                    "pattern": kalip,
                    "example": compact_space(((top_examples or [{}])[0]).get("sentence") or ""),
                    "register": register,
                    "domain": domain,
                    "source_type": sorted(row_sources),
                    "confidence": confidence_score(row_sources, conflicts, 2 if dwds_flag else 1),
                    "why": [
                        "Korpus kullanimindan kollokasyon/kalip adayi cikti.",
                        f"Frekans: {int(candidate.get('count') or 0)}",
                    ],
                    "source_basis": {
                        "corpus_count": int(candidate.get("count") or 0),
                    },
                    "conflicts_with_existing": conflicts,
                    "review_required": True,
                    "human_review_reason": "pattern_candidate",
                }
            )

    if examples_row:
        existing_examples = {
            normalize_text(compact_space(item.get("almanca") or ""))
            for item in (record.get("ornekler") or [])
            if isinstance(item, dict)
        }
        top_level = normalize_text(record.get("ornek_almanca") or "")
        if top_level:
            existing_examples.add(top_level)
        for example in top_examples[:3]:
            sentence = compact_space(example.get("sentence") or "")
            if not sentence or normalize_text(sentence) in existing_examples:
                continue
            row_sources = set(source_types)
            row_sources.add(example.get("source") or "corpus-derived")
            rows.append(
                {
                    "lemma": lemma,
                    "pos": pos,
                    "missing_fields": missing_fields,
                    "candidate_sense": "",
                    "pattern": "",
                    "example": sentence,
                    "register": register,
                    "domain": domain,
                    "source_type": sorted(row_sources),
                    "confidence": confidence_score(row_sources, conflicts_summary, 1),
                    "why": [
                        "Yuksek puanli ornek cumle bulundu.",
                        f"Kaynak: {compact_space(example.get('source') or 'corpus-derived')}",
                    ],
                    "source_basis": {
                        "example_score": float(example.get("score") or 0.0),
                    },
                    "conflicts_with_existing": list(conflicts_summary),
                    "review_required": True,
                    "human_review_reason": "example_candidate",
                }
            )

    return rows, conflicts_summary


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "lemma",
        "pos",
        "missing_fields",
        "candidate_sense",
        "pattern",
        "example",
        "register",
        "domain",
        "source_type",
        "confidence",
        "why",
        "source_basis",
        "conflicts_with_existing",
        "review_required",
        "human_review_reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            normalized = dict(row)
            for key in ("missing_fields", "source_type", "why", "source_basis", "conflicts_with_existing"):
                normalized[key] = json.dumps(normalized.get(key, []), ensure_ascii=False)
            writer.writerow(normalized)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build non-destructive deep-research enrichment candidates.")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--usage-path", type=Path, default=DEFAULT_USAGE_PATH)
    parser.add_argument("--clusters-path", type=Path, default=DEFAULT_CLUSTERS_PATH)
    parser.add_argument("--examples-path", type=Path, default=DEFAULT_EXAMPLES_PATH)
    parser.add_argument("--valency-path", type=Path, default=DEFAULT_VALENCY_PATH)
    parser.add_argument("--dwds-report-path", type=Path, default=DEFAULT_DWDS_REPORT_PATH)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-jsonl", type=Path, default=DEFAULT_OUTPUT_JSONL)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--pos", default="fiil", help="Only process this part of speech (default: fiil). Use * for all.")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    dictionary = load_json(args.dict_path, [])
    usage_index = load_json(args.usage_path, {})
    clusters = load_json(args.clusters_path, {})
    examples = load_json(args.examples_path, {})
    valency = load_json(args.valency_path, {})
    dwds_report = load_json(args.dwds_report_path, {})
    dwds_flags = build_dwds_flag_map(dwds_report if isinstance(dwds_report, dict) else {})

    grouped: dict[str, dict] = {}
    flat_rows: list[dict] = []
    counters = Counter()

    records = [item for item in dictionary if isinstance(item, dict)]
    if args.pos != "*":
        records = [item for item in records if compact_space(item.get("tur") or "").casefold() == args.pos.casefold()]
    if args.limit > 0:
        records = records[: args.limit]

    for record in records:
        lemma = compact_space(record.get("almanca") or "")
        if not lemma:
            continue
        key = normalize_text(lemma)
        rows, conflicts = build_flat_rows_for_record(
            record,
            usage_index.get(key, {}),
            clusters.get(key),
            valency.get(key),
            examples.get(key),
            dwds_flags.get(key),
        )
        if not rows:
            continue
        missing_fields = detect_missing_fields(record)
        grouped[key] = {
            "lemma": lemma,
            "pos": compact_space(record.get("tur") or ""),
            "current_translation": compact_space(record.get("turkce") or ""),
            "missing_fields": missing_fields,
            "conflicts_with_existing": conflicts,
            "candidates": rows,
        }
        flat_rows.extend(rows)
        counters["lemmas_with_candidates"] += 1
        for field in missing_fields:
            counters[f"missing::{field}"] += 1
        for row in rows:
            counters[f"candidate::{row['human_review_reason']}"] += 1

    save_json(args.output_json, grouped)
    write_jsonl(args.output_jsonl, flat_rows)
    write_csv(args.output_csv, flat_rows)
    save_json(
        args.report_path,
        {
            "pos_filter": args.pos,
            "records_scanned": len(records),
            "lemmas_with_candidates": len(grouped),
            "flat_candidate_rows": len(flat_rows),
            "counters": dict(counters),
            "outputs": {
                "json": str(args.output_json),
                "jsonl": str(args.output_jsonl),
                "csv": str(args.output_csv),
            },
        },
    )
    print(
        json.dumps(
            {
                "records_scanned": len(records),
                "lemmas_with_candidates": len(grouped),
                "flat_candidate_rows": len(flat_rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
