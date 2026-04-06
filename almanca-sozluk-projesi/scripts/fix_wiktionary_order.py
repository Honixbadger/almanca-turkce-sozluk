# -*- coding: utf-8 -*-
"""
fix_wiktionary_order.py
========================
İki işi yapar:

1. ÇOKLU KAYIT BİRLEŞTİRME (311 kelime)
   Aynı kelime + tur için birden fazla kayıt varsa (trwiktionary + dewiktionary ayrı
   satırlar), trwiktionary öncelikli olacak şekilde tek kayıtta birleştirir.
   Öncelik: trwiktionary > dewiktionary > WikDict

2. ANLAM SIRALAMA
   `turkce` alanındaki `;` ile ayrılmış anlamları önce trwiktionary,
   sonra dewiktionary sırasına göre düzenler (kaynak bilgisine dayanarak).

Usage:
  python fix_wiktionary_order.py [--dry-run]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent
DICT_PATH = SCRIPTS_DIR.parent / "output" / "dictionary.json"

SOURCE_PRIORITY = {
    "trwiktionary": 0,
    "dewiktionary": 1,
    "WikDict": 2,
    "goethe-institut": 3,
}


def source_rank(record: dict) -> int:
    """Kaydın en yüksek öncelikli kaynağının rank'ı."""
    kaynak = record.get("kaynak", "")
    for src, rank in sorted(SOURCE_PRIORITY.items(), key=lambda x: x[1]):
        if src in kaynak:
            return rank
    return 99


def merge_two(primary: dict, secondary: dict) -> dict:
    """secondary'deki bilgileri primary'ye aktar, primary öncelikli."""
    # Türkçe çevirileri birleştir: primary önce, secondary'den ekstra anlamlar ekle
    p_meanings = [m.strip() for m in primary.get("turkce", "").split(";") if m.strip()]
    s_meanings = [m.strip() for m in secondary.get("turkce", "").split(";") if m.strip()]

    # Önce primary'nin tüm bireysel anlamlarını topla (virgülle ayrılmış alt anlamlar dahil)
    all_atoms: set[str] = set()
    for m in p_meanings:
        for atom in m.split(","):
            all_atoms.add(atom.strip().lower())

    merged_meanings = list(p_meanings)
    for m in s_meanings:
        # Bu anlam (ya da atom'ları) zaten var mı?
        m_atoms = {atom.strip().lower() for atom in m.split(",")}
        if not m_atoms.issubset(all_atoms):
            merged_meanings.append(m)
            all_atoms.update(m_atoms)

    primary["turkce"] = "; ".join(merged_meanings)

    # Kaynak birleştir
    p_sources = set(primary.get("kaynak", "").split("; "))
    s_sources = set(secondary.get("kaynak", "").split("; "))
    all_sources = sorted(p_sources | s_sources - {""})
    primary["kaynak"] = "; ".join(all_sources)

    # Açıklama: uzun olanı al
    if len(secondary.get("aciklama_turkce", "")) > len(primary.get("aciklama_turkce", "")):
        primary["aciklama_turkce"] = secondary["aciklama_turkce"]

    # Örnek cümleler: primary'de yoksa secondary'den al
    if not primary.get("ornek_almanca") and secondary.get("ornek_almanca"):
        primary["ornek_almanca"] = secondary["ornek_almanca"]
        primary["ornek_turkce"] = secondary.get("ornek_turkce", "")

    # ornekler listesi: ekstra olanları ekle
    existing_de = {o.get("almanca", "") for o in primary.get("ornekler", [])}
    for ornek in secondary.get("ornekler", []):
        if ornek.get("almanca", "") and ornek["almanca"] not in existing_de:
            primary.setdefault("ornekler", []).append(ornek)
            existing_de.add(ornek["almanca"])

    # not: uzun olanı al
    if len(secondary.get("not", "")) > len(primary.get("not", "")):
        primary["not"] = secondary["not"]

    # seviye: primary'de yoksa secondary'den al
    if not primary.get("seviye") and secondary.get("seviye"):
        primary["seviye"] = secondary["seviye"]

    # zipf_skoru: büyük olanı al
    if secondary.get("zipf_skoru", 0) > primary.get("zipf_skoru", 0):
        primary["zipf_skoru"] = secondary["zipf_skoru"]

    return primary


def main(dry_run: bool = False) -> None:
    with open(DICT_PATH, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Toplam kayıt: {len(data)}")

    # Kelime+tur bazında grupla
    groups: dict[tuple, list] = defaultdict(list)
    for r in data:
        key = (r.get("almanca", "").lower().strip(), r.get("tur", ""))
        groups[key].append(r)

    multi_groups = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"Çoklu kayıt grubu: {len(multi_groups)}")

    to_remove: set[int] = set()
    merged_count = 0

    for (word, tur), records in multi_groups.items():
        # Kaynak önceliğine göre sırala
        sorted_recs = sorted(records, key=source_rank)
        primary = sorted_recs[0]

        for secondary in sorted_recs[1:]:
            if not dry_run:
                merge_two(primary, secondary)
            print(f"  [BİRLEŞTİR] '{word}' ({tur}): "
                  f"{secondary.get('kaynak','')[:30]!r} → {primary.get('kaynak','')[:30]!r}")
            to_remove.add(id(secondary))
            merged_count += 1

    new_data = [r for r in data if id(r) not in to_remove]

    print(f"\n{'='*60}")
    print(f"Birleştirilen (silinen) kayıt: {merged_count}")
    print(f"Eski kayıt sayısı: {len(data)}")
    print(f"Yeni kayıt sayısı: {len(new_data)}")

    if not dry_run:
        with open(DICT_PATH, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        print(f"Kaydedildi: {DICT_PATH}")
    else:
        print("[DRY RUN]")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
