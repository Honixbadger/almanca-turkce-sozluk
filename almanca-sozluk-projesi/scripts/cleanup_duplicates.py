#!/usr/bin/env python3
"""
cleanup_duplicates.py
======================
Aynı `almanca` değerine sahip kayıtları tespit eder ve birleştirir.

Birleştirme stratejisi:
  - En zengin kaydı (en çok dolu alan) ana kayıt seçer
  - Diğer kayıtların alanlarından eksik olanları ana kayda ekler
  - ornekler listesi birleştirilir (tekrarlar çıkarılır)
  - Rapor: output/duplicates_report.json

Kullanım:
    python scripts/cleanup_duplicates.py --dry-run   # Sadece rapor
    python scripts/cleanup_duplicates.py             # Birleştir + kaydet
"""
from __future__ import annotations
import json, sys, collections
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH   = Path("output/dictionary.json")
REPORT_PATH = Path("output/duplicates_report.json")

LIST_FIELDS   = ["ornekler", "sinonim", "antonim", "esanlamlilar", "anlamlar",
                 "baglamlar", "kategoriler", "fiil_kaliplari", "bilesen_kelimeler",
                 "ilgili_kayitlar", "referans_linkler", "kelime_ailesi"]
SCALAR_FIELDS = ["turkce", "tur", "telaffuz", "artikel", "cogul", "seviye",
                 "aciklama_turkce", "tanim_almanca", "ornek_almanca", "ornek_turkce",
                 "zipf_skoru", "ceviri_durumu", "genitiv_endung", "verb_typ",
                 "trennbar", "trennbar_prefix", "valenz", "partizip2",
                 "prateritum", "perfekt_yardimci"]


def richness(rec: dict) -> int:
    """Doluluk skoru — ne kadar çok alan dolu, o kadar yüksek."""
    score = 0
    for v in rec.values():
        if v and v not in ([], {}, "", None):
            score += 1
            if isinstance(v, list):
                score += len(v)
    return score


def merge(records: list[dict]) -> dict:
    """Birden fazla kaydı tek kayda birleştirir."""
    records_sorted = sorted(records, key=richness, reverse=True)
    base = dict(records_sorted[0])

    for rec in records_sorted[1:]:
        # Scalar alanlar: base'de boşsa doldur
        for f in SCALAR_FIELDS:
            if not (base.get(f) or "").strip() if isinstance(base.get(f), str) else not base.get(f):
                if rec.get(f):
                    base[f] = rec[f]

        # Liste alanları: birleştir, tekrarları çıkar
        for f in LIST_FIELDS:
            existing = base.get(f) or []
            incoming = rec.get(f) or []
            if not incoming:
                continue
            if f == "ornekler":
                seen_de = {(e.get("almanca") or "").strip().casefold() for e in existing}
                for e in incoming:
                    key = (e.get("almanca") or "").strip().casefold()
                    if key and key not in seen_de:
                        existing.append(e)
                        seen_de.add(key)
            else:
                seen = {str(x).strip().casefold() for x in existing}
                for x in incoming:
                    if str(x).strip().casefold() not in seen:
                        existing.append(x)
                        seen.add(str(x).strip().casefold())
            base[f] = existing

        # Kaynak birleştir
        k1 = (base.get("kaynak") or "")
        k2 = (rec.get("kaynak") or "")
        if k2 and k2 not in k1:
            base["kaynak"] = "; ".join(filter(None, [k1, k2]))

    return base


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Kaydetmeden rapor üret")
    args = parser.parse_args()

    print("Sözlük yükleniyor...", flush=True)
    data: list[dict] = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(data):,} kayıt", flush=True)

    # Grupla
    groups: dict[str, list[int]] = collections.defaultdict(list)
    for i, rec in enumerate(data):
        key = (rec.get("almanca") or "").strip()
        if key:
            groups[key].append(i)

    dup_groups = {k: idxs for k, idxs in groups.items() if len(idxs) > 1}
    total_extra = sum(len(v) - 1 for v in dup_groups.values())

    print(f"  Duplike kelime: {len(dup_groups):,}", flush=True)
    print(f"  Silinecek fazla kayıt: {total_extra:,}", flush=True)

    # Rapor
    report = []
    merged_data: list[dict] = []
    removed_indices: set[int] = set()

    for almanca, idxs in dup_groups.items():
        records = [data[i] for i in idxs]
        merged = merge(records)
        report.append({
            "almanca": almanca,
            "kopya_sayisi": len(idxs),
            "birlestirildi": True,
            "ornekler_oncesi": sum(len(data[i].get("ornekler") or []) for i in idxs),
            "ornekler_sonrasi": len(merged.get("ornekler") or []),
        })
        # Ana kayıt olarak merged'i kullan, diğerlerini işaretle
        data[idxs[0]] = merged
        for i in idxs[1:]:
            removed_indices.add(i)

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRapor: {REPORT_PATH}", flush=True)

    if args.dry_run:
        print("Dry-run — kaydedilmedi.")
        print("\nÖrnek birleştirmeler:")
        for r in report[:5]:
            print(f"  {r['almanca']}: {r['kopya_sayisi']}x → ornekler {r['ornekler_oncesi']} → {r['ornekler_sonrasi']}")
        return

    # Temiz listeyi oluştur
    clean = [rec for i, rec in enumerate(data) if i not in removed_indices]
    DICT_PATH.write_text(json.dumps(clean, ensure_ascii=False, separators=(",",":")), encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"ÖZET")
    print(f"  Önceki kayıt sayısı : {len(data):,}")
    print(f"  Silinen fazla kayıt : {total_extra:,}")
    print(f"  Yeni kayıt sayısı   : {len(clean):,}")
    print(f"  Kaydedildi: {DICT_PATH}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
