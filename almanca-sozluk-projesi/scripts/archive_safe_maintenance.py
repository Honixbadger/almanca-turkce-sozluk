#!/usr/bin/env python3
"""Archive old maintenance artifacts without touching active runtime files."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs"
OUTPUT_DIR = PROJECT_ROOT / "output"
ARCHIVE_DIR = PROJECT_ROOT / "maintenance_archives"

OUTPUT_PREFIXES = (
    "dictionary_safe_noon_stage_",
    "dictionary_priority_stage_",
    "dictionary_verb_patterns_stage_",
    "dictionary_verb_patterns_stage_fix_",
    "dictionary_verb_forms_stage_fix_",
    "dictionary_semantic_stage_",
    "dictionary_tatoeba_stage_",
    "dictionary_image_group_smoke",
    "dictionary_local_stage",
    "dictionary_quality_stage",
    "dictionary_senses_stage",
    "dictionary_verb_stage",
    "dictionary_stage_safe_",
    "sense_enrichment_report_",
    "sense_example_alignment_report_",
    "local_baglamlar_report_",
    "verb_forms_stage_report_",
    "verb_patterns_report_",
    "verb_patterns_report_fix_",
    "verb_forms_stage_fix_report_",
    "dictionary_quality_report_",
    "image_group_suggestions_report_",
    "image_group_suggestions_smoke",
    "phrase_candidates_review_",
    "phrase_candidates_import_report_",
    "auto_phrase_report_",
    "semantic_normalization_report_",
)

KEEP_OUTPUT_NAMES = {
    "dictionary.json",
    "dictionary_quality_report.json",
    "priority_enrichment_summary.json",
    "safe_until_noon_summary.json",
    "word_image_manifest.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs-hours", type=float, default=2.0)
    parser.add_argument("--output-hours", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def is_old_enough(path: Path, cutoff: datetime) -> bool:
    return datetime.fromtimestamp(path.stat().st_mtime) < cutoff


def collect_old_logs(cutoff: datetime) -> list[Path]:
    if not LOG_DIR.exists():
        return []
    return [path for path in LOG_DIR.iterdir() if path.is_file() and is_old_enough(path, cutoff)]


def collect_old_outputs(cutoff: datetime) -> list[Path]:
    if not OUTPUT_DIR.exists():
        return []
    files: list[Path] = []
    for path in OUTPUT_DIR.iterdir():
        if not path.is_file():
            continue
        if path.name in KEEP_OUTPUT_NAMES:
            continue
        if path.name.startswith("groq_tr_checkpoint"):
            continue
        if not path.name.startswith(OUTPUT_PREFIXES):
            continue
        if not is_old_enough(path, cutoff):
            continue
        files.append(path)
    return files


def collect_pycache_dirs() -> list[Path]:
    return [path for path in PROJECT_ROOT.rglob("__pycache__") if path.is_dir()]


def archive_files(paths: list[Path], archive_path: Path) -> None:
    temp_dir = archive_path.with_suffix("")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        target = temp_dir / path.relative_to(PROJECT_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    shutil.make_archive(str(archive_path.with_suffix("")), "zip", root_dir=temp_dir)
    shutil.rmtree(temp_dir)


def main() -> int:
    args = parse_args()
    now = datetime.now()
    log_cutoff = now - timedelta(hours=args.logs_hours)
    output_cutoff = now - timedelta(hours=args.output_hours)

    old_logs = collect_old_logs(log_cutoff)
    old_outputs = collect_old_outputs(output_cutoff)
    pycache_dirs = collect_pycache_dirs()
    pycache_files = sum(len(list(path.glob("*"))) for path in pycache_dirs)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVE_DIR / f"maintenance_cleanup_{now.strftime('%Y%m%d-%H%M%S')}.zip"

    if not args.dry_run and (old_logs or old_outputs):
        archive_files(old_logs + old_outputs, archive_path)
        for path in old_logs + old_outputs:
            path.unlink(missing_ok=True)
    if not args.dry_run:
        for path in pycache_dirs:
            shutil.rmtree(path, ignore_errors=True)

    files_remaining = sum(1 for _ in PROJECT_ROOT.rglob("*") if _.is_file())
    payload = {
        "archive_path": str(archive_path) if (old_logs or old_outputs) else "",
        "removed_logs": len(old_logs),
        "removed_output_files": len(old_outputs),
        "removed_pycache_files": pycache_files,
        "files_remaining": files_remaining,
        "dry_run": args.dry_run,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
