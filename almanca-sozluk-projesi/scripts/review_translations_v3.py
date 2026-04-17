#!/usr/bin/env python3
"""
review_translations_v3.py — Round 3
Semantik hatalar + zamir/zarf/kısaltma hataları düzeltilir.
"""
from __future__ import annotations
import json, re, sys, shutil
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JSONL = Path("C:/Users/ozan/Desktop/almanca sözlük projesi/Playground-Yedek/almanca-sozluk-projesi/output/dictionary.jsonl")

# ─── Hedefli düzeltmeler (almanca, eski_turkce_substr_veya_None) → yeni_turkce ─
FIXES: dict[tuple[str, str | None], str] = {

    # ── SEMANTİK YANLIŞLAR ─────────────────────────────────────────────────
    # Locke = bukle (kıvırcık saç), kilit DEĞİL
    ("Locke", "kilit"):         "bukle, kıvırcık saç; lokma",

    # wohin = nereye, helâ DEĞİL
    ("wohin", "helâ"):          "nereye",

    # woher = nereden, "geldiği" DEĞİL
    ("woher", "geldiği"):       "nereden",

    # zumindest = en azından; synonyms list DEĞİL
    ("zumindest", "eş anlamlı"): "en azından, hiç değilse, asgari olarak",

    # ich: ': ben' → 'ben'
    ("ich", ": ben"):           "ben",

    # binnen = içinde, süre içinde; sadece 'iç' yetersiz
    ("binnen", "iç"):           "içinde, süre içinde, -e kadar",

    # A kısaltması → "O" yanlış; Almancada A = Autobahn veya Ampere
    ("A", "O"):                 "A (Autobahn veya Ampere kısaltması)",

    # ja (ünlem) → açıklama formatı
    ("ja", "Bir başarı sonucu"): "evet!, ya!, vay be! (başarı veya sevinci belirtir)",

    # ── KISALTMA HATALAR: 'X kavramının kısaltması' → Türkçe anlam ──────────
    ("BM",  "Belichtungsmesser kavramının"):
        "Pozlama Ölçer (Belichtungsmesser)",

    ("DLR", "Deutsches Zentrum"):
        "Almanya Hava ve Uzay Araştırma Merkezi",

    ("ADB", "Automatische Differantial-Bremse"):
        "Otomatik Diferansiyel Fren (ADB)",

    ("KBA", "Kraftfahrt-Bundesamt"):
        "Almanya Federal Motorlu Taşıtlar Dairesi",

    ("BIS", "Bremsstrahlungsisochromatenspektroskopie"):
        "Bremsstrahlung İzokromat Spektroskopisi (BIS)",

    ("LIF", "Lichtenfels kavramının"):
        "LIF (Lichtenfels kısaltması)",

    ("LED", "LED"):
        "Işık Yayan Diyot (LED – Light Emitting Diode)",

    ("DDSG", "Erste Donau"):
        "Birinci Tuna Buharlı Gemi Şirketi (DDSG)",

    # Abf. → Almanca açıklamalı; temizle
    ("Abf.", "Abfahrt (Hareket"):
        "Kalkış (Abfahrt kısaltması)",

    # ── BAĞLAÇ / EDAT FORMAT ────────────────────────────────────────────────
    # 'ja' edat anlamı 'malum olduğu üzere' → biraz düzenle
    ("ja", "malum olduğu üzere"): "malum olduğu üzere, hani ya, bilirsiniz",
}


def main():
    backup = JSONL.with_suffix(".jsonl.bak_review3")
    shutil.copy2(JSONL, backup)
    print(f"Yedek: {backup}\n")

    entries = []
    with open(JSONL, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    log: list[dict] = []
    fixed = 0

    for e in entries:
        alm = e["almanca"]
        tr  = e.get("turkce", "").strip()

        for (key_alm, key_sub), new_tr in FIXES.items():
            if alm != key_alm:
                continue
            match = (key_sub is None) or (key_sub in tr)
            if match:
                e["turkce"] = new_tr
                log.append({"almanca": alm, "eski": tr, "yeni": new_tr})
                fixed += 1
                break  # her kayıt için en fazla bir düzeltme

    # ── Çift `also` girişlerini teke indir (zarf olarak birden fazla kopyası var) ──
    # also 3x zarf, 4x ünlem, 1x bağlaç → zarf için tek tut, diğerlerini bırak
    seen_also_zarf = 0
    new_entries = []
    for e in entries:
        if e["almanca"] == "also" and e.get("tur") == "zarf":
            seen_also_zarf += 1
            if seen_also_zarf > 1:
                log.append({"almanca": "also (zarf-duplikat)", "eski": e["turkce"], "yeni": "SİLİNDİ"})
                fixed += 1
                continue
        new_entries.append(e)
    entries = new_entries

    # ── Kaydet ──────────────────────────────────────────────────────────────
    with open(JSONL, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"Toplam düzeltilen: {fixed}\n")
    print("=" * 65)
    for l in log:
        if l["yeni"] != "SİLİNDİ":
            print(f"  [{l['almanca']:25}]")
            print(f"    ESK: {l['eski'][:70]}")
            print(f"    YEN: {l['yeni'][:70]}")
            print()
        else:
            print(f"  SİLİNDİ: {l['almanca']} | {l['eski'][:50]}")


if __name__ == "__main__":
    main()
