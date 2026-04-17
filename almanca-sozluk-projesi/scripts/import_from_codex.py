#!/usr/bin/env python3
"""
import_from_codex.py
=====================
GPT Codex'ten gelen doldurulmuş batch dosyalarını dictionary.json'a yazar.

Kullanım:
  # Tek dosya:
  python scripts/import_from_codex.py output/codex/fiil_kaliplari_batch_01.json

  # Bir dizindeki tüm dosyalar:
  python scripts/import_from_codex.py output/codex/

  # Sadece belirli görev:
  python scripts/import_from_codex.py output/codex/ --gorev fiil_kaliplari
  python scripts/import_from_codex.py output/codex/ --gorev ceviri

GPT'nin doldurması gereken alanlar:
  fiil_kaliplari görevi → her fiil için "fiil_kaliplari" listesi eklenmeli
  ceviri görevi        → her kayıt için "turkce_cumleler" listesi eklenmeli
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATH    = PROJECT_ROOT / "output" / "dictionary.json"
SOURCE_FIIL   = "GPT Codex (otomatik kalıp)"
SOURCE_CEVIRI = "GPT Codex (otomatik çeviri)"
SOURCE_TANIM  = "GPT Codex (otomatik tanım)"


def import_fiil_kaliplari(batch: dict, lookup: dict[str, int], dictionary: list[dict]) -> tuple[int, int]:
    """fiil_kaliplari batch'ini işle. Döndürür: (eklenen_fiil, eklenen_kalip)"""
    updated_verbs = 0
    added_patterns = 0

    for item in batch.get("fiiller", []):
        almanca = (item.get("almanca") or "").strip()
        new_kaliplar = item.get("fiil_kaliplari") or []
        if not almanca or not new_kaliplar:
            continue

        idx = lookup.get(almanca)
        if idx is None:
            print(f"  UYARI: '{almanca}' sözlükte bulunamadı, atlanıyor.")
            continue

        rec = dictionary[idx]
        existing: list[dict] = list(rec.get("fiil_kaliplari") or [])
        existing_keys = {(k.get("kalip") or "").strip().casefold() for k in existing}

        added = 0
        for p in new_kaliplar:
            kalip_str = (p.get("kalip") or "").strip()
            kalip_tr  = (p.get("turkce") or "").strip()
            if not kalip_str or not kalip_tr:
                continue
            if kalip_str.casefold() in existing_keys:
                continue
            existing.append({
                "kalip": kalip_str,
                "turkce": kalip_tr,
                "ornek_almanca": (p.get("ornek_almanca") or "").strip(),
                "ornek_turkce":  (p.get("ornek_turkce") or "").strip(),
                "kaynak": SOURCE_FIIL,
            })
            existing_keys.add(kalip_str.casefold())
            added += 1
            added_patterns += 1

        if added:
            dictionary[idx]["fiil_kaliplari"] = existing
            updated_verbs += 1
            print(f"  ✓ {almanca}: {added} kalıp eklendi")

    return updated_verbs, added_patterns


def import_ceviriler(batch: dict, lookup: dict[str, int], dictionary: list[dict]) -> tuple[int, int]:
    """ceviri batch'ini işle. Döndürür: (guncellenen_kayit, eklenen_ceviri)"""
    updated_records = 0
    added_translations = 0

    for item in batch.get("kayitlar", []):
        almanca = (item.get("almanca") or "").strip()
        turkce_cumleler = item.get("turkce_cumleler") or []
        if not almanca or not turkce_cumleler:
            continue

        idx = lookup.get(almanca)
        if idx is None:
            print(f"  UYARI: '{almanca}' sözlükte bulunamadı, atlanıyor.")
            continue

        rec = dictionary[idx]
        ornekler: list[dict] = rec.get("ornekler") or []

        # Türkçesi eksik cümleleri bul (export ile aynı sıra)
        eksik_indices = [
            i for i, ex in enumerate(ornekler)
            if (ex.get("almanca") or "").strip()
            and not (ex.get("turkce") or "").strip()
        ]

        added = 0
        for local_i, tr_text in enumerate(turkce_cumleler):
            tr_text = str(tr_text).strip()
            if not tr_text or local_i >= len(eksik_indices):
                break
            real_i = eksik_indices[local_i]
            ornekler[real_i]["turkce"] = tr_text
            ornekler[real_i]["kaynak"] = ornekler[real_i].get("kaynak", "") or SOURCE_CEVIRI
            added += 1
            added_translations += 1

            # İlk örnek ise üst seviye alanı da doldur
            if real_i == 0 and not (rec.get("ornek_turkce") or "").strip():
                dictionary[idx]["ornek_turkce"] = tr_text

        if added:
            dictionary[idx]["ornekler"] = ornekler
            updated_records += 1

    return updated_records, added_translations


