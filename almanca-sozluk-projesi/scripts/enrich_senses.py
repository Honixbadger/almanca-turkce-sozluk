#!/usr/bin/env python3
"""Build structured sense records (anlamlar) from deWiktionary and existing fields.

This script adds a new `anlamlar` field without removing or rewriting the
existing top-level summary fields (`turkce`, `tanim_almanca`, `aciklama_turkce`).

Each sense may contain:
- sira
- tanim_almanca
- turkce
- aciklama_turkce
- etiketler
- ornekler
- kaynak
- guven
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

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_DUMP_PATH = PROJECT_ROOT / "data" / "raw" / "downloads" / "dewiktionary.gz"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "sense_enrichment_report.json"

TOPIC_MAP = {
    "electrical-engineering": "elektrik-elektronik",
    "technology": "teknik",
    "information-technology": "bilişim",
    "computing": "bilişim",
    "geometry": "geometri",
    "fashion": "moda",
    "medicine": "tıp",
    "military": "askeri",
    "law": "hukuk",
    "chemistry": "kimya",
    "physics": "fizik",
    "music": "müzik",
    "linguistics": "dilbilim",
    "transport": "ulaşım",
    "automotive": "otomotiv",
}

POS_MAP = {
    "isim": {"noun", "name", "proper-noun"},
    "fiil": {"verb"},
    "sıfat": {"adjective"},
    "zarf": {"adverb"},
    "ifade": {"phrase", "proverb", "idiom"},
    "deyim": {"phrase", "proverb", "idiom"},
    "kalıp": {"phrase", "proverb", "idiom"},
}


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().casefold()


def compact_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def split_multi_value(text: str) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for part in re.split(r"\s*;\s*|\s*\|\s*", str(text or "")):
        item = compact_space(part.strip(" ,;/"))
        if not item:
            continue
        key = normalize(item)
        if key in seen:
            continue
        seen.add(key)
        values.append(item)
    return values


def dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = compact_space(value)
        if not item:
            continue
        key = normalize(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def clean_gloss(text: str) -> str:
    value = compact_space(text)
    value = re.sub(r"\[.*?\]", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\{\{[^}]*\}\}", "", value)
    value = re.sub(r"\s+", " ", value).strip(" ,;")
    return compact_space(value)


def clean_translation(text: str) -> str:
    value = compact_space(text)
    value = value.replace("ð", "ğ").replace("ý", "ı")
    value = re.sub(r"\[[^\]]+\]", "", value)
    value = re.sub(r"\s+", " ", value).strip(" ,;")
    return value


def clean_example_text(text: str) -> str:
    value = compact_space(text)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_alt_meanings(note: str) -> list[str]:
    match = re.search(r"Alternatif anlamlar:\s*(.+)", str(note or ""), re.IGNORECASE)
    if not match:
        return []
    return dedupe_strings(re.split(r"\s*\|\s*", match.group(1)))


def parse_explanation_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for part in re.split(r"\s*;\s*", str(text or "")):
        if "->" not in part:
            continue
        left, right = part.rsplit("->", 1)
        left_clean = compact_space(left)
        right_clean = clean_translation(right)
        if left_clean and right_clean:
            pairs.append((normalize(left_clean), right_clean))
    return pairs


def map_topic_label(value: str) -> str:
    token = normalize(value)
    if token in TOPIC_MAP:
        return TOPIC_MAP[token]
    return compact_space(str(value or "").replace("-", " "))


def extract_sense_labels(sense: dict, record_categories: list[str], *, allow_record_categories: bool) -> list[str]:
    labels: list[str] = []
    for topic in sense.get("topics") or []:
        label = map_topic_label(topic)
        if label:
            labels.append(label)
    gloss = compact_space(sense.get("tanim_almanca") or "")
    prefix_match = re.match(r"^([A-ZÄÖÜa-zäöüß][^:]{2,32}):\s*", gloss)
    if prefix_match:
        labels.append(map_topic_label(prefix_match.group(1)))
    if allow_record_categories and not labels:
        labels.extend(compact_space(item) for item in record_categories if compact_space(item))
    return dedupe_strings(labels)


def normalize_pos(value: str) -> str:
    return normalize(value).replace(" ", "-")


def pos_matches(record: dict, pos_value: str) -> bool:
    expected = POS_MAP.get(str(record.get("tur") or "").strip(), set())
    if not expected:
        return True
    return normalize_pos(pos_value) in expected


def extract_translations(obj: dict) -> dict[str, list[str]]:
    by_index: dict[str, list[str]] = defaultdict(list)
    for item in obj.get("translations") or []:
        if item.get("lang_code") != "tr":
            continue
        sense_index = str(item.get("sense_index") or "")
        word = clean_translation(item.get("word") or "")
        if word:
            by_index[sense_index].append(word)
    return {key: dedupe_strings(values) for key, values in by_index.items() if values}


def extract_examples(sense: dict) -> list[dict]:
    examples: list[dict] = []
    for item in sense.get("examples") or []:
        if not isinstance(item, dict):
            continue
        de_text = clean_example_text(item.get("text") or "")
        tr_text = clean_example_text(item.get("translation") or "")
        ref = compact_space(item.get("ref") or "")
        if not de_text:
            continue
        payload = {
            "almanca": de_text,
            "turkce": tr_text,
            "kaynak": "deWiktionary",
            "not": ref,
        }
        examples.append(payload)
    return examples[:3]


def build_dewikt_index(dump_path: Path) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = defaultdict(list)
    seen: dict[str, set[tuple[str, str]]] = defaultdict(set)
    with gzip.open(dump_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("lang_code") != "de":
                continue
            word = compact_space(obj.get("word") or "")
            if not word:
                continue
            tags = {normalize(tag) for tag in (obj.get("tags") or [])}
            if "form-of" in tags:
                continue
            translations = extract_translations(obj)
            for sense in obj.get("senses") or []:
                gloss = clean_gloss((sense.get("glosses") or [""])[0])
                if len(gloss) < 4:
                    continue
                sense_index = str(sense.get("sense_index") or "")
                sense_item = {
                    "sense_index": sense_index,
                    "pos": compact_space(obj.get("pos") or ""),
                    "tanim_almanca": gloss,
                    "turkce_adaylari": translations.get(sense_index, []),
                    "ornekler": extract_examples(sense),
                    "topics": dedupe_strings(
                        [compact_space(topic) for topic in (sense.get("topics") or [])]
                    ),
                }
                dedupe_key = (normalize(sense_item["pos"]), normalize(gloss))
                word_key = normalize(word)
                if dedupe_key in seen[word_key]:
                    continue
                seen[word_key].add(dedupe_key)
                index[word_key].append(sense_item)
    return dict(index)


def collect_record_examples(record: dict) -> list[dict]:
    examples: list[dict] = []
    for item in record.get("ornekler") or []:
        if not isinstance(item, dict):
            continue
        de_text = clean_example_text(item.get("almanca") or "")
        tr_text = clean_example_text(item.get("turkce") or "")
        if not de_text:
            continue
        examples.append(
            {
                "almanca": de_text,
                "turkce": tr_text,
                "kaynak": compact_space(item.get("kaynak") or record.get("kaynak") or ""),
                "not": compact_space(item.get("not") or ""),
            }
        )
    fallback_de = clean_example_text(record.get("ornek_almanca") or "")
    fallback_tr = clean_example_text(record.get("ornek_turkce") or "")
    if fallback_de:
        examples.append(
            {
                "almanca": fallback_de,
                "turkce": fallback_tr,
                "kaynak": compact_space(record.get("kaynak") or ""),
                "not": "",
            }
        )
    deduped: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in examples:
        key = (normalize(item.get("almanca", "")), normalize(item.get("turkce", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def fallback_translation_for_sense(
    sense: dict,
    record_variants: list[str],
    explanation_pairs: list[tuple[str, str]],
    sense_count: int,
    index: int,
) -> tuple[str, str, float]:
    gloss_key = normalize(sense.get("tanim_almanca") or "")
    topic_keys = {normalize(item) for item in (sense.get("topics") or [])}
    for left_key, right_value in explanation_pairs:
        if gloss_key and (gloss_key in left_key or left_key in gloss_key):
            return right_value, "aciklama_turkce", 0.86
        if topic_keys and any(topic in left_key for topic in topic_keys):
            return right_value, "aciklama_turkce", 0.8
    if record_variants and len(record_variants) == sense_count and index < len(record_variants):
        return record_variants[index], "kayit-eslesme", 0.76
    if record_variants and sense_count == 1:
        return record_variants[0], "kayit-ozeti", 0.64
    return "", "", 0.0


def build_record_senses(record: dict, dewikt_senses: list[dict]) -> list[dict]:
    record_categories = [
        compact_space(item)
        for item in (record.get("kategoriler") or [])
        if compact_space(item)
    ]
    raw_variants = split_multi_value(record.get("turkce") or "")
    raw_variants.extend(parse_alt_meanings(record.get("not") or ""))
    record_variants = dedupe_strings(raw_variants)
    explanation_pairs = parse_explanation_pairs(record.get("aciklama_turkce") or "")

    filtered = [sense for sense in dewikt_senses if pos_matches(record, sense.get("pos") or "")]
    if not filtered:
        filtered = dewikt_senses[:]

    if not filtered:
        fallback_senses = []
        de_parts = split_multi_value(record.get("tanim_almanca") or "")
        tr_parts = record_variants or [compact_space(record.get("turkce") or "")]
        count = max(len(de_parts), len(tr_parts), 0)
        for index in range(count):
            de_value = de_parts[index] if index < len(de_parts) else ""
            tr_value = tr_parts[index] if index < len(tr_parts) else ""
            if not de_value and not tr_value:
                continue
            fallback_senses.append(
                {
                    "sira": len(fallback_senses) + 1,
                    "tanim_almanca": de_value,
                    "turkce": tr_value,
                    "aciklama_turkce": "",
                    "etiketler": dedupe_strings(record_categories),
                    "ornekler": collect_record_examples(record)[:2] if len(fallback_senses) == 0 else [],
                    "kaynak": "mevcut-kayit",
                    "guven": 0.48,
                }
            )
        return fallback_senses

    total = len(filtered)
    generic_examples = collect_record_examples(record)
    result: list[dict] = []
    for index, sense in enumerate(filtered):
        tr_candidates = dedupe_strings(sense.get("turkce_adaylari") or [])
        if tr_candidates:
            turkce = "; ".join(tr_candidates[:4])
            source = "deWiktionary-tr"
            confidence = 0.97
        else:
            turkce, source, confidence = fallback_translation_for_sense(
                sense,
                record_variants,
                explanation_pairs,
                total,
                index,
            )
        examples = []
        for item in sense.get("ornekler") or []:
            payload = dict(item)
            payload["etiket_turkce"] = ""
            examples.append(payload)
        if not examples and total == 1:
            examples = [dict(item) for item in generic_examples[:3]]
        result.append(
            {
                "sira": len(result) + 1,
                "tanim_almanca": compact_space(sense.get("tanim_almanca") or ""),
                "turkce": compact_space(turkce),
                "aciklama_turkce": "",
                "etiketler": extract_sense_labels(
                    sense,
                    record_categories,
                    allow_record_categories=(total == 1),
                ),
                "ornekler": examples,
                "kaynak": source or "deWiktionary",
                "guven": round(confidence, 2),
            }
        )
    return result


def merge_existing_senses(existing: list[dict], generated: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in existing + generated:
        if not isinstance(item, dict):
            continue
        key = (
            normalize(item.get("tanim_almanca") or ""),
            normalize(item.get("turkce") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        payload = {
            "sira": len(merged) + 1,
            "tanim_almanca": compact_space(item.get("tanim_almanca") or ""),
            "turkce": compact_space(item.get("turkce") or ""),
            "aciklama_turkce": compact_space(item.get("aciklama_turkce") or ""),
            "etiketler": dedupe_strings(
                [compact_space(label) for label in (item.get("etiketler") or [])]
            ),
            "ornekler": [],
            "kaynak": compact_space(item.get("kaynak") or ""),
            "guven": item.get("guven", 0.0),
        }
        example_seen: set[tuple[str, str]] = set()
        for example in item.get("ornekler") or []:
            if not isinstance(example, dict):
                continue
            ex_key = (
                normalize(example.get("almanca") or ""),
                normalize(example.get("turkce") or ""),
            )
            if ex_key in example_seen:
                continue
            example_seen.add(ex_key)
            payload["ornekler"].append(
                {
                    "almanca": clean_example_text(example.get("almanca") or ""),
                    "turkce": clean_example_text(example.get("turkce") or ""),
                    "kaynak": compact_space(example.get("kaynak") or ""),
                    "not": compact_space(example.get("not") or ""),
                    "etiket_turkce": compact_space(example.get("etiket_turkce") or ""),
                }
            )
        merged.append(payload)
    return merged


def enrich_dictionary(
    dict_path: Path,
    dump_path: Path,
    report_path: Path,
    *,
    overwrite: bool,
    limit: int | None,
    dry_run: bool,
) -> dict:
    data = json.loads(dict_path.read_text(encoding="utf-8"))
    dewikt_index = build_dewikt_index(dump_path)
    counters = Counter()

    for record in data:
        if limit is not None and counters["records_scanned"] >= limit:
            break
        counters["records_scanned"] += 1
        word_key = normalize(record.get("almanca") or "")
        existing_senses = record.get("anlamlar") or []
        dewikt_senses = dewikt_index.get(word_key, [])
        if not dewikt_senses and not record.get("tanim_almanca") and not record.get("turkce"):
            counters["records_without_source"] += 1
            continue

        generated = build_record_senses(record, dewikt_senses)
        if not generated:
            counters["records_without_generated_senses"] += 1
            continue

        if existing_senses and not overwrite:
            merged = merge_existing_senses(existing_senses, generated)
            if merged == existing_senses:
                counters["records_unchanged_existing"] += 1
                continue
            record["anlamlar"] = merged
            counters["records_extended_existing"] += 1
        else:
            record["anlamlar"] = generated
            counters["records_updated"] += 1

        counters["sense_count"] += len(record["anlamlar"])
        for sense in record["anlamlar"]:
            if sense.get("turkce"):
                counters["senses_with_translation"] += 1
            if sense.get("kaynak") == "deWiktionary-tr":
                counters["senses_with_direct_tr"] += 1
            if sense.get("ornekler"):
                counters["senses_with_examples"] += 1

    report = {
        "dict_path": str(dict_path),
        "dump_path": str(dump_path),
        "dry_run": dry_run,
        "overwrite": overwrite,
        "limit": limit,
        "counters": dict(counters),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not dry_run:
        dict_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Structured sense enrichment for the dictionary")
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--dump-path", type=Path, default=DEFAULT_DUMP_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dict_path.exists():
        print(f"Sözlük bulunamadı: {args.dict_path}", file=sys.stderr)
        return 1
    if not args.dump_path.exists():
        print(f"deWiktionary dump bulunamadı: {args.dump_path}", file=sys.stderr)
        return 1
    report = enrich_dictionary(
        args.dict_path,
        args.dump_path,
        args.report_path,
        overwrite=args.overwrite,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
