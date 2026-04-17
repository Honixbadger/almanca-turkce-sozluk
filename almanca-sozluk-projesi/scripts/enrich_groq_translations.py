#!/usr/bin/env python3
"""Fill missing Turkish example translations via Groq.

Supports safe parallel execution by splitting the dictionary into non-overlapping
shards and by merge-saving only the translated fields back into dictionary.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import requests as _requests

    _USE_REQUESTS = True
except ImportError:
    _requests = None
    _USE_REQUESTS = False


DICT_PATH = Path("output/dictionary.json")
CHECKPOINT_PATH = Path("output/groq_tr_checkpoint.json")
SETTINGS_PATH = Path("data/manual/desktop_settings.json")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MIN_INTERVAL = 2.5
LOCK_PATH = DICT_PATH.with_suffix(".json.lock")


def load_api_key(cli_value: str | None) -> str:
    if cli_value and cli_value.strip():
        return cli_value.strip()

    env_value = (os.getenv("GROQ_API_KEY") or "").strip()
    if env_value:
        return env_value

    if SETTINGS_PATH.exists():
        try:
            settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            multi_values = settings.get("groq_api_keys") or []
            if isinstance(multi_values, list):
                for item in multi_values:
                    value = str(item or "").strip()
                    if value and "BURAYA_GROQ_API_ANAHTARINIZI_GIRIN" not in value:
                        return value
            value = str(settings.get("llm_api_key") or "").strip()
            if value and "BURAYA_GROQ_API_ANAHTARINIZI_GIRIN" not in value:
                return value
        except Exception:
            pass
    return ""


def shard_matches(key: str, shard_index: int, shard_count: int) -> bool:
    if shard_count <= 1:
        return True
    digest = hashlib.md5(key.encode("utf-8", errors="ignore")).hexdigest()
    return (int(digest[:8], 16) % shard_count) == shard_index


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


def call_groq(api_key: str, model: str, messages: list[dict], max_tokens: int = 400) -> str | None:
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.15,
        }
    ).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    backoff = 5

    for _attempt in range(4):
        try:
            if _USE_REQUESTS:
                resp = _requests.post(GROQ_API_URL, headers=headers, data=payload, timeout=30)
                if resp.status_code == 429:
                    print(f"  Rate limit - {backoff} sn bekleniyor...", flush=True)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 64)
                    continue
                if resp.status_code != 200:
                    print(f"  HTTP {resp.status_code}", flush=True)
                    return None
                return resp.json()["choices"][0]["message"]["content"].strip()

            req = urllib.request.Request(
                GROQ_API_URL,
                data=payload,
                headers={**headers, "User-Agent": "Mozilla/5.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read())["choices"][0]["message"]["content"].strip()
        except Exception as ex:
            if "429" in str(ex):
                print(f"  Rate limit - {backoff} sn bekleniyor...", flush=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, 64)
            else:
                print(f"  Hata: {ex}", flush=True)
                return None
    return None


def translate_batch(api_key: str, model: str, word: str, sentences: list[str]) -> dict[int, str]:
    numbered = "\n".join(f"{i + 1}. {sentence}" for i, sentence in enumerate(sentences))
    prompt = (
        f'Almanca kelime: "{word}"\n\n'
        "Asagidaki Almanca cumleleri Turkceye cevir. "
        "Sadece numarali cevirileri yaz, aciklama ekleme:\n\n"
        f"{numbered}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "Sen Almanca-Turkce profesyonel bir cevirmenisin. "
                "Sadece numarali cevirileri ver, baska hicbir sey yazma."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    response = call_groq(api_key, model, messages, max_tokens=len(sentences) * 60 + 50)
    if not response:
        return {}

    result: dict[int, str] = {}
    for line in response.splitlines():
        match = re.match(r"^(\d+)[.)]\s*(.+)$", line.strip())
        if not match:
            continue
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(sentences):
            result[idx] = match.group(2).strip()
    return result


def _merge_save(mem_data: list[dict], path: Path) -> None:
    if not hasattr(_merge_save, "_thread_lock"):
        _merge_save._thread_lock = threading.Lock()

    with _merge_save._thread_lock:
        with InterProcessFileLock(LOCK_PATH):
            try:
                disk_data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                disk_data = mem_data

            disk_idx = {str(entry.get("almanca", "")): entry for entry in disk_data}
            for mem_entry in mem_data:
                key = str(mem_entry.get("almanca", ""))
                disk_entry = disk_idx.get(key)
                if disk_entry is None:
                    continue

                mem_examples = mem_entry.get("ornekler") or []
                disk_examples = disk_entry.get("ornekler") or []
                for index, mem_example in enumerate(mem_examples):
                    if index >= len(disk_examples):
                        continue
                    mem_tr = str(mem_example.get("turkce") or "").strip()
                    disk_tr = str(disk_examples[index].get("turkce") or "").strip()
                    if mem_tr and not disk_tr:
                        disk_examples[index]["turkce"] = mem_tr
                        if mem_example.get("kaynak"):
                            disk_examples[index]["kaynak"] = mem_example["kaynak"]

                mem_top_tr = str(mem_entry.get("ornek_turkce") or "").strip()
                disk_top_tr = str(disk_entry.get("ornek_turkce") or "").strip()
                if mem_top_tr and not disk_top_tr:
                    disk_entry["ornek_turkce"] = mem_top_tr

            path.write_text(json.dumps(disk_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def save_done(done: set[str], checkpoint_path: Path) -> None:
    checkpoint_path.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")


def get_missing_indices(entry: dict) -> list[int]:
    return [
        index
        for index, example in enumerate(entry.get("ornekler") or [])
        if (example.get("almanca") or "").strip()
        and (not (example.get("turkce") or "").strip() or example.get("turkce") == "-")
    ]


def build_tasks(data: list[dict], done: set[str], shard_index: int, shard_count: int) -> list[tuple[dict, str, list[int]]]:
    tasks: list[tuple[dict, str, list[int]]] = []
    for entry in data:
        almanca = str(entry.get("almanca") or "").strip()
        if not almanca:
            continue
        if not shard_matches(almanca, shard_index, shard_count):
            continue
        if almanca in done:
            continue

        missing_indices = get_missing_indices(entry)
        if missing_indices:
            tasks.append((entry, almanca, missing_indices))
    return tasks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key")
    parser.add_argument(
        "--model",
        default="llama-3.1-8b-instant",
        choices=["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
    )
    parser.add_argument("--limit", type=int, default=0, help="Max islenecek entry sayisi")
    parser.add_argument("--checkpoint-path", default=str(CHECKPOINT_PATH), help="Checkpoint dosyasi yolu")
    parser.add_argument("--shard-index", type=int, default=0, help="0-based shard index")
    parser.add_argument("--shard-count", type=int, default=1, help="Toplam shard sayisi")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.shard_count < 1:
        parser.error("--shard-count en az 1 olmali")
    if not (0 <= args.shard_index < args.shard_count):
        parser.error("--shard-index, 0 ile shard-count-1 arasinda olmali")
    return args


def main() -> None:
    args = parse_args()
    checkpoint_path = Path(args.checkpoint_path)
    api_key = load_api_key(args.api_key)
    if not api_key:
        print(
            "Groq API anahtari bulunamadi. --api-key verin, GROQ_API_KEY ayarlayin veya desktop_settings.json icine llm_api_key ekleyin.",
            flush=True,
        )
        sys.exit(2)

    model_short = args.model.split("-")[1] if "-" in args.model else args.model[:8]

    print("Sozluk yukleniyor...", flush=True)
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))

    done: set[str] = set()
    if checkpoint_path.exists():
        done = set(json.loads(checkpoint_path.read_text(encoding="utf-8")))

    tasks = build_tasks(data, done, args.shard_index, args.shard_count)
    print(f"Eksik ceviri olan entry: {len(tasks)}", flush=True)
    print(f"Toplam eksik cumle: {sum(len(item[2]) for item in tasks)}", flush=True)
    print(f"Shard: {args.shard_index + 1}/{args.shard_count}", flush=True)

    if args.dry_run:
        print("Dry-run, cikiliyor.", flush=True)
        return

    if args.limit:
        tasks = tasks[: args.limit]

    updated_entries = 0
    updated_sentences = 0
    last_request = 0.0

    for index, (entry, key, missing_indices) in enumerate(tasks, start=1):
        sentences = [entry["ornekler"][i]["almanca"] for i in missing_indices]
        almanca = str(entry.get("almanca") or "")
        print(f"[{index}/{len(tasks)}] {almanca} ({len(sentences)} cumle)", flush=True)

        elapsed = time.time() - last_request
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        last_request = time.time()

        translations = translate_batch(api_key, args.model, almanca, sentences)
        if translations:
            for local_idx, tr_text in translations.items():
                real_idx = missing_indices[local_idx]
                entry["ornekler"][real_idx]["turkce"] = tr_text
                entry["ornekler"][real_idx]["kaynak"] = f"groq-{model_short}"
                if real_idx == 0 and (entry.get("ornek_almanca") or "").strip() and not (entry.get("ornek_turkce") or "").strip():
                    entry["ornek_turkce"] = tr_text
                updated_sentences += 1
                print(f"  -> {sentences[local_idx][:50]} | {tr_text[:50]}", flush=True)
            updated_entries += 1
        else:
            print("  Ceviri alinamadi.", flush=True)

        if not get_missing_indices(entry):
            done.add(key)
        if index % 20 == 0:
            _merge_save(data, DICT_PATH)
            save_done(done, checkpoint_path)
            print(f"  [Checkpoint: {updated_sentences} cumle cevrildi]", flush=True)

    _merge_save(data, DICT_PATH)
    save_done(done, checkpoint_path)
    print(f"\nBitti: {updated_entries} entry, {updated_sentences} cumle cevrildi.", flush=True)


if __name__ == "__main__":
    main()
