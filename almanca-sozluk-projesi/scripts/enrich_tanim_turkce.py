#!/usr/bin/env python3
"""
enrich_tanim_turkce.py
=======================
tanim_almanca alanı dolu ama aciklama_turkce boş olan kayıtlara
Groq ile Türkçe tanım çevirisi ekler.

8.147 kayıt hedef — 10 key rotation, rate limit otomatik yönetilir.

Kullanım:
    python scripts/enrich_tanim_turkce.py
    python scripts/enrich_tanim_turkce.py --dry-run
    python scripts/enrich_tanim_turkce.py --limit 500
"""

from __future__ import annotations
import json, re, sys, time
from pathlib import Path
try:
    import requests as _requests
    _USE_REQUESTS = True
except ImportError:
    import urllib.request, urllib.error
    _USE_REQUESTS = False

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH       = Path("output/dictionary.json")
CHECKPOINT_PATH = Path("output/tanim_turkce_checkpoint.json")
GROQ_URL        = "https://api.groq.com/openai/v1/chat/completions"
MODEL           = "llama-3.3-70b-versatile"

REQUESTS_PER_MIN = 28
COOLDOWN_SEC     = 63.0
MIN_INTERVAL     = 60.0 / REQUESTS_PER_MIN
BATCH_SIZE       = 20   # tek API çağrısında kaç tanım çevrilir (büyük batch = daha az çağrı)
SAVE_EVERY       = 100  # kaç kelimede bir kaydet

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
    def __init__(self, keys):
        self.keys = keys
        self.state = [{"last": 0.0, "count": 0, "window_start": 0.0, "cooldown_until": 0.0}
                      for _ in keys]
        self.current = 0

    def _ok(self, i):
        now = time.time()
        s = self.state[i]
        if now < s["cooldown_until"]:
            return False
        if now - s["window_start"] >= 60.0:
            s["count"] = 0; s["window_start"] = now
        return s["count"] < REQUESTS_PER_MIN

    def get(self):
        for _ in range(len(self.keys)):
            i = self.current % len(self.keys)
            if self._ok(i):
                return self.keys[i], i
            self.current += 1
        return None

    def record(self, i):
        s = self.state[i]
        elapsed = time.time() - s["last"]
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        s["last"] = time.time()
        if time.time() - s["window_start"] >= 60.0:
            s["count"] = 0; s["window_start"] = time.time()
        s["count"] += 1
        self.current = (i + 1) % len(self.keys)

    def mark_limited(self, i):
        self.state[i]["cooldown_until"] = time.time() + COOLDOWN_SEC
        print(f"  ⚠ key{i+1} rate limit → {COOLDOWN_SEC:.0f}s", flush=True)
        self.current = (i + 1) % len(self.keys)

    def wait_get(self):
        while True:
            r = self.get()
            if r: return r
            now = time.time()
            waits = [s["cooldown_until"] - now for s in self.state if now < s["cooldown_until"]]
            wait = (min(waits) + 0.5) if waits else 2.0
            print(f"  Tüm keyler meşgul, {wait:.0f}s...", flush=True)
            time.sleep(wait)


# ── API ───────────────────────────────────────────────────────────────────────

