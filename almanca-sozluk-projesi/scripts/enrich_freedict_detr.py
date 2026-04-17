#!/usr/bin/env python3
"""
enrich_freedict_detr.py
========================
FreeDict Almanca-Türkçe açık kaynak ikidilli sözlüğünden
ek çeviriler çıkarıp sözlüğe ekler.

Doldurduğu alanlar:
  turkce   — boşsa FreeDict çevirisini ekler
  anlamlar — mevcut listeye yeni anlamlar ekler

Kaynak:
  FreeDict deu-tur (LGPL / GNU FDL)
  https://github.com/freedict/fd-dictionaries/tree/master/deu-tur
"""

from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
import urllib.request as ur
import xml.etree.ElementTree as ET
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATH    = PROJECT_ROOT / "output" / "dictionary.json"
DATA_DIR     = PROJECT_ROOT / "data" / "raw" / "downloads"
TEI_PATH     = DATA_DIR / "freedict_deu_tur.tei"

TEI_URL = (
    "https://raw.githubusercontent.com/freedict/fd-dictionaries"
    "/master/deu-tur/deu-tur.tei"
)
UA = "AlmancaSozluk/1.0 (educational; contact: github.com/Honixbadger)"
SOURCE_TAG = "FreeDict deu-tur (LGPL)"

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().casefold()


def strip_article(word: str) -> str:
    parts = word.strip().split(" ", 1)
    if len(parts) == 2 and normalize(parts[0]) in {"der", "die", "das"}:
        return parts[1]
    return word.strip()


def get_text(elem) -> str:
    """Elementten tüm metni (alt elementler dahil) al."""
    return "".join(elem.itertext()).strip()


def download_tei(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  Zaten var ({dest.stat().st_size // 1024} KB), atlanıyor.")
        return True
    print(f"  İndiriliyor: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = ur.Request(url, headers={"User-Agent": UA})
        with ur.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
            f.write(resp.read())
        print(f"  Tamamlandı: {dest.stat().st_size // 1024} KB")
        return True
    except Exception as e:
        print(f"  HATA: {e}")
        return False


def parse_tei(tei_path: Path) -> dict[str, list[str]]:
    """
    FreeDict TEI dosyasını parse et.
    Döndürür: {normalize(de_lemma): [tr_çeviri, ...]}
    """
    print(f"  Parse ediliyor: {tei_path}")
    result: dict[str, list[str]] = {}

    tree = ET.parse(str(tei_path))
    root = tree.getroot()

    # TEI namespace'i bul (varsa)
    ns = ""
    tag = root.tag
    if tag.startswith("{"):
        ns = tag[: tag.index("}") + 1]

    entry_tag   = f"{ns}entry"
    form_tag    = f"{ns}form"
    orth_tag    = f"{ns}orth"
    sense_tag   = f"{ns}sense"
    cit_tag     = f"{ns}cit"
    quote_tag   = f"{ns}quote"

    body = root.find(f".//{ns}body") or root

    for entry in body.iter(entry_tag):
        # Almanca lemma
        de_word = ""
        form_elem = entry.find(f".//{form_tag}[@type='lemma']")
        if form_elem is None:
            form_elem = entry.find(f".//{form_tag}")
        if form_elem is not None:
            orth = form_elem.find(orth_tag)
            if orth is not None:
                de_word = get_text(orth)
        if not de_word:
            continue

        # Türkçe çeviriler
        translations: list[str] = []
        for sense in entry.iter(sense_tag):
            for cit in sense.iter(cit_tag):
                cit_type = cit.get("type", "")
                if cit_type in ("trans", "translation", ""):
                    quote = cit.find(quote_tag)
                    if quote is not None:
                        tr = get_text(quote)
                        if tr and len(tr) <= 80:
                            translations.append(tr)

        if not translations:
            continue

        key = normalize(strip_article(de_word))
        if key not in result:
            result[key] = []
        for tr in translations:
            tr_n = normalize(tr)
            if tr_n and not any(normalize(x) == tr_n for x in result[key]):
                result[key].append(tr)

    print(f"  {len(result):,} Almanca lemma yüklendi.")
    return result


def apply_freedict(
    dictionary: list[dict],
    freedict: dict[str, list[str]],
) -> dict[str, int]:
    counters = {
        "turkce_filled": 0,
        "anlamlar_added": 0,
        "entries_updated": 0,
    }

    for rec in dictionary:
        word = (rec.get("almanca") or "").strip()
        key = normalize(strip_article(word))
        if not key:
            continue

        translations = freedict.get(key, [])
        if not translations:
            continue

        changed = False
        tr_current = (rec.get("turkce") or "").strip()

        # turkce alanı boşsa doldur
        if not tr_current:
            new_tr = "; ".join(translations[:3])
            rec["turkce"] = new_tr
            counters["turkce_filled"] += 1
            changed = True

        # anlamlar listesine ekle (zaten yoksa)
        existing_anlamlar: list[dict] = list(rec.get("anlamlar") or [])
        existing_tr_norms = {normalize(a.get("turkce", "")) for a in existing_anlamlar}
        existing_tr_norms.add(normalize(tr_current))
        # Aynı zamanda mevcut turkce alanındaki tüm çevirileri ekle
        for part in re.split(r"[;,]", tr_current):
            existing_tr_norms.add(normalize(part.strip()))

        for tr in translations:
            tr_n = normalize(tr)
            if not tr_n or tr_n in existing_tr_norms:
                continue
            existing_anlamlar.append({
                "sira": len(existing_anlamlar) + 1,
                "turkce": tr,
                "tanim_almanca": "",
                "kaynak": SOURCE_TAG,
                "guven": 0.6,
            })
            existing_tr_norms.add(tr_n)
            counters["anlamlar_added"] += 1
            changed = True

        if changed:
            if existing_anlamlar != (rec.get("anlamlar") or []):
                rec["anlamlar"] = existing_anlamlar
            src = rec.get("kaynak") or ""
            if "FreeDict" not in src:
                rec["kaynak"] = (src + f"; {SOURCE_TAG}").lstrip("; ")
            counters["entries_updated"] += 1

    return counters


def main() -> None:
    start = time.time()

    print("=" * 65)
    print("enrich_freedict_detr.py — FreeDict DE-TR Entegrasyonu")
    print("Kaynak: FreeDict deu-tur (LGPL)")
    print("URL: https://github.com/freedict/fd-dictionaries")
    print("=" * 65)

    print("\n[1/4] FreeDict sözlüğü indiriliyor...")
    if not download_tei(TEI_URL, TEI_PATH):
        sys.exit(1)

    print("\n[2/4] TEI dosyası parse ediliyor...")
    freedict = parse_tei(TEI_PATH)
    if not freedict:
        print("Veri okunamadı.")
        sys.exit(1)

    print("\n[3/4] Ana sözlük yükleniyor...")
    dictionary: list[dict] = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(dictionary):,} kayıt")

    print("\n[4/4] FreeDict verileri uygulanıyor...")
    counters = apply_freedict(dictionary, freedict)

    DICT_PATH.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    elapsed = time.time() - start

    print(f"\n{'=' * 65}")
    print("SONUÇ")
    print(f"  Güncellenen kayıt     : {counters['entries_updated']:,}")
    print(f"  Doldurulan turkce     : {counters['turkce_filled']:,}")
    print(f"  Eklenen anlamlar      : {counters['anlamlar_added']:,}")
    print(f"  Süre                  : {elapsed:.0f}s")
    print(f"{'=' * 65}")
    print(f"\nKaydedildi: {DICT_PATH}")


if __name__ == "__main__":
    main()
