#!/usr/bin/env python3
"""Clear obviously bad Groq translations so they can be retried later."""

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
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "groq_quality_filter_report.json"
LOCK_PATH = DEFAULT_DICT_PATH.with_suffix(".json.lock")
TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüßÇĞİIÖŞÜçğıöşü]{2,}")


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


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def token_set(text: str) -> set[str]:
    return {normalize(item) for item in TOKEN_RE.findall(str(text or "")) if normalize(item)}


def is_groq_source(source: str) -> bool:
    return "groq" in normalize(source)


def is_bad_translation(de_text: str, tr_text: str) -> bool:
    de = compact(de_text)
    tr = compact(tr_text)
    if not tr:
        return False
    if re.match(r"^\d+[.)]\s*", tr):
        return True
    lowered = normalize(tr)
    if any(mark in lowered for mark in ("translation:", "turkce:", "çeviri:", "{", "}", "[", "]")):
        return True
    if normalize(de) == lowered:
        return True
    de_tokens = token_set(de)
    tr_tokens = token_set(tr)
    if len(de_tokens) >= 4 and de_tokens:
        overlap = len(de_tokens & tr_tokens) / max(len(de_tokens), 1)
        if overlap >= 0.8:
            return True
    if len(de.split()) >= 5 and len(tr.split()) <= 1:
        return True
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DEFAULT_DICT_PATH)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dict_path = args.dict_path
    output_path = args.output_path or dict_path
    counters = Counter()

    with InterProcessFileLock(LOCK_PATH if output_path == dict_path else output_path.with_suffix(".lock")):
        data = json.loads(dict_path.read_text(encoding="utf-8"))

        for record in data:
            examples = record.get("ornekler") or []
            if not isinstance(examples, list):
                continue
            for index, example in enumerate(examples):
                if not isinstance(example, dict):
                    continue
                source = compact(example.get("kaynak") or "")
                de_text = compact(example.get("almanca") or "")
                tr_text = compact(example.get("turkce") or "")
                if not de_text or not tr_text or not is_groq_source(source):
                    continue
                if not is_bad_translation(de_text, tr_text):
                    continue
                example["turkce"] = ""
                counters["examples_cleared"] += 1
                if index == 0 and compact(record.get("ornek_turkce") or "") == tr_text:
                    record["ornek_turkce"] = ""
                    counters["top_level_cleared"] += 1

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
