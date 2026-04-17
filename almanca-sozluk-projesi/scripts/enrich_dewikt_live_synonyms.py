#!/usr/bin/env python3
"""
de.wiktionary.org MediaWiki API'sinden canlı sinonim çeker.
Yalnızca sinonim BOŞ olan kayıtlar işlenir.
Wikitext parse: {{Synonyme}} / === Synonyme === bölümü
"""
import sys, json, time, re, unicodedata, urllib.request, urllib.parse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH  = Path("output/dictionary.json")
CHECKPOINT = Path("output/dewikt_live_syn_checkpoint.json")
API        = "https://de.wiktionary.org/w/api.php"
DELAY      = 0.4
BATCH_SAVE = 200
MAX_SYN    = 20

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
        req = urllib.request.Request(url, headers={"User-Agent": "AlmancaSozluk/1.0 (educational)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            slots = page.get("revisions", [{}])[0].get("slots", {})
            return slots.get("main", {}).get("*", "") or ""
        return ""
    except Exception:
        return ""

def parse_synonyms(wikitext: str, word: str) -> list[str]:
    """Almanca Wiktionary'den Synonyme bölümünü parse et."""
    # ==Deutsch== bölümünü bul
    de_match = re.search(r'==\s*Deutsch\s*==', wikitext)
    if not de_match:
        return []
    de_text = wikitext[de_match.start():]
    # Sonraki dil başlığında dur
    next_lang = re.search(r'\n==\s*(?!Deutsch)\w', de_text[5:])
    if next_lang:
        de_text = de_text[:next_lang.start() + 5]

    # Synonyme bölümünü bul
    syn_match = re.search(r'===\s*Synonyme\s*===(.+?)(?===|\Z)', de_text, re.DOTALL)
    if not syn_match:
        # {{Synonyme}} template
        syn_match = re.search(r'\{\{Synonyme\}\}(.+?)(?=\{\{|\Z)', de_text, re.DOTALL)
    if not syn_match:
        return []

    syn_text = syn_match.group(1)
    # [[Link]] veya [[Link|Text]] veya {{l|de|Word}} pattern
    words = []
    wn = norm(word)
    for m in re.finditer(r'\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]|\{\{l\|de\|([^|}]+)', syn_text):
        w = (m.group(1) or m.group(2) or "").strip()
        if w and norm(w) != wn and not w.startswith("Wiktionary") and len(w) <= 60:
            words.append(w)
    return list(dict.fromkeys(words))[:MAX_SYN]  # deduplicate, keep order

print("Sözlük yükleniyor...")
raw = json.loads(DICT_PATH.read_text(encoding="utf-8"))
entries = list(raw.values()) if isinstance(raw, dict) else raw

done = set()
if CHECKPOINT.exists():
    done = set(json.loads(CHECKPOINT.read_text(encoding="utf-8")))

targets = [e for e in entries
           if not e.get("sinonim")
           and strip_art(e.get("almanca","")) not in done]

print(f"  {len(entries):,} kayıt | checkpoint: {len(done):,} | işlenecek: {len(targets):,}")

added_total = 0
for i, entry in enumerate(targets, 1):
    almanca = strip_art(entry.get("almanca") or "")
    if not almanca:
        continue

    wikitext = fetch_wikitext(almanca)
    syns = parse_synonyms(wikitext, almanca) if wikitext else []

    if syns:
        entry["sinonim"] = syns
        added_total += 1
        print(f"[{i}/{len(targets)}] {almanca}: {', '.join(syns[:4])}")
    elif i % 500 == 0:
        print(f"[{i}/{len(targets)}] ... {added_total} eklendi")

    done.add(almanca)

    if i % BATCH_SAVE == 0:
        CHECKPOINT.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
        DICT_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [Checkpoint {i}: {added_total} eklendi]")

    time.sleep(DELAY)

CHECKPOINT.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
DICT_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

total_syn = sum(1 for e in entries if e.get("sinonim"))
print(f"\nBitti: {added_total:,} kayda sinonim eklendi")
print(f"Toplam sinonim dolu: {total_syn:,}/{len(entries):,} ({100*total_syn//len(entries)}%)")
