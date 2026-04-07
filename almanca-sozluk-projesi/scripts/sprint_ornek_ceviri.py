#!/usr/bin/env python3
"""
sprint_ornek_ceviri.py  –  v2 (düzeltilmiş key rotasyon)
==========================================================
5 dakika boyunca tüm Groq keylerini sırayla döndürerek
ornekler[].turkce alanlarını max hızda doldurur.

10 key × 28 RPM = 280 çağrı/dk × 12 cümle/çağrı = ~3.360 cümle/dk
5 dakikada teorik maks: ~16.800 örnek cümle
"""

from __future__ import annotations
import argparse, json, re, sys, time
from pathlib import Path

try:
    import requests as _req; USE_REQ = True
except ImportError:
    import urllib.request; USE_REQ = False

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH  = Path(__file__).resolve().parents[1] / "output" / "dictionary.json"
CKPT_PATH  = Path(__file__).resolve().parents[1] / "output" / "ornek_ceviri_checkpoint.json"
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
MODEL      = "llama-3.3-70b-versatile"
BATCH      = 15       # bir çağrıda kaç cümle
SAVE_EVERY = 500      # kaç çeviride bir kaydet
RPM        = 28       # key başına dakikada max istek
MIN_GAP    = 60.0 / RPM   # key başına min bekleme (≈2.14s)

import os as _os
API_KEYS = [k.strip() for k in _os.environ.get("GROQ_API_KEYS", "").split(",") if k.strip()]
if not API_KEYS:
    print("HATA: GROQ_API_KEYS env degiskeni eksik.", file=sys.stderr); sys.exit(1)
N = len(API_KEYS)


class KeyPool:
    """Her key için son istek zamanını ve cooldown'ı takip eder."""
    def __init__(self):
        self.last_used  = [0.0] * N
        self.cooldown   = [0.0] * N
        self.win_start  = [time.time()] * N
        self.win_count  = [0] * N
        self.ptr        = 0

    def next(self) -> tuple[str, int]:
        """Uygun ilk key'i döndür, gerekirse kısa bekle."""
        for attempt in range(N * 3):
            i = self.ptr % N
            self.ptr += 1
            now = time.time()

            # Cooldown kontrolü
            if now < self.cooldown[i]:
                continue

            # Dakika penceresi sıfırla
            if now - self.win_start[i] >= 60.0:
                self.win_start[i] = now
                self.win_count[i] = 0

            # RPM kontrolü
            if self.win_count[i] >= RPM:
                continue

            # Min interval kontrolü (rate limit'e çarpmamak için)
            gap = MIN_GAP - (now - self.last_used[i])
            if gap > 0:
                time.sleep(gap)

            self.last_used[i] = time.time()
            self.win_count[i] += 1
            return API_KEYS[i], i

        # Tüm keyler meşgul → en erken açılacak olanı bekle
        now = time.time()
        waits = []
        for i in range(N):
            if now < self.cooldown[i]:
                waits.append(self.cooldown[i] - now)
            else:
                remaining = 60.0 - (now - self.win_start[i])
                if self.win_count[i] >= RPM and remaining > 0:
                    waits.append(remaining)
        wait = (min(waits) + 0.5) if waits else 2.0
        print(f"  Tüm keyler meşgul, {wait:.0f}s bekleniyor...", flush=True)
        time.sleep(wait)
        return self.next()

    def mark_limited(self, i: int):
        self.cooldown[i] = time.time() + 65.0
        print(f"  ⚠ key{i+1} rate-limit → 65s", flush=True)


