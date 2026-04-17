#!/usr/bin/env python3
"""
review_translations_v2.py
Kapsamlı çeviri kalite düzeltmesi — Round 2
Tespit edilen tüm hata kategorileri düzeltilir ve raporlanır.
"""
from __future__ import annotations
import json, re, sys, shutil
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JSONL = Path("C:/Users/ozan/Desktop/almanca sözlük projesi/Playground-Yedek/almanca-sozluk-projesi/output/dictionary.jsonl")

# ─────────────────────────────────────────────────────────────────────────────
# HATA KATEGORİLERİ VE DÜZELTMELERİ
# Key format:  (almanca_kelime, eski_turkce_substr_veya_None)  → yeni_turkce
# None: bu almanca kelimeye ait TEK bir eşleşen turkce değeri var veya
#       ilk bulunan problematic giriş düzeltilir
# ─────────────────────────────────────────────────────────────────────────────

# (almanca, eski_turkce) → yeni_turkce
# eski_turkce=None → o kelimenin sorunlu girişini bul (büyük harf ile başlıyor veya nokta ile bitiyor)
TARGETED_FIXES: dict[tuple[str, str | None], str] = {

    # ── FİİL HATALAR ─────────────────────────────────────────────────────────

    # "Benimsemek." → yanlış anlam + yanlış format
    ("aufgreifen", None): "yakalamak, gözaltına almak; (bir konuyu) ele almak, derinleştirmek",

    # "kadar gitmek" → tamamen yanlış
    ("hochfahren", None): "yukarıya gitmek, çıkmak; (bilgisayar) açmak, başlatmak; (kişi) öfkeyle yerinden fırlamak",

    # "Belirli bir zaman aralığı..." → açıklama formatı
    ("ablaufen", "Belirli"): "sona ermek, bitmek, dolmak (süre için); akmak (sıvı)",

    # "çözmek" → çok genel
    ("abkoppeln", "çözmek"): "ayırmak, kopmak, bağlantısını kesmek (vagon, treyler vb.)",

    # "açıklamak" → yanlış anlam
    ("vermitteln", "açıklamak"): "aracılık etmek, arabuluculuk yapmak; aktarmak, iletmek; öğretmek",

    # "gölgede bırakmak" → yanlış (sinema terimi)
    ("überblenden", None): "üst üste bindirmek (sinema/fotoğraf); geçiş efekti uygulamak, soldurmak",

    # "sığ suda dolaşmak" → yanlış
    ("staken", None): "sırıkla tekne sürmek, kayıkçı sırığıyla itmek",

    # Nokta sonlu modal fiil
    ("müssen", None): "-malı/-meli; bir şeyi yapmak zorunda olmak",

    # ── SIFAT HATALAR ────────────────────────────────────────────────────────

    # Açıklama formatı
    ("wirtschaftlich", "Ekonomiyi"): "ekonomik, iktisadi; tutumlu, verimli",

    # "Almanlara ait, has, özgü" → ana anlam eksik
    ("deutsch", "Almanlara"): "Alman; Almanca, Almanlara özgü",

    # ── İSİM HATALAR ─────────────────────────────────────────────────────────

    # Bett — jeolojik/biyolojik açıklama yerine kısa çeviri
    ("Bett", "su kütleleri"): "yatak (nehir, okyanus yatağı); tarh (bahçe)",

    # Schütze — teknik açıklama
    ("Schütze", "Regülasyon"): "bent kapağı, savak kapağı; kilit kapağı",

    # Schütze — soyadı girişini temizle
    ("Schütze", "Bir soyadı"): "Schütze (Alman soyadı)",

    # Ara — biyolojik açıklama
    ("Ara", "Nesli tükenmemiş"): "makaw papağanı (Ara cinsi, Amerika'ya özgü)",

    # Forschungsförderung — nokta sonlu
    ("Forschungsförderung", None): "araştırma desteği, araştırma finansmanı, araştırma teşviki",

    # ── EDAT HATALAR (açıklama → kısa çeviri) ───────────────────────────────

    # auf
    ("auf", "Konuşulan dili belirtir"): "bir dilde (konuşmayı belirtir; auf Deutsch = Almanca olarak)",
    ("auf", "Bazı fiillerin nesnesini işaretler"): "bazı fiillerle birlikte kullanılan edat (-a/-e, -da/-de)",

    # in
    ("in", "Diller için bulunma"): "bir dilde, bir alanda (in Deutsch = Almancada)",
    ("in", "Bazı fiillerin nesnesini işaretler"): "bazı fiillerle birlikte kullanılan edat (-de/-da, -e/-a)",

    # zu
    ("zu", "Amaç veya hedef belirtir"): "için, -e/-a (amaç veya hedef belirtir)",

    # durch
    ("durch", "boyunca, Bir hareketin"): "boyunca, -dan/-den geçerek; bir hareketin gerçekleştiği alanı gösterir",
}


