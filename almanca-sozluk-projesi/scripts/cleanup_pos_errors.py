#!/usr/bin/env python3
"""Yanlış tür (tur) etiketli ve mastar olmayan fiil formlarını temizler.

Yapılan düzeltmeler:
1. İnfinitive'i zaten mevcut olan çekimli fiiller → silinir
2. Yanlış 'fiil' etiketli kelimeler → doğru türe taşınır
3. Partizip II / I → 'sıfat' olarak düzeltilir
4. Çekimli sıfatlar → base forma düzeltilir veya silinir
5. Anlamsız / bozuk girişler → silinir
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"

# ── 1. İnfinitive mevcut olduğu için silinecek çekimli fiiller ──────────────
REMOVE_IF_INF_EXISTS: dict[str, str] = {
    # çekimli form → beklenen infinitive
    "fliegt":  "fliegen",
    "scheidt": "scheiden",
    "täuscht": "täuschen",
    "zieht":   "ziehen",
    "zeige":   "zeigen",
    "möchte":  "mögen",
    "sollte":  "sollen",
}

# ── 2. Kesinlikle silinecek bozuk/anlamsız girişler ──────────────────────────
ALWAYS_REMOVE: set[str] = {
    "radeiser",   # Almanca değil
    "wortet",     # bağımsız kelime değil (beantwortet parçası)
    "gesollt",    # sollen'ın partizipi, bağımsız kullanımı yok
    "gebadet",    # bağımsız kullanımı yok
    "genäht",     # bağımsız kullanımı yok
}

# ── 3. Tür düzeltmeleri: almanca → yeni tur ─────────────────────────────────
FIX_TUR: dict[str, str] = {
    # Edatlar
    "außer":  "edat",
    "beim":   "edat",
    "hinter": "edat",
    "seit":   "edat",
    "statt":  "edat",
    "über":   "edat",

    # Bağlaçlar
    "damit":   "bağlaç",
    "denn":    "bağlaç",
    "indem":   "bağlaç",
    "seitdem": "bağlaç",
    "trotzdem":"bağlaç",
    "während": "bağlaç",
    "nämlich": "bağlaç",

    # Zarflar
    "wahrscheinlich": "zarf",
    "offenbar":       "zarf",
    "leider":         "zarf",
    "fast":           "zarf",
    "früher":         "zarf",
    "später":         "zarf",
    "weiter":         "zarf",
    "lange":          "zarf",
    "sehr":           "zarf",

    # Zamirler
    "deinem":  "zamir",
    "deiner":  "zamir",
    "diesem":  "zamir",
    "dieses":  "zamir",
    "eine":    "zamir",
    "keine":   "zamir",
    "meine":   "zamir",
    "meiner":  "zamir",
    "unsere":  "zamir",
    "welchem": "zamir",

    # Sıfatlar (basit)
    "jung":      "sıfat",
    "faul":      "sıfat",
    "sauer":     "sıfat",
    "schwanger": "sıfat",
    "praktisch": "sıfat",

    # Partizip I → sıfat
    "aufregend":   "sıfat",
    "entspannend": "sıfat",

    # Partizip II yaygın sıfat kullanımı olan
    "verliebt":    "sıfat",
    "verrückt":    "sıfat",
    "begeistert":  "sıfat",
    "bewölkt":     "sıfat",
    "geehrt":      "sıfat",
    "möbliert":    "sıfat",
    "erkältet":    "sıfat",
    "verpflichtet":"sıfat",
    "besetzt":     "sıfat",
    "geparkt":     "sıfat",
    "befreit":     "sıfat",
    "befreit":     "sıfat",
}

# ── 4. Çekimli sıfatlar: inflected form → base form ─────────────────────────
# Eğer base form zaten sözlükte varsa bu giriş silinir;
# yoksa almanca alanı base forma güncellenir.
FIX_ADJ_BASE: dict[str, str] = {
    "bequeme": "bequem",
    "große":   "groß",
    "gute":    "gut",
    "klare":   "klar",
    "warme":   "warm",
    # sıfat kategorisindeki çekimliler
    "meisten":                   "meist",
    "verhassten":                "verhasst",
    "verantwortungsbewussten":   "verantwortungsbewusst",
    "offenem":                   "offen",
    "feisten":                   "feist",
}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    dict_path = DEFAULT_DICT_PATH
    print(f"Sözlük yükleniyor: {dict_path}")
    with open(dict_path, encoding="utf-8") as f:
        data: list[dict] = json.load(f)

    print(f"Başlangıç kayıt sayısı: {len(data)}")

    # Mevcut kelimeleri küçük harfle indeksle
    existing_lower: set[str] = {e.get("almanca", "").lower() for e in data}

    removed: list[str] = []
    fixed_tur: list[tuple[str, str, str]] = []   # (almanca, eski_tur, yeni_tur)
    fixed_base: list[tuple[str, str]] = []        # (eski_form, yeni_form)

    new_data: list[dict] = []

    for entry in data:
        word = entry.get("almanca", "")
        word_lower = word.lower()
        tur = entry.get("tur", "")

        # 1. Kesinlikle silinecekler
        if word_lower in ALWAYS_REMOVE:
            removed.append(word)
            continue

        # 2. İnfinitive mevcut → çekimli formu sil
        if word_lower in {k.lower() for k in REMOVE_IF_INF_EXISTS}:
            inf = REMOVE_IF_INF_EXISTS.get(word_lower) or next(
                v for k, v in REMOVE_IF_INF_EXISTS.items() if k.lower() == word_lower
            )
            if inf.lower() in existing_lower:
                removed.append(word)
                continue

        # 3. Tür düzeltmesi
        if word_lower in {k.lower() for k in FIX_TUR}:
            new_tur = next(v for k, v in FIX_TUR.items() if k.lower() == word_lower)
            if tur != new_tur:
                fixed_tur.append((word, tur, new_tur))
                entry = dict(entry)
                entry["tur"] = new_tur

        # 4. Çekimli sıfat → base form
        if word_lower in {k.lower() for k in FIX_ADJ_BASE}:
            base = next(v for k, v in FIX_ADJ_BASE.items() if k.lower() == word_lower)
            if base.lower() in existing_lower:
                # Base form zaten var → bu girişi sil
                removed.append(word)
                continue
            else:
                # Base form yok → kelimeyi düzelt
                fixed_base.append((word, base))
                entry = dict(entry)
                entry["almanca"] = base
                entry["tur"] = "sıfat"
                existing_lower.add(base.lower())

        new_data.append(entry)

    # Rapor
    print(f"\n{'─'*50}")
    print(f"Silinen kayıt       : {len(removed)}")
    print(f"Tür düzeltilen      : {len(fixed_tur)}")
    print(f"Base form düzeltilen: {len(fixed_base)}")
    print(f"Sonuç kayıt sayısı  : {len(new_data)}")

    print("\nSilinenler:")
    for w in removed:
        print(f"  ✗ {w}")

    print("\nTür düzeltmeleri:")
    for word, old, new in fixed_tur:
        print(f"  {word}: {old} → {new}")

    print("\nBase form düzeltmeleri:")
    for old, new in fixed_base:
        print(f"  {old} → {new}")

    # Yedek al
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = dict_path.with_name(f"dictionary.backup.pos-cleanup-{ts}.json")
    shutil.copy2(dict_path, backup)
    print(f"\nYedek: {backup.name}")

    # Kaydet
    with open(dict_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    print(f"Sözlük güncellendi: {len(new_data)} kayıt ({len(new_data) - len(data):+d})")


if __name__ == "__main__":
    main()
