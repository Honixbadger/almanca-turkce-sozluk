# -*- coding: utf-8 -*-
"""
cleanup_plural_nouns.py
=======================
Sözlükteki çoğul isim duplikalarını temizler.

Yöntem (GÜVENLİ):
  cogul alanını kullan: eğer bir kayıt A'nın cogul değeri başka bir kayıt B'nin
  almanca değeriyle aynıysa, B çoğul duplikasıdır → silinir, verisi A'ya aktarılır.

  Tek başına duran kayıtlara (cogul eşleşmesi olmayan) ASLA dokunma.

Örnek:
  Abkürzung (cogul=Abkürzungen) + Abkürzungen (ayrı kayıt) → Abkürzungen silindi.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent
DICT_PATH = SCRIPTS_DIR.parent / "output" / "dictionary.json"

# İsimle ilişkili türler
NOUN_TURS = {"isim", "isim (kısaltma)", "özel isim", "noun"}


def merge_into(canonical: dict, duplicate: dict) -> None:
    """Duplikattaki benzersiz verileri canonical'a aktar."""
    # Örnek cümleler
    existing = {o.get("almanca", "") for o in canonical.get("ornekler", [])}
    for ornek in duplicate.get("ornekler", []):
        if ornek.get("almanca", "") and ornek["almanca"] not in existing:
            canonical.setdefault("ornekler", []).append(ornek)
            existing.add(ornek["almanca"])

    # Basit örnek alanı
    if not canonical.get("ornek_almanca") and duplicate.get("ornek_almanca"):
        canonical["ornek_almanca"] = duplicate["ornek_almanca"]
        canonical["ornek_turkce"] = duplicate.get("ornek_turkce", "")

    # ilgili_kayitlar
    ilgili = set(canonical.get("ilgili_kayitlar", []))
    ilgili.update(duplicate.get("ilgili_kayitlar", []))
    canonical["ilgili_kayitlar"] = sorted(ilgili)

    # kategoriler
    kats = set(canonical.get("kategoriler", []))
    kats.update(duplicate.get("kategoriler", []))
    canonical["kategoriler"] = sorted(kats)

    # not
    if duplicate.get("not") and not canonical.get("not"):
        canonical["not"] = duplicate["not"]

    # turkce — farklı anlamları birleştir
    existing_tr = {t.strip() for t in canonical.get("turkce", "").split(";") if t.strip()}
    for t in duplicate.get("turkce", "").split(";"):
        t = t.strip()
        if t:
            existing_tr.add(t)
    canonical["turkce"] = "; ".join(sorted(existing_tr))


def main(dry_run: bool = False) -> None:
    with open(DICT_PATH, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Toplam kayıt: {len(data)}")

    # İsim türündeki kayıtlar
    noun_records = [r for r in data if r.get("tur", "").strip().lower() in NOUN_TURS]
    print(f"İsim kaydı: {len(noun_records)}")

    # almanca → kayıt haritası (hızlı arama için)
    almanca_map: dict[str, dict] = {}
    for r in noun_records:
        key = r.get("almanca", "").strip()
        if key:
            almanca_map[key] = r

    # cogul → tekil eşleştirmesi
    # Bir kaydın cogul değeri başka bir kaydın almanca değeriyle eşleşiyorsa o çoğul duplikası
    to_remove: set[int] = set()
    processed: list[str] = []

    for singular in noun_records:
        cogul = singular.get("cogul", "").strip()
        if not cogul:
            continue

        # cogul değeri başka bir kayıt olarak var mı?
        plural_record = almanca_map.get(cogul)
        if plural_record is None or plural_record is singular:
            continue

        print(f"\n  Tekil: {singular.get('almanca')!r} (cogul={cogul!r})")
        print(f"  Çoğul: {plural_record.get('almanca')!r} (tur={plural_record.get('tur')!r})")
        print(f"  → Çoğul silinecek, veri tekile aktarılacak")

        processed.append(f"{cogul!r} → {singular.get('almanca')!r}")
        to_remove.add(id(plural_record))
        if not dry_run:
            merge_into(singular, plural_record)

    # Yeni liste
    new_data = [r for r in data if id(r) not in to_remove]

    print(f"\n{'='*50}")
    print(f"Özet:")
    print(f"  Silinen çoğul duplikat: {len(to_remove)}")
    print(f"  Yeni toplam kayıt: {len(new_data)}")

    if not dry_run:
        with open(DICT_PATH, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        print(f"  Kaydedildi: {DICT_PATH}")
    else:
        print("  [DRY RUN — dosya değiştirilmedi]")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
