# -*- coding: utf-8 -*-
"""
import_goethe_words.py
======================
Goethe Institut kelime listelerinden (A1/A2/B1) çıkartılan kelimeleri
sözlüğe ekler.

- Sözlükte zaten var olan kelimeler atlanır (büyük/küçük harf duyarsız).
- Türkçe anlam BEKLENMİYOR — zenginleştirme çalıştırıldığında doldurulur.
- Her yeni kayıt için minimal yapı oluşturulur.

Kaynak dosya:
  Scriptle aynı klasörde veya proje kökünde "final_words.json" olmalıdır.
  Komut satırından farklı yol belirtmek için:
    python import_goethe_words.py --source /path/to/final_words.json
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DICT_PATH   = _PROJECT_ROOT / "output" / "dictionary.json"
# SOURCE_PATH: aynı klasörde, proje kökünde veya --source argümanıyla belirtilir
_default_source_candidates = [
    Path(__file__).resolve().parent / "final_words.json",
    _PROJECT_ROOT / "final_words.json",
    _PROJECT_ROOT / "data" / "manual" / "goethe_words.json",
]
SOURCE_PATH = next((p for p in _default_source_candidates if p.exists()), _default_source_candidates[0])


def infer_tur(entry: dict) -> str:
    """Artikel varsa 'isim', yoksa 'fiil' (Goethe listesindeki eksiz kelimeler genellikle fiil)."""
    artikel = (entry.get("artikel") or "").strip()
    if artikel in ("der", "die", "das"):
        return "isim"
    almanca = (entry.get("almanca") or "").strip()
    # "(sich) ..." → fiil
    if almanca.startswith("(") or (almanca and almanca[0].islower()):
        return "fiil"
    return ""


def normalize_key(s: str) -> str:
    """Karşılaştırma için normalize et: küçük harf, "(sich) " gibi ön ekleri kaldır."""
    s = s.strip().lower()
    for prefix in ("(sich) ", "(sich)", "sich "):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s


def build_entry(goethe: dict) -> dict:
    almanca = (goethe.get("almanca") or "").strip()
    artikel = (goethe.get("artikel") or "").strip()
    seviye  = (goethe.get("seviye")  or "").strip()
    tur     = infer_tur(goethe)

    entry: dict = {
        "almanca": almanca,
        "artikel": artikel,
        "turkce": "",
        "kategoriler": [],
        "aciklama_turkce": "",
        "ilgili_kayitlar": [],
        "tur": tur,
        "ornek_almanca": "",
        "ornek_turkce": "",
        "ornekler": [],
        "kaynak": "goethe-institut",
        "kaynak_url": "https://www.goethe.de/de/spr/ueb/ger.html",
        "ceviri_durumu": "eksik",
        "ceviri_inceleme_notu": "",
        "ceviri_kaynaklari": [],
        "not": "",
        "referans_linkler": {},
        "seviye": seviye,
        "kelime_ailesi": [],
    }
    return entry


def main(dry_run: bool = False) -> None:
    # Sözlüğü yükle
    with open(DICT_PATH, encoding="utf-8") as f:
        data: list[dict] = json.load(f)

    print(f"Mevcut sözlük kayıt sayısı : {len(data)}")

    # Mevcut kelimeleri normalize edilmiş şekilde index'e al
    existing_keys: set[str] = set()
    for rec in data:
        existing_keys.add(normalize_key(rec.get("almanca", "")))

    # Goethe kelimelerini yükle
    with open(SOURCE_PATH, encoding="utf-8") as f:
        goethe_words: list[dict] = json.load(f)

    print(f"Goethe kelime sayısı        : {len(goethe_words)}")

    added = 0
    skipped = 0
    new_entries: list[dict] = []

    for gw in goethe_words:
        almanca = (gw.get("almanca") or "").strip()
        if not almanca:
            skipped += 1
            continue

        key = normalize_key(almanca)
        if key in existing_keys:
            skipped += 1
            continue

        entry = build_entry(gw)
        new_entries.append(entry)
        existing_keys.add(key)  # çift eklemeyi önle
        added += 1

    print(f"\n{'='*55}")
    print(f"Özet:")
    print(f"  Eklenecek yeni kelime  : {added}")
    print(f"  Atlanan (zaten mevcut) : {skipped}")
    print(f"  Yeni toplam kayıt      : {len(data) + added}")

    if dry_run:
        print("\nÖrnek yeni kayıtlar (ilk 10):")
        for e in new_entries[:10]:
            print(f"  [{e['seviye']}] {e['almanca']!r}  ({e['tur'] or '?'})")
        print("  [DRY RUN — dosya değiştirilmedi]")
        return

    # Yeni kelimeleri sona ekle
    data.extend(new_entries)
    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  Kaydedildi: {DICT_PATH}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
