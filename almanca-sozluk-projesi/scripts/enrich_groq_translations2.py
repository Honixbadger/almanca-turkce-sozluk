#!/usr/bin/env python3
"""
Groq API ile ornekler listesindeki eksik Türkçe çevirileri tamamlar.

Kullanım:
    python scripts/enrich_groq_translations.py --api-key YOUR_GROQ_KEY
    python scripts/enrich_groq_translations.py --api-key KEY --limit 200 --model llama-3.3-70b-versatile
    python scripts/enrich_groq_translations.py --api-key KEY --dry-run

Ücretsiz Groq API key: https://console.groq.com/
"""

import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import unicodedata
import urllib.request
import urllib.error
from pathlib import Path
try:
    import requests as _requests
    _USE_REQUESTS = True
except ImportError:
    _USE_REQUESTS = False

DICT_PATH = Path("output/dictionary.json")
CHECKPOINT_PATH = Path("output/groq_tr_checkpoint2.json")
SETTINGS_PATH = Path("data/manual/desktop_settings.json")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MIN_INTERVAL = 2.5  # seconds between requests (30 req/min safe limit)


def load_api_key(cli_value: str | None) -> str:
    if cli_value and cli_value.strip():
        return cli_value.strip()

    env_value = (os.getenv("GROQ_API_KEY") or "").strip()
    if env_value:
        return env_value

    if SETTINGS_PATH.exists():
        try:
            settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            value = str(settings.get("llm_api_key") or "").strip()
            if value and "BURAYA_GROQ_API_ANAHTARINIZI_GIRIN" not in value:
                return value
        except Exception:
            pass
    return ""


def call_groq(api_key: str, model: str, messages: list, max_tokens: int = 400) -> str | None:
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.15,
    }).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    backoff = 5
    for attempt in range(4):
        try:
            if _USE_REQUESTS:
                resp = _requests.post(GROQ_API_URL, headers=headers,
                                      data=payload, timeout=30)
                if resp.status_code == 429:
                    print(f"  Rate limit — {backoff}sn bekleniyor...", flush=True)
                    time.sleep(backoff); backoff = min(backoff * 2, 64); continue
                if resp.status_code != 200:
                    print(f"  HTTP {resp.status_code}", flush=True); return None
                return resp.json()["choices"][0]["message"]["content"].strip()
            else:
                req = urllib.request.Request(GROQ_API_URL, data=payload,
                    headers={**headers, "User-Agent": "Mozilla/5.0"}, method="POST")
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read())["choices"][0]["message"]["content"].strip()
        except Exception as ex:
            if "429" in str(ex):
                print(f"  Rate limit — {backoff}sn bekleniyor...", flush=True)
                time.sleep(backoff); backoff = min(backoff * 2, 64)
            else:
                print(f"  Hata: {ex}", flush=True); return None
    return None


def translate_batch(api_key: str, model: str, word: str, sentences: list[str]) -> dict[int, str]:
    """Bir kelimeye ait birden fazla cümleyi tek seferde çevir."""
    numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sentences))
    prompt = (
        f"Almanca kelime: \"{word}\"\n\n"
        f"Aşağıdaki Almanca cümleleri Türkçeye çevir. "
        f"Sadece numaralı çevirileri yaz, açıklama ekleme:\n\n{numbered}"
    )
    messages = [
        {"role": "system", "content": "Sen Almanca-Türkçe profesyonel bir çevirmenisin. Sadece numaralı çevirileri ver, başka hiçbir şey yazma."},
        {"role": "user", "content": prompt},
    ]
    response = call_groq(api_key, model, messages, max_tokens=len(sentences) * 60 + 50)
    if not response:
        return {}

    result = {}
    for line in response.splitlines():
        m = re.match(r"^(\d+)[.)]\s*(.+)$", line.strip())
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(sentences):
                result[idx] = m.group(2).strip()
    return result


