#!/usr/bin/env python3
"""
review_translations.py
Tüm çevirileri tarar, hataları sınıflandırır, otomatik düzeltir ve rapor üretir.
"""
from __future__ import annotations
import json, re, sys, shutil
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JSONL = Path("C:/Users/ozan/Desktop/almanca sözlük projesi/Playground-Yedek/almanca-sozluk-projesi/output/dictionary.jsonl")

# ─── Bilinen manuel düzeltmeler ──────────────────────────────────────────────
MANUAL_FIXES = {
    # almanca_kelime : yeni_turkce
    "also":            "öyleyse, demek ki, peki, ee (Almancada dolgu sözcüğü olarak da kullanılır)",
    "automatisieren":  "otomatikleştirmek",
    "umherstreifen":   "ortalıkta dolaşmak, avare gezmek",
    "Kokon":           "koza (ipek böceği pupası)",
    "Ostfälisch":      "Ostfalya lehçesi (Orta Almanca diyalekti)",
    # gramer notları içeren fiiller — temizlenmiş hali:
    "abfahren":        "ayrılmak, kalkmak (bir yerden hareket etmek)",
    "raten":           "tavsiye vermek, önermek, nasihat vermek",
    "denken":          "düşünmek, akıl yürütmek",
    "fragen":          "sormak, soru sormak",
    "kosten":          "maliyeti olmak, tutmak (fiyat belirtmek)",
    "sorgen":          "endişelenmek, kaygılanmak; sağlamak, temin etmek",
    "arbeiten":        "çalışmak, iş yapmak",
    "erinnern":        "hatırlatmak, anımsatmak; (sich erinnern) hatırlamak",
    "anstoßen":        "kadeh tokuşturmak; çarpmak, tokuşmak",
    "verurteilen":     "mahkûm etmek, hüküm giydirmek",
    "entschuldigen":   "özür dilemek, affını istemek; mazur görmek",
    "saufen":          "içmek (hayvanlar için); aşırı içmek (argo)",
}

# ─── Hata tespit kuralları ───────────────────────────────────────────────────

def detect_problems(alm: str, tr: str, tur: str) -> list[tuple[str, str]]:
    probs = []
    tr = tr.strip()

    # 1. İngilizce açıklama (Wiktionary kalıntısı)
    if re.search(r"\{\{|\}\}|^\s*An [a-z]|^\s*The [a-z]", tr):
        probs.append(("INGILIZCE_ACIKLAMA", tr[:60]))

    # 2. Gömülü Almanca gramer notu ([+ Dativ ...] gibi)
    if re.search(r"\[\s*\+\s*(Dativ|Akkusativ|Genitiv|yönelme|belirtme|çekimi)", tr):
        probs.append(("GRAMER_NOTU_EMBEDDED", tr[:60]))

    # 3. Fiil ama Türkçe mastar eki yok
    if tur == "fiil" and tr:
        clean = tr.rstrip(" .,;")
        if not re.search(r"(mak|mek)$", clean.split(",")[-1].split(";")[-1].strip()):
            probs.append(("FIIL_EKSIK_MASTAR", tr[:60]))

    # 4. Tanım gibi cümle (çeviri değil açıklama)
    if len(tr) > 20 and re.search(r"(belirtir|ifade eder|kullanılır|anlamına gelir)\s*\.", tr):
        if tur == "fiil":
            probs.append(("TANIM_DEGIL_CEVIRI", tr[:60]))

    # 5. Bilinen yanlış çeviriler
    if alm in MANUAL_FIXES:
        probs.append(("BILINEN_HATALI_CEVIRI", f"'{tr[:50]}' => '{MANUAL_FIXES[alm][:50]}'"))

    # 6. Türkçe olmayan karakterler yoğunluğu (Latin ama Türkçe dışı)
    if len(tr) > 10:
        non_tr = sum(1 for c in tr.lower() if c.isalpha() and c not in
                     "abcçdefgğhıijklmnoöprsştuüvyz ")
        ratio = non_tr / max(len([c for c in tr if c.isalpha()]), 1)
        if ratio > 0.3 and not any(c in tr for c in "çğışöüÇĞİŞÖÜ") and len(tr) > 15:
            probs.append(("LATIN_DISI_YOGUN", tr[:60]))

    # 7. Parantez içi gürültü (Almanca açıklama izi)
    if re.search(r"\(mit\s|mit\s+Dativ|mit\s+Akkusativ\)", tr):
        probs.append(("ALMANCA_GRAMER_PARANTEZ", tr[:60]))

    return probs


# ─── Ana döngü ───────────────────────────────────────────────────────────────

