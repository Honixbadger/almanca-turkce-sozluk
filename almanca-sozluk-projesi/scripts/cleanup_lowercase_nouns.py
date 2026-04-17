#!/usr/bin/env python3
"""Küçük harfle başlayan yanlış 'isim' kayıtlarını temizler.

Almancada isimler büyük harfle başlar. Küçük harfli 'isim' kayıtları
ya yanlış etiketlenmiş (sıfat/zarf/edat) ya da çekimli formlar.

Eylem öncelik sırası:
1. Bilinen sayı, edat, zarf, bağlaç  → tur düzelt
2. Mastar biçimi (-en/-eln/-ern)      → tur = fiil
3. Präteritum biçimi (-te vb.)        → infinitive varsa sil, yoksa tur = fiil
4. Partizip II / present participle   → tur = sıfat
5. Inflekte sıfat sonu (-sche, vb.)   → base form varsa sil, yoksa tur = sıfat
6. Geri kalan küçük harfli            → tur = sıfat (en makul tahmin)
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"

# ── Bilinen kelimeler ────────────────────────────────────────────────────────
KNOWN_SAYILAR = {
    'null','eins','zwei','drei','vier','fünf','sechs','sieben','acht','neun',
    'zehn','elf','zwölf','dreizehn','vierzehn','fünfzehn','sechzehn',
    'siebzehn','achtzehn','neunzehn','zwanzig','dreißig','vierzig','fünfzig',
    'sechzig','siebzig','achtzig','neunzig','hundert','tausend',
}
KNOWN_EDATLAR = {
    'trotz','mangels','gemäß','laut','mittels','kraft','anhand','bezüglich',
    'mithilfe','zufolge','aufgrund','angesichts','anlässlich','hinsichtlich',
    'infolge','zwecks','wegen',
}
KNOWN_ZARFLAR = {
    'mehr','teils','erstmals','relativ','solar','immun','desto','oftmals',
    'weltweit','zunehmend','teilweise','jeweils','circa','knapp','selbst',
    'einfach','extrem','flexibel','beziehungsweise','weshalb','abends',
    'abermals','abkürzend','abertausende','normalerweise','ungefähr',
    'meistens','manchmal','immer','niemals','kaum','selten','häufig',
    'ebenfalls','gleichzeitig','tatsächlich','natürlich','allerdings',
    'schließlich','außerdem','dennoch','deshalb','daher','jedoch','obwohl',
    'sowohl','weder','entweder','falls','sofern','sobald','solange',
    'rapide','apriorisch','profund','übrigens','nämlich','zumindest',
    'mindestens','höchstens','insgesamt','überhaupt','eigentlich',
    'lediglich','ausschließlich','hauptsächlich','besonders','vor allem',
}
KNOWN_BAGLAÇLAR = {
    'obwohl','weil','damit','indem','obgleich','sofern','sobald','solange',
    'nachdem','bevor','während','falls','wenn','da','als','wie','ob',
}

# ── Regex araçları ───────────────────────────────────────────────────────────
# Präteritum son ekleri (schwach fiil)
PRAET = re.compile(
    r'(achtete|achteten|ertete|erteten|'      # doppelte
    r'schte|schten|'                           # wusch → wuschte değil ama yaygın
    r'ckte|ckten|'                             # hängte, drückte
    r'llte|llten|rnte|rnten|'
    r'hnte|hnten|tzte|tzten|'
    r'hrte|hrten|rkte|rkten|'
    r'nkte|nkten|chte|chten|'
    r'igte|igten|'                             # bewegte, zeigte
    r'erte|erten|'                             # änderte, orderte
    r'[^aeiouyäöü]te|[^aeiouyäöü]ten'         # allg. schwach Präteritum
    r')$'
)
# Inflekte sıfat son ekleri
ADJ_INFL = re.compile(
    r'(sche|schen|scher|sches|'
    r'liche|lichen|licher|liches|'
    r'ische|ischen|ischer|isches|'
    r'artige|artigen|artiger|'
    r'mäßige|mäßigen|mäßiger|'
    r'süße|süßen|'
    r'[aeiouäöü]le|[aeiouäöü]len|'
    r'erne|ernen)$'
)
# Partizip II / I
PART2 = re.compile(r'(iert|igte|igten|end|ende|endes|ig|ige|igen)$')
PART2_T = re.compile(r'(tet|tet|nkt|nkte|chte)$')  # Partizip II -t


def find_infinitive(w: str, existing: set[str]) -> str | None:
    """Olası infinitive formları türetir, sözlükte varsa döndürür."""
    cands: list[str] = []

    # Präteritum → infinitive
    for suffix, replacement in [
        ('achtete', 'achten'), ('ertete', 'erten'),
        ('schte', 'schen'), ('ckte', 'cken'), ('llte', 'llen'),
        ('rnte', 'rnen'), ('hnte', 'hnen'), ('tzte', 'tzen'),
        ('hrte', 'hren'), ('rkte', 'rken'), ('nkte', 'nken'),
        ('chte', 'chen'), ('igte', 'igen'), ('erte', 'ern'),
    ]:
        if w.endswith(suffix):
            cands.append(w[:-len(suffix)] + replacement)
    # Präteritum -ten (Plural)
    if w.endswith('ten') and len(w) > 5:
        cands.append(w[:-3] + 'en')
    # Allgemein -t → -ten/-en
    if w.endswith('t'):
        cands += [w[:-1] + 'en', w + 'en', w[:-1] + 'ten']
    if w.endswith('te'):
        cands.append(w[:-2] + 'en')

    # Partizip II -iert → -ieren
    if w.endswith('iert'):
        cands.append(w[:-4] + 'ieren')
    # present tense 3sg -t
    if w.endswith('t') and len(w) > 4:
        cands.append(w[:-1] + 'en')

    return next((c for c in cands if c.lower() in existing), None)


def adj_base(w: str) -> str | None:
    """Inflekte sıfatı base forma çevirir."""
    for suffix, base in [
        ('lichen', 'lich'), ('liche', 'lich'), ('licher', 'lich'), ('liches', 'lich'),
        ('ischen', 'isch'), ('ische', 'isch'), ('ischer', 'isch'), ('isches', 'isch'),
        ('schen',  'sch'),  ('sche',  'sch'),  ('scher',  'sch'),  ('sches',  'sch'),
        ('artige', 'artig'), ('artigen', 'artig'),
        ('mäßige', 'mäßig'), ('mäßigen', 'mäßig'),
    ]:
        if w.endswith(suffix):
            return w[:-len(suffix)] + base
    return None


def classify(entry: dict, existing: set[str]) -> tuple[str, str | None]:
    """
    Returns (action, new_tur_or_none):
      'keep_as'  → change tur to new_tur
      'remove'   → delete entry
      'fix_word' → fix almanca to new_tur (base form), tur = sıfat
    """
    w = entry['almanca']
    wl = w.lower()

    # 1. Bilinen kelimeler
    if wl in KNOWN_SAYILAR:
        return ('keep_as', 'sayı')
    if wl in KNOWN_EDATLAR:
        return ('keep_as', 'edat')
    if wl in KNOWN_ZARFLAR:
        return ('keep_as', 'zarf')
    if wl in KNOWN_BAGLAÇLAR:
        return ('keep_as', 'bağlaç')

    # 2. Mastar (-en/-eln/-ern) → fiil
    if re.search(r'(en|eln|ern)$', w) and not w.endswith('sten'):
        return ('keep_as', 'fiil')

    # 3. Partizip II / I → sıfat
    if PART2.search(w):
        return ('keep_as', 'sıfat')

    # 4. Präteritum tespiti
    if PRAET.search(w):
        inf = find_infinitive(w, existing)
        if inf:
            return ('remove', None)   # infinitive zaten var
        return ('keep_as', 'fiil')    # infinitive yok, fiil olarak tut

    # 5. Present tense 3rd singular (-t/-st) → infinitive varsa sil
    if re.search(r'(st|(?<![aeiouyäöü])t)$', w) and not re.search(r'(echt|icht|acht|ucht|schaft|keit|heit)$', w):
        inf = find_infinitive(w, existing)
        if inf:
            return ('remove', None)

    # 6. Inflekte sıfat
    base = adj_base(w)
    if base:
        if base.lower() in existing:
            return ('remove', None)
        return ('fix_word', base)

    # 7. Geri kalan küçük harfli → sıfat (en iyi tahmin; isim kesinlikle değil)
    return ('keep_as', 'sıfat')


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    dict_path = DEFAULT_DICT_PATH

    with open(dict_path, encoding='utf-8') as f:
        data: list[dict] = json.load(f)

    print(f"Başlangıç: {len(data)} kayıt")

    existing_lower: set[str] = {e.get('almanca', '').lower() for e in data}

    # Sadece küçük harfli tek-kelime "isim" kayıtlarını işle
    suspects: set[int] = {
        i for i, e in enumerate(data)
        if e.get('tur') == 'isim'
        and e.get('almanca', '')
        and e['almanca'][0].islower()
        and ' ' not in e['almanca']
    }

    stats = {'remove': 0, 'keep_as': {}, 'fix_word': 0}
    new_data: list[dict] = []

    for i, entry in enumerate(data):
        if i not in suspects:
            new_data.append(entry)
            continue

        action, value = classify(entry, existing_lower)

        if action == 'remove':
            stats['remove'] += 1
            continue

        entry = dict(entry)

        if action == 'keep_as':
            entry['tur'] = value
            stats['keep_as'][value] = stats['keep_as'].get(value, 0) + 1

        elif action == 'fix_word':
            # Base form yok → almanca'yı düzelt
            entry['almanca'] = value
            entry['tur'] = 'sıfat'
            existing_lower.add(value.lower())
            stats['fix_word'] += 1

        new_data.append(entry)

    # Rapor
    print(f"\n{'─'*45}")
    print(f"Silinen          : {stats['remove']}")
    print(f"Kelime düzeltilen: {stats['fix_word']}")
    print(f"Tür düzeltilen   :")
    for tur, cnt in sorted(stats['keep_as'].items(), key=lambda x: -x[1]):
        print(f"  → {tur:<15} {cnt}")
    total_changed = stats['remove'] + stats['fix_word'] + sum(stats['keep_as'].values())
    print(f"Toplam değişen   : {total_changed}")
    print(f"Sonuç            : {len(new_data)} kayıt ({len(new_data) - len(data):+d})")

    # Yedek + kaydet
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = dict_path.with_name(f"dictionary.backup.lowercase-nouns-{ts}.json")
    shutil.copy2(dict_path, backup)
    print(f"\nYedek: {backup.name}")

    with open(dict_path, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    print("Sözlük güncellendi.")


if __name__ == '__main__':
    main()
