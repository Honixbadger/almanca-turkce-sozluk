#!/usr/bin/env python3
"""
enrich_dewiktionary_definitions.py
===================================
de.wiktionary dump'ından (dewiktionary.gz) Almanca kelimelerin
Almanca tanımlarını (tanim_almanca) sözlüğe ekler.

Kaynak: Wikimedia dewiktionary JSONL dump
Lisans: CC BY-SA 3.0 — https://creativecommons.org/licenses/by-sa/3.0/
Kaynak URL: https://dumps.wikimedia.org/dewiktionary/

Kredi: Bu verideki Almanca tanımlar Wiktionary katılımcılarına aittir.
Attribution: Wiktionary contributors, CC BY-SA 3.0
"""

from __future__ import annotations

import gzip
import json
import re
import time
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEWIKT_PATH = PROJECT_ROOT / "data" / "raw" / "downloads" / "dewiktionary.gz"

# Maksimum tanım uzunluğu (karakter)
MAX_DEF_LEN = 300
# Kelime başına max kaç sense birleştir
MAX_SENSES = 3


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().casefold()


def clean_gloss(gloss: str) -> str:
    """Tanımı temizle: wiki markup, gereksiz boşluklar."""
    # Köşeli parantez içeriğini kaldır [...]
    gloss = re.sub(r"\[.*?\]", "", gloss)
    # HTML tag temizle
    gloss = re.sub(r"<[^>]+>", "", gloss)
    # Çoklu boşluk
    gloss = re.sub(r"\s+", " ", gloss).strip()
    return gloss


def is_useful_gloss(gloss: str) -> bool:
    """Çok kısa, meta ya da biçim bilgisi içeren tanımları filtrele."""
    if len(gloss) < 8:
        return False
    # Sadece dilbilgisi formu tanımları (bükünlü formlar)
    skip_patterns = [
        r"^\d+\. Person",
        r"^Nominativ",
        r"^Genitiv",
        r"^Dativ",
        r"^Akkusativ",
        r"^Plural",
        r"^Singular",
        r"^Komparativ",
        r"^Superlativ",
        r"^Präteritum",
        r"^Partizip",
        r"^Infinitiv",
        r"^flektierte Form",
        r"^konjugierte Form",
        r"^deklinierte Form",
        r"^alternative Schreibweise",
        r"^veraltete Schreibweise",
        r"^Kurzform",
    ]
    g_lower = gloss.lower()
    for pat in skip_patterns:
        if re.match(pat, gloss, re.IGNORECASE):
            return False
    return True


def build_wiktionary_index() -> dict[str, str]:
    """
    dewiktionary.gz'yi okuyup {normalize(word): tanim} sözlüğü döndür.
    Bir kelime için birden fazla sense varsa '; ' ile birleştirir.
    """
    print("dewiktionary.gz okunuyor (bu 1-2 dakika sürebilir)...")
    index: dict[str, list[str]] = {}

    with gzip.open(str(DEWIKT_PATH), "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("lang_code") != "de":
                continue

            word = obj.get("word", "").strip()
            if not word:
                continue

            senses = obj.get("senses") or []
            glosses: list[str] = []
            for sense in senses[:MAX_SENSES]:
                raw = (sense.get("glosses") or [""])[0]
                cleaned = clean_gloss(raw)
                if is_useful_gloss(cleaned):
                    truncated = cleaned[:MAX_DEF_LEN]
                    if truncated and truncated not in glosses:
                        glosses.append(truncated)

            if not glosses:
                continue

            key = normalize(word)
            if key not in index:
                index[key] = glosses
            else:
                # Farklı POS'lardan gelen anlamları birleştir (max MAX_SENSES toplam)
                existing = index[key]
                for g in glosses:
                    if g not in existing and len(existing) < MAX_SENSES:
                        existing.append(g)

    # List → string
    result: dict[str, str] = {}
    for key, glosses in index.items():
        result[key] = "; ".join(glosses)

    print(f"İndeks hazır: {len(result):,} benzersiz Almanca kelime")
    return result


def main() -> None:
    start = time.time()

    print("=" * 65)
    print("enrich_dewiktionary_definitions.py")
    print("Kaynak: Wiktionary contributors, CC BY-SA 3.0")
    print("=" * 65)

    if not DEWIKT_PATH.exists():
        print(f"HATA: {DEWIKT_PATH} bulunamadı.")
        return

    # 1. Wiktionary indeksini oluştur
    wikt_index = build_wiktionary_index()

    # 2. Sözlüğü yükle
    print(f"\nSözlük yükleniyor: {DICT_PATH}")
    dictionary = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"Toplam kayıt: {len(dictionary):,}")

    # 3. Eşleştir ve güncelle
    updated = 0
    already_had = 0
    not_found = 0

    for entry in dictionary:
        word = (entry.get("almanca") or "").strip()
        if not word:
            continue

        # Zaten doluysa atla
        if entry.get("tanim_almanca", "").strip():
            already_had += 1
            continue

        key = normalize(word)
        definition = wikt_index.get(key)

        if definition:
            entry["tanim_almanca"] = definition
            # Kaynak bilgisi
            existing_source = entry.get("kaynak", "")
            if "Wiktionary" not in existing_source:
                entry["kaynak"] = (existing_source + "; Wiktionary DE (CC BY-SA 3.0)").lstrip("; ")
            updated += 1
        else:
            not_found += 1

    elapsed = time.time() - start

    # 4. Kaydet
    DICT_PATH.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n{'=' * 65}")
    print("SONUÇ")
    print(f"  Tanım eklenen      : {updated:,}")
    print(f"  Zaten doluydu      : {already_had:,}")
    print(f"  Eşleşme bulunamadı : {not_found:,}")
    print(f"  Toplam kayıt       : {len(dictionary):,}")
    print(f"  Süre               : {elapsed:.1f}s")
    print(f"{'=' * 65}")
    print(f"\nKaydedildi: {DICT_PATH}")


if __name__ == "__main__":
    main()
