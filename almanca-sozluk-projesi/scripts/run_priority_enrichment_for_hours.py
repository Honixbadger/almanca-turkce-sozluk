#!/usr/bin/env python3
"""Run ordered enrichment passes safely for a fixed number of hours."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOG_DIR = PROJECT_ROOT / "logs"
TIMEZONE = timezone(timedelta(hours=3), name="UTC+03:00")
SUMMARY_PATH = OUTPUT_DIR / "priority_enrichment_summary.json"


def parse_deadline(hours: float, raw_deadline: str | None) -> datetime:
    now = datetime.now(TIMEZONE)
    if raw_deadline:
        parsed = datetime.fromisoformat(raw_deadline)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TIMEZONE)
        return parsed.astimezone(TIMEZONE)
    return now + timedelta(hours=hours)


def write_summary(payload: dict) -> None:
    SUMMARY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def stage_path(cycle: int) -> Path:
    ts = datetime.now(TIMEZONE).strftime("%Y%m%d-%H%M%S")
    return OUTPUT_DIR / f"dictionary_priority_stage_{ts}_c{cycle}.json"


def report_path(prefix: str, cycle: int) -> Path:
    ts = datetime.now(TIMEZONE).strftime("%Y%m%d-%H%M%S")
    return OUTPUT_DIR / f"{prefix}_{ts}_c{cycle}.json"


def run_command(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    return int(completed.returncode)


def build_commands(stage: Path, cycle: int, image_refresh_limit: int, image_prefetch_terms: int) -> list[tuple[str, list[str]]]:
    py = sys.executable
    phrase_candidate_path = OUTPUT_DIR / f"phrase_candidates_review_{datetime.now(TIMEZONE).strftime('%Y%m%d-%H%M%S')}_c{cycle}.json"
    return [
        ("senses", [py, str(SCRIPTS_DIR / "enrich_senses.py"), "--dict-path", str(stage), "--report-path", str(report_path("sense_enrichment_report", cycle))]),
        ("sense_examples", [py, str(SCRIPTS_DIR / "align_examples_to_senses.py"), "--dict-path", str(stage), "--output-path", str(stage), "--report-path", str(report_path("sense_example_alignment_report", cycle))]),
        ("verb_forms", [py, str(SCRIPTS_DIR / "enrich_verb_forms.py"), "--dict-path", str(stage), "--report-path", str(report_path("verb_forms_stage_report", cycle))]),
        ("verb_patterns", [py, str(SCRIPTS_DIR / "enrich_verb_patterns.py"), "--dict-path", str(stage), "--output-path", str(stage), "--report-path", str(report_path("verb_patterns_report", cycle))]),
        ("baglamlar", [py, str(SCRIPTS_DIR / "generate_local_baglamlar.py"), "--dict-path", str(stage), "--output-path", str(stage), "--report-path", str(report_path("local_baglamlar_report", cycle))]),
        ("phrase_patterns", [py, str(SCRIPTS_DIR / "enrich_phrase_patterns.py"), "--dict-path", str(stage), "--report-path", str(report_path("auto_phrase_report", cycle))]),
        ("phrase_mining", [py, str(SCRIPTS_DIR / "mine_phrase_candidates.py"), "--dict-path", str(stage), "--output-path", str(phrase_candidate_path)]),
        ("phrase_import", [py, str(SCRIPTS_DIR / "import_phrase_candidates.py"), "--dict-path", str(stage), "--input-path", str(phrase_candidate_path), "--report-path", str(report_path("phrase_candidates_import_report", cycle))]),
        ("image_groups", [py, str(SCRIPTS_DIR / "suggest_image_groups.py"), "--dict-path", str(stage), "--output-path", str(stage), "--report-path", str(report_path("image_group_suggestions_report", cycle))]),
        ("merge", [py, str(SCRIPTS_DIR / "merge_stage_dictionary_safe.py"), "--staged-path", str(stage), "--fields", "anlamlar", "baglamlar", "fiil_kaliplari", "ilgili_kayitlar", "ornekler", "ornek_turkce", "ornek_almanca", "partizip2", "prateritum", "perfekt_yardimci", "trennbar", "trennbar_prefix", "verb_typ", "cekimler", "kaynak", "gorsel_grubu", "gorsel_ipucu"]),
        ("quality_report", [py, str(SCRIPTS_DIR / "build_quality_report.py"), "--dict-path", str(OUTPUT_DIR / "dictionary.json"), "--output-path", str(report_path("dictionary_quality_report", cycle))]),
        ("image_refresh", [py, str(SCRIPTS_DIR / "refresh_contextual_word_images.py"), "--limit", str(image_refresh_limit)]),
        ("image_prefetch", [py, str(SCRIPTS_DIR / "prefetch_word_images.py"), "--max-terms", str(image_prefetch_terms)]),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=4.0)
    parser.add_argument("--deadline", default="")
    parser.add_argument("--cooldown-seconds", type=int, default=300)
    parser.add_argument("--image-refresh-limit", type=int, default=8)
    parser.add_argument("--image-prefetch-terms", type=int, default=12)
    parser.add_argument("--max-cycles", type=int, default=0)
    args = parser.parse_args()

    deadline = parse_deadline(args.hours, args.deadline or None)
    cycles: list[dict] = []
    cycle = 0

    print(f"deadline={deadline.isoformat()}", flush=True)
    print(f"summary={SUMMARY_PATH}", flush=True)

    while datetime.now(TIMEZONE) < deadline:
        if args.max_cycles and cycle >= args.max_cycles:
            break

        cycle += 1
        started_at = datetime.now(TIMEZONE)
        stage = stage_path(cycle)
        shutil.copy2(OUTPUT_DIR / "dictionary.json", stage)
        print(f"[cycle {cycle}] stage={stage.name}", flush=True)

        command_results: list[dict] = []
        for label, command in build_commands(stage, cycle, args.image_refresh_limit, args.image_prefetch_terms):
            if datetime.now(TIMEZONE) >= deadline:
                command_results.append({"label": label, "exit": 99})
                break
            print(f"[cycle {cycle}] start {label}: {' '.join(command)}", flush=True)
            exit_code = run_command(command)
            print(f"[cycle {cycle}] done {label}: exit={exit_code}", flush=True)
            command_results.append({"label": label, "exit": exit_code})

        finished_at = datetime.now(TIMEZONE)
        cycles.append(
            {
                "cycle": cycle,
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "stage_path": str(stage),
                "commands": command_results,
            }
        )
        write_summary(
            {
                "deadline": deadline.isoformat(),
                "last_updated": datetime.now(TIMEZONE).isoformat(),
                "cycles": cycles,
            }
        )

        remaining = int((deadline - datetime.now(TIMEZONE)).total_seconds())
        if remaining <= 0:
            break
        sleep_for = min(args.cooldown_seconds, remaining)
        print(f"[cycle {cycle}] cooldown={sleep_for}s", flush=True)
        time.sleep(max(0, sleep_for))

    print("finished", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
