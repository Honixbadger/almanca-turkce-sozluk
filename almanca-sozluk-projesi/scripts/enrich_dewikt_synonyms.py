#!/usr/bin/env python3
"""
dewiktionary.gz dump'ından sinonim ve antonim çeker.
synonyms/antonyms alanları zaten parse edilmiş — internet gerekmez.
"""
import sys, json, gzip, unicodedata, re
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH  = Path("output/dictionary.json")
DUMP_PATH  = Path("data/raw/downloads/dewiktionary.gz")
MAX_SYN    = 20
MAX_ANT    = 10

def norm(t):
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().casefold()

def strip_art(w):
    p = w.strip().split(" ", 1)
    return p[1] if len(p) == 2 and norm(p[0]) in {"der","die","das"} else w.strip()

print("dewiktionary.gz taranıyor (sinonim/antonim)...")
dump_syn = {}   # word -> list[str]
dump_ant = {}   # word -> list[str]

with gzip.open(DUMP_PATH, "rt", encoding="utf-8", errors="replace") as f:
    for line in f:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("lang_code") != "de":
            continue
        word = (d.get("word") or "").strip()
        if not word:
            continue

        syns = []
        for s in (d.get("synonyms") or []):
            w2 = (s.get("word") or "").strip()
            if w2 and norm(w2) != norm(word) and len(w2) <= 60:
                syns.append(w2)

        ants = []
        for a in (d.get("antonyms") or []):
            w2 = (a.get("word") or "").strip()
            if w2 and norm(w2) != norm(word) and len(w2) <= 60:
                ants.append(w2)

        key = norm(word)
        if syns:
            dump_syn.setdefault(key, [])
            for s in syns:
                if s not in dump_syn[key]:
                    dump_syn[key].append(s)
        if ants:
            dump_ant.setdefault(key, [])
            for a in ants:
                if a not in dump_ant[key]:
                    dump_ant[key].append(a)

print(f"  {len(dump_syn):,} kelimede sinonim, {len(dump_ant):,} kelimede antonim bulundu")

print("Sözlük yükleniyor...")
raw = json.loads(DICT_PATH.read_text(encoding="utf-8"))
entries = list(raw.values()) if isinstance(raw, dict) else raw
print(f"  {len(entries):,} kayıt")

syn_added = ant_added = syn_entries = ant_entries = 0

for entry in entries:
    almanca = strip_art(entry.get("almanca") or "")
    key = norm(almanca)

    # — sinonim —
    new_syns = dump_syn.get(key, [])
    if new_syns:
        existing = list(entry.get("sinonim") or [])
        existing_norms = {norm(x) for x in existing}
        added = 0
        for s in new_syns:
            if norm(s) not in existing_norms and len(existing) < MAX_SYN:
                existing.append(s)
                existing_norms.add(norm(s))
                added += 1
        if added:
            entry["sinonim"] = existing
            syn_added += added
            syn_entries += 1

    # — antonim —
    new_ants = dump_ant.get(key, [])
    if new_ants:
        existing = list(entry.get("antonim") or [])
        existing_norms = {norm(x) for x in existing}
        added = 0
        for a in new_ants:
            if norm(a) not in existing_norms and len(existing) < MAX_ANT:
                existing.append(a)
                existing_norms.add(norm(a))
                added += 1
        if added:
            entry["antonim"] = existing
            ant_added += added
            ant_entries += 1

print(f"\nSonuç:")
print(f"  Sinonim: {syn_added:,} kelime eklendi → {syn_entries:,} kayıt güncellendi")
print(f"  Antonim: {ant_added:,} kelime eklendi → {ant_entries:,} kayıt güncellendi")

total_syn = sum(1 for e in entries if e.get("sinonim"))
total_ant = sum(1 for e in entries if e.get("antonim"))
print(f"  Toplam sinonim dolu: {total_syn:,}/{len(entries):,} ({100*total_syn//len(entries)}%)")
print(f"  Toplam antonim dolu: {total_ant:,}/{len(entries):,} ({100*total_ant//len(entries)}%)")

print("\nKaydediliyor...")
DICT_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
print("Tamamlandı.")
