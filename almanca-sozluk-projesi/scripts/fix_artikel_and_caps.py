# -*- coding: utf-8 -*-
"""
fix_artikel_and_caps.py
========================
1. Artikel sadece isimlere ait  → isim olmayan kayıtlardan artikel siler
2. tur=isim + artikel var + küçük harf + tek kelime → büyük harfe çevirir
3. tur=isim + artikel yok + küçük harf + tek kelime → raporlar (tur hatası, dokunmaz)

Usage:
  python fix_artikel_and_caps.py [--dry-run]
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent
DICT_PATH = SCRIPTS_DIR.parent / "output" / "dictionary.json"

NOUN_TURS = {"isim", "isim (kısaltma)", "kısaltma", "kisaltma"}


def main(dry_run: bool = False) -> None:
    with open(DICT_PATH, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Toplam kayıt: {len(data)}")

    stat_artikel_removed = 0
    stat_caps_fixed = 0
    stat_skipped_no_art = 0

    for r in data:
        tur = r.get("tur", "").lower()
        w = r.get("almanca", "").strip()
        art = r.get("artikel", "").strip()

        # --- 1. Artikel temizliği: sadece isimde olmalı ---
        if art and tur not in NOUN_TURS:
            print(f"  [ARTIKEL-SIL] artikel={art!r} {w!r} (tur={r.get('tur','')!r})")
            if not dry_run:
                r["artikel"] = ""
            stat_artikel_removed += 1

        # --- 2. & 3. İsim büyük harf kontrolü ---
        if tur == "isim" and w and w[0].islower():
            # x-Achse gibi: tek harf + tire → meşru küçük harf
            if len(w) >= 2 and w[1] == "-":
                continue
            # Çok kelimeli ifade (grüner Pfeffer) → dokunma
            if len(w.split()) > 1:
                continue

            if art:
                # Artikel var → büyük ihtimalle gerçek isim, büyük harfe çevir
                new_w = w[0].upper() + w[1:]
                print(f"  [CAPS] {w!r} -> {new_w!r} ({art})")
                if not dry_run:
                    r["almanca"] = new_w
                stat_caps_fixed += 1
            else:
                # Artikel yok → büyük ihtimalle yanlış tur etiketi, raporla
                print(f"  [ATLA-NO-ART] {w!r} (tur=isim, artikel yok - tur hatası olabilir)")
                stat_skipped_no_art += 1

    print(f"\n{'='*60}")
    print(f"Artikel silinen (non-isim): {stat_artikel_removed}")
    print(f"Büyük harfe çevrilen isim:  {stat_caps_fixed}")
    print(f"Atlanan (artikel yok):      {stat_skipped_no_art}")

    if not dry_run:
        with open(DICT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Kaydedildi: {DICT_PATH}")
    else:
        print("[DRY RUN]")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
