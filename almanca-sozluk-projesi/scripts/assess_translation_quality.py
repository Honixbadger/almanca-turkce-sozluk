#!/usr/bin/env python3
"""
assess_translation_quality.py
==============================
DWDS'ten Almanca tanım çeker, Groq ile Türkçe çeviriyle karşılaştırır.
Potansiyel hatalı çevirileri raporlar.

Strateji:
  1. zipf_skoru yüksek (sık kullanılan) kelimelerden örneklem al
  2. DWDS HTML → tanım, wortart, artikel
  3. Groq: "Bu tanıma göre bu çeviri doğru mu?"
  4. Şüphelileri output/translation_quality_report.json'a yaz

Kullanım:
    python scripts/assess_translation_quality.py --sample 300
    python scripts/assess_translation_quality.py --sample 300 --dry-run
"""
from __future__ import annotations
import argparse, json, re, sys, time, urllib.request, urllib.error
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH    = Path("output/dictionary.json")
REPORT_PATH  = Path("output/translation_quality_report.json")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
MODEL        = "llama-3.3-70b-versatile"
DWDS_DELAY   = 0.3   # DWDS'e nazik ol
GROQ_BATCH   = 6     # tek Groq çağrısında kaç kelime

REQUESTS_PER_MIN = 28
COOLDOWN_SEC     = 63.0
MIN_INTERVAL     = 60.0 / REQUESTS_PER_MIN

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
        if now < s["cooldown_until"]: return False
        if now - s["window_start"] >= 60.0:
            s["count"] = 0; s["window_start"] = now
        return s["count"] < REQUESTS_PER_MIN

    def get(self):
        for _ in range(len(self.keys)):
            i = self.current % len(self.keys)
            if self._ok(i): return self.keys[i], i
            self.current += 1
        return None

    def record(self, i):
        s = self.state[i]
        elapsed = time.time() - s["last"]
        if elapsed < MIN_INTERVAL: time.sleep(MIN_INTERVAL - elapsed)
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


# ── DWDS ─────────────────────────────────────────────────────────────────────

