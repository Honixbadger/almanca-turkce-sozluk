#!/usr/bin/env python3
"""
Leipzig Wortschatz API'sinden benzer kelimeler çeker.
kelime_ailesi alanını zenginleştirir.

API: https://api.corpora.uni-leipzig.de/ws/similarity/deu_news_2012_1M/similarTerms?word=WORD&limit=8
Lisans: CC BY

Kullanim:
    python scripts/enrich_word_relations.py
    python scripts/enrich_word_relations.py --limit 2000
"""
import json, re, sys, time, unicodedata, urllib.request, urllib.parse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH   = Path("output/dictionary.json")
CHECKPOINT  = Path("output/word_relations_checkpoint.json")
CORPUS      = "deu_news_2012_1M"
BASE        = "https://api.corpora.uni-leipzig.de/ws"
DELAY       = 0.35
STOP_WORDS  = {"der","die","das","und","oder","ist","ein","eine","einen","dem","den","des","sich","es","er","sie","wir","ihr","zu","in","an","auf","von","mit","bei","nach","als","auch","aber","wenn","dann","nicht"}

def norm(t):
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().casefold()

def strip_art(w):
    p = w.strip().split(" ", 1)
    return p[1] if len(p)==2 and norm(p[0]) in {"der","die","das"} else w.strip()

def fetch_similar(word: str) -> list[str]:
    params = urllib.parse.urlencode({"word": word, "limit": 8})
    url = f"{BASE}/similarity/{CORPUS}/similarTerms?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AlmancaSozluk/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        wn = norm(word)
        result = []
        for item in (data if isinstance(data, list) else []):
            t = str(item.get("term") or item.get("word") or "").strip()
            tn = norm(t)
            if t and tn != wn and tn not in STOP_WORDS and len(t) > 2 and len(t) <= 40:
                result.append(t)
        return result[:8]
    except Exception:
        return []

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()

    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    done: set[str] = set()
    if CHECKPOINT.exists():
        done = set(json.loads(CHECKPOINT.read_text(encoding="utf-8")))

    targets = [(e, strip_art(str(e.get("almanca") or ""))) for e in data]
    targets = [(e, bare) for e, bare in targets if bare and bare not in done and (args.overwrite or not e.get("kelime_ailesi"))]
    if args.limit:
        targets = targets[:args.limit]

    print(f"Hedef: {len(targets)}", flush=True)
    if args.dry_run:
        return

    updated = 0
    for idx, (entry, bare) in enumerate(targets):
        similar = fetch_similar(bare)
        if similar:
            existing = list(entry.get("kelime_ailesi") or [])
            existing_set = {norm(x) for x in existing}
            new = [s for s in similar if norm(s) not in existing_set]
            if new:
                entry["kelime_ailesi"] = existing + new[:6]
                updated += 1
                print(f"[{idx+1}] {bare}: {', '.join(new[:4])}", flush=True)
            else:
                print(f"[{idx+1}] {bare}: zaten var", flush=True)
        else:
            print(f"[{idx+1}] {bare}: bulunamadi", flush=True)
        done.add(bare)
        if (idx+1) % 100 == 0:
            DICT_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
            CHECKPOINT.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
            print(f"  [Checkpoint: {updated} guncellendi]", flush=True)
        time.sleep(DELAY)

    DICT_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
    CHECKPOINT.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
    print(f"\nBitti: {updated}/{len(targets)}", flush=True)

if __name__ == "__main__":
    main()