def import_tanim_turkce(batch: dict, lookup: dict[str, int], dictionary: list[dict]) -> int:
    """tanim_turkce batch'ini işle. Döndürür: güncellenen kayıt sayısı"""
    updated = 0
    for item in batch.get("kayitlar", []):
        almanca = (item.get("almanca") or "").strip()
        aciklama = (item.get("aciklama_turkce") or "").strip()
        if not almanca or not aciklama:
            continue
        idx = lookup.get(almanca)
        if idx is None:
            print(f"  UYARI: '{almanca}' sözlükte bulunamadı, atlanıyor.")
            continue
        if (dictionary[idx].get("aciklama_turkce") or "").strip():
            continue  # zaten dolu, üzerine yazma
        dictionary[idx]["aciklama_turkce"] = aciklama
        updated += 1
        print(f"  ✓ {almanca}: {aciklama[:60]}")
    return updated


def collect_batch_files(path: Path, gorev: str | None) -> list[Path]:
    if path.is_file():
        return [path]
    files = sorted(path.glob("*.json"))
    if gorev:
        files = [f for f in files if f.name.startswith(gorev)]
    # Sadece GPT'nin doldurduğu dosyalar (orijinal export dosyaları değil)
    return files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Batch dosyası veya dizin yolu")
    parser.add_argument("--gorev", choices=["fiil_kaliplari", "ceviri", "tanim_turkce"],
                        help="Sadece bu görev tipini işle")
    parser.add_argument("--dry-run", action="store_true", help="Kaydetmeden kontrol et")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"HATA: {target} bulunamadı")
        sys.exit(1)

    files = collect_batch_files(target, args.gorev)
    if not files:
        print("İşlenecek dosya bulunamadı.")
        sys.exit(0)

    print(f"Sözlük yükleniyor...")
    dictionary: list[dict] = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    lookup = {(r.get("almanca") or "").strip(): i for i, r in enumerate(dictionary)}
    print(f"  {len(dictionary):,} kayıt | {len(files)} batch dosyası\n")

    total_verbs = total_patterns = total_records = total_translations = total_tanim = 0

    for fpath in files:
        try:
            batch = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  HATA ({fpath.name}): {e}")
            continue

        gorev = batch.get("gorev", "")
        print(f"[{fpath.name}] gorev={gorev}")

        if gorev == "fiil_kaliplari":
            v, p = import_fiil_kaliplari(batch, lookup, dictionary)
            total_verbs += v
            total_patterns += p
        elif gorev == "ceviri":
            r, t = import_ceviriler(batch, lookup, dictionary)
            total_records += r
            total_translations += t
        elif gorev == "tanim_turkce":
            n = import_tanim_turkce(batch, lookup, dictionary)
            total_tanim += n
        else:
            print(f"  Bilinmeyen görev: {gorev}, atlanıyor.")

    if not args.dry_run:
        DICT_PATH.write_text(
            json.dumps(dictionary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nKaydedildi: {DICT_PATH}")

    print(f"\n{'='*50}")
    print("ÖZET")
    if total_verbs:
        print(f"  Fiil kalıbı eklenen fiil  : {total_verbs:,}")
        print(f"  Eklenen toplam kalıp      : {total_patterns:,}")
    if total_records:
        print(f"  Çeviri eklenen kayıt      : {total_records:,}")
        print(f"  Eklenen toplam çeviri     : {total_translations:,}")
    if total_tanim:
        print(f"  Türkçe tanım eklenen kayıt: {total_tanim:,}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
