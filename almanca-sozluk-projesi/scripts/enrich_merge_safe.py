#!/usr/bin/env python3
"""
Güvenli merge: dictionary.json'ı OKUR, sadece boş alanları doldurur, kaydeder.
Diğer scriptlerle çakışmaz - sadece eksik alanları yazar.

Kullanım: python scripts/enrich_merge_safe.py
Birden fazla kez çalıştırılabilir, idempotent.
"""
import sys, json, sqlite3, re, unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT = Path("output/dictionary.json")
DB   = Path("data/raw/downloads/de-tr.sqlite3")

def norm(t):
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().casefold()

def strip_art(w):
    p = w.strip().split(" ", 1)
    return p[1] if len(p)==2 and norm(p[0]) in {"der","die","das"} else w.strip()

print("Yukleniyor...", flush=True)
data = json.loads(DICT.read_text(encoding="utf-8"))

# --- SQLite ---
if DB.exists():
    db = sqlite3.connect(str(DB))
    cur = db.cursor()
    n_acik = 0
    for entry in data:
        if entry.get("aciklama_turkce"):
            continue
        bare = strip_art(str(entry.get("almanca") or "")).strip()
        if not bare:
            continue
        cur.execute(
            "SELECT sense, trans_list FROM translation "
            "WHERE written_rep=? AND is_good=1 AND sense IS NOT NULL AND sense!='' "
            "ORDER BY score DESC LIMIT 4", (bare,))
        rows = cur.fetchall()
        if rows:
            parts, seen = [], set()
            for sense, tr_list in rows:
                tr = (tr_list or "").strip().split(" | ")[0].strip()
                if tr and norm(tr) not in seen and len(tr) < 80:
                    seen.add(norm(tr))
                    sc = (sense or "").strip()
                    parts.append(f"{sc} -> {tr}" if sc and len(sc) < 120 else tr)
            if parts:
                entry["aciklama_turkce"] = "; ".join(parts[:3])
                n_acik += 1
        else:
            cur.execute("SELECT trans_list FROM simple_translation WHERE written_rep=?", (bare,))
            row = cur.fetchone()
            if row and row[0]:
                tr_parts = [t.strip() for t in row[0].split(" | ") if t.strip() and len(t.strip()) < 50]
                if tr_parts:
                    entry["aciklama_turkce"] = ", ".join(tr_parts[:4])
                    n_acik += 1
    db.close()
    print(f"SQLite: {n_acik} aciklama_turkce eklendi", flush=True)

# --- ODENet ---
try:
    import wn as wn_lib
    wn_lib.download("odenet")
    de = wn_lib.Wordnet("odenet")
    n_syn = n_ant = 0
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
        syn_terms, ant_terms = [], []
        seen = {norm(bare)}
        for w in words:
            for ss in w.synsets():
                for sw in ss.words():
                    try:
                        lm = sw.lemma()
                    except Exception:
                        lm = str(sw)
                    if norm(lm) not in seen and 2 <= len(lm) <= 40:
                        seen.add(norm(lm))
                        syn_terms.append(lm)
                for related_ss in ss.get_related("antonym"):
                    for sw in related_ss.words():
                        try:
                            lm = sw.lemma()
                        except Exception:
                            lm = str(sw)
                        ant_terms.append(lm)
        if syn_terms and not entry.get("sinonim"):
            entry["sinonim"] = syn_terms[:6]
            n_syn += 1
        if ant_terms and not entry.get("antonim"):
            entry["antonim"] = ant_terms[:4]
            n_ant += 1
    print(f"ODENet: {n_syn} sinonim, {n_ant} antonim eklendi", flush=True)
except Exception as e:
    print(f"ODENet atlandi: {e}", flush=True)

print("Kaydediliyor...", flush=True)
DICT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("Tamam.", flush=True)

# Istatistik
fields = ["aciklama_turkce","sinonim","antonim","telaffuz"]
for f in fields:
    c = sum(1 for e in data if e.get(f))
    print(f"  {f}: {c}/{len(data)} ({100*c//len(data)}%)", flush=True)
