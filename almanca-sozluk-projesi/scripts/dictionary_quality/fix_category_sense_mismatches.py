#!/usr/bin/env python3
"""Report and optionally normalize category lists that disagree with sense evidence."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from quality_common import (
    DEFAULT_DICT_PATH,
    DEFAULT_REPORT_DIR,
    compact,
    configure_stdio,
    read_records,
    record_label,
    unique_list,
    write_json,
    write_records,
)


DOMAIN_KEYWORDS = {
    "otomotiv": {
        "motor",
        "arac",
        "otomobil",
        "direksiyon",
        "piston",
        "sanziman",
        "şanzıman",
        "fren",
        "akü",
        "aku",
        "ateşleme",
        "atesleme",
        "sürücü",
        "surucu",
        "lastik",
    },
    "elektrik-elektronik": {
        "elektrik",
        "elektronik",
        "devre",
        "sensor",
        "sensör",
        "gerilim",
        "volt",
        "akım",
        "akim",
        "batarya",
        "kablo",
    },
    "doğa-çevre": {
        "çevre",
        "cevre",
        "iklim",
        "ekoloji",
        "doğa",
        "doga",
        "çevresel",
        "cevresel",
    },
    "enerji": {
        "enerji",
        "yakıt",
        "yakit",
        "yakıtlı",
        "fuel",
        "güç",
        "guc",
        "şarj",
        "sarj",
    },
    "bilişim-teknoloji": {
        "bilgisayar",
        "yazılım",
        "yazilim",
        "disk",
        "sektör",
        "veri",
        "sunucu",
        "ağ",
        "ag",
        "uygulama",
    },
}


def score_domains(record: dict) -> dict[str, int]:
    text_parts = [
        compact(record.get("turkce") or ""),
        compact(record.get("aciklama_turkce") or ""),
        " ".join(compact(item) for item in (record.get("anlamlar") or []) if compact(item)),
        compact(record.get("ornek_turkce") or ""),
    ]
    blob = " ".join(text_parts).casefold()
    scores: dict[str, int] = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        scores[domain] = sum(1 for keyword in keywords if keyword in blob)
    return scores


def dominant_domain(scores: dict[str, int], minimum: int = 2) -> str | None:
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ordered or ordered[0][1] < minimum:
        return None
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return None
    return ordered[0][0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_DIR / "category_sense_mismatches.json",
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--apply-fixes", action="store_true")
    parser.add_argument("--add-suggested-category", action="store_true")
    parser.add_argument("--replace-single-category", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    records = read_records(args.dict_path)
    counters = Counter()
    samples: list[dict] = []

    for rec_idx, record in enumerate(records):
        categories = [compact(item) for item in (record.get("kategoriler") or []) if compact(item)]
        if not categories:
            continue
        scores = score_domains(record)
        suggested = dominant_domain(scores)
        if not suggested:
            continue
        if any(suggested == compact(cat).casefold() for cat in categories):
            continue

        counters["flagged_records"] += 1
        samples.append(
            {
                "record_index": rec_idx,
                "record": record_label(record, rec_idx),
                "current_categories": categories,
                "scores": scores,
                "suggested_category": suggested,
            }
        )

        if not args.apply_fixes:
            continue
        if args.replace_single_category and len(categories) == 1:
            record["kategoriler"] = [suggested]
            counters["replaced_single_categories"] += 1
        elif args.add_suggested_category:
            record["kategoriler"] = unique_list(categories + [suggested])
            counters["added_categories"] += 1

    payload = {
        "dict_path": str(args.dict_path),
        "apply_fixes": args.apply_fixes,
        "counters": dict(counters),
        "samples": samples[: args.sample_limit],
    }
    write_json(args.report_path, payload)

    if args.apply_fixes:
        target = write_records(
            records=records,
            dict_path=args.dict_path,
            output_path=args.output_path,
            in_place=args.in_place,
        )
        payload["output_path"] = str(target)
        write_json(args.report_path, payload)

    print(payload["counters"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
