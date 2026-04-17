#!/usr/bin/env python3
"""Attach top-level examples to the most likely structured senses."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "sense_example_alignment_report.json"
STOPWORDS = {
    "der", "die", "das", "ein", "eine", "und", "oder", "ist", "im", "in", "mit", "den", "dem",
    "des", "bir", "ve", "ile", "için", "olan", "olanı", "bu", "şu", "da", "de", "birçok",
}
TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüßÇĞİIÖŞÜçğıöşü]{3,}")


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().casefold()


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def tokens(text: str) -> set[str]:
    result = set()
    for match in TOKEN_RE.findall(str(text or "")):
        token = normalize(match)
        if token and token not in STOPWORDS:
            result.add(token)
    return result


def example_key(example: dict) -> tuple[str, str]:
    return (
        normalize(example.get("almanca") or ""),
        normalize(example.get("turkce") or ""),
    )


def score_example_for_sense(example: dict, sense: dict) -> float:
    score = 0.0
    ex_de = tokens(example.get("almanca") or "")
    ex_tr = tokens(example.get("turkce") or "")
    sense_tr = tokens(sense.get("turkce") or "")
    sense_desc = tokens(sense.get("aciklama_turkce") or "")
    sense_de = tokens(sense.get("tanim_almanca") or "")
    labels = tokens(" ".join(sense.get("etiketler") or []))

    if ex_tr and sense_tr:
        score += len(ex_tr & sense_tr) * 3.0
    if ex_tr and sense_desc:
        score += len(ex_tr & sense_desc) * 2.0
    if ex_de and sense_de:
        score += len(ex_de & sense_de) * 1.4
    if ex_de and labels:
        score += len(ex_de & labels) * 1.2
    if ex_tr and labels:
        score += len(ex_tr & labels) * 1.0
    return score


def choose_best_sense(example: dict, senses: list[dict]) -> int:
    if len(senses) == 1:
        return 0
    best_index = 0
    best_score = -1.0
    for index, sense in enumerate(senses):
        score = score_example_for_sense(example, sense)
        if score > best_score:
            best_index = index
            best_score = score
    return best_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-per-sense", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dict_path = args.dict_path
    output_path = args.output_path or dict_path

    data = json.loads(dict_path.read_text(encoding="utf-8"))
    counters = Counter()

    for record in data:
        senses = record.get("anlamlar")
        examples = record.get("ornekler") or []
        if not isinstance(senses, list) or not senses or not isinstance(examples, list):
            continue
        counters["records_scanned"] += 1

        sense_existing = []
        for sense in senses:
            seen = {
                example_key(example)
                for example in (sense.get("ornekler") or [])
                if isinstance(example, dict)
            }
            sense_existing.append(seen)

        changed = False
        for example in examples:
            if not isinstance(example, dict):
                continue
            ex_de = compact(example.get("almanca") or "")
            if not ex_de:
                continue
            key = example_key(example)
            if any(key in seen for seen in sense_existing):
                continue

            sense_index = choose_best_sense(example, senses)
            target = senses[sense_index]
            live_examples = list(target.get("ornekler") or [])
            if len(live_examples) >= args.max_per_sense:
                continue

            payload = {
                "almanca": ex_de,
                "turkce": compact(example.get("turkce") or ""),
                "kaynak": compact(example.get("kaynak") or ""),
                "not": compact(example.get("not") or ""),
                "etiket_turkce": compact(target.get("turkce") or ""),
            }
            live_examples.append(payload)
            target["ornekler"] = live_examples
            sense_existing[sense_index].add(key)
            counters["examples_attached"] += 1
            changed = True

        if changed:
            counters["records_updated"] += 1

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
