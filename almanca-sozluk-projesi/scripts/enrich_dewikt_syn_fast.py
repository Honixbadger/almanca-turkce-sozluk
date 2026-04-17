#!/usr/bin/env python3
"""
de.wiktionary.org'dan 8 thread ile hızlı sinonim/antonim çeker.
"""
import sys, json, time, re, unicodedata, urllib.request, urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH  = Path("output/dictionary.json")
CHECKPOINT = Path("output/dewikt_syn_fast_checkpoint.json")
API        = "https://de.wiktionary.org/w/api.php"
THREADS    = 8
BATCH_SAVE = 400
MAX_SYN    = 20
MAX_ANT    = 10
lock       = threading.Lock()

def norm(t):
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().casefold()

def strip_art(w):
    p = w.strip().split(" ", 1)
    return p[1] if len(p) == 2 and norm(p[0]) in {"der","die","das"} else w.strip()

def fetch_wikitext(title: str) -> str:
    params = urllib.parse.urlencode({
        "action": "query", "titles": title,
        "prop": "revisions", "rvprop": "content",
        "rvslots": "main", "format": "json"
    })
    url = f"{API}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AlmancaSozluk/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        for page in data.get("query", {}).get("pages", {}).values():
            slots = page.get("revisions", [{}])[0].get("slots", {})
            return slots.get("main", {}).get("*", "") or ""
    except Exception:
        pass
    return ""

def extract_list_items(section_text: str, word: str, max_items: int) -> list[str]:
    wn = norm(word)
    items = []
    for m in re.finditer(r'\[\[([^\]|#<>{}]+?)(?:\|[^\]]+)?\]\]|\{\{l\|de\|([^|}]+)', section_text):
        w = (m.group(1) or m.group(2) or "").strip()
        if w and norm(w) != wn and not re.search(r'[:<>/{}]', w) and 1 < len(w) <= 60:
            if w not in items:
                items.append(w)
        if len(items) >= max_items:
            break
    return items

def parse_section(wikitext: str, section_name: str, word: str, max_items: int) -> list[str]:
    de_m = re.search(r'==\s*Deutsch\s*==', wikitext)
    if not de_m:
        return []
    de_text = wikitext[de_m.start():]
    next_l = re.search(r'\n==\s*(?!Deutsch)\w', de_text[5:])
    if next_l:
        de_text = de_text[:next_l.start() + 5]
    m = re.search(rf'===\s*{section_name}\s*===(.+?)(?===|\Z)', de_text, re.DOTALL)
    if not m:
        return []
    return extract_list_items(m.group(1), word, max_items)

def process_entry(entry):
    almanca = strip_art(entry.get("almanca") or "")
    if not almanca:
        return almanca, [], []
    wikitext = fetch_wikitext(almanca)
    if not wikitext:
        return almanca, [], []
    syns = parse_section(wikitext, "Synonyme", almanca, MAX_SYN)
    ants = parse_section(wikitext, "Antonyme", almanca, MAX_ANT)
    return almanca, syns, ants

print("Sözlük yükleniyor...")
raw = json.loads(DICT_PATH.read_text(encoding="utf-8"))
entries = list(raw.values()) if isinstance(raw, dict) else raw

done = set()
if CHECKPOINT.exists():
    done = set(json.loads(CHECKPOINT.read_text(encoding="utf-8")))

# İşlenecekler: sinonim VEYA antonim boş
targets = [e for e in entries
           if (not e.get("sinonim") or not e.get("antonim"))
           and strip_art(e.get("almanca","")) not in done]

print(f"  {len(entries):,} kayıt | checkpoint: {len(done):,} | işlenecek: {len(targets):,}")

syn_added = ant_added = 0
processed = 0
start = time.time()

with ThreadPoolExecutor(max_workers=THREADS) as pool:
    futures = {pool.submit(process_entry, e): e for e in targets}
    for fut in as_completed(futures):
        entry = futures[fut]
        try:
            almanca, syns, ants = fut.result()
        except Exception:
            almanca = strip_art(entry.get("almanca",""))
            syns, ants = [], []

        with lock:
            if syns and not entry.get("sinonim"):
                entry["sinonim"] = syns
                syn_added += 1
            if ants and not entry.get("antonim"):
                entry["antonim"] = ants
                ant_added += 1
            done.add(almanca)
            processed += 1

            if syns or ants:
                print(f"[{processed}/{len(targets)}] {almanca}: syn={syns[:3]} ant={ants[:2]}")

            if processed % BATCH_SAVE == 0:
                elapsed = time.time() - start
                rate = processed / elapsed
                remaining = (len(targets) - processed) / rate / 60
                print(f"  [Checkpoint {processed}: +{syn_added}syn +{ant_added}ant | ~{remaining:.0f}dk kaldı]")
                CHECKPOINT.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
                DICT_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

CHECKPOINT.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
DICT_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

total_syn = sum(1 for e in entries if e.get("sinonim"))
total_ant = sum(1 for e in entries if e.get("antonim"))
elapsed = (time.time() - start) / 60
print(f"\nBitti ({elapsed:.1f} dk): +{syn_added} sinonim, +{ant_added} antonim eklendi")
print(f"Toplam: sinonim {total_syn:,}/{len(entries):,} ({100*total_syn//len(entries)}%) | antonim {total_ant:,}/{len(entries):,} ({100*total_ant//len(entries)}%)")