def main():
    backup = JSONL.with_suffix(".jsonl.bak_review")
    shutil.copy2(JSONL, backup)
    print(f"Yedek: {backup}\n")

    entries = []
    with open(JSONL, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    all_issues: dict[str, dict] = {}
    fixed_count = 0
    error_type_counter: Counter = Counter()

    # PASS 1 – Tespit + manuel düzeltme
    for e in entries:
        alm = e["almanca"]
        tr  = e.get("turkce", "").strip()
        tur = e.get("tur", "")

        probs = detect_problems(alm, tr, tur)
        if not probs:
            continue

        for tip, _ in probs:
            error_type_counter[tip] += 1

        all_issues[alm] = {
            "eski_turkce": tr,
            "tur": tur,
            "probs": probs,
            "fixed": False,
        }

        # Otomatik düzeltme: bilinen hatalar
        if alm in MANUAL_FIXES:
            e["turkce"] = MANUAL_FIXES[alm]
            all_issues[alm]["yeni_turkce"] = MANUAL_FIXES[alm]
            all_issues[alm]["fixed"] = True
            fixed_count += 1
            continue

        # Gömülü gramer notlarını temizle
        if any(t == "GRAMER_NOTU_EMBEDDED" for t, _ in probs):
            clean = re.sub(r"\s*\[.*?\]", "", tr).strip().rstrip(",;")
            if clean and clean != tr:
                e["turkce"] = clean
                all_issues[alm]["yeni_turkce"] = clean
                all_issues[alm]["fixed"] = True
                fixed_count += 1

    # PASS 2 – Fiil format düzeltmesi (mastar eki eksik, ama gömülü not yoksa)
    for e in entries:
        alm = e["almanca"]
        tr  = e.get("turkce", "").strip()
        tur = e.get("tur", "")
        if tur != "fiil" or alm in MANUAL_FIXES:
            continue
        if alm not in all_issues:
            continue
        probs = all_issues[alm].get("probs", [])
        if all_issues[alm].get("fixed"):
            continue
        for tip, _ in probs:
            if tip == "FIIL_EKSIK_MASTAR":
                # 'otomatikleştirme' → 'otomatikleştirmek'
                last_part = tr.rstrip(" .,;").split(",")[-1].strip()
                if last_part.endswith("me") or last_part.endswith("ma"):
                    yeni = tr.rstrip(" .,;") + "k"
                    e["turkce"] = yeni
                    all_issues[alm]["yeni_turkce"] = yeni
                    all_issues[alm]["fixed"] = True
                    fixed_count += 1

    # PASS 3 – Almanca gramer parantezi temizle
    for e in entries:
        alm = e["almanca"]
        tr  = e.get("turkce", "").strip()
        if alm in all_issues and all_issues[alm].get("fixed"):
            continue
        if re.search(r"\(mit\s+Dativ\)|\(mit\s+Akkusativ\)|\(haben\)|\(sein\)", tr):
            clean = re.sub(r"\s*\(mit\s+(Dativ|Akkusativ)\)", "", tr)
            clean = re.sub(r"\s*\((haben|sein)\)", "", clean).strip()
            if clean != tr:
                e["turkce"] = clean
                if alm not in all_issues:
                    all_issues[alm] = {"eski_turkce": tr, "tur": e.get("tur",""), "probs": [("ALMANCA_GRAMER_PARANTEZ","")], "fixed": True}
                all_issues[alm]["yeni_turkce"] = clean
                all_issues[alm]["fixed"] = True
                fixed_count += 1

    # ─── Kaydet ───────────────────────────────────────────────────────────────
    with open(JSONL, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # ─── Rapor ────────────────────────────────────────────────────────────────
    print("=" * 65)
    print("HATA TİPİ DAĞILIMI")
    print("=" * 65)
    for tip, cnt in error_type_counter.most_common():
        print(f"  {tip:35s} : {cnt}")

    print(f"\n{'='*65}")
    print(f"TOPLAM TESPİT  : {len(all_issues)}")
    print(f"OTOMATİK DÜZELTİLEN : {fixed_count}")
    print(f"HÂLÂ EL GEREKTİREN  : {len(all_issues) - fixed_count}")

    print(f"\n{'='*65}")
    print("DÜZELTILEN KAYITLAR")
    print("=" * 65)
    for alm, info in all_issues.items():
        if info.get("fixed"):
            print(f"  [{info['tur']:6}] {alm:25}")
            print(f"         ESKİ: {info['eski_turkce'][:70]}")
            print(f"         YENİ: {info.get('yeni_turkce','')[:70]}")
            print()

    print(f"\n{'='*65}")
    print("EL GEREKTİREN KAYITLAR (incelenmeli)")
    print("=" * 65)
    for alm, info in all_issues.items():
        if not info.get("fixed"):
            tips = [t for t,_ in info["probs"]]
            print(f"  [{info['tur']:6}] {alm:25} | {info['eski_turkce'][:50]} | {tips}")


if __name__ == "__main__":
    main()
