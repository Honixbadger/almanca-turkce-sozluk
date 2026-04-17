#!/usr/bin/env python3
"""
ODENet'ten hypernym/hyponym/holonym ilişkilerini kelime_ailesi alanına ekler.
Kurulu wn paketi ve ODENet kullanır — internet gerekmez.
"""
import sys, json, re, unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH = Path("output/dictionary.json")

def norm(t):
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().casefold()

def strip_art(w):
    p = w.strip().split(" ", 1)
    return p[1] if len(p) == 2 and norm(p[0]) in {"der","die","das"} else w.strip()

print("ODENet yükleniyor...")
try:
    import wn
    de = wn.Wordnet("odenet:1.4")
except Exception as e:
    print(f"HATA: {e}")
    sys.exit(1)

print("Sözlük yükleniyor...")
raw = json.loads(DICT_PATH.read_text(encoding="utf-8"))
entries = list(raw.values()) if isinstance(raw, dict) else raw
print(f"  {len(entries):,} kayıt")

added = 0
for entry in entries:
    almanca = strip_art(entry.get("almanca") or "")
    if not almanca:
        continue

    existing_ka = list(entry.get("kelime_ailesi") or [])
    existing_norms = {norm(x) for x in existing_ka}

    related = []
    try:
        words = de.words(almanca)
        for word in words[:2]:
            for ss in word.synsets()[:3]:
                # Hypernyms (üst kavram)
                for hyper in ss.hypernyms()[:2]:
                    for lm in hyper.lemmas()[:2]:
                        w = lm.strip()
                        if w and norm(w) != norm(almanca) and norm(w) not in existing_norms:
                            related.append(w)
                # Hyponyms (alt kavram)
                for hypo in ss.hyponyms()[:3]:
                    for lm in hypo.lemmas()[:2]:
                        w = lm.strip()
                        if w and norm(w) != norm(almanca) and norm(w) not in existing_norms:
                            related.append(w)
                # Holonyms (parça-bütün)
                for holo in (ss.holonyms() if hasattr(ss, 'holonyms') else [])[:2]:
                    for lm in holo.lemmas()[:2]:
                        w = lm.strip()
                        if w and norm(w) != norm(almanca) and norm(w) not in existing_norms:
                            related.append(w)
    except Exception:
        pass

    if related:
        # Deduplicate
        seen = set(existing_norms)
        new_items = []
        for r in related:
            if norm(r) not in seen and len(r) <= 60:
                new_items.append(r)
                seen.add(norm(r))
        if new_items:
            entry["kelime_ailesi"] = existing_ka + new_items[:8]
            added += 1

print(f"\nSonuç: {added:,} kayda ilişkili kelime eklendi")
total_ka = sum(1 for e in entries if e.get("kelime_ailesi"))
print(f"Toplam kelime_ailesi dolu: {total_ka:,}/{len(entries):,} ({100*total_ka//len(entries)}%)")

print("Kaydediliyor...")
DICT_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
print("Tamamlandı.")
