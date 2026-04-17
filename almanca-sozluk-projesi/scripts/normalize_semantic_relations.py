#!/usr/bin/env python3
"""Normalize synonym and antonym fields into consistent unions."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "semantic_normalization_report.json"
LOCK_PATH = DEFAULT_DICT_PATH.with_suffix(".json.lock")


class InterProcessFileLock:
    def __init__(self, path: Path, timeout: float = 120.0, poll_interval: float = 0.2) -> None:
        self.path = path
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.fd: int | None = None

    def __enter__(self):
        start = time.time()
        payload = f"{os.getpid()}|{time.time()}".encode("utf-8", errors="ignore")
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, payload)
                return self
            except FileExistsError:
                if time.time() - start >= self.timeout:
                    raise TimeoutError(f"Kilide erisilemedi: {self.path}")
                time.sleep(self.poll_interval)

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.fd is not None:
                os.close(self.fd)
        finally:
            self.fd = None
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().casefold()


def to_list(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        raw = re.split(r"\s*;\s*|\s*\|\s*|\s*,\s*", value)
    else:
        raw = []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        key = normalize(text)
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--max-synonyms", type=int, default=14)
    parser.add_argument("--max-antonyms", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dict_path = args.dict_path
    output_path = args.output_path or dict_path
    counters = Counter()

    with InterProcessFileLock(LOCK_PATH if output_path == dict_path else output_path.with_suffix(".lock")):
        data = json.loads(dict_path.read_text(encoding="utf-8"))
        for record in data:
            synonyms = to_list(record.get("sinonim")) + to_list(record.get("esanlamlilar"))
            antonyms = to_list(record.get("antonim")) + to_list(record.get("zit_anlamlilar"))
            syn_union = to_list(synonyms)[: args.max_synonyms]
            ant_union = to_list(antonyms)[: args.max_antonyms]

            if syn_union:
                if to_list(record.get("sinonim")) != syn_union:
                    record["sinonim"] = syn_union
                    counters["sinonim_updated"] += 1
                if to_list(record.get("esanlamlilar")) != syn_union:
                    record["esanlamlilar"] = syn_union
                    counters["esanlamlilar_updated"] += 1

            if ant_union:
                if to_list(record.get("antonim")) != ant_union:
                    record["antonim"] = ant_union
                    counters["antonim_updated"] += 1
                if to_list(record.get("zit_anlamlilar")) != ant_union:
                    record["zit_anlamlilar"] = ant_union
                    counters["zit_anlamlilar_updated"] += 1

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
