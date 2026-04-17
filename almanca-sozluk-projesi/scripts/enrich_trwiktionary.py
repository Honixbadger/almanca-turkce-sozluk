#!/usr/bin/env python3
"""
tr.wiktionary.org MediaWiki API'sinden Türkçe tanımları çeker.
aciklama_turkce alanını doldurur.

Kullanım:
    cd almanca-sozluk-projesi
    python scripts/enrich_trwiktionary.py
    python scripts/enrich_trwiktionary.py --limit 500 --dry-run
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
CHECKPOINT_PATH = Path("output/trwiktionary_checkpoint.json")
API_URL = "https://tr.wiktionary.org/w/api.php"
REQUEST_DELAY = 1.1  # seconds between requests (polite to Wikimedia)


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().casefold()


def strip_article(word: str) -> str:
    parts = word.strip().split(" ", 1)
    if len(parts) == 2 and normalize(parts[0]) in {"der", "die", "das"}:
        return parts[1]
    return word.strip()


def clean_wikitext(text: str) -> str:
    """Wikitext markup temizle."""
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    text = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'{2,3}", "", text)
    text = re.sub(r"^[#*:;]+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_definition(wikitext: str) -> str | None:
    """Wikitext'ten Almanca bölümündeki Türkçe tanımı çıkar."""
    # Find ==Almanca== section
    de_match = re.search(r"==\s*Almanca\s*==", wikitext)
    if not de_match:
        return None

    section = wikitext[de_match.end():]
    # Cut at next level-2 heading
    next_h2 = re.search(r"\n==\s*[^=]", section)
    if next_h2:
        section = section[: next_h2.start()]

    # Find ===Anlam=== or ===Anlamlar=== subsection
    anlam_match = re.search(r"===\s*Anlam(?:lar)?\s*===", section)
    if anlam_match:
        subsection = section[anlam_match.end():]
        next_h3 = re.search(r"\n===", subsection)
        if next_h3:
            subsection = subsection[: next_h3.start()]
        lines = [
            clean_wikitext(line)
            for line in subsection.splitlines()
            if line.strip().startswith("#") and not line.strip().startswith("##")
        ]
        if lines:
            return "; ".join(l for l in lines if len(l) > 2)

    # Fallback: any # lines in section
    lines = [
        clean_wikitext(line)
        for line in section.splitlines()
        if line.strip().startswith("#") and not line.strip().startswith("##")
    ]
    if lines:
        return "; ".join(l for l in lines[:3] if len(l) > 2)

    return None


def fetch_definition(word: str) -> str | None:
    """tr.wiktionary.org'dan kelime tanımını getir."""
    params = urllib.parse.urlencode({
        "action": "parse",
        "page": word,
        "prop": "wikitext",
        "format": "json",
        "redirects": "1",
    })
    url = f"{API_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AlmancaSozluk/1.0 (educational)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        if "error" in data:
            return None
        wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
        if not wikitext:
            return None
        return extract_definition(wikitext)
    except Exception:
        return None


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
        if not args.overwrite and entry.get("aciklama_turkce"):
            continue
        if bare in done:
            continue
        targets.append((entry, bare))

    total = len(targets)
    print(f"İşlenecek kayıt: {total}", flush=True)
    if args.dry_run:
        print("Dry-run, çıkılıyor.")
        return

    if args.limit:
        targets = targets[: args.limit]

    updated = 0
    for idx, (entry, bare) in enumerate(targets):
        defn = fetch_definition(bare)
        if defn and len(defn) > 5:
            entry["aciklama_turkce"] = defn
            updated += 1
            print(f"[{idx+1}/{len(targets)}] {bare}: {defn[:80]}", flush=True)
        else:
            print(f"[{idx+1}/{len(targets)}] {bare}: bulunamadı", flush=True)

        done.add(bare)

        if (idx + 1) % 50 == 0:
            DICT_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            CHECKPOINT_PATH.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
            print(f"  → Checkpoint: {updated} güncellendi", flush=True)

        time.sleep(REQUEST_DELAY)

    DICT_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    CHECKPOINT_PATH.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")
    print(f"\nBitti: {updated}/{len(targets)} kayıt güncellendi.", flush=True)


if __name__ == "__main__":
    main()