def call_groq(pool: KeyPool, messages: list, max_tokens: int) -> str | None:
    payload = {"model": MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": 0.1}
    for _ in range(len(pool.keys) + 1):
        api_key, idx = pool.wait_get()
        pool.record(idx)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            if _USE_REQUESTS:
                r = _requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
                if r.status_code == 429:
                    pool.mark_limited(idx); continue
                if r.status_code != 200:
                    print(f"  HTTP {r.status_code}", flush=True); return None
                return r.json()["choices"][0]["message"]["content"].strip()
            else:
                import urllib.request, urllib.error
                data = json.dumps(payload).encode()
                req = urllib.request.Request(GROQ_URL, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if "429" in str(e):
                pool.mark_limited(idx); continue
            print(f"  Hata: {e}", flush=True); return None
    return None


def translate_batch(pool: KeyPool, items: list[tuple[str, str]]) -> dict[int, str]:
    """[(almanca, tanim_de), ...] → {index: turkce_tanim}"""
    numbered = "\n".join(
        f"{i+1}. [{w}]: {t[:200]}" for i, (w, t) in enumerate(items)
    )
    messages = [
        {"role": "system", "content": (
            "Sen Almanca sözlük tanımlarını Türkçeye çeviren uzmansın. "
            "Her tanımı kısa, doğal Türkçeyle çevir. "
            "Sadece numaralı çevirileri ver — başka hiçbir şey yazma."
        )},
        {"role": "user", "content": (
            f"Aşağıdaki Almanca sözlük tanımlarını Türkçeye çevir:\n\n{numbered}"
        )},
    ]
    max_tokens = len(items) * 60 + 50
    response = call_groq(pool, messages, max_tokens)
    if not response:
        return {}
    result = {}
    for line in response.splitlines():
        m = re.match(r"^(\d+)[.)]\s*(.+)$", line.strip())
        if m:
            i = int(m.group(1)) - 1
            if 0 <= i < len(items):
                result[i] = m.group(2).strip()
    return result


# ── Ana akış ──────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    print("Sözlük yükleniyor...", flush=True)
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))

    done: set[str] = set()
    if CHECKPOINT_PATH.exists():
        done = set(json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8")))
        print(f"  Checkpoint: {len(done):,} kayıt daha önce işlendi.", flush=True)

    # Hedef: tanim_almanca dolu, aciklama_turkce boş, işlenmemiş
    targets = []
    for rec in data:
        almanca = (rec.get("almanca") or "").strip()
        if not almanca or almanca in done:
            continue
        tanim_de = (rec.get("tanim_almanca") or "").strip()
        tanim_tr = (rec.get("aciklama_turkce") or "").strip()
        if tanim_de and not tanim_tr:
            targets.append(rec)

    print(f"  İşlenecek kayıt: {len(targets):,}", flush=True)
    if args.limit:
        targets = targets[:args.limit]

    if args.dry_run:
        print("\nDry-run — ilk 5 hedef:")
        for r in targets[:5]:
            print(f"  [{r['almanca']}] {r.get('tanim_almanca','')[:80]}")
        return

    if not targets:
        print("Yapılacak iş yok."); return

    pool = KeyPool(API_KEYS)
    added = 0
    # Lookup: almanca → index in data
    lookup = {(r.get("almanca") or "").strip(): i for i, r in enumerate(data)}

    # Batch'ler halinde işle
    batches = [targets[i:i+BATCH_SIZE] for i in range(0, len(targets), BATCH_SIZE)]
    for b_i, batch in enumerate(batches):
        items = [(r.get("almanca",""), r.get("tanim_almanca","")) for r in batch]
        print(f"[Batch {b_i+1}/{len(batches)}] {', '.join(w for w,_ in items[:3])}{'...' if len(items)>3 else ''}", flush=True)

        translations = translate_batch(pool, items)

        for local_i, tr_text in translations.items():
            rec = batch[local_i]
            almanca = (rec.get("almanca") or "").strip()
            idx = lookup.get(almanca)
            if idx is not None:
                data[idx]["aciklama_turkce"] = tr_text
                done.add(almanca)
                added += 1
                print(f"  ✓ [{almanca}] {tr_text[:70]}", flush=True)

        # Checkpoint işaretlenmemiş olanları da ekle
        for r in batch:
            done.add((r.get("almanca") or "").strip())

        if (b_i + 1) % (SAVE_EVERY // BATCH_SIZE) == 0:
            DICT_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
            CHECKPOINT_PATH.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
            print(f"  [Checkpoint: {added:,} çeviri eklendi]", flush=True)

    DICT_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
    CHECKPOINT_PATH.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"ÖZET: {added:,} kayda Türkçe tanım eklendi.")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
