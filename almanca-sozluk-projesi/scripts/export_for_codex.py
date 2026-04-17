#!/usr/bin/env python3
"""
export_for_codex.py
====================
GPT Codex / ChatGPT için iki görev dosyası oluşturur:

1. output/codex/fiil_kaliplari_batch_XX.json
   → 1.646 fiilin valenz kalıplarını ürettirmek için

2. output/codex/ceviri_batch_XX.json
   → Eksik Türkçe örnek çevirilerini ürettirmek için

Her batch ~100 kayıt içerir, GPT'ye birer birer gönderilebilir.
Geri dönen sonuçları birleştirmek için import_from_codex.py kullanılır.
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATH    = PROJECT_ROOT / "output" / "dictionary.json"
OUT_DIR      = PROJECT_ROOT / "output" / "codex"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FIIL_BATCH_SIZE  = 100   # Her fiil batch'inde kaç fiil
CEVIRI_BATCH_SIZE = 50   # Her çeviri batch'inde kaç kayıt


def export_fiil_kaliplari(data: list[dict]) -> None:
    """Fiil kalıbı eksik olan fiilleri batchler halinde export et."""
    targets = []
    for rec in data:
        tur = (rec.get("tur") or "").casefold()
        if tur not in {"fiil", "verb"}:
            continue
        almanca = (rec.get("almanca") or "").strip()
        if not almanca:
            continue
        kaliplar = rec.get("fiil_kaliplari") or []
        if len(kaliplar) >= 2:
            continue
        targets.append({
            "almanca": almanca,
            "turkce":  (rec.get("turkce") or "").strip(),
        })

    print(f"  Fiil kalıbı eksik: {len(targets):,}")

    ACIKLAMA = (
        "Aşağıdaki Almanca fiillerin her biri için 3 yaygın valenz kalıbı (Valenzmuster) listele.\n"
        "Her satırda: ALMANCA_KALIP | TÜRKÇE_AÇIKLAMA\n"
        "Kısaltmalar: jd.=jemand(Nom), jdn.=jemanden(Akk), jdm.=jemandem(Dat), "
        "etw.(A)=etwas Akkusativ, etw.(D)=etwas Dativ, irgendwo=bir yerde, irgendwohin=bir yere\n"
        "Örnek: etw. kaufen | bir şey satın almak\n"
        "Çıktı formatı: Her fiil için 'almanca' alanı aynı kalacak, "
        "'fiil_kaliplari' listesine şu formatta ekle:\n"
        '{"kalip": "ALMANCA_KALIP", "turkce": "TÜRKÇE"}'
    )

    batch_num = 0
    for start in range(0, len(targets), FIIL_BATCH_SIZE):
        batch_num += 1
        batch = targets[start:start + FIIL_BATCH_SIZE]
        out = {
            "gorev": "fiil_kaliplari",
            "aciklama": ACIKLAMA,
            "batch": batch_num,
            "toplam_batch": (len(targets) + FIIL_BATCH_SIZE - 1) // FIIL_BATCH_SIZE,
            "fiiller": batch,
            "beklenen_cikti_formati": [
                {
                    "almanca": "ÖRNEK_FİİL",
                    "fiil_kaliplari": [
                        {"kalip": "etw. ÖRNEK_FİİL", "turkce": "bir şeyi örnek etmek"},
                        {"kalip": "jdm. etw. ÖRNEK_FİİL", "turkce": "birine bir şeyi örnek etmek"}
                    ]
                }
            ]
        }
        path = OUT_DIR / f"fiil_kaliplari_batch_{batch_num:02d}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  → {path.name}  ({len(batch)} fiil)")

    print(f"  Toplam {batch_num} fiil kalıbı batch dosyası oluşturuldu.\n")


def export_ceviriler(data: list[dict]) -> None:
    """Türkçe çevirisi eksik örnek cümleleri batchler halinde export et."""
    targets = []
    for rec in data:
        almanca = (rec.get("almanca") or "").strip()
        if not almanca:
            continue
        eksik = [
            ex.get("almanca", "").strip()
            for ex in (rec.get("ornekler") or [])
            if ex.get("almanca", "").strip()
            and not (ex.get("turkce") or "").strip()
        ]
        if not eksik:
            continue
        targets.append({
            "almanca": almanca,
            "turkce_anlam": (rec.get("turkce") or "").strip(),
            "cevirilecek_cumleler": eksik,
        })

    toplam_cumle = sum(len(t["cevirilecek_cumleler"]) for t in targets)
    print(f"  Çevirisi eksik kayıt: {len(targets):,}  ({toplam_cumle:,} cümle)")

    ACIKLAMA = (
        "Aşağıdaki Almanca kelimelerin örnek cümlelerini Türkçeye çevir.\n"
        "Her cümle için kısa, doğal Türkçe çeviri yaz.\n"
        "Çıktı formatı: 'almanca' alanı aynı kalacak, "
        "'cevirilecek_cumleler' dizisindeki her cümle için "
        "aynı sırayla Türkçe karşılığını 'turkce_cumleler' listesine yaz."
    )

    batch_num = 0
    for start in range(0, len(targets), CEVIRI_BATCH_SIZE):
        batch_num += 1
        batch = targets[start:start + CEVIRI_BATCH_SIZE]
        cumle_sayisi = sum(len(t["cevirilecek_cumleler"]) for t in batch)
        out = {
            "gorev": "ceviri",
            "aciklama": ACIKLAMA,
            "batch": batch_num,
            "toplam_batch": (len(targets) + CEVIRI_BATCH_SIZE - 1) // CEVIRI_BATCH_SIZE,
            "kayitlar": batch,
            "beklenen_cikti_formati": [
                {
                    "almanca": "kaufen",
                    "turkce_cumleler": [
                        "Dün bir kitap satın aldım.",
                        "O her hafta alışveriş yapar."
                    ]
                }
            ]
        }
        path = OUT_DIR / f"ceviri_batch_{batch_num:03d}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        if batch_num <= 5 or batch_num % 20 == 0:
            print(f"  → {path.name}  ({len(batch)} kayıt, {cumle_sayisi} cümle)")

    print(f"  ... toplam {batch_num} çeviri batch dosyası oluşturuldu.\n")


def main() -> None:
    print("=" * 60)
    print("export_for_codex.py — GPT Codex Export")
    print("=" * 60)

    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(data):,} kayıt yüklendi.\n")

    print("[ 1 ] Fiil kalıpları export...")
    export_fiil_kaliplari(data)

    print("[ 2 ] Eksik çeviriler export...")
    export_ceviriler(data)

    print("=" * 60)
    print(f"Tüm dosyalar: {OUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