def dwds_fetch(word: str) -> dict:
    """DWDS HTML'den tanım, wortart ve artikel çıkarır."""
    from urllib.parse import quote
    url = f"https://www.dwds.de/wb/{quote(word)}"
    req = urllib.request.Request(url, headers={"User-Agent": "almanca-sozluk-qa/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode("utf-8")
    except Exception:
        return {}

    # Tanımlar
    defs = re.findall(
        r'<span[^>]+class="[^"]*dwdswb-definition[^"]*"[^>]*>(.*?)</span>',
        html, re.DOTALL
    )
    clean_defs = []
    for d in defs[:4]:
        t = re.sub(r"<[^>]+>", "", d).strip()
        t = re.sub(r"\s+", " ", t)
        if t and len(t) > 8:
            clean_defs.append(t)

    # Wortart
    wortart_m = re.search(r'<span[^>]+class="[^"]*dwdswb-wortart[^"]*"[^>]*>(.*?)</span>', html)
    wortart = re.sub(r"<[^>]+>", "", wortart_m.group(1)).strip() if wortart_m else ""

    # Artikel (Grammatik başlığından)
    artikel_m = re.search(r'\b(der|die|das)\b.*?<span[^>]+class="[^"]*dwdswb-ft-[^"]*"', html)
    artikel = artikel_m.group(1) if artikel_m else ""

    return {"dwds_defs": clean_defs, "dwds_wortart": wortart, "dwds_artikel": artikel}


# ── Groq kalite değerlendirmesi ───────────────────────────────────────────────

RATE_LABELS = {1: "YANLIŞ", 2: "ZAYIF", 3: "KABUL", 4: "İYİ", 5: "MÜKEMMEL"}

def assess_batch(pool: KeyPool, items: list[dict]) -> list[dict]:
    """
    Her item: {almanca, turkce, dwds_defs}
    Groq'a: 1-5 arası puan + kısa gerekçe ister.
    """
    numbered = "\n".join(
        f"{i+1}. [{it['almanca']}] "
        f"DWDS tanım: \"{'; '.join(it['dwds_defs'][:2])}\" "
        f"→ Türkçe çeviri: \"{it['turkce']}\""
        for i, it in enumerate(items)
    )
    messages = [
        {"role": "system", "content": (
            "Sen Almanca-Türkçe çeviri kalitesini değerlendiren bir uzmansın. "
            "Her kelime için DWDS tanımına bakarak Türkçe çeviriye 1-5 puan ver.\n"
            "1=Tamamen yanlış, 2=Zayıf/eksik, 3=Kabul edilebilir, 4=İyi, 5=Mükemmel\n"
            "Format (sadece bunu yaz, başka hiçbir şey):\n"
            "1. PUAN|gerekçe (max 10 kelime)\n"
            "2. PUAN|gerekçe\n..."
        )},
        {"role": "user", "content": numbered},
    ]
    payload = json.dumps({"model": MODEL, "messages": messages,
                          "max_tokens": len(items) * 40 + 30,
                          "temperature": 0.1}).encode()

    for _ in range(len(pool.keys) + 1):
        api_key, idx = pool.wait_get()
        pool.record(idx)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            req = urllib.request.Request(GROQ_URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read())["choices"][0]["message"]["content"].strip()
            # Parse
            results = list(items)
            for line in resp.splitlines():
                m = re.match(r"^(\d+)[.)]\s*(\d)[|:]\s*(.+)$", line.strip())
                if m:
                    i = int(m.group(1)) - 1
                    if 0 <= i < len(results):
                        score = int(m.group(2))
                        results[i]["skor"] = score
                        results[i]["gerekcе"] = m.group(3).strip()
                        results[i]["etiket"] = RATE_LABELS.get(score, "?")
            return results
        except urllib.error.HTTPError as e:
            if e.code == 429:
                pool.mark_limited(idx); continue
            return items
        except Exception as e:
            print(f"  Hata: {e}", flush=True); return items
    return items


# ── Örneklem seçimi ───────────────────────────────────────────────────────────

SKIP_TYPES = {"zamir", "pronomen", "artikel", "determiner", "partikel",
              "interjektion", "konjunktion", "präposition", "preposition",
              "numerale", "zahl"}

def select_sample(data: list[dict], n: int) -> list[dict]:
    """
    İçerik kelimeleri (isim, fiil, sıfat, zarf) arasından
    sık kullanılan + şüpheli çevirilerden karma örneklem.
    """
    candidates = []
    for rec in data:
        almanca = (rec.get("almanca") or "").strip()
        turkce  = (rec.get("turkce") or "").strip()
        tur     = (rec.get("tur") or "").strip().casefold()
        if not almanca or not turkce or len(turkce) < 2:
            continue
        # İşlev kelimelerini (zamir, artikel, edat vb.) atla
        if any(skip in tur for skip in SKIP_TYPES):
            continue
        # Tek harfli, çok uzun veya söz öbeği olanları atla
        if " " in almanca or len(almanca) < 3 or len(almanca) > 25:
            continue
        zipf = float(rec.get("zipf_skoru") or 0)
        # Şüphe skoru
        suspicion = 0
        if len(turkce) < 4:
            suspicion += 3
        if len(turkce.split(";")) > 5:
            suspicion += 1
        # Kaynak zayıfsa şüphe artar
        kaynak = (rec.get("kaynak") or "").lower()
        if "groq" in kaynak or "codex" in kaynak:
            suspicion += 1
        candidates.append((rec, zipf, suspicion))

    # Sıralama: önce şüpheli, sonra sık kullanılan
    candidates.sort(key=lambda x: (-x[2], -x[1]))

    # Her kelime türünden dengeli örneklem
    by_type: dict[str, list] = {}
    for rec, zipf, sus in candidates:
        t = (rec.get("tur") or "diğer").casefold()
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(rec)

    selected = []
    types = list(by_type.keys())
    per_type = max(1, n // max(len(types), 1))
    for t in types:
        selected.extend(by_type[t][:per_type])
    # Kalan slotları doldur
    all_remaining = [r for t in types for r in by_type[t][per_type:]]
    selected.extend(all_remaining[:max(0, n - len(selected))])

    return selected[:n]


# ── Ana akış ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Sözlük yükleniyor...", flush=True)
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    sample = select_sample(data, args.sample)
    print(f"  Örneklem: {len(sample)} kelime\n", flush=True)

    if args.dry_run:
        print("Dry-run — ilk 10 kelime:")
        for r in sample[:10]:
            print(f"  [{r['almanca']}] ({r.get('tur','?')}) → {r.get('turkce','')[:50]}")
        return

    pool = KeyPool(API_KEYS)
    results = []

    # 1. DWDS'ten tanım çek
    print("DWDS tanımları çekiliyor...", flush=True)
    dwds_ok = 0
    for i, rec in enumerate(sample):
        word = rec.get("almanca", "").strip()
        # artikel varsa çıkar (der/die/das Wort → Wort)
        bare = re.sub(r"^(der|die|das)\s+", "", word, flags=re.I)
        info = dwds_fetch(bare)
        time.sleep(DWDS_DELAY)
        results.append({
            "almanca":      word,
            "turkce":       (rec.get("turkce") or "").strip(),
            "tur":          (rec.get("tur") or "").strip(),
            "zipf":         rec.get("zipf_skoru", 0),
            "dwds_defs":    info.get("dwds_defs", []),
            "dwds_wortart": info.get("dwds_wortart", ""),
            "skor":         None,
            "etiket":       None,
            "gerekçe":      None,
        })
        if info.get("dwds_defs"):
            dwds_ok += 1
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(sample)} DWDS sorgu ({dwds_ok} tanım bulundu)", flush=True)

    print(f"  Toplam DWDS tanım: {dwds_ok}/{len(sample)}\n", flush=True)

    # DWDS tanımı olmayanları filtrele (değerlendirilemiyor)
    with_def = [r for r in results if r["dwds_defs"]]
    without_def = [r for r in results if not r["dwds_defs"]]
    print(f"  Tanımsız (değerlendirilemiyor): {len(without_def)}", flush=True)
    print(f"  Değerlendirilecek: {len(with_def)}\n", flush=True)

    # 2. Groq ile değerlendir
    print("Groq ile çeviri kalitesi değerlendiriliyor...", flush=True)
    batches = [with_def[i:i+GROQ_BATCH] for i in range(0, len(with_def), GROQ_BATCH)]
    for b_i, batch in enumerate(batches):
        print(f"  Batch {b_i+1}/{len(batches)}: {', '.join(r['almanca'] for r in batch)}", flush=True)
        assessed = assess_batch(pool, batch)
        for item in assessed:
            for r in with_def:
                if r["almanca"] == item["almanca"]:
                    r.update(item)
                    break

    # 3. Rapor
    all_results = with_def + without_def
    all_results.sort(key=lambda r: (r.get("skor") or 99))

    # Özet istatistik
    scored = [r for r in all_results if r.get("skor")]
    dist = {s: sum(1 for r in scored if r.get("skor") == s) for s in range(1, 6)}
    problems = [r for r in scored if r.get("skor", 5) <= 2]

    print(f"\n{'='*55}")
    print("SONUÇ")
    print(f"  Değerlendirilen   : {len(scored)}")
    print(f"  Puan dağılımı     : " + " | ".join(f"{RATE_LABELS[s]}:{dist[s]}" for s in range(1,6)))
    print(f"  Sorunlu (1-2 puan): {len(problems)}")
    print(f"{'='*55}\n")

    if problems:
        print("Sorunlu çeviriler (ilk 15):")
        for r in problems[:15]:
            print(f"  [{r['almanca']}] ({r.get('etiket')}) "
                  f"TR:\"{r['turkce']}\" "
                  f"DWDS:\"{'; '.join(r['dwds_defs'][:1])[:60]}\" "
                  f"| {r.get('gerekçe','')}")

    REPORT_PATH.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\nRapor: {REPORT_PATH}")


if __name__ == "__main__":
    main()
