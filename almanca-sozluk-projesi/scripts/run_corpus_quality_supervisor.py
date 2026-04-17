#!/usr/bin/env python3
"""Run a resumable corpus-quality pipeline for a fixed number of hours."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from corpus_quality_utils import CORPUS_OUTPUT_DIR, load_json, save_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DEFAULT_SUMMARY_PATH = CORPUS_OUTPUT_DIR / "corpus_quality_supervisor_summary.json"


PIPELINE = [
    ("build_corpus_usage_index.py", ["--max-html-files-per-run", "10", "--max-tatoeba-lines-per-run", "18000", "--max-dewiktionary-lines-per-run", "30000"]),
    ("cluster_sense_usages.py", ["--max-lemmas-per-run", "700"]),
    ("extract_verb_valency_from_corpus.py", ["--max-verbs-per-run", "350"]),
    ("rank_example_sentences.py", ["--max-lemmas-per-run", "1200"]),
    ("build_review_candidates.py", ["--max-records-per-run", "1500"]),
]

CHECKPOINT_MAP = {
    "cluster_sense_usages.py": CORPUS_OUTPUT_DIR / "corpus_sense_clusters.checkpoint.json",
    "extract_verb_valency_from_corpus.py": CORPUS_OUTPUT_DIR / "corpus_verb_valency.checkpoint.json",
    "rank_example_sentences.py": CORPUS_OUTPUT_DIR / "corpus_ranked_examples.checkpoint.json",
    "build_review_candidates.py": CORPUS_OUTPUT_DIR / "corpus_review_candidates.checkpoint.json",
}
USAGE_REPORT_PATH = CORPUS_OUTPUT_DIR / "corpus_usage_index_report.json"


def run_step(script_name: str, extra_args: list[str], timeout_seconds: int) -> dict:
    script_path = SCRIPTS_DIR / script_name
    started_at = datetime.now()
    command = [sys.executable, str(script_path), *extra_args]
    result = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )
    ended_at = datetime.now()
    return {
        "script": script_name,
        "args": extra_args,
        "started_at": started_at.isoformat(timespec="seconds"),
        "ended_at": ended_at.isoformat(timespec="seconds"),
        "returncode": result.returncode,
        "stdout_tail": "\n".join((result.stdout or "").splitlines()[-20:]),
        "stderr_tail": "\n".join((result.stderr or "").splitlines()[-20:]),
    }


def checkpoint_finished(script_name: str) -> bool:
    checkpoint_path = CHECKPOINT_MAP.get(script_name)
    if not checkpoint_path or not checkpoint_path.exists():
        return False
    payload = load_json(checkpoint_path, {})
    offset = int(payload.get("offset", 0) or 0)
    total = int(payload.get("total", 0) or 0)
    return bool(total and offset >= total)


def usage_finished() -> bool:
    if not USAGE_REPORT_PATH.exists():
        return False
    payload = load_json(USAGE_REPORT_PATH, {})
    progress = payload.get("progress") or {}
    counters = payload.get("counters") or {}
    html_done = int(progress.get("html_index", 0) or 0) >= int(progress.get("html_total_files", 0) or 0)
    no_new_payload = (
        int(counters.get("html_sentences_seen", 0) or 0) == 0
        and int(counters.get("tatoeba_sentences_seen", 0) or 0) == 0
        and int(counters.get("dewiktionary_examples_seen", 0) or 0) == 0
        and int(counters.get("tatoeba_lines_advanced", 0) or 0) == 0
        and int(counters.get("dewiktionary_lines_advanced", 0) or 0) == 0
    )
    return html_done and no_new_payload


def should_skip_step(script_name: str) -> tuple[bool, str]:
    if script_name == "build_corpus_usage_index.py" and usage_finished():
        return True, "usage-finished"
    if checkpoint_finished(script_name):
        return True, "checkpoint-complete"
    return False, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run corpus quality pipeline for a fixed number of hours.")
    parser.add_argument("--hours", type=float, default=2.0)
    parser.add_argument("--sleep-seconds", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    args = parser.parse_args()

    CORPUS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now()
    deadline = started_at + timedelta(hours=max(0.1, args.hours))
    summary = {
        "started_at": started_at.isoformat(timespec="seconds"),
        "deadline": deadline.isoformat(timespec="seconds"),
        "hours": args.hours,
        "sleep_seconds": args.sleep_seconds,
        "timeout_seconds": args.timeout_seconds,
        "cycles": [],
        "status": "running",
    }
    save_json(args.summary_path, summary)

    cycle_no = 0
    while datetime.now() < deadline:
        cycle_no += 1
        cycle = {
            "cycle": cycle_no,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "steps": [],
        }
        for script_name, extra_args in PIPELINE:
            if datetime.now() >= deadline:
                break
            skip, reason = should_skip_step(script_name)
            if skip:
                step_result = {
                    "script": script_name,
                    "args": extra_args,
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                    "ended_at": datetime.now().isoformat(timespec="seconds"),
                    "returncode": 0,
                    "skipped": True,
                    "skip_reason": reason,
                    "stdout_tail": "",
                    "stderr_tail": "",
                }
                cycle["steps"].append(step_result)
                summary["cycles"].append(step_result)
                save_json(args.summary_path, summary)
                continue
            try:
                step_result = run_step(script_name, extra_args, args.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                step_result = {
                    "script": script_name,
                    "args": extra_args,
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                    "ended_at": datetime.now().isoformat(timespec="seconds"),
                    "returncode": 124,
                    "stdout_tail": "\n".join((exc.stdout or "").splitlines()[-20:]),
                    "stderr_tail": "\n".join((exc.stderr or "").splitlines()[-20:]),
                    "error": "timeout",
                }
            cycle["steps"].append(step_result)
            summary["cycles"].append(step_result)
            save_json(args.summary_path, summary)
        cycle["ended_at"] = datetime.now().isoformat(timespec="seconds")
        cycle["completed_steps"] = len(cycle["steps"])
        save_json(args.summary_path, summary)
        if datetime.now() < deadline and args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    summary["ended_at"] = datetime.now().isoformat(timespec="seconds")
    summary["status"] = "completed"
    save_json(args.summary_path, summary)
    print(json.dumps({"status": "completed", "summary_path": str(args.summary_path), "cycle_count": cycle_no}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
