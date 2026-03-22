# -*- coding: utf-8 -*-
"""
cleanup_subset_duplicates.py
=============================
Aynı almanca + tur kombinasyonuna sahip, Türkçe anlamı bakımından
biri diğerinin alt kümesi olan duplikat kayıtları temizler.

Örnek:
  Kraftstoff (isim) → "yakıt"
  Kraftstoff (isim) → "akaryakıt; yakıt"   ← kapsamlı olan
  → "yakıt" kaydı silinir, eğer benzersiz verisi varsa kapsamlı olana aktarılır.

GÜVENLİ: Yalnızca Türkçe anlamların biri diğerinin gerçek alt kümesi
          olduğu durumlarda birleştirir. Farklı anlamları olan
          polisemik kelimeler (bank→banka/sıra, gift→zehir/hediye) korunur.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

DICT_PATH = Path(__file__).resolve().parent.parent / "output" / "dictionary.json"


def parse_turkce(s: str) -> set[str]:
    return {t.strip() for t in s.split(";") if t.strip()}


def merge_into(target: dict, source: dict) -> None:
    """Kaynak kaydın benzersiz verilerini hedefe aktar."""
    # Örnek cümleler
    existing = {o.get("almanca", "") for o in target.get("ornekler", [])}
    for ornek in source.get("ornekler", []):
        if ornek.get("almanca", "") and ornek["almanca"] not in existing:
            target.setdefault("ornekler", []).append(ornek)
            existing.add(ornek["almanca"])

    # kelime_ailesi
    ka_set = set(target.get("kelime_ailesi", []))
    ka_set.update(source.get("kelime_ailesi", []))
    if ka_set:
        target["kelime_ailesi"] = sorted(ka_set)

    # ilgili_kayitlar
    ilgili = set(target.get("ilgili_kayitlar", []))
    ilgili.update(source.get("ilgili_kayitlar", []))
    if ilgili:
        target["ilgili_kayitlar"] = sorted(ilgili)

    # kategoriler
    kats = set(target.get("kategoriler", []))
    kats.update(source.get("kategoriler", []))
    if kats:
        target["kategoriler"] = sorted(kats)

    # referans_linkler (dict formatı: {"duden": "url", "dwds": "url", ...})
    src_links = source.get("referans_linkler", {})
    tgt_links = target.get("referans_linkler", {})
    if isinstance(src_links, dict) and isinstance(tgt_links, dict):
        for k, v in src_links.items():
            if k not in tgt_links:
                tgt_links[k] = v
        if tgt_links:
            target["referans_linkler"] = tgt_links

    # not
    if source.get("not") and not target.get("not"):
        target["not"] = source["not"]

    # ornek_almanca / ornek_turkce
    if source.get("ornek_almanca") and not target.get("ornek_almanca"):
        target["ornek_almanca"] = source["ornek_almanca"]
        target["ornek_turkce"] = source.get("ornek_turkce", "")

    # Türkçe anlamları birleştir (superset zaten büyük, küçük olanlar eklenebilir)
    existing_tr = parse_turkce(target.get("turkce", ""))
    new_tr = parse_turkce(source.get("turkce", ""))
    merged_tr = existing_tr | new_tr
    if merged_tr != existing_tr:
        target["turkce"] = "; ".join(sorted(merged_tr))


def main(dry_run: bool = False) -> None:
    with open(DICT_PATH, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Toplam kayıt: {len(data)}")

    # almanca+tur bazında grupla
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, r in enumerate(data):
        almanca = r.get("almanca", "").strip().lower()
        tur = r.get("tur", "").strip().lower()
        if almanca:
            groups[(almanca, tur)].append(i)

    to_remove: set[int] = set()
    merge_count = 0

    for (almanca, tur), indices in groups.items():
        if len(indices) < 2:
            continue

        recs = [(idx, data[idx]) for idx in indices]
        trs = [(idx, parse_turkce(r.get("turkce", ""))) for idx, r in recs]

        # Alt küme tespiti: biri diğerinin gerçek alt kümesi mi?
        for i1, (idx1, t1) in enumerate(trs):
            if idx1 in to_remove:
                continue
            for i2, (idx2, t2) in enumerate(trs):
                if i1 == i2 or idx2 in to_remove:
                    continue
                # t1, t2'nin gerçek alt kümesiyse → idx1 redundant
                if t1 and t2 and t1 < t2:  # strict subset
                    print(f"  [{almanca!r}/{tur!r}] '{'; '.join(sorted(t1))}' → '{'; '.join(sorted(t2))}' içinde. Siliniyor.")
                    if not dry_run:
                        merge_into(data[idx2], data[idx1])
                    to_remove.add(idx1)
                    merge_count += 1
                    break

    new_data = [r for i, r in enumerate(data) if i not in to_remove]

    print(f"\n{'='*50}")
    print(f"Özet:")
    print(f"  Birleştirilen alt küme duplikat: {merge_count}")
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
