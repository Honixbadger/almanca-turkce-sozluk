#!/usr/bin/env python3
"""Run resumable enrichment tasks until a local deadline."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TIMEZONE = timezone(timedelta(hours=3), name="UTC+03:00")
DEFAULT_TASKS = ("odenet", "ipa", "trwiktionary", "openthesaurus")


@dataclass
class Task:
    name: str
    command: list[str]
    seconds_per_item: float | None = None
    safety_factor: float = 0.85
    min_limit: int = 0


def next_midnight(now: datetime) -> datetime:
    tomorrow = now.date() + timedelta(days=1)
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=TIMEZONE)


def parse_deadline(raw: str | None) -> datetime:
    now = datetime.now(TIMEZONE)
    if not raw:
        return next_midnight(now)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TIMEZONE)
    return parsed.astimezone(TIMEZONE)


def build_tasks() -> dict[str, Task]:
    python = sys.executable
    return {
        "odenet": Task(
            name="odenet",
            command=[python, str(SCRIPTS_DIR / "enrich_odenet.py")],
        ),
        "ipa": Task(
            name="ipa",
            command=[python, str(SCRIPTS_DIR / "enrich_ipa.py")],
            seconds_per_item=0.35,
            safety_factor=0.75,
            min_limit=50,
        ),
        "trwiktionary": Task(
            name="trwiktionary",
            command=[python, str(SCRIPTS_DIR / "enrich_trwiktionary.py")],
            seconds_per_item=1.25,
            safety_factor=0.8,
            min_limit=20,
        ),
        "openthesaurus": Task(
            name="openthesaurus",
            command=[python, str(SCRIPTS_DIR / "enrich_openthesaurus.py")],
            seconds_per_item=0.6,
            safety_factor=0.8,
            min_limit=50,
        ),
    }


def compute_limit(task: Task, deadline: datetime) -> int | None:
    if task.seconds_per_item is None:
        return None
    remaining = (deadline - datetime.now(TIMEZONE)).total_seconds()
    if remaining <= 0:
        return 0
    budget = max(0, int((remaining * task.safety_factor) / task.seconds_per_item))
    if budget < task.min_limit:
        return 0
    return budget


def run_task(task: Task, deadline: datetime) -> int:
    command = list(task.command)
    limit = compute_limit(task, deadline)
    if limit == 0:
        print(f"[skip] {task.name}: deadline için yeterli süre kalmadı", flush=True)
        return 0
    if limit:
        command.extend(["--limit", str(limit)])
    print(f"[start] {task.name}: {shlex.join(command)}", flush=True)
    started = time.time()
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    elapsed = time.time() - started
    print(f"[done] {task.name}: exit={completed.returncode} süre={elapsed:.1f}s", flush=True)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deadline", help="ISO datetime, örn: 2026-03-25T00:00:00+03:00")
    parser.add_argument("--tasks", nargs="+", default=list(DEFAULT_TASKS))
    args = parser.parse_args()

    deadline = parse_deadline(args.deadline)
    print(f"deadline={deadline.isoformat()}", flush=True)

    task_map = build_tasks()
    for name in args.tasks:
        task = task_map.get(name)
        if task is None:
            print(f"[skip] bilinmeyen task: {name}", flush=True)
            continue
        if datetime.now(TIMEZONE) >= deadline:
            print("[stop] deadline aşıldı", flush=True)
            break
        code = run_task(task, deadline)
        if code != 0:
            print(f"[warn] {name} başarısız oldu, sonraki task'a geçiliyor", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
