#!/usr/bin/env python3
"""Run safe verb-form enrichment cycles for a fixed number of hours."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIVE_DICT = PROJECT_ROOT / "output" / "dictionary.json"
STAGE_DICT = PROJECT_ROOT / "output" / "dictionary_verb_focus_stage.json"
LOG_DIR = PROJECT_ROOT / "logs"
OUTPUT_DIR = PROJECT_ROOT / "output"


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def parse_last_json_blob(text: str) -> dict:
    start = text.rfind("{")
    if start == -1:
        return {}
    snippet = text[start:]
    try:
        return json.loads(snippet)
    except Exception:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=5.0)
    parser.add_argument("--interval-minutes", type=float, default=20.0)
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now()
    deadline = started_at + timedelta(hours=max(args.hours, 0.1))
    interval_seconds = max(int(args.interval_minutes * 60), 30)
    cycles: list[dict] = []

    print(
        json.dumps(
            {
                "event": "verb-focus-started",
                "started_at": started_at.isoformat(timespec="seconds"),
                "deadline": deadline.isoformat(timespec="seconds"),
                "interval_seconds": interval_seconds,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    cycle_index = 0
    while datetime.now() < deadline:
        cycle_index += 1
        cycle_stamp = timestamp()
        cycle_report = OUTPUT_DIR / f"verb_forms_stage_report_{cycle_stamp}.json"

        shutil.copy2(LIVE_DICT, STAGE_DICT)
        enrich = run_cmd(
            [
                sys.executable,
                "scripts/enrich_verb_forms.py",
                "--dict-path",
                str(STAGE_DICT),
                "--report-path",
                str(cycle_report),
            ]
        )

        enrich_report = {}
        if cycle_report.exists():
            try:
                enrich_report = json.loads(cycle_report.read_text(encoding="utf-8"))
            except Exception:
                enrich_report = parse_last_json_blob(enrich.stdout)

        merge_report = {}
        if enrich.returncode == 0 and enrich_report.get("updated_entries", 0):
            merge = run_cmd(
                [
                    sys.executable,
                    "scripts/merge_stage_dictionary_safe.py",
                    "--staged-path",
                    str(STAGE_DICT),
                    "--fields",
                    "prateritum",
                    "cekimler",
                ]
            )
            merge_report = parse_last_json_blob(merge.stdout)
        else:
            merge = None

        cycle_payload = {
            "cycle": cycle_index,
            "at": datetime.now().isoformat(timespec="seconds"),
            "enrich_returncode": enrich.returncode,
            "enrich_updated_entries": enrich_report.get("updated_entries", 0),
            "prateritum_added": enrich_report.get("prateritum_added", 0),
            "prateritum_fallback_added": enrich_report.get("prateritum_fallback_added", 0),
            "cekimler_added": enrich_report.get("cekimler_added", 0),
            "merge_updated_entries": merge_report.get("updated_entries", 0),
            "merge_field_updates": merge_report.get("field_updates", {}),
        }
        cycles.append(cycle_payload)
        print(json.dumps(cycle_payload, ensure_ascii=False), flush=True)

        remaining = (deadline - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        time.sleep(min(interval_seconds, max(int(remaining), 1)))

    summary = {
        "event": "verb-focus-finished",
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "cycles": len(cycles),
        "total_enrich_updates": sum(item["enrich_updated_entries"] for item in cycles),
        "total_merge_updates": sum(item["merge_updated_entries"] for item in cycles),
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
