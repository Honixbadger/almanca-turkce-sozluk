#!/usr/bin/env python3
"""
enrich_verb_patterns_groq.py
=============================
Sözlükteki fiil_kaliplari eksik olan fiiller için Groq üzerinden
Almanca valenz kalıpları (Valenzmuster) üretir ve ekler.

Her fiil için 2-3 tipik kullanım kalıbı + Türkçe açıklama alır.
Format: {"kalip": "etw. kaufen", "turkce": "bir şey satın almak", ...}
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
CHECKPOINT_PATH = PROJECT_ROOT / "output" / "verb_patterns_checkpoint.json"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

MODEL = "llama-3.3-70b-versatile"
SOURCE = "Groq / LLaMA-3.3-70B (otomatik kalıp)"
MAX_PATTERNS = 3
BATCH_SAVE_EVERY = 25

REQUESTS_PER_MIN = 28        # Key başına güvenli limit
COOLDOWN_SEC     = 63.0      # Rate limit yiyince bekleme
MIN_INTERVAL     = 60.0 / REQUESTS_PER_MIN  # ~2.14s/istek

API_KEYS = [
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
]


# ── KeyPool ───────────────────────────────────────────────────────────────────

class KeyPool:
    def __init__(self, keys: list[str]):
        self.keys = keys
        self.state: list[dict] = [
            {"last": 0.0, "count": 0, "window_start": 0.0, "cooldown_until": 0.0}
            for _ in keys
        ]
        self.current = 0

    def _available(self, i: int) -> bool:
        now = time.time()
        s = self.state[i]
        if now < s["cooldown_until"]:
            return False
        if now - s["window_start"] >= 60.0:
            s["count"] = 0
            s["window_start"] = now
        return s["count"] < REQUESTS_PER_MIN

    def get(self) -> tuple[str, int] | None:
        for _ in range(len(self.keys)):
            i = self.current % len(self.keys)
            if self._available(i):
                return self.keys[i], i
            self.current += 1
        return None

    def record(self, i: int) -> None:
        s = self.state[i]
        now = time.time()
        elapsed = now - s["last"]
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        s["last"] = time.time()
        if time.time() - s["window_start"] >= 60.0:
            s["count"] = 0
            s["window_start"] = time.time()
        s["count"] += 1
        self.current = (i + 1) % len(self.keys)

    def mark_limited(self, i: int) -> None:
        self.state[i]["cooldown_until"] = time.time() + COOLDOWN_SEC
        print(f"  ⚠ key{i+1} rate limit → {COOLDOWN_SEC:.0f}s bekleniyor", flush=True)
        self.current = (i + 1) % len(self.keys)

    def wait_get(self) -> tuple[str, int]:
        while True:
            r = self.get()
            if r:
                return r
            now = time.time()
            waits = [s["cooldown_until"] - now for s in self.state if now < s["cooldown_until"]]
            wait = (min(waits) + 0.5) if waits else 2.0
            print(f"  Tüm keyler meşgul, {wait:.0f}s bekleniyor...", flush=True)
            time.sleep(wait)


# ── API çağrısı ───────────────────────────────────────────────────────────────

def call_groq(pool: KeyPool, messages: list[dict], max_tokens: int = 300) -> str | None:
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }).encode("utf-8")

    for _ in range(len(pool.keys) + 1):
        api_key, idx = pool.wait_get()
        pool.record(idx)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AlmancaSozluk/1.0",
        }
        try:
            req = urllib.request.Request(GROQ_API_URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as ex:
            if ex.code == 429:
                pool.mark_limited(idx)
                continue
            print(f"  HTTP {ex.code}", flush=True)
            return None
        except Exception as ex:
            print(f"  Hata: {ex}", flush=True)
            return None
    return None


def generate_patterns(pool: KeyPool, verb: str, turkce: str) -> list[dict]:
    """Bir fiil için valenz kalıpları üret."""
    turkce_hint = f' (Türkçe: "{turkce}")' if turkce else ""
    prompt = (
        f'Almanca fiil: "{verb}"{turkce_hint}\n\n'
        f'Bu fiilin en yaygın {MAX_PATTERNS} kullanım kalıbını (Valenzmuster/Ergänzungen) listele.\n'
        'Her satırda: ALMANCA_KALIP | TÜRKÇE_AÇIKLAMA\n'
        'Kısaltmalar: jd. = jemand (birisi, Nom), jdn. = jemanden (birini, Akk), '
        'jdm. = jemandem (birine, Dat), etw. = etwas (bir şey, Akk), '
        'irgendwo = bir yerde, irgendwohin = bir yere\n\n'
        'Örnek format:\n'
        'etw. kaufen | bir şey satın almak\n'
        'jdm. etw. kaufen | birine bir şey satın almak\n\n'
        'Sadece kalıpları yaz, açıklama veya başlık ekleme.'
    )
    messages = [
        {
            "role": "system",
            "content": (
                "Sen Almanca dilbilgisi uzmanısın. "
                "Almanca fiillerin valenz yapılarını (Ergänzungsrahmen) biliyorsun. "
                "Sadece istenen formatta cevap ver."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    response = call_groq(pool, messages, max_tokens=250)
    if not response:
        return []

    patterns = []
    for line in response.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|", 1)
        if len(parts) != 2:
            continue
        kalip_de = parts[0].strip()
        kalip_tr = parts[1].strip()
        # Temel doğrulama
        if not kalip_de or not kalip_tr:
            continue
        if len(kalip_de) > 120 or len(kalip_tr) > 120:
            continue
        # Fiil adı geçmeli veya makul bir yapı olmalı
        patterns.append({
            "kalip": kalip_de,
            "turkce": kalip_tr,
            "ornek_almanca": "",
            "ornek_turkce": "",
            "kaynak": SOURCE,
        })
        if len(patterns) >= MAX_PATTERNS:
            break

    return patterns


def main() -> None:
    print("=" * 65)
    print("enrich_verb_patterns_groq.py — Fiil Kalıp Zenginleştirme")
    print(f"Model: {MODEL}")
    print("=" * 65)

    pool = KeyPool(API_KEYS)
    print(f"  {len(API_KEYS)} Groq API anahtarı yüklendi.")

    dictionary: list[dict] = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(dictionary):,} kayıt yüklendi.")

    # Checkpoint
    done: set[str] = set()
    if CHECKPOINT_PATH.exists():
        try:
            done = set(json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8")))
            print(f"  Checkpoint: {len(done)} fiil daha önce işlendi.")
        except Exception:
            pass

    # Hedef: fiil_kaliplari eksik veya boş olan fiiller
    targets: list[tuple[int, dict]] = []
    for i, rec in enumerate(dictionary):
        tur = (rec.get("tur") or "").strip().casefold()
        if tur not in {"fiil", "verb"}:
            continue
        almanca = (rec.get("almanca") or "").strip()
        if not almanca:
            continue
        if almanca in done:
            continue
        kaliplar = rec.get("fiil_kaliplari") or []
        if len(kaliplar) >= 2:  # Zaten 2+ kalıp var, atla
            continue
        targets.append((i, rec))

    print(f"  İşlenecek fiil: {len(targets):,}")
    print()

    updated = 0
    skipped = 0

    for task_num, (dict_idx, rec) in enumerate(targets, start=1):
        almanca = (rec.get("almanca") or "").strip()
        turkce = (rec.get("turkce") or "").strip()
        existing_k: list[dict] = list(rec.get("fiil_kaliplari") or [])
        existing_kn = {(k.get("kalip") or k.get("kalip_de") or "").strip().casefold()
                       for k in existing_k}

        print(f"[{task_num}/{len(targets)}] {almanca}", flush=True)

        patterns = generate_patterns(pool, almanca, turkce)
        if not patterns:
            print(f"  Kalıp üretilemedi.", flush=True)
            skipped += 1
            done.add(almanca)
            continue

        added = 0
        for p in patterns:
            kn = p["kalip"].strip().casefold()
            if kn and kn not in existing_kn:
                existing_k.append(p)
                existing_kn.add(kn)
                added += 1
                print(f"  + {p['kalip']} | {p['turkce']}", flush=True)

        if added:
            dictionary[dict_idx]["fiil_kaliplari"] = existing_k
            updated += 1

        done.add(almanca)

        if task_num % BATCH_SAVE_EVERY == 0:
            DICT_PATH.write_text(
                json.dumps(dictionary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            CHECKPOINT_PATH.write_text(
                json.dumps(sorted(done), ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"  [Checkpoint: {updated} fiil güncellendi]", flush=True)

    # Son kayıt
    DICT_PATH.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    CHECKPOINT_PATH.write_text(
        json.dumps(sorted(done), ensure_ascii=False),
        encoding="utf-8",
    )

    # Özet
    verbs = [r for r in dictionary if (r.get("tur") or "").casefold() in {"fiil", "verb"}]
    has_kalip = sum(1 for r in verbs if r.get("fiil_kaliplari"))
    tv = len(verbs)

    print(f"\n{'=' * 65}")
    print("SONUÇ")
    print(f"  İşlenen fiil          : {len(targets):,}")
    print(f"  Güncellenen fiil      : {updated:,}")
    print(f"  Atlanan (kalıp yok)   : {skipped:,}")
    print()
    print(f"  fiil_kaliplari dolu   : {has_kalip:,} / {tv:,}  (%{100 * has_kalip // max(tv, 1)})")
    print(f"{'=' * 65}")
    print(f"\nKaydedildi: {DICT_PATH}")


if __name__ == "__main__":
    main()
