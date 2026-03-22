# -*- coding: utf-8 -*-
"""
cleanup_inflected_adjectives.py
================================
Sözlükteki çekimli sıfat duplikalarını temizler.

Örnek: rasant + rasante + rasanten → sadece rasant kalır.

GÜVENLİ STRATEJİ:
  Yalnızca sözlükte birden fazla versiyonu olan grupları işle.
  Tek başına duran kayıtlara (tapfer, sicher, erfahren vs.) asla dokunma.

  1. Her sıfat kaydının potansiyel kök formunu lemmatize_adjective() ile bul.
  2. Aynı köke sahip FARKLI almanca'lara sahip 2+ kayıt varsa → grup olarak işle.
  3. Grupta kökün kendisi bir kayıt olarak mevcutsa:
       → Diğerlerini (çekimli) sil, verilerini köke birleştir.
  4. Grupta kök mevcut değilse:
       → En kısa almanca'yı kanonik say, türünü 'sıfat' yap, diğerlerini sil.
  5. Tek elemanlı gruplar: DOKUNMA.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from grammar_utils import lemmatize_adjective

DICT_PATH = SCRIPTS_DIR.parent / "output" / "dictionary.json"

# Sıfatla ilişkili türler
ADJECTIVE_TURS = {"sıfat", "sifat", "adjektiv", "adj", "sıfat (kısaltma)"}


def merge_into(canonical: dict, duplicate: dict) -> None:
    """Duplikattaki verileri canonical'a aktar."""
    # Örnek cümleler
    existing = {o.get("almanca", "") for o in canonical.get("ornekler", [])}
    for ornek in duplicate.get("ornekler", []):
        if ornek.get("almanca", "") and ornek["almanca"] not in existing:
            canonical.setdefault("ornekler", []).append(ornek)
            existing.add(ornek["almanca"])

    # Ornek almanca (basit alan)
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

    # Tüm almanca'ları küçük harfle indexle
    all_keys_lower = {r.get("almanca", "").strip().lower(): r for r in data}

    # Sadece tur=sıfat olan kayıtları işle.
    # Küçük harfle başlayan ama sıfat olarak etiketlenmemiş kayıtlar (fiil çekimleri,
    # zarflar vb.) false positive ürettiği için dahil edilmiyor.
    adjective_records = [
        r for r in data
        if r.get("tur", "").strip().lower() in ADJECTIVE_TURS
    ]

    print(f"Sıfat aday kaydı: {len(adjective_records)}")

    # Kök bazında grupla
    groups: dict[str, list[dict]] = defaultdict(list)
    for rec in adjective_records:
        almanca = rec.get("almanca", "").strip()
        base = lemmatize_adjective(almanca)
        groups[base].append(rec)

    to_remove: set[int] = set()
    modified: list[str] = []

    for base, group in sorted(groups.items(), key=lambda x: x[0]):
        # Farklı almanca değerine sahip kayıtları say
        unique_almanca = {r.get("almanca", "").strip() for r in group}

        if len(unique_almanca) <= 1:
            # Tek versiyon → dokunma
            continue

        # Birden fazla farklı yazım → çekimli duplikalar var
        print(f"\nGrup [{base!r}]: {sorted(unique_almanca)}")

        # Kanonik: base formun kendisi varsa onu kullan
        canonical = None
        for r in group:
            if r.get("almanca", "").strip().lower() == base.lower():
                canonical = r
                break

        # Yoksa en kısayı al
        if canonical is None:
            canonical = min(group, key=lambda r: len(r.get("almanca", "")))
            if not dry_run:
                old_almanca = canonical["almanca"]
                # Sıfatlar Almanca'da küçük harf başlar
                canonical["almanca"] = base[0].lower() + base[1:]
                canonical["tur"] = "sıfat"
                modified.append(f"{old_almanca!r} → {canonical['almanca']!r}")
                print(f"  Kanonik (düzeltildi): {old_almanca!r} → {canonical['almanca']!r}")
            else:
                print(f"  Kanonik (düzeltilecek): {canonical['almanca']!r} → {base!r}")

        for rec in group:
            if rec is canonical:
                print(f"  ✓ Korundu: {rec['almanca']!r}")
                continue
            # Bu bir çekimli duplikat — canonical'a birleştir ve sil
            print(f"  ✗ Silindi: {rec['almanca']!r}")
            if not dry_run:
                merge_into(canonical, rec)
            to_remove.add(id(rec))

    # Yeni liste: silinmeyenler
    new_data = [r for r in data if id(r) not in to_remove]

    print(f"\n{'='*50}")
    print(f"Özet:")
    print(f"  Silinen çekimli duplikat: {len(to_remove)}")
    print(f"  Düzeltilen kanonik form: {len(modified)}")
    print(f"  Yeni toplam kayıt: {len(new_data)}")

    if modified:
        print("  Düzeltmeler:")
        for m in modified:
            print(f"    {m}")

    if not dry_run:
        with open(DICT_PATH, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        print(f"  Kaydedildi: {DICT_PATH}")
    else:
        print("  [DRY RUN — dosya değiştirilmedi]")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
