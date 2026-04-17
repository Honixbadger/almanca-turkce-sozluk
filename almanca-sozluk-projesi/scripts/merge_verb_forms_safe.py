#!/usr/bin/env python3
"""Safely merge staged verb-form enrichment into the live dictionary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIVE_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEFAULT_STAGED_PATH = PROJECT_ROOT / "output" / "dictionary_verb_stage.json"
VERB_FIELDS = ("partizip2", "prateritum", "perfekt_yardimci", "trennbar", "verb_typ")


def compact_space(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def normalized_field_value(field: str, value) -> str:
    if field == "trennbar":
        if value in (True, "True", "true", 1):
            return "trennbar"
        if value in (False, "False", "false", 0, None, ""):
            return ""
    return compact_space(value)


def normalize_key(record: dict) -> tuple[str, str]:
    return (compact_space(record.get("almanca") or ""), compact_space(record.get("tur") or ""))


def merge_cekimler(live_value: dict | None, staged_value: dict | None, overwrite: bool) -> tuple[dict, int]:
    live = dict(live_value or {})
    staged = dict(staged_value or {})
    changes = 0

    for top_key in ("präteritum", "perfekt", "imperativ"):
        staged_text = compact_space(staged.get(top_key) or "")
        live_text = compact_space(live.get(top_key) or "")
        if staged_text and (overwrite or not live_text):
            if live_text != staged_text:
                live[top_key] = staged_text
                changes += 1

    staged_present = dict(staged.get("präsens") or {})
    live_present = dict(live.get("präsens") or {})
    for slot, staged_text in staged_present.items():
        staged_text = compact_space(staged_text)
        if not staged_text:
            continue
        live_text = compact_space(live_present.get(slot) or "")
        if overwrite or not live_text:
            if live_text != staged_text:
                live_present[slot] = staged_text
                changes += 1
    if live_present:
        live["präsens"] = live_present

    return live, changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged-path", default=str(DEFAULT_STAGED_PATH))
    parser.add_argument("--live-path", default=str(LIVE_DICT_PATH))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    staged_path = Path(args.staged_path)
    live_path = Path(args.live_path)

    if not staged_path.exists():
        print(f"staged dictionary not found: {staged_path}", flush=True)
        return 2
    if not live_path.exists():
        print(f"live dictionary not found: {live_path}", flush=True)
        return 2

    staged = json.loads(staged_path.read_text(encoding="utf-8"))
    live = json.loads(live_path.read_text(encoding="utf-8"))

    staged_index = {normalize_key(row): row for row in staged if normalize_key(row)[0]}
    updated_entries = 0
    field_updates = {field: 0 for field in VERB_FIELDS}
    field_updates["cekimler"] = 0

    for row in live:
        key = normalize_key(row)
        staged_row = staged_index.get(key)
        if staged_row is None or key[1].casefold() != "fiil":
            continue

        changed = False
        for field in VERB_FIELDS:
            staged_text = normalized_field_value(field, staged_row.get(field))
            live_text = normalized_field_value(field, row.get(field))
            if staged_text and (args.overwrite or not live_text):
                if live_text != staged_text:
                    row[field] = staged_text
                    field_updates[field] += 1
                    changed = True

        merged_cekimler, local_changes = merge_cekimler(row.get("cekimler"), staged_row.get("cekimler"), args.overwrite)
        if local_changes:
            row["cekimler"] = merged_cekimler
            field_updates["cekimler"] += 1
            changed = True

        if changed:
            updated_entries += 1

    report = {
        "updated_entries": updated_entries,
        "field_updates": field_updates,
        "dry_run": args.dry_run,
        "staged_path": str(staged_path),
        "live_path": str(live_path),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)

    if not args.dry_run:
        live_path.write_text(json.dumps(live, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"saved: {live_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
