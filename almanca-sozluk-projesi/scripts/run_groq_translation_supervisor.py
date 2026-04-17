#!/usr/bin/env python3
"""Supervise looped Groq translation shards with controlled per-run workload."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "enrich_groq_translations.py"
SETTINGS_PATH = ROOT / "data" / "manual" / "desktop_settings.json"
LOG_DIR = ROOT / "logs"
OUTPUT_DIR = ROOT / "output"
SUPERVISOR_LOG = LOG_DIR / "groq-supervisor.log"
SUPERVISOR_PID = LOG_DIR / "groq-supervisor.pid"
LOCK_PATH = LOG_DIR / "groq-supervisor.lock"


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    line = f"[{ts()}] {message}"
    print(line, flush=True)
    with SUPERVISOR_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class SingleInstanceLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def acquire(self) -> None:
        payload = f"{os.getpid()}|{ts()}".encode("utf-8", errors="ignore")
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, payload)
                return
            except FileExistsError:
                try:
                    raw = self.path.read_text(encoding="utf-8").strip().split("|", 1)[0]
                    existing_pid = int(raw)
                except Exception:
                    existing_pid = 0
                if existing_pid and pid_exists(existing_pid):
                    raise RuntimeError(f"Supervisor zaten calisiyor (PID {existing_pid})")
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                time.sleep(0.2)

    def release(self) -> None:
        try:
            if self.fd is not None:
                os.close(self.fd)
        finally:
            self.fd = None
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_api_keys() -> list[str]:
    settings = load_settings()
    keys: list[str] = []
    multi = settings.get("groq_api_keys") or []
    if isinstance(multi, list):
        for item in multi:
            value = str(item or "").strip()
            if value and "BURAYA_GROQ_API_ANAHTARINIZI_GIRIN" not in value and value not in keys:
                keys.append(value)

    fallback = str(settings.get("llm_api_key") or "").strip()
    if fallback and "BURAYA_GROQ_API_ANAHTARINIZI_GIRIN" not in fallback and fallback not in keys:
        keys.append(fallback)
    return keys


def sanitize_name(label: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in label)


def parse_missing_count(stdout_path: Path) -> int | None:
    try:
        for line in stdout_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Eksik ceviri olan entry:"):
                return int(line.rsplit(":", 1)[1].strip())
    except Exception:
        return None
    return None


def read_stdout_text(stdout_path: Path | None) -> str:
    if not stdout_path or not stdout_path.exists():
        return ""
    try:
        return stdout_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def has_auth_failure(stdout_path: Path | None) -> bool:
    return "HTTP 401" in read_stdout_text(stdout_path)


@dataclass
class WorkerState:
    shard_index: int
    api_key: str
    key_index: int = 0
    process: subprocess.Popen | None = None
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    child_pid_path: Path | None = None
    last_exit_at: float = 0.0
    completed: bool = False
    runs: int = 0
    disabled_reason: str | None = None
    attempted_key_indexes: set[int] | None = None


def build_worker_command(args: argparse.Namespace, shard_index: int) -> list[str]:
    checkpoint_path = OUTPUT_DIR / f"groq_tr_checkpoint_9way_shard{shard_index + 1}.json"
    command = [
        sys.executable,
        str(SCRIPT_PATH),
        "--model",
        args.model,
        "--limit",
        str(args.worker_limit),
        "--shard-index",
        str(shard_index),
        "--shard-count",
        str(args.shard_count),
        "--checkpoint-path",
        str(checkpoint_path),
    ]
    return command


def start_worker(state: WorkerState, args: argparse.Namespace) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    state.runs += 1
    run_tag = sanitize_name(datetime.now().strftime("%Y%m%d-%H%M%S"))
    state.stdout_path = LOG_DIR / f"groq-supervisor-shard{state.shard_index + 1}-{run_tag}.out.log"
    state.stderr_path = LOG_DIR / f"groq-supervisor-shard{state.shard_index + 1}-{run_tag}.err.log"
    state.child_pid_path = LOG_DIR / f"groq-supervisor-shard{state.shard_index + 1}.pid"

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["GROQ_API_KEY"] = state.api_key

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    stdout_handle = state.stdout_path.open("a", encoding="utf-8")
    stderr_handle = state.stderr_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        build_worker_command(args, state.shard_index),
        cwd=str(ROOT),
        stdout=stdout_handle,
        stderr=stderr_handle,
        env=env,
        creationflags=creationflags,
    )
    state.process = process
    state.child_pid_path.write_text(str(process.pid), encoding="utf-8")
    log(
        f"Shard {state.shard_index + 1}/{args.shard_count} basladi | PID {process.pid} | "
        f"limit={args.worker_limit} | key={state.key_index + 1} | stdout={state.stdout_path.name}"
    )


def stop_worker(state: WorkerState) -> None:
    if not state.process:
        return
    try:
        if state.process.poll() is None:
            state.process.terminate()
            try:
                state.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                state.process.kill()
                state.process.wait(timeout=5)
    except Exception:
        pass
    finally:
        state.process = None
        if state.child_pid_path:
            try:
                state.child_pid_path.unlink()
            except FileNotFoundError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="llama-3.1-8b-instant")
    parser.add_argument("--shard-count", type=int, default=9)
    parser.add_argument("--worker-limit", type=int, default=12)
    parser.add_argument("--cooldown-seconds", type=int, default=4)
    parser.add_argument("--poll-seconds", type=int, default=2)
    parser.add_argument("--start-stagger-seconds", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    lock = SingleInstanceLock(LOCK_PATH)
    lock.acquire()
    SUPERVISOR_PID.write_text(str(os.getpid()), encoding="utf-8")

    stopping = False

    def request_stop(_signum, _frame) -> None:
        nonlocal stopping
        stopping = True
        log("Supervisor durdurma sinyali aldi.")

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        api_keys = load_api_keys()
        if not api_keys:
            raise RuntimeError("desktop_settings.json icinde groq_api_keys veya llm_api_key bulunamadi.")

        shared_bad_key_indexes: set[int] = set()

        def first_usable_key_index(start_index: int = 0, blocked: set[int] | None = None) -> int | None:
            blocked = blocked or set()
            for offset in range(len(api_keys)):
                idx = (start_index + offset) % len(api_keys)
                if idx in shared_bad_key_indexes or idx in blocked:
                    continue
                return idx
            return None

        workers: list[WorkerState] = []
        for i in range(args.shard_count):
            key_index = first_usable_key_index(i)
            if key_index is None:
                raise RuntimeError("Kullanilabilir Groq anahtari kalmadi.")
            workers.append(
                WorkerState(
                    shard_index=i,
                    api_key=api_keys[key_index],
                    key_index=key_index,
                    attempted_key_indexes={key_index},
                )
            )
        log(
            f"Supervisor basladi | shard={args.shard_count} | worker_limit={args.worker_limit} | "
            f"cooldown={args.cooldown_seconds}s"
        )

        for index, state in enumerate(workers):
            if stopping:
                break
            start_worker(state, args)
            if index < len(workers) - 1 and args.start_stagger_seconds > 0:
                time.sleep(args.start_stagger_seconds)

        while not stopping:
            active_count = 0
            for state in workers:
                if state.completed:
                    continue

                if state.process is None:
                    if state.last_exit_at and (time.time() - state.last_exit_at) < args.cooldown_seconds:
                        continue
                    start_worker(state, args)
                    active_count += 1
                    continue

                exit_code = state.process.poll()
                if exit_code is None:
                    active_count += 1
                    continue

                state.last_exit_at = time.time()
                if state.child_pid_path:
                    try:
                        state.child_pid_path.unlink()
                    except FileNotFoundError:
                        pass

                missing = parse_missing_count(state.stdout_path) if state.stdout_path else None
                if has_auth_failure(state.stdout_path):
                    shared_bad_key_indexes.add(state.key_index)
                    next_key_index = first_usable_key_index(
                        state.shard_index,
                        state.attempted_key_indexes or set(),
                    )
                    if next_key_index is None:
                        state.completed = True
                        state.disabled_reason = "auth-failure"
                        log(
                            f"Shard {state.shard_index + 1} devre disi birakildi | "
                            f"neden=HTTP 401 | code={exit_code} | kullanilabilir anahtar kalmadi"
                        )
                    else:
                        state.api_key = api_keys[next_key_index]
                        state.key_index = next_key_index
                        if state.attempted_key_indexes is None:
                            state.attempted_key_indexes = set()
                        state.attempted_key_indexes.add(next_key_index)
                        log(
                            f"Shard {state.shard_index + 1} anahtar degistirdi | "
                            f"neden=HTTP 401 | yeni-key={next_key_index + 1}"
                        )
                elif missing == 0:
                    state.completed = True
                    log(f"Shard {state.shard_index + 1} tamamlandi, yeniden baslatilmayacak.")
                else:
                    log(
                        f"Shard {state.shard_index + 1} cikti | code={exit_code} | "
                        f"eksik={missing if missing is not None else 'bilinmiyor'} | "
                        f"{args.cooldown_seconds}s sonra yeniden denenecek."
                    )
                state.process = None

            if active_count == 0 and all(state.completed for state in workers):
                log("Tum shard'lar tamamlandi, supervisor cikiyor.")
                break
            time.sleep(args.poll_seconds)
    finally:
        for maybe_state in locals().get("workers", []):
            stop_worker(maybe_state)
        try:
            SUPERVISOR_PID.unlink()
        except FileNotFoundError:
            pass
        lock.release()


if __name__ == "__main__":
    main()
