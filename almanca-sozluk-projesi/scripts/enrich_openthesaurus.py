#!/usr/bin/env python3
"""
OpenThesaurus.de API'sinden Almanca eş/zıt anlamlıları çeker.
sinonim alanını doldurur.

API: https://www.openthesaurus.de/synonyme/search?q=WORD&format=application/json
Lisans: LGPL (ticari kullanımda atıf gerekir, eğitim için serbest)

Kullanım:
    python scripts/enrich_openthesaurus.py
    python scripts/enrich_openthesaurus.py --limit 1000
"""

import json
import re
import sys
import time
import unicodedata
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH = Path("output/dictionary.json")
CHECKPOINT_PATH = Path("output/openthesaurus_checkpoint.json")
API_BASE = "https://www.openthesaurus.de/synonyme/search"
REQUEST_DELAY = 0.5


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().casefold()


def strip_article(word: str) -> str:
    parts = word.strip().split(" ", 1)
    if len(parts) == 2 and normalize(parts[0]) in {"der", "die", "das"}:
        return parts[1]
    return word.strip()


def fetch_synonyms(word: str) -> list[str]:
    """OpenThesaurus'tan eş anlamlıları getir."""
    params = urllib.parse.urlencode({"q": word, "format": "application/json"})
    url = f"{API_BASE}?{params}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AlmancaSozluk/1.0 (educational project)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        synonyms = []
        word_norm = normalize(word)
        for synset in data.get("synsets", []):
            for term in synset.get("terms", []):
                t = str(term.get("term", "")).strip()
                if t and normalize(t) != word_norm:
                    synonyms.append(t)
        # Deduplicate preserving order
        seen = set()
        result = []
        for s in synonyms:
            key = normalize(s)
            if key not in seen:
                seen.add(key)
                result.append(s)
        return result[:15]  # max 15 synonyms
    except Exception:
        return []


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    print(f"Sözlük yükleniyor: {DICT_PATH}", flush=True)
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))

    done: set[str] = set()
    if CHECKPOINT_PATH.exists():
        done = set(json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8")))

    targets = []
    for entry in data:
        bare = strip_article(str(entry.get("almanca") or "")).strip()
        if not bare:
            continue
        if not args.overwrite and entry.get("sinonim"):
            continue
        if bare in done:
            continue
        targets.append((entry, bare))

    total = len(targets)
    print(f"İşlenecek kayıt: {total}", flush=True)
    if args.dry_run:
        print(f"Dry-run örnek: ilk 5 hedef: {[t[1] for t in targets[:5]]}")
        return

    if args.limit:
        targets = targets[: args.limit]

    updated = 0
    for idx, (entry, bare) in enumerate(targets):
        syns = fetch_synonyms(bare)
        if syns:
            entry["sinonim"] = syns
            updated += 1
            print(f"[{idx+1}/{len(targets)}] {bare}: {', '.join(syns[:5])}", flush=True)
        else:
            print(f"[{idx+1}/{len(targets)}] {bare}: bulunamadı", flush=True)

        done.add(bare)

        if (idx + 1) % 100 == 0:
            DICT_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            CHECKPOINT_PATH.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
            print(f"  → Checkpoint: {updated} güncellendi", flush=True)

        time.sleep(REQUEST_DELAY)

    DICT_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    CHECKPOINT_PATH.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
    print(f"\nBitti: {updated}/{len(targets)} kayıt güncellendi.", flush=True)


if __name__ == "__main__":
    main()
