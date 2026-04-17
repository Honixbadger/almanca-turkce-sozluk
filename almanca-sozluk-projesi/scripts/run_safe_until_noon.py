#!/usr/bin/env python3
"""Run additive enrichment tasks safely until the next local noon deadline."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TIMEZONE = timezone(timedelta(hours=3), name="UTC+03:00")


@dataclass
class CycleResult:
    cycle: int
    started_at: str
    finished_at: str
    stage_path: str
    align_exit: int
    baglam_exit: int
    merge_exit: int
    image_refresh_exit: int
    image_prefetch_exit: int
    duration_seconds: float


def parse_deadline(raw: str | None) -> datetime:
    now = datetime.now(TIMEZONE)
    if raw:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TIMEZONE)
        return parsed.astimezone(TIMEZONE)
    if now.hour < 12:
        return now.replace(hour=12, minute=0, second=0, microsecond=0)
    tomorrow = now.date() + timedelta(days=1)
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=TIMEZONE).replace(hour=12)


def run_command(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    return int(completed.returncode)


def stage_dictionary_path(cycle: int) -> Path:
    timestamp = datetime.now(TIMEZONE).strftime("%Y%m%d-%H%M%S")
    return OUTPUT_DIR / f"dictionary_safe_noon_stage_{timestamp}_c{cycle}.json"


def report_path(prefix: str, cycle: int) -> Path:
    timestamp = datetime.now(TIMEZONE).strftime("%Y%m%d-%H%M%S")
    return OUTPUT_DIR / f"{prefix}_{timestamp}_c{cycle}.json"


def build_cycle_commands(stage_path: Path, cycle: int, image_refresh_limit: int, image_prefetch_terms: int) -> list[list[str]]:
    python = sys.executable
    return [
        [
            python,
            str(SCRIPTS_DIR / "align_examples_to_senses.py"),
            "--dict-path",
            str(stage_path),
            "--output-path",
            str(stage_path),
            "--report-path",
            str(report_path("sense_example_alignment_report", cycle)),
        ],
        [
            python,
            str(SCRIPTS_DIR / "generate_local_baglamlar.py"),
            "--dict-path",
            str(stage_path),
            "--output-path",
            str(stage_path),
            "--report-path",
            str(report_path("local_baglamlar_report", cycle)),
        ],
        [
            python,
            str(SCRIPTS_DIR / "merge_stage_dictionary_safe.py"),
            "--staged-path",
            str(stage_path),
            "--fields",
            "anlamlar",
            "baglamlar",
        ],
        [
            python,
            str(SCRIPTS_DIR / "refresh_contextual_word_images.py"),
            "--limit",
            str(image_refresh_limit),
        ],
        [
            python,
            str(SCRIPTS_DIR / "prefetch_word_images.py"),
            "--max-terms",
            str(image_prefetch_terms),
        ],
    ]


def write_summary(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deadline", help="ISO datetime. Default: next local 12:00 (+03:00).")
    parser.add_argument("--cooldown-seconds", type=int, default=1800, help="Pause between cycles.")
    parser.add_argument("--image-refresh-limit", type=int, default=8)
    parser.add_argument("--image-prefetch-terms", type=int, default=12)
    parser.add_argument("--max-cycles", type=int, default=0, help="0 means unlimited until deadline.")
    args = parser.parse_args()

    deadline = parse_deadline(args.deadline)
    summary_path = OUTPUT_DIR / "safe_until_noon_summary.json"
    cycles: list[dict] = []
    cycle_number = 0

    print(f"deadline={deadline.isoformat()}", flush=True)
    print(f"summary={summary_path}", flush=True)

    while datetime.now(TIMEZONE) < deadline:
        if args.max_cycles and cycle_number >= args.max_cycles:
            print("max_cycles reached", flush=True)
            break

        cycle_number += 1
        started = datetime.now(TIMEZONE)
        stage_path = stage_dictionary_path(cycle_number)
        shutil.copy2(OUTPUT_DIR / "dictionary.json", stage_path)
        print(f"[cycle {cycle_number}] stage={stage_path.name}", flush=True)

        commands = build_cycle_commands(
            stage_path=stage_path,
            cycle=cycle_number,
            image_refresh_limit=args.image_refresh_limit,
            image_prefetch_terms=args.image_prefetch_terms,
        )

        started_ts = time.time()
        exits = []
        labels = ["align", "baglam", "merge", "image_refresh", "image_prefetch"]
        for label, command in zip(labels, commands, strict=True):
            if datetime.now(TIMEZONE) >= deadline:
                print(f"[cycle {cycle_number}] deadline reached before {label}", flush=True)
                exits.append(99)
                continue
            print(f"[cycle {cycle_number}] start {label}: {' '.join(command)}", flush=True)
            exit_code = run_command(command)
            print(f"[cycle {cycle_number}] done {label}: exit={exit_code}", flush=True)
            exits.append(exit_code)

        finished = datetime.now(TIMEZONE)
        result = CycleResult(
            cycle=cycle_number,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            stage_path=str(stage_path),
            align_exit=exits[0] if len(exits) > 0 else 99,
            baglam_exit=exits[1] if len(exits) > 1 else 99,
            merge_exit=exits[2] if len(exits) > 2 else 99,
            image_refresh_exit=exits[3] if len(exits) > 3 else 99,
            image_prefetch_exit=exits[4] if len(exits) > 4 else 99,
            duration_seconds=round(time.time() - started_ts, 2),
        )
        cycles.append(result.__dict__)
        write_summary(
            summary_path,
            {
                "deadline": deadline.isoformat(),
                "last_updated": datetime.now(TIMEZONE).isoformat(),
                "cycles": cycles,
            },
        )

        remaining = (deadline - datetime.now(TIMEZONE)).total_seconds()
        if remaining <= 0:
            break
        sleep_for = min(args.cooldown_seconds, max(0, int(remaining)))
        print(f"[cycle {cycle_number}] cooldown={sleep_for}s", flush=True)
        time.sleep(sleep_for)

    print("finished", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
