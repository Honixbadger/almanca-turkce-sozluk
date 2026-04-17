#!/usr/bin/env python3
"""Artikelsiz isim kayıtlarını düzeltir:

1. Tekili sözlükte mevcut olan ÇOĞUL FORMLAR → silinir
2. Gerçekten artikelsiz isimler → DWDS forms veritabanından artikel çıkartır,
   bulunamazsa dewiktionary.gz'den çeker.

Kaynak: Almancada büyük harfle başlayan her ismin der/die/das artikeli vardır.
Özel isimler (şehir, ülke, isim) hariç.
"""

from __future__ import annotations

import gzip
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH  = PROJECT_ROOT / "output" / "dictionary.json"
DEWIKT_PATH        = PROJECT_ROOT / "data" / "raw" / "downloads" / "dewiktionary.gz"

# ── Çoğul tespiti için son ek çiftleri ──────────────────────────────────────
# (çoğul_sonu, tekil_sonu) — None ise sadece son eki kaldır
PLURAL_RULES: list[tuple[str, str | None]] = [
    # Kesin eşleşmeler (uzun → kısa önce)
    ('innen',    None),    # Schülerinnen → Schülerin
    ('ungen',    'ung'),   # Beschränkungen → Beschränkung
    ('heiten',   'heit'),
    ('keiten',   'keit'),
    ('schaften', 'schaft'),
    ('tionen',   'tion'),
    ('ionen',    'ion'),
    ('nnen',     'n'),     # Studentinnen → Studentin
    ('ssen',     'sse'),   # Flüsse
    ('rten',     'rte'),
    ('ten',      'te'),
    ('nen',      'ne'),
    ('ren',      're'),
    ('gen',      'ge'),
    ('nge',      'ng'),
    ('sse',      'ss'),
    ('fer',      'fer'),   # umlaut çoğullar — güvensiz, atla
    ('ser',      None),
    ('ler',      None),
    ('ner',      None),
    ('men',      None),
    ('ern',      None),    # Kinder, Bilder vb.
    ('er',       None),
    ('en',       None),
    ('e',        None),
    ('n',        None),
    ('s',        None),
]

# ── Artikelsiz olması normal olan kelimeler (silinmeyecek) ────────────────────
# Özel isimler, ülkeler, şehirler vb. (büyük liste değil, sadece yaygın örnekler)
PROPER_NOUN_CLUES = re.compile(
    r'^(Deutschland|Österreich|Schweiz|Europa|Amerika|China|Japan|'
    r'[A-Z][a-z]+(burg|berg|stadt|dorf|bach|hausen|ingen|stein|au|ow|'
    r'land|mark|reich))$'
)


def try_find_singular(word: str, existing: set[str]) -> str | None:
    """Çoğul formu → olası tekil formu döndürür (sözlükte mevcutsa)."""
    for plural_end, singular_end in PLURAL_RULES:
        if not word.endswith(plural_end):
            continue
        stem = word[: -len(plural_end)]
        if len(stem) < 3:
            continue
        if singular_end is None:
            candidate = stem
        else:
            candidate = stem + singular_end
        if candidate.lower() in existing and candidate.lower() != word.lower():
            return candidate
    return None


def build_dewikt_artikel_index(dump_path: Path) -> dict[str, str]:
    """dewiktionary.gz'den Almanca isimlerin artikel bilgisini çıkartır."""
    index: dict[str, str] = {}
    print("Dewiktionary dump'ından artikel bilgisi çekiliyor...")
    with gzip.open(dump_path, 'rt', encoding='utf-8') as f:
        for line in f:
            entry = json.loads(line)
            if entry.get('lang_code') != 'de' or entry.get('pos') != 'noun':
                continue
            word = entry.get('word', '')
            if not word or not word[0].isupper():
                continue
            for form in entry.get('forms', []):
                tags = form.get('tags', [])
                if 'nominative' in tags and 'singular' in tags:
                    art = form.get('article', '')
                    if art in ('der', 'die', 'das'):
                        index[word.lower()] = art
                        break
    print(f"  {len(index):,} isim için artikel bulundu.")
    return index


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')

    dict_path = DEFAULT_DICT_PATH
    with open(dict_path, encoding='utf-8') as f:
        data: list[dict] = json.load(f)

    print(f"Başlangıç: {len(data):,} kayıt")

    existing_lower: set[str] = {e.get('almanca', '').lower() for e in data}

    # Artikelsiz büyük harfli tek-kelime isimleri bul
    targets: list[int] = [
        i for i, e in enumerate(data)
        if e.get('tur') == 'isim'
        and e.get('almanca', '')
        and e['almanca'][0].isupper()
        and not e.get('artikel')
        and ' ' not in e['almanca']
    ]
    print(f"Artikelsiz isim hedef: {len(targets):,}")

    # ── Adım 1: Çoğul tespiti ──────────────────────────────────────────────
    to_remove: set[int] = set()
    for i in targets:
        w = data[i]['almanca']
        singular = try_find_singular(w, existing_lower)
        if singular:
            to_remove.add(i)

    print(f"Tekili mevcut çoğul (silinecek): {len(to_remove):,}")

    remaining_targets = [i for i in targets if i not in to_remove]
    print(f"Artikel eklenecek kalan: {len(remaining_targets):,}")

    # ── Adım 2: Dewiktionary'den artikel çek ──────────────────────────────
    if DEWIKT_PATH.exists():
        artikel_index = build_dewikt_artikel_index(DEWIKT_PATH)
    else:
        print("UYARI: dewiktionary.gz bulunamadı, artikel eklenemiyor.")
        artikel_index = {}

    artikel_added   = 0
    artikel_missing = 0

    for i in remaining_targets:
        w = data[i]['almanca']
        art = artikel_index.get(w.lower(), '')
        if art:
            data[i] = dict(data[i])
            data[i]['artikel'] = art
            artikel_added += 1
        else:
            artikel_missing += 1

    print(f"Artikel eklenen  : {artikel_added:,}")
    print(f"Artikel bulunamayan: {artikel_missing:,}")

    # ── Sonuç ──────────────────────────────────────────────────────────────
    new_data = [e for i, e in enumerate(data) if i not in to_remove]

    print(f"\nSonuç: {len(new_data):,} kayıt ({len(new_data) - len(data):+d})")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = dict_path.with_name(f"dictionary.backup.artikel-fix-{ts}.json")
    shutil.copy2(dict_path, backup)
    print(f"Yedek: {backup.name}")

    with open(dict_path, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    print("Sözlük güncellendi.")


if __name__ == '__main__':
    main()