def translate_batch(pool: KeyPool, sentences: list[str]) -> dict[int, str]:
    numbered = "\n".join(f"{i+1}. {s[:200]}" for i, s in enumerate(sentences))
    messages = [
        {"role": "system", "content":
            "Sen Almanca cümleleri doğal Türkçeye çeviren uzmansın. "
            "Sadece numaralı çevirileri yaz, başka açıklama ekleme."},
        {"role": "user", "content":
            f"Şu Almanca cümleleri Türkçeye çevir:\n\n{numbered}"},
    ]
    payload = {"model": MODEL, "messages": messages,
               "max_tokens": len(sentences) * 50 + 60, "temperature": 0.1}

    key, idx = pool.next()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        if USE_REQ:
            r = _req.post(GROQ_URL, headers=headers, json=payload, timeout=30)
            if r.status_code == 429:
                pool.mark_limited(idx)
                return {}
            if r.status_code != 200:
                print(f"  HTTP {r.status_code}", flush=True)
                return {}
            text = r.json()["choices"][0]["message"]["content"].strip()
        else:
            import urllib.request
            req = urllib.request.Request(GROQ_URL,
                  data=json.dumps(payload).encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = json.loads(resp.read())["choices"][0]["message"]["content"].strip()

        out = {}
        for line in text.splitlines():
            m = re.match(r"^(\d+)[.)]\s*(.+)$", line.strip())
            if m:
                i = int(m.group(1)) - 1
                if 0 <= i < len(sentences):
                    out[i] = m.group(2).strip()
        return out

    except Exception as e:
        if "429" in str(e):
            pool.mark_limited(idx)
        else:
            print(f"  Hata: {e}", flush=True)
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sure", type=int, default=300)
    args = parser.parse_args()

    deadline   = time.time() + args.sure
    start_time = time.time()

    print(f"Sozluk yukleniyor... ({args.sure}s sprint, {N} key)", flush=True)
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))

    done: set[str] = set()
    if CKPT_PATH.exists():
        done = set(json.loads(CKPT_PATH.read_text(encoding="utf-8")))
        print(f"  Checkpoint: {len(done):,} zaten tamamlandı", flush=True)

    # Kuyruk: (rec_idx, ornek_idx, almanca_cumle)
    queue = []
    for ri, rec in enumerate(data):
        for oi, ornek in enumerate(rec.get("ornekler", [])):
            alm = ornek.get("almanca", "").strip()
            tr  = ornek.get("turkce", "").strip()
            key = f"{ri}:{oi}"
            if alm and not tr and key not in done:
                queue.append((ri, oi, alm))

    total = len(queue)
    print(f"  Çevrilecek: {total:,} örnek cümle", flush=True)
    if not queue:
        print("Yapılacak iş yok."); return

    pool    = KeyPool()
    filled  = 0
    ptr     = 0
    last_log = time.time()

    while time.time() < deadline and ptr < len(queue):
        # Batch hazırla
        batch_items = queue[ptr : ptr + BATCH]
        ptr += len(batch_items)
        if not batch_items:
            break

        sentences = [item[2] for item in batch_items]
        translations = translate_batch(pool, sentences)

        for local_i, tr in translations.items():
            ri, oi, _ = batch_items[local_i]
            data[ri]["ornekler"][oi]["turkce"] = tr
            done.add(f"{ri}:{oi}")
            filled += 1

        # Periyodik log
        if time.time() - last_log >= 15:
            elapsed = int(time.time() - start_time)
            kalan   = max(0, int(deadline - time.time()))
            hiz     = filled / max(elapsed, 1) * 60
            print(f"  [{elapsed}s | {kalan}s kaldı] {filled:,} çeviri | ~{hiz:.0f}/dk", flush=True)
            last_log = time.time()

        # Periyodik kaydet
        if filled > 0 and filled % SAVE_EVERY == 0:
            DICT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            CKPT_PATH.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
            print(f"  [Kaydedildi: {filled:,}]", flush=True)

    # Son kaydet
    DICT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    CKPT_PATH.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")

    elapsed = int(time.time() - start_time)
    print(f"\n{'='*55}", flush=True)
    print(f"Süre         : {elapsed}s", flush=True)
    print(f"Toplam çeviri: {filled:,} / {total:,}", flush=True)
    print(f"Ortalama hız : {filled/max(elapsed,1)*60:.0f} çeviri/dk", flush=True)
    print(f"{'='*55}", flush=True)


if __name__ == "__main__":
    main()
