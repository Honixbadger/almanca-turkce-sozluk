#!/usr/bin/env python3
"""
DWDS Synonymwörterbuch API'sinden sinonim çeker.
Endpoint: https://www.dwds.de/api/synonyms?q=WORD
Lisans: CC BY-SA — https://www.dwds.de/
Yalnızca sinonim'i BOŞ olan kayıtlar işlenir.
"""
import sys, json, time, re, unicodedata, urllib.request, urllib.parse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH  = Path("output/dictionary.json")
CHECKPOINT = Path("output/dwds_syn_checkpoint.json")
BASE       = "https://www.dwds.de/api/synonyms?q={}"
DELAY      = 0.3
BATCH_SAVE = 200
MAX_SYN    = 20

def norm(t):
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().casefold()

def strip_art(w):
    p = w.strip().split(" ", 1)
    return p[1] if len(p) == 2 and norm(p[0]) in {"der","die","das"} else w.strip()

def fetch_synonyms(word: str) -> list[str]:
    url = BASE.format(urllib.parse.quote(word))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AlmancaSozluk/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        result = []
        wn = norm(word)
        # DWDS returns list of synonym groups
        groups = data if isinstance(data, list) else []
        for group in groups:
            for item in (group.get("terms") or group if isinstance(group, list) else []):
                w2 = (item.get("word") if isinstance(item, dict) else str(item)).strip()
                if w2 and norm(w2) != wn and len(w2) <= 60:
                    result.append(w2)
        return result[:MAX_SYN]
    except Exception:
        return []

print("Sözlük yükleniyor...")
raw = json.loads(DICT_PATH.read_text(encoding="utf-8"))
entries = list(raw.values()) if isinstance(raw, dict) else raw

done = set()
if CHECKPOINT.exists():
    done = set(json.loads(CHECKPOINT.read_text(encoding="utf-8")))
print(f"  {len(entries):,} kayıt | checkpoint: {len(done):,} işlendi")

targets = [e for e in entries if not e.get("sinonim") and strip_art(e.get("almanca","")) not in done]
print(f"  İşlenecek (sinonim boş): {len(targets):,}")

added_total = 0
for i, entry in enumerate(targets, 1):
    almanca = strip_art(entry.get("almanca") or "")
    if not almanca:
        continue

    syns = fetch_synonyms(almanca)
    if syns:
        entry["sinonim"] = syns
        added_total += 1
        print(f"[{i}/{len(targets)}] {almanca}: {', '.join(syns[:4])}")
    else:
        if i % 200 == 0:
            print(f"[{i}/{len(targets)}] ...")

    done.add(almanca)

    if i % BATCH_SAVE == 0:
        CHECKPOINT.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
        DICT_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [Checkpoint: {added_total} eklendi]")

    time.sleep(DELAY)

CHECKPOINT.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
DICT_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

total_syn = sum(1 for e in entries if e.get("sinonim"))
print(f"\nBitti: {added_total:,} kayda sinonim eklendi")
print(f"Toplam sinonim dolu: {total_syn:,}/{len(entries):,} ({100*total_syn//len(entries)}%)")
