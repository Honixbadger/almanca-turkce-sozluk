#!/usr/bin/env python3
"""
enrich_groq_translations5.py
=============================
10 Groq API key rotation ile:
  1. Başlangıçta 3 key × birkaç model test eder, çalışanları bulur
  2. Eksik Türkçe çevirileri tamamlar (61 cümle)
  3. GPT Codex çevirilerinden kalite kontrolünden geçemeyenleri yeniden çevirir
  4. Key başına dakika limitini takip eder, dolunca sıradaki keye geçer

Kullanım:
    python scripts/enrich_groq_translations5.py
    python scripts/enrich_groq_translations5.py --dry-run
    python scripts/enrich_groq_translations5.py --model llama-3.3-70b-versatile
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import requests as _req
    _USE_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    _USE_REQUESTS = False

# ── Sabitler ──────────────────────────────────────────────────────────────────
DICT_PATH       = Path("output/dictionary.json")
CHECKPOINT_PATH = Path("output/groq_tr_checkpoint5.json")
GROQ_URL        = "https://api.groq.com/openai/v1/chat/completions"

# Groq ücretsiz tier: dakikada ~30 istek / key
REQUESTS_PER_MIN = 28          # güvenli sınır
COOLDOWN_SEC     = 62.0        # key limit dolunca bekle (1 dk + tampon)
MIN_INTERVAL     = 60.0 / REQUESTS_PER_MIN   # ~2.14 sn/istek

# Test edilecek modeller (hız × kalite dengesi)
CANDIDATE_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "llama3-70b-8192",
]

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


# ── API yardımcıları ──────────────────────────────────────────────────────────

def _post(api_key: str, payload_bytes: bytes) -> tuple[int, str]:
    """(status_code, body) döndürür."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if _USE_REQUESTS:
        r = _req.post(GROQ_URL, headers=headers, data=payload_bytes, timeout=30)
        return r.status_code, r.text
    else:
        req = urllib.request.Request(
            GROQ_URL, data=payload_bytes,
            headers={**headers, "User-Agent": "Mozilla/5.0"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return 200, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")


def call_groq(api_key: str, model: str, messages: list, max_tokens: int = 400) -> tuple[str | None, bool]:
    """(yanıt_metni | None, rate_limited: bool) döndürür."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.15,
    }).encode("utf-8")

    status, body = _post(api_key, payload)
    if status == 200:
        try:
            return json.loads(body)["choices"][0]["message"]["content"].strip(), False
        except Exception:
            return None, False
    elif status == 429:
        return None, True   # rate limited
    else:
        return None, False  # başka hata (403, 401 vb.)


# ── Model & key testi ─────────────────────────────────────────────────────────

def find_working_model(keys: list[str], candidates: list[str]) -> str | None:
    """İlk 3 key üzerinde test yaparak çalışan bir model bulur."""
    test_payload = json.dumps({
        "model": "",  # sonradan doldurulacak
        "messages": [{"role": "user", "content": "Translate to Turkish (one line only): Das Wetter ist schön."}],
        "max_tokens": 30,
        "temperature": 0.1,
    })

    test_keys = keys[:3]
    print("── Model testi ──────────────────────────")
    for model in candidates:
        for i, key in enumerate(test_keys, 1):
            payload = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": "Translate to Turkish (one line only): Das Wetter ist schön."}],
                "max_tokens": 30,
                "temperature": 0.1,
            }).encode("utf-8")
            status, body = _post(key, payload)
            if status == 200:
                try:
                    text = json.loads(body)["choices"][0]["message"]["content"].strip()
                    print(f"  ✓ {model} (key{i}): {text[:50]}")
                    return model
                except Exception:
                    pass
            elif status == 429:
                print(f"  ~ {model} (key{i}): rate limit, sonraki key...")
                continue
            else:
                print(f"  ✗ {model} (key{i}): HTTP {status}")
                break   # bu model tüm keylerle hatalı, sonraki modele geç
    return None


# ── KeyPool: key rotasyonu ve rate-limit takibi ───────────────────────────────

class KeyPool:
    def __init__(self, keys: list[str]):
        # Her key için: son_istek_zamani, dakikadaki_istek_sayısı, dakika_başlangıcı
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
        # Dakika penceresi geçtiyse sayacı sıfırla
        if now - s["window_start"] >= 60.0:
            s["count"] = 0
            s["window_start"] = now
        return s["count"] < REQUESTS_PER_MIN

    def get(self) -> tuple[str, int] | None:
        """Kullanılabilir bir (api_key, index) döndürür; yoksa None."""
        for _ in range(len(self.keys)):
            i = self.current % len(self.keys)
            if self._available(i):
                return self.keys[i], i
            self.current += 1
        return None

    def record_request(self, i: int) -> None:
        s = self.state[i]
        now = time.time()
        elapsed = now - s["last"]
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        s["last"] = time.time()
        if now - s["window_start"] >= 60.0:
            s["count"] = 0
            s["window_start"] = now
        s["count"] += 1
        self.current = (i + 1) % len(self.keys)   # round-robin

    def mark_rate_limited(self, i: int) -> None:
        self.state[i]["cooldown_until"] = time.time() + COOLDOWN_SEC
        print(f"  ⚠ key{i+1} rate limited → {COOLDOWN_SEC:.0f}sn bekleniyor")
        self.current = (i + 1) % len(self.keys)

    def wait_for_available(self) -> tuple[str, int]:
        """Kullanılabilir key çıkana kadar bekler."""
        while True:
            result = self.get()
            if result:
                return result
            # En yakın cooldown bitişini bul
            now = time.time()
            waits = []
            for s in self.state:
                if now < s["cooldown_until"]:
                    waits.append(s["cooldown_until"] - now)
            wait = min(waits) + 0.5 if waits else 2.0
            print(f"  Tüm keyler meşgul, {wait:.0f}sn bekleniyor...", flush=True)
            time.sleep(wait)


# ── Çeviri fonksiyonu ─────────────────────────────────────────────────────────

def translate_batch(pool: KeyPool, model: str, word: str, sentences: list[str]) -> dict[int, str]:
    numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sentences))
    messages = [
        {"role": "system", "content": (
            "Sen Almanca-Türkçe profesyonel bir çevirmenisin. "
            "Sadece numaralı çevirileri ver, başka hiçbir şey yazma."
        )},
        {"role": "user", "content": (
            f"Almanca kelime: \"{word}\"\n\n"
            f"Aşağıdaki Almanca cümleleri Türkçeye çevir. "
            f"Sadece numaralı çevirileri yaz:\n\n{numbered}"
        )},
    ]
    max_tokens = len(sentences) * 70 + 60

    for attempt in range(len(pool.keys) + 1):
        api_key, idx = pool.wait_for_available()
        pool.record_request(idx)
        result, rate_limited = call_groq(api_key, model, messages, max_tokens)
        if rate_limited:
            pool.mark_rate_limited(idx)
            continue
        if result:
            translations = {}
            for line in result.splitlines():
                m = re.match(r"^(\d+)[.)]\s*(.+)$", line.strip())
                if m:
                    i = int(m.group(1)) - 1
                    if 0 <= i < len(sentences):
                        translations[i] = m.group(2).strip()
            return translations
        break   # başka hata (403 vb.) → boş döndür
    return {}


# ── Kalite filtresi ───────────────────────────────────────────────────────────

def is_low_quality(de: str, tr: str) -> bool:
    """GPT Codex çevirisinin yeniden çevrilmesi gerekip gerekmediğini kontrol eder."""
    de = de.strip()
    tr = tr.strip()
    if not de or not tr:
        return False

    # URL veya kaynak satırı → çevrilemez, skip
    if "http" in tr or tr.startswith("↑") or tr.startswith("=") or tr.startswith("_"):
        return False

    # Çok kısa oran: DE uzunluğunun %20'sinden az ve DE 40+ karakter
    if len(de) > 40 and len(tr) < len(de) * 0.20:
        return True

    # Çeviri İngilizce gibi görünüyor (Türkçe harf yok, İngilizce kelime var)
    tr_lower = tr.lower()
    en_words = {"the ", " is ", " are ", " was ", " has ", " have ", " and ", " or ", " of "}
    tr_chars = set("şğıçİŞĞÇ")
    has_tr_char = any(c in tr for c in tr_chars)
    has_en_words = sum(1 for w in en_words if w in tr_lower) >= 2
    if not has_tr_char and has_en_words and len(tr) > 20:
        return True

    return False


# ── Ana iş akışı ──────────────────────────────────────────────────────────────

def collect_tasks(data: list[dict]) -> list[dict]:
    """
    Yeniden çevrilmesi gereken görevleri toplar:
      - turkce alanı boş olanlar
      - GPT Codex kaynaklı düşük kaliteli olanlar
    """
    tasks = []
    for entry in data:
        almanca = (entry.get("almanca") or "").strip()
        if not almanca:
            continue
        ornekler = entry.get("ornekler") or []
        indices = []
        reasons = []

        for i, ex in enumerate(ornekler):
            de = (ex.get("almanca") or "").strip()
            tr = (ex.get("turkce") or "").strip()
            kaynak = (ex.get("kaynak") or "").lower()
            if not de:
                continue

            if not tr:
                indices.append(i)
                reasons.append("eksik")
            elif "gpt codex" in kaynak or "codex" in kaynak:
                if is_low_quality(de, tr):
                    indices.append(i)
                    reasons.append("düşük kalite")

        if indices:
            tasks.append({
                "entry": entry,
                "almanca": almanca,
                "indices": indices,
                "reasons": reasons,
            })
    return tasks


def save(data: list[dict]) -> None:
    DICT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="", help="Zorla bu modeli kullan")
    parser.add_argument("--dry-run", action="store_true", help="Kaydetmeden görevleri listele")
    args = parser.parse_args()

    # ── 1. Model testi ────────────────────────────────────────────────────────
    if args.model:
        model = args.model
        print(f"Model: {model} (manuel seçim)")
    else:
        model = find_working_model(API_KEYS, CANDIDATE_MODELS)
        if not model:
            print("HATA: Çalışan model bulunamadı. Tüm keyler 403/hata veriyor.", flush=True)
            sys.exit(1)
        print(f"Seçilen model: {model}\n")

    # ── 2. Sözlük ve görev listesi ────────────────────────────────────────────
    print("Sözlük yükleniyor...", flush=True)
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))

    done: set[str] = set()
    if CHECKPOINT_PATH.exists():
        done = set(json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8")))

    all_tasks = collect_tasks(data)
    tasks = [t for t in all_tasks if t["almanca"] not in done]

    total_sentences = sum(len(t["indices"]) for t in tasks)
    eksik  = sum(1 for t in tasks for r in t["reasons"] if r == "eksik")
    kalite = sum(1 for t in tasks for r in t["reasons"] if r == "düşük kalite")

    print(f"Toplam görev (kelime): {len(tasks)}")
    print(f"  Eksik çeviri      : {eksik} cümle")
    print(f"  Düşük kalite      : {kalite} cümle")
    print(f"  Toplam cümle      : {total_sentences}")
    print(f"Zaten işlenmiş      : {len(done)} kelime (checkpoint)\n")

    if args.dry_run:
        print("── Dry-run: ilk 10 görev ────────────────")
        for t in tasks[:10]:
            for i, reason in zip(t["indices"], t["reasons"]):
                de = t["entry"]["ornekler"][i].get("almanca", "")[:60]
                tr = t["entry"]["ornekler"][i].get("turkce", "")[:50]
                print(f"  [{t['almanca']}] ({reason}) DE: {de}")
                if tr:
                    print(f"    Mevcut TR: {tr}")
        return

    if not tasks:
        print("Yapılacak iş yok, çıkılıyor.")
        return

    # ── 3. Çeviri döngüsü ────────────────────────────────────────────────────
    pool = KeyPool(API_KEYS)
    updated_entries = 0
    updated_sentences = 0

    for task_i, task in enumerate(tasks):
        entry    = task["entry"]
        almanca  = task["almanca"]
        indices  = task["indices"]
        ornekler = entry["ornekler"]
        sentences = [ornekler[i]["almanca"] for i in indices]

        reasons_str = ", ".join(set(task["reasons"]))
        print(f"[{task_i+1}/{len(tasks)}] {almanca} ({len(sentences)} cümle | {reasons_str})", flush=True)

        translations = translate_batch(pool, model, almanca, sentences)

        added = 0
        for local_i, tr_text in translations.items():
            real_i = indices[local_i]
            ornekler[real_i]["turkce"] = tr_text
            ornekler[real_i]["kaynak"] = f"groq-{model.split('-')[1]}"
            if real_i == 0 and not (entry.get("ornek_turkce") or "").strip():
                entry["ornek_turkce"] = tr_text
            de_preview = sentences[local_i][:45]
            print(f"  → {de_preview} | {tr_text[:45]}", flush=True)
            added += 1
            updated_sentences += 1

        if translations:
            updated_entries += 1

        done.add(almanca)

        # Her 15 kelimede checkpoint
        if (task_i + 1) % 15 == 0:
            save(data)
            CHECKPOINT_PATH.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
            print(f"  [Checkpoint: {updated_sentences} cümle çevrildi]", flush=True)

    save(data)
    CHECKPOINT_PATH.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"ÖZET")
    print(f"  Çeviri eklenen kelime : {updated_entries}")
    print(f"  Toplam eklenen cümle  : {updated_sentences}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
