#!/usr/bin/env python3
"""Shared helpers for dictionary quality detection and cleanup scripts."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "output" / "quality_reports"
RELATION_FIELDS = ("esanlamlilar", "sinonim", "zit_anlamlilar", "antonim")
TURKISH_TEXT_FIELDS = ("turkce", "aciklama_turkce", "notlar", "ornek_turkce")


class InterProcessFileLock:
    """Very small lock file helper for in-place dictionary updates."""

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


def configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def compact(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_key(value: object) -> str:
    text = compact(value)
    text = strip_accents(text).casefold()
    text = re.sub(r"[^\w\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize_words(value: object) -> list[str]:
    return [token for token in re.findall(r"[A-Za-zÄÖÜäöüßÇĞİIÖŞÜçğıöşü]+", str(value or "")) if token]


def to_list(value: object) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = re.split(r"\s*;\s*|\s*\|\s*|\s*,\s*", value)
    else:
        raw_items = []
    return unique_list(compact(item) for item in raw_items if compact(item))


def unique_list(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = compact(value)
        key = normalize_key(item)
        if not item or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def read_records(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def timestamp_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def backup_path(target: Path) -> Path:
    return target.with_name(f"{target.stem}.backup-{timestamp_slug()}{target.suffix}")


def resolve_output_path(dict_path: Path, output_path: Path | None, in_place: bool) -> Path:
    if in_place:
        return dict_path
    if output_path is not None:
        return output_path
    return dict_path.with_name(f"{dict_path.stem}.cleaned{dict_path.suffix}")


def write_records(
    *,
    records: list[dict],
    dict_path: Path,
    output_path: Path | None,
    in_place: bool,
    make_backup: bool = True,
) -> Path:
    target = resolve_output_path(dict_path, output_path, in_place)
    ensure_parent(target)
    lock_path = target.with_suffix(target.suffix + ".lock")
    with InterProcessFileLock(lock_path):
        if in_place and make_backup:
            backup = backup_path(dict_path)
            backup.write_text(dict_path.read_text(encoding="utf-8"), encoding="utf-8")
        target.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def record_label(record: dict, index: int) -> str:
    lemma = compact(record.get("almanca") or "") or "<bos-lemma>"
    kind = compact(record.get("tur") or "")
    if kind:
        return f"{lemma} [{kind}] #{index}"
    return f"{lemma} #{index}"


def iter_example_slots(record: dict) -> list[dict]:
    slots: list[dict] = []
    top_de = compact(record.get("ornek_almanca") or "")
    top_tr = compact(record.get("ornek_turkce") or "")
    if top_de or top_tr:
        slots.append(
            {
                "kind": "top",
                "index": None,
                "almanca": top_de,
                "turkce": top_tr,
            }
        )
    for idx, item in enumerate(record.get("ornekler") or []):
        if not isinstance(item, dict):
            continue
        slots.append(
            {
                "kind": "nested",
                "index": idx,
                "almanca": compact(item.get("almanca") or ""),
                "turkce": compact(item.get("turkce") or ""),
            }
        )
    return slots


def clear_top_example(record: dict) -> bool:
    changed = False
    if compact(record.get("ornek_almanca") or ""):
        record["ornek_almanca"] = ""
        changed = True
    if compact(record.get("ornek_turkce") or ""):
        record["ornek_turkce"] = ""
        changed = True
    return changed


def drop_nested_examples(record: dict, indexes: set[int]) -> int:
    if not indexes:
        return 0
    examples = record.get("ornekler")
    if not isinstance(examples, list):
        return 0
    kept = [item for idx, item in enumerate(examples) if idx not in indexes]
    removed = len(examples) - len(kept)
    if removed:
        record["ornekler"] = kept
    return removed


def relation_index(records: list[dict]) -> dict[str, list[int]]:
    index: dict[str, list[int]] = {}
    for rec_idx, record in enumerate(records):
        lemma = compact(record.get("almanca") or "")
        if not lemma:
            continue
        index.setdefault(normalize_key(lemma), []).append(rec_idx)
    return index


def get_text_field_paths() -> list[tuple[str, str]]:
    return [(field, field) for field in TURKISH_TEXT_FIELDS]


def cjk_present(value: object) -> bool:
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", str(value or "")))


def contains_mojibake(value: object) -> bool:
    text = str(value or "")
    markers = ("Ã", "Ä", "Å", "â€™", "â€“", "â€œ", "â€", "�")
    return any(marker in text for marker in markers)


def stem_tokens(value: object, min_len: int = 4) -> set[str]:
    stems: set[str] = set()
    for token in tokenize_words(value):
        normalized = normalize_key(token)
        if len(normalized) < min_len:
            continue
        stems.add(normalized[: min(8, len(normalized))])
    return stems
