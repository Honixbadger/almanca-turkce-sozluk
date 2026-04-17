#!/usr/bin/env python3
"""
review_translations_v4.py — Round 4
Semantik hatalar + duplikat temizliği.
"""
from __future__ import annotations
import json, sys, shutil
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JSONL = Path("C:/Users/ozan/Desktop/almanca sözlük projesi/Playground-Yedek/almanca-sozluk-projesi/output/dictionary.jsonl")

# (almanca, eski_substr) → yeni_turkce
FIXES = {
    # Ode → od YANLIŞ (od=ateş Türkçede)
    ("Ode", "od"):                  "ode (şiir türü); boş, ıssız (eski kullanım)",

    # Dienst → 'iş' çok dar
    ("Dienst", "iş"):               "hizmet, görev, servis",

    # Dienst → 'beraberce aynı işi...' tamamen yanlış
    ("Dienst", "beraberce"):        "nöbet, vardiya; hizmet görevi",

    # Stelle → 'iş' → konum/yer daha doğru
    ("Stelle", "iş"):               "konum, yer, pozisyon; görev yeri",

    # Management → uzun açıklama
    ("Management", "Bir problem"):  "yönetim, yöneticilik",

    # Wort (bilgisayar terimi) → uzun
    ("Wort", "belli bir uzunlukta"): "sözcük, kelime; veri kelimesi (bilişim)",

    # Hund → 'it' informal (köpek daha nötr)
    ("Hund", "it"):                 "köpek",
}

# Duplikat kaldırma: (almanca, tur) için ikinci ve sonraki kopyaları sil
DEDUP_KEYS = {
    ("also",  "ünlem"),   # 4 kopya → 1'e indir
    ("woher", "zamir"),   # 2 kopya → 1'e indir
    ("wohin", "zamir"),   # 2 kopya → 1'e indir
}


def main():
    backup = JSONL.with_suffix(".jsonl.bak_review4")
    shutil.copy2(JSONL, backup)
    print(f"Yedek: {backup}\n")

    entries = []
    with open(JSONL, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    log = []
    fixed = 0

    # ── Hedefli düzeltmeler ──────────────────────────────────────────────────
    for e in entries:
        alm = e["almanca"]
        tr  = e.get("turkce", "").strip()
        for (k_alm, k_sub), new_tr in FIXES.items():
            if alm == k_alm and k_sub in tr:
                e["turkce"] = new_tr
                log.append({"almanca": alm, "eski": tr, "yeni": new_tr})
                fixed += 1
                break

    # ── Duplikat temizliği ───────────────────────────────────────────────────
    seen_counts: dict[tuple, int] = {}
    new_entries = []
    for e in entries:
        key = (e["almanca"], e.get("tur", ""))
        if key in DEDUP_KEYS:
            seen_counts[key] = seen_counts.get(key, 0) + 1
            if seen_counts[key] > 1:
                log.append({"almanca": f"{e['almanca']} ({e.get('tur')}) duplikat",
                            "eski": e.get("turkce", ""), "yeni": "SİLİNDİ"})
                fixed += 1
                continue
        new_entries.append(e)
    entries = new_entries

    # ── Kaydet ──────────────────────────────────────────────────────────────
    with open(JSONL, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # ── Rapor ───────────────────────────────────────────────────────────────
    print(f"Toplam işlem: {fixed}\n{'='*65}")
    for l in log:
        if "SİLİNDİ" in l["yeni"]:
            print(f"  SİLİNDİ: {l['almanca']} | {l['eski'][:50]}")
        else:
            print(f"  [{l['almanca']:22}] ESK: {l['eski'][:50]}")
            print(f"  {'':22}   YEN: {l['yeni'][:50]}")
            print()


if __name__ == "__main__":
    main()
