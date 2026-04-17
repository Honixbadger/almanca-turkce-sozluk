#!/usr/bin/env python3
"""Safely merge staged dictionary enrichments into the live dictionary."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIVE_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
LOCK_PATH = LIVE_DICT_PATH.with_suffix(".json.lock")
DEFAULT_FIELDS = [
    "aciklama_turkce",
    "sinonim",
    "antonim",
    "valenz",
    "kelime_ailesi",
    "ilgili_kayitlar",
    "anlamlar",
    "baglamlar",
    "fiil_kaliplari",
    "ornek_almanca",
    "ornek_turkce",
    "ornekler",
]


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


def compact_space(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def normalize_key(record: dict) -> str:
    return compact_space(record.get("almanca") or "")


def normalized_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = compact_space(item)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def merge_list_field(live_row: dict, staged_row: dict, field: str) -> int:
    live_values = normalized_list(live_row.get(field))
    staged_values = normalized_list(staged_row.get(field))
    seen = {value.casefold() for value in live_values}
    added = 0
    for value in staged_values:
        if value.casefold() not in seen:
            live_values.append(value)
            seen.add(value.casefold())
            added += 1
    if added:
        live_row[field] = live_values
    return added


def merge_examples(live_row: dict, staged_row: dict) -> int:
    live_examples = list(live_row.get("ornekler") or [])
    staged_examples = list(staged_row.get("ornekler") or [])
    live_index: dict[str, dict] = {}

    for example in live_examples:
        if not isinstance(example, dict):
            continue
        key = compact_space(example.get("almanca") or "")
        if key:
            live_index[key.casefold()] = example

    changes = 0
    for staged in staged_examples:
        if not isinstance(staged, dict):
            continue
        de_text = compact_space(staged.get("almanca") or "")
        tr_text = compact_space(staged.get("turkce") or "")
        kaynak = compact_space(staged.get("kaynak") or "")
        if not de_text:
            continue
        existing = live_index.get(de_text.casefold())
        if existing is None:
            new_example = {"almanca": de_text}
            if tr_text:
                new_example["turkce"] = tr_text
            if kaynak:
                new_example["kaynak"] = kaynak
            live_examples.append(new_example)
            live_index[de_text.casefold()] = new_example
            changes += 1
            continue
        if tr_text and not compact_space(existing.get("turkce") or ""):
            existing["turkce"] = tr_text
            changes += 1
        if kaynak and not compact_space(existing.get("kaynak") or ""):
            existing["kaynak"] = kaynak
            changes += 1

    if changes:
        live_row["ornekler"] = live_examples
    return changes


def merge_scalar_fill(live_row: dict, staged_row: dict, field: str) -> int:
    live_value = compact_space(live_row.get(field) or "")
    staged_value = compact_space(staged_row.get(field) or "")
    if staged_value and not live_value:
        live_row[field] = staged_value
        return 1
    return 0


def sense_key(sense: dict) -> tuple[str, str]:
    return (
        compact_space(sense.get("tanim_almanca") or "").casefold(),
        compact_space(sense.get("turkce") or "").casefold(),
    )


def merge_sense_examples(live_examples: list, staged_examples: list) -> int:
    if not isinstance(live_examples, list):
        live_examples = []
    if not isinstance(staged_examples, list):
        staged_examples = []

    existing: dict[tuple[str, str], dict] = {}
    for example in live_examples:
        if not isinstance(example, dict):
            continue
        key = (
            compact_space(example.get("almanca") or "").casefold(),
            compact_space(example.get("turkce") or "").casefold(),
        )
        existing[key] = example

    changes = 0
    for staged in staged_examples:
        if not isinstance(staged, dict):
            continue
        key = (
            compact_space(staged.get("almanca") or "").casefold(),
            compact_space(staged.get("turkce") or "").casefold(),
        )
        if not key[0]:
            continue
        live_item = existing.get(key)
        if live_item is None:
            payload = {
                "almanca": compact_space(staged.get("almanca") or ""),
                "turkce": compact_space(staged.get("turkce") or ""),
                "kaynak": compact_space(staged.get("kaynak") or ""),
                "not": compact_space(staged.get("not") or ""),
                "etiket_turkce": compact_space(staged.get("etiket_turkce") or ""),
            }
            live_examples.append(payload)
            existing[key] = payload
            changes += 1
            continue
        for field in ("turkce", "kaynak", "not", "etiket_turkce"):
            staged_value = compact_space(staged.get(field) or "")
            live_value = compact_space(live_item.get(field) or "")
            if staged_value and not live_value:
                live_item[field] = staged_value
                changes += 1
    return changes


def merge_senses(live_row: dict, staged_row: dict) -> int:
    live_senses = live_row.get("anlamlar")
    staged_senses = staged_row.get("anlamlar")
    if not isinstance(staged_senses, list) or not staged_senses:
        return 0
    if not isinstance(live_senses, list) or not live_senses:
        live_row["anlamlar"] = staged_senses
        return 1

    changes = 0
    by_key: dict[tuple[str, str], dict] = {}
    by_def: dict[str, dict] = {}
    for sense in live_senses:
        if not isinstance(sense, dict):
            continue
        by_key[sense_key(sense)] = sense
        def_key = compact_space(sense.get("tanim_almanca") or "").casefold()
        if def_key:
            by_def[def_key] = sense

    for staged_sense in staged_senses:
        if not isinstance(staged_sense, dict):
            continue
        key = sense_key(staged_sense)
        target = by_key.get(key)
        if target is None:
            target = by_def.get(compact_space(staged_sense.get("tanim_almanca") or "").casefold())
        if target is None:
            live_senses.append(staged_sense)
            by_key[key] = staged_sense
            changes += 1
            continue

        for field in ("turkce", "aciklama_turkce", "kaynak"):
            staged_value = compact_space(staged_sense.get(field) or "")
            live_value = compact_space(target.get(field) or "")
            if staged_value and not live_value:
                target[field] = staged_value
                changes += 1

        live_labels = normalized_list(target.get("etiketler"))
        staged_labels = normalized_list(staged_sense.get("etiketler"))
        seen_labels = {item.casefold() for item in live_labels}
        for label in staged_labels:
            if label.casefold() not in seen_labels:
                live_labels.append(label)
                seen_labels.add(label.casefold())
                changes += 1
        if live_labels:
            target["etiketler"] = live_labels

        target_conf = float(target.get("guven") or 0.0)
        staged_conf = float(staged_sense.get("guven") or 0.0)
        if staged_conf > target_conf:
            target["guven"] = staged_conf
            changes += 1

        live_examples = target.get("ornekler")
        if not isinstance(live_examples, list):
            live_examples = []
        changes += merge_sense_examples(live_examples, staged_sense.get("ornekler") or [])
        target["ornekler"] = live_examples

    if changes:
        live_row["anlamlar"] = live_senses
    return changes


def merge_baglamlar(live_row: dict, staged_row: dict) -> int:
    live_items = list(live_row.get("baglamlar") or [])
    staged_items = list(staged_row.get("baglamlar") or [])
    if not staged_items:
        return 0
    if not live_items:
        live_row["baglamlar"] = staged_items
        return 1

    by_cat: dict[str, dict] = {}
    for item in live_items:
        if not isinstance(item, dict):
            continue
        cat = compact_space(item.get("kategori") or "").casefold()
        if cat:
            by_cat[cat] = item

    changes = 0
    for staged in staged_items:
        if not isinstance(staged, dict):
            continue
        cat = compact_space(staged.get("kategori") or "")
        if not cat:
            continue
        target = by_cat.get(cat.casefold())
        if target is None:
            live_items.append(staged)
            by_cat[cat.casefold()] = staged
            changes += 1
            continue
        live_examples = list(target.get("cumleler") or [])
        seen = {
            (
                compact_space(example.get("de") or "").casefold(),
                compact_space(example.get("tr") or "").casefold(),
            )
            for example in live_examples
            if isinstance(example, dict)
        }
        for example in staged.get("cumleler") or []:
            if not isinstance(example, dict):
                continue
            key = (
                compact_space(example.get("de") or "").casefold(),
                compact_space(example.get("tr") or "").casefold(),
            )
            if not key[0] or key in seen:
                continue
            live_examples.append(
                {
                    "de": compact_space(example.get("de") or ""),
                    "tr": compact_space(example.get("tr") or ""),
                }
            )
            seen.add(key)
            changes += 1
        target["cumleler"] = live_examples

    if changes:
        live_row["baglamlar"] = live_items
    return changes


def merge_source_hint(live_row: dict, staged_row: dict) -> int:
    live_source = compact_space(live_row.get("kaynak") or "")
    staged_source = compact_space(staged_row.get("kaynak") or "")
    if not staged_source:
        return 0
    if not live_source:
        live_row["kaynak"] = staged_source
        return 1
    if staged_source in live_source:
        return 0
    if "Tatoeba" in staged_source and "Tatoeba" not in live_source:
        live_row["kaynak"] = f"{live_source}; {staged_source}"
        return 1
    return 0


def merge_verb_patterns(live_row: dict, staged_row: dict) -> int:
    staged_items = staged_row.get("fiil_kaliplari")
    if not isinstance(staged_items, list) or not staged_items:
        return 0

    normalized_stage: list[dict] = []
    seen: set[str] = set()
    for staged_item in staged_items:
        if not isinstance(staged_item, dict):
            continue
        phrase = compact_space(staged_item.get("kalip") or "")
        if not phrase:
            continue
        key = phrase.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized_stage.append(
            {
                "kalip": phrase,
                "turkce": compact_space(staged_item.get("turkce") or ""),
                "aciklama_turkce": compact_space(staged_item.get("aciklama_turkce") or ""),
                "ornek_almanca": compact_space(staged_item.get("ornek_almanca") or ""),
                "ornek_turkce": compact_space(staged_item.get("ornek_turkce") or ""),
                "kaynak": compact_space(staged_item.get("kaynak") or ""),
            }
        )

    live_items = list(live_row.get("fiil_kaliplari") or [])
    if json.dumps(live_items, ensure_ascii=False, sort_keys=True) != json.dumps(normalized_stage, ensure_ascii=False, sort_keys=True):
        live_row["fiil_kaliplari"] = normalized_stage
        return len(normalized_stage) or 1
    return 0


def merge_cekimler(live_row: dict, staged_row: dict) -> int:
    live_value = live_row.get("cekimler")
    staged_value = staged_row.get("cekimler")
    if not isinstance(staged_value, dict) or not staged_value:
        return 0

    live = dict(live_value or {})
    changes = 0

    for top_key in ("präteritum", "perfekt", "imperativ"):
        staged_text = compact_space(staged_value.get(top_key) or "")
        live_text = compact_space(live.get(top_key) or "")
        if staged_text and not live_text:
            live[top_key] = staged_text
            changes += 1

    staged_present = dict(staged_value.get("präsens") or {})
    live_present = dict(live.get("präsens") or {})
    for slot, staged_text in staged_present.items():
        staged_text = compact_space(staged_text or "")
        if not staged_text:
            continue
        live_text = compact_space(live_present.get(slot) or "")
        if not live_text:
            live_present[slot] = staged_text
            changes += 1
    if live_present:
        live["präsens"] = live_present

    if changes:
        live_row["cekimler"] = live
    return changes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged-path", required=True)
    parser.add_argument("--live-path", default=str(LIVE_DICT_PATH))
    parser.add_argument("--fields", nargs="+", default=DEFAULT_FIELDS)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    staged_path = Path(args.staged_path)
    live_path = Path(args.live_path)

    if not staged_path.exists():
        print(f"staged dictionary not found: {staged_path}", flush=True)
        return 2
    if not live_path.exists():
        print(f"live dictionary not found: {live_path}", flush=True)
        return 2

    staged = json.loads(staged_path.read_text(encoding="utf-8"))
    field_counts = {field: 0 for field in args.fields}
    updated_entries = 0

    with InterProcessFileLock(LOCK_PATH):
        live = json.loads(live_path.read_text(encoding="utf-8"))
        staged_index = {normalize_key(row): row for row in staged if normalize_key(row)}

        for live_row in live:
            key = normalize_key(live_row)
            staged_row = staged_index.get(key)
            if staged_row is None:
                continue

            changed = False
            for field in args.fields:
                delta = 0
                if field == "ornekler":
                    delta = merge_examples(live_row, staged_row)
                elif field == "anlamlar":
                    delta = merge_senses(live_row, staged_row)
                elif field == "baglamlar":
                    delta = merge_baglamlar(live_row, staged_row)
                elif field == "cekimler":
                    delta = merge_cekimler(live_row, staged_row)
                elif field == "fiil_kaliplari":
                    delta = merge_verb_patterns(live_row, staged_row)
                elif field in {"sinonim", "antonim", "valenz", "kelime_ailesi", "ilgili_kayitlar"}:
                    delta = merge_list_field(live_row, staged_row, field)
                elif field == "kaynak":
                    delta = merge_source_hint(live_row, staged_row)
                else:
                    delta = merge_scalar_fill(live_row, staged_row, field)
                if delta:
                    field_counts[field] += delta
                    changed = True

            if changed:
                updated_entries += 1

        if not args.dry_run:
            live_path.write_text(json.dumps(live, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    report = {
        "staged_path": str(staged_path),
        "live_path": str(live_path),
        "updated_entries": updated_entries,
        "field_updates": field_counts,
        "dry_run": args.dry_run,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
