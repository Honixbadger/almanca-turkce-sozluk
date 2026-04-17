#!/usr/bin/env python3
"""
API gerektirmeyen tüm local zenginleştirmeleri sıralı çalıştırır.
Çakışma olmadan tüm alanları doldurur.

Kullanım: python scripts/enrich_local_all.py
"""
import argparse, sys, json, sqlite3, re, unicodedata, subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_DICT = Path("output/dictionary.json")
DB   = Path("data/raw/downloads/de-tr.sqlite3")

def norm(t):
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().casefold()

def strip_art(w):
    p = w.strip().split(" ", 1)
    return p[1] if len(p) == 2 and norm(p[0]) in {"der","die","das"} else w.strip()

# ── 1. SQLite → aciklama_turkce ──────────────────────────────────────────────
def enrich_sqlite(data):
    if not DB.exists():
        print("SQLite DB bulunamadı, atlanıyor.", flush=True)
        return 0
    db = sqlite3.connect(str(DB))
    cur = db.cursor()
    updated = 0
    for entry in data:
        if entry.get("aciklama_turkce"):
            continue
        bare = strip_art(str(entry.get("almanca") or "")).strip()
        if not bare:
            continue
        cur.execute(
            "SELECT sense, trans_list FROM translation "
            "WHERE written_rep=? AND is_good=1 AND sense IS NOT NULL AND sense!='' "
            "ORDER BY score DESC LIMIT 4",
            (bare,),
        )
        rows = cur.fetchall()
        if rows:
            parts, seen = [], set()
            for sense, tr_list in rows:
                tr = (tr_list or "").strip().split(" | ")[0].strip()
                if tr and norm(tr) not in seen and len(tr) < 80:
                    seen.add(norm(tr))
                    sense_clean = (sense or "").strip()
                    parts.append(f"{sense_clean} → {tr}" if sense_clean and len(sense_clean) < 120 else tr)
            if parts:
                entry["aciklama_turkce"] = "; ".join(parts[:3])
                updated += 1
        else:
            cur.execute("SELECT trans_list FROM simple_translation WHERE written_rep=?", (bare,))
            row = cur.fetchone()
            if row and row[0]:
                tr_parts = [t.strip() for t in row[0].split(" | ") if t.strip() and len(t.strip()) < 50]
                if tr_parts:
                    entry["aciklama_turkce"] = ", ".join(tr_parts[:4])
                    updated += 1
    db.close()
    return updated

# ── 2. ODENet → sinonim / antonim ───────────────────────────────────────────
def enrich_odenet(data):
    try:
        import wn as wn_lib
    except ImportError:
        print("wn paketi yok, ODENet atlanıyor.", flush=True)
        return 0, 0
    try:
        wn_lib.download("odenet", progress=False)
        de = wn_lib.Wordnet("odenet")
    except Exception as e:
        print(f"ODENet yüklenemedi: {e}", flush=True)
        return 0, 0

    syn_updated = ant_updated = 0
    for entry in data:
        bare = strip_art(str(entry.get("almanca") or "")).strip()
        if not bare:
            continue
        try:
            words = de.words(bare)
        except Exception:
            continue
        if not words:
            continue
        synsets = []
        for w in words:
            synsets.extend(w.synsets())
        syn_terms, ant_terms = [], []
        seen = {norm(bare)}
        for ss in synsets:
            for w in ss.words():
                lm = str(w.lemmas()[0]) if w.lemmas() else str(w)
                if norm(lm) not in seen and 2 <= len(lm) <= 40:
                    seen.add(norm(lm))
                    syn_terms.append(lm)
            # antonyms
            for related_ss in ss.get_related("also"):
                for w in related_ss.words():
                    lm = str(w.lemmas()[0]) if w.lemmas() else str(w)
                    if norm(lm) not in seen:
                        ant_terms.append(lm)
        if syn_terms and not entry.get("sinonim"):
            entry["sinonim"] = syn_terms[:6]
            syn_updated += 1
        if ant_terms and not entry.get("antonim"):
            entry["antonim"] = ant_terms[:4]
            ant_updated += 1
    return syn_updated, ant_updated

# ── Main ─────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input-path", default=str(DEFAULT_DICT))
    p.add_argument("--output-path", default="")
    return p.parse_args()


args = parse_args()
DICT = Path(args.input_path)
OUT = Path(args.output_path) if args.output_path else DICT

print("=" * 50, flush=True)
print("Local zenginleştirme başlıyor", flush=True)
print("=" * 50, flush=True)

print("\n[1/2] Sözlük yükleniyor...", flush=True)
data = json.loads(DICT.read_text(encoding="utf-8"))
print(f"  {len(data):,} kayıt", flush=True)

print("\n[2/3] SQLite (de-tr) → aciklama_turkce", flush=True)
n = enrich_sqlite(data)
print(f"  ✓ {n:,} kayıt güncellendi", flush=True)

print("\n[3/3] ODENet → sinonim / antonim", flush=True)
ns, na = enrich_odenet(data)
print(f"  ✓ eş anlamlı: {ns:,} | zıt anlamlı: {na:,}", flush=True)

print("\nKaydediliyor...", flush=True)
OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("✓ Kaydedildi.", flush=True)

# İstatistik
print("\n── Güncel İstatistik ──", flush=True)
fields = ["aciklama_turkce","sinonim","antonim","telaffuz","baglamlar"]
for f in fields:
    c = sum(1 for e in data if e.get(f))
    print(f"  {f}: {c:,}/{len(data):,} ({100*c//len(data)}%)", flush=True)