def _merge_save(mem_data: list, path) -> None:
    """Disk'teki güncel dosyayı okuyup sadece ornekler.turkce değişikliklerini uygular."""
    import threading
    if not hasattr(_merge_save, "_lock"):
        _merge_save._lock = threading.Lock()
    with _merge_save._lock:
        try:
            disk_data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            disk_data = mem_data
        disk_idx = {str(e.get("almanca","")): e for e in disk_data}
        for mem_entry in mem_data:
            key = str(mem_entry.get("almanca",""))
            disk_entry = disk_idx.get(key)
            if disk_entry is None:
                continue
            mem_ornekler = mem_entry.get("ornekler") or []
            disk_ornekler = disk_entry.get("ornekler") or []
            for i, mem_ex in enumerate(mem_ornekler):
                if i < len(disk_ornekler):
                    if (mem_ex.get("turkce") or "").strip() and not (disk_ornekler[i].get("turkce") or "").strip():
                        disk_ornekler[i]["turkce"] = mem_ex["turkce"]
                        if mem_ex.get("kaynak"):
                            disk_ornekler[i]["kaynak"] = mem_ex["kaynak"]
            if (mem_entry.get("ornek_turkce") or "").strip() and not (disk_entry.get("ornek_turkce") or "").strip():
                disk_entry["ornek_turkce"] = mem_entry["ornek_turkce"]
        path.write_text(json.dumps(disk_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key")
    parser.add_argument("--model", default="llama-3.1-8b-instant",
                        choices=["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "mixtral-8x7b-32768"])
    parser.add_argument("--limit", type=int, default=0, help="Max işlenecek entry sayısı")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    api_key = load_api_key(args.api_key)
    if not api_key:
        print("Groq API anahtarı bulunamadı. --api-key verin, GROQ_API_KEY ayarlayın veya data/manual/desktop_settings.json içine llm_api_key ekleyin.", flush=True)
        sys.exit(2)

    model_short = args.model.split("-")[1] if "-" in args.model else args.model[:8]

    print(f"Sözlük yükleniyor...", flush=True)
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))

    done: set[str] = set()
    if CHECKPOINT_PATH.exists():
        done = set(json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8")))

    # Group missing by entry
    tasks = []
    for entry in data:
        almanca = str(entry.get("almanca") or "").strip()
        if not almanca:
            continue
        key = almanca
        if key in done:
            continue
        missing_indices = [
            i for i, ex in enumerate(entry.get("ornekler") or [])
            if (ex.get("almanca") or "").strip()
            and (not (ex.get("turkce") or "").strip() or ex.get("turkce") == "-")
        ]
        if missing_indices:
            tasks.append((entry, key, missing_indices))

    print(f"Eksik çeviri olan entry: {len(tasks)}", flush=True)
    total_sentences = sum(len(t[2]) for t in tasks)
    print(f"Toplam eksik cümle: {total_sentences}", flush=True)

    if args.dry_run:
        print("Dry-run, çıkılıyor.")
        return

    if args.limit:
        tasks = tasks[: args.limit]

    updated_entries = 0
    updated_sentences = 0
    last_request = 0.0

    for idx, (entry, key, missing_indices) in enumerate(tasks):
        sentences = [entry["ornekler"][i]["almanca"] for i in missing_indices]
        almanca = str(entry.get("almanca") or "")

        print(f"[{idx+1}/{len(tasks)}] {almanca} ({len(sentences)} cümle)", flush=True)

        # Rate limit
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
                print(f"  → {sentences[local_idx][:50]} | {tr_text[:50]}", flush=True)
            updated_entries += 1
        else:
            print(f"  Çeviri alınamadı.", flush=True)

        done.add(key)

        if (idx + 1) % 20 == 0:
            _merge_save(data, DICT_PATH)
            CHECKPOINT_PATH.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
            print(f"  [Checkpoint: {updated_sentences} cümle çevrildi]", flush=True)

    _merge_save(data, DICT_PATH)
    CHECKPOINT_PATH.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
    print(f"\nBitti: {updated_entries} entry, {updated_sentences} cümle çevrildi.", flush=True)


if __name__ == "__main__":
    main()
