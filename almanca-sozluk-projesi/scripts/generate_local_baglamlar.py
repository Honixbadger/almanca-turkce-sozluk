#!/usr/bin/env python3
"""Build baglamlar from translated examples and sense labels without API usage."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "local_baglamlar_report.json"

CATEGORY_KEYWORDS = {
    "otomotiv": {"motor", "araç", "otomotiv", "fren", "tekerlek", "kupplung", "reifen", "airbag"},
    "teknik": {"teknik", "cihaz", "sistem", "makine", "teknoloji", "bilgisayar"},
    "iş": {"iş", "çalış", "firma", "ofis", "müşteri", "proje", "toplantı", "büro"},
    "eğitim": {"okul", "ders", "sınav", "öğren", "üniversite", "kurs", "eğitim"},
    "seyahat": {"seyahat", "otel", "uçak", "tren", "havaalanı", "tatil", "yolculuk"},
    "sosyal": {"arkadaş", "aile", "parti", "konuş", "buluş", "ziyaret", "sosyal"},
    "günlük": {"ev", "gün", "zaman", "al", "ver", "git", "gel", "yap"},
}


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().casefold()


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def all_text_tokens(*values: str) -> set[str]:
    joined = " ".join(str(value or "") for value in values)
    return {normalize(item) for item in re.findall(r"[A-Za-zÄÖÜäöüßÇĞİIÖŞÜçğıöşü]{3,}", joined)}


def classify_category(record: dict, sense: dict | None, example: dict) -> str:
    tokens = all_text_tokens(
        record.get("almanca") or "",
        record.get("turkce") or "",
        sense.get("tanim_almanca") if sense else "",
        " ".join(sense.get("etiketler") or []) if sense else "",
        example.get("almanca") or "",
        example.get("turkce") or "",
    )
    best_category = "günlük"
    best_score = -1
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = len(tokens & {normalize(k) for k in keywords})
        if score > best_score:
            best_score = score
            best_category = category
    return best_category


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-categories", type=int, default=3)
    parser.add_argument("--max-examples-per-category", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dict_path = args.dict_path
    output_path = args.output_path or dict_path
    data = json.loads(dict_path.read_text(encoding="utf-8"))
    counters = Counter()

    for record in data:
        if record.get("baglamlar"):
            continue
        grouped: dict[str, list[dict]] = defaultdict(list)
        seen: set[tuple[str, str, str]] = set()
        senses = record.get("anlamlar") or []

        for sense in senses:
            if not isinstance(sense, dict):
                continue
            for example in sense.get("ornekler") or []:
                if not isinstance(example, dict):
                    continue
                de = compact(example.get("almanca") or "")
                tr = compact(example.get("turkce") or "")
                if not de or not tr:
                    continue
                category = classify_category(record, sense, example)
                key = (category, normalize(de), normalize(tr))
                if key in seen:
                    continue
                seen.add(key)
                grouped[category].append({"de": de, "tr": tr})

        for example in record.get("ornekler") or []:
            if not isinstance(example, dict):
                continue
            de = compact(example.get("almanca") or "")
            tr = compact(example.get("turkce") or "")
            if not de or not tr:
                continue
            category = classify_category(record, None, example)
            key = (category, normalize(de), normalize(tr))
            if key in seen:
                continue
            seen.add(key)
            grouped[category].append({"de": de, "tr": tr})

        if not grouped:
            continue

        ordered = sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True)[: args.max_categories]
        baglamlar = []
        for category, examples in ordered:
            baglamlar.append({
                "kategori": category,
                "cumleler": examples[: args.max_examples_per_category],
            })
        if baglamlar:
            record["baglamlar"] = baglamlar
            counters["records_updated"] += 1
            counters["categories_created"] += len(baglamlar)

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "dict_path": str(dict_path),
        "output_path": str(output_path),
        "counters": dict(counters),
    }
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
