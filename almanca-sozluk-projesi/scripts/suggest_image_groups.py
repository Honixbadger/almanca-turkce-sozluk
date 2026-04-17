#!/usr/bin/env python3
"""Suggest shared image-group metadata for high-confidence paired terms."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "image_group_suggestions_report.json"

PAIR_PREFIXES = [
    ("innen", "aussen", "iç kısmı göster", "dış kısmı göster"),
    ("innen", "außen", "iç kısmı göster", "dış kısmı göster"),
    ("vorder", "hinter", "ön kısmı göster", "arka kısmı göster"),
    ("ober", "unter", "üst kısmı göster", "alt kısmı göster"),
    ("links", "rechts", "sol tarafı göster", "sağ tarafı göster"),
]


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().casefold()


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def raw_word(record: dict) -> str:
    return compact(record.get("almanca") or "")


def build_index(records: list[dict]) -> dict[tuple[str, str], dict]:
    index: dict[tuple[str, str], dict] = {}
    for record in records:
        word = raw_word(record)
        pos = compact(record.get("tur") or "")
        if word and pos:
            index[(normalize(word), normalize(pos))] = record
    return index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    dict_path = args.dict_path
    output_path = args.output_path or dict_path

    data = json.loads(dict_path.read_text(encoding="utf-8"))
    index = build_index(data)
    counters = Counter()
    samples: list[dict] = []

    for record in data:
        word = raw_word(record)
        pos = compact(record.get("tur") or "")
        if not word or not pos:
            continue
        norm_word = normalize(word)

        for left_prefix, right_prefix, left_hint, right_hint in PAIR_PREFIXES:
            if not norm_word.startswith(left_prefix):
                continue

            remainder = norm_word[len(left_prefix):].strip()
            if len(remainder) < 3:
                continue

            sibling = index.get((f"{right_prefix}{remainder}", normalize(pos)))
            if sibling is None:
                continue

            group_value = f"cift:{remainder}"
            changed = False

            if not compact(record.get("gorsel_grubu") or ""):
                record["gorsel_grubu"] = group_value
                changed = True
                counters["gorsel_grubu_left"] += 1
            if not compact(sibling.get("gorsel_grubu") or ""):
                sibling["gorsel_grubu"] = group_value
                changed = True
                counters["gorsel_grubu_right"] += 1

            if not compact(record.get("gorsel_ipucu") or ""):
                record["gorsel_ipucu"] = left_hint
                changed = True
                counters["gorsel_ipucu_left"] += 1
            if not compact(sibling.get("gorsel_ipucu") or ""):
                sibling["gorsel_ipucu"] = right_hint
                changed = True
                counters["gorsel_ipucu_right"] += 1

            if changed and len(samples) < 24:
                samples.append(
                    {
                        "left": raw_word(record),
                        "right": raw_word(sibling),
                        "group": group_value,
                    }
                )
                counters["pairs_updated"] += 1
            break

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "dict_path": str(dict_path),
        "output_path": str(output_path),
        "counters": dict(counters),
        "sample": samples,
    }
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