# ─────────────────────────────────────────────────────────────────────────────
# Genel temizlik kuralları (regex bazlı, tüm kayıtlara uygulanır)
# ─────────────────────────────────────────────────────────────────────────────

def genel_temizle(tr: str, tur: str) -> str | None:
    """Değişiklik varsa yeni değeri döndür, yoksa None."""
    original = tr

    # 1. Sondaki nokta (fiil/isim/sıfat için)
    if tur in ("fiil", "isim", "sıfat", "zarf") and tr.endswith("."):
        tr = tr.rstrip(".")

    # 2. Almanca gramer parantezleri
    tr = re.sub(r"\s*\(mit\s+(?:Dativ|Akkusativ)\)", "", tr)
    tr = re.sub(r"\s*\((?:haben|sein)\)\s*", " ", tr)
    tr = re.sub(r"\s*\[[\s\+]*(Dativ|Akkusativ|Genitiv|Nominativ|yönelme\s+çekimi|belirtme\s+çekimi)[^\]]*\]", "", tr)

    # 3. Çift boşluk
    tr = re.sub(r"  +", " ", tr).strip()

    return tr if tr != original else None


# ─────────────────────────────────────────────────────────────────────────────
# ANA DÖNGÜ
# ─────────────────────────────────────────────────────────────────────────────

def main():
    backup = JSONL.with_suffix(".jsonl.bak_review2")
    shutil.copy2(JSONL, backup)
    print(f"Yedek: {backup}\n")

    entries = []
    with open(JSONL, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    log: list[dict] = []
    fixed_total = 0

    for e in entries:
        alm = e["almanca"]
        tr  = e.get("turkce", "").strip()
        tur = e.get("tur", "")

        # 1. Hedefli düzeltme — tam eşleşme veya prefix eşleşme
        fixed = False
        for (key_alm, key_tr_prefix), new_tr in TARGETED_FIXES.items():
            if alm != key_alm:
                continue
            if key_tr_prefix is None:
                # Sorunlu girişi bul: büyük harf başlangıç VEYA nokta sonu VEYA çok kısa
                if (tr and tr[0].isupper() and tur not in ("isim",)) or tr.endswith(".") or len(tr) < 6:
                    e["turkce"] = new_tr
                    log.append({"tip": "HEDEFLI", "almanca": alm, "eski": tr, "yeni": new_tr})
                    fixed_total += 1
                    fixed = True
                    break
            else:
                if tr.startswith(key_tr_prefix) or key_tr_prefix in tr:
                    e["turkce"] = new_tr
                    log.append({"tip": "HEDEFLI", "almanca": alm, "eski": tr, "yeni": new_tr})
                    fixed_total += 1
                    fixed = True
                    break

        if fixed:
            continue

        # 2. Genel temizlik
        temiz = genel_temizle(tr, tur)
        if temiz is not None:
            log.append({"tip": "GENEL_TEMIZLIK", "almanca": alm, "eski": tr, "yeni": temiz})
            e["turkce"] = temiz
            fixed_total += 1

    # ── Kaydet ────────────────────────────────────────────────────────────────
    with open(JSONL, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # ── Rapor ─────────────────────────────────────────────────────────────────
    from collections import Counter
    tip_counter = Counter(l["tip"] for l in log)

    print("=" * 70)
    print(f"TOPLAM DÜZELTİLEN: {fixed_total}")
    print("=" * 70)
    for tip, cnt in tip_counter.most_common():
        print(f"  {tip:25s}: {cnt}")

    print(f"\n{'='*70}")
    print("HEDEFLI DÜZELTİLENLER")
    print("=" * 70)
    for l in log:
        if l["tip"] == "HEDEFLI":
            print(f"  [{l['almanca']:25}]")
            print(f"    ESK: {l['eski'][:75]}")
            print(f"    YEN: {l['yeni'][:75]}")
            print()

    print(f"{'='*70}")
    print("GENEL TEMİZLİK ÖRNEKLERİ (ilk 15)")
    print("=" * 70)
    count = 0
    for l in log:
        if l["tip"] == "GENEL_TEMIZLIK":
            print(f"  [{l['almanca']:25}] '{l['eski'][:50]}' -> '{l['yeni'][:50]}'")
            count += 1
            if count >= 15:
                break


if __name__ == "__main__":
    main()
