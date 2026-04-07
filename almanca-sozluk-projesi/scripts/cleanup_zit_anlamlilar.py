#!/usr/bin/env python3
"""
cleanup_zit_anlamlilar.py
=========================
OdeNet kaynakli yanlis zit_anlamlilar degerlerini temizler.
Acikca yanlis olanlari siler, mantikli olanlari korur.
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH = Path(__file__).resolve().parents[1] / "output" / "dictionary.json"

# ── Asla antonym olamayacak spesifik degerler ─────────────────────────────────
# (OdeNet'te yanlis etiketlenmis synset'lerden gelen gürültü)
BAD_ANTONYM_VALUES = {
    # Havaalani terimleri (Eingang/Zugang -> Ausgang dogru ama Gate/Flugsteig degil)
    "Gate", "Flugsteig",
    # "Yok etme" fiilleri (arbeiten/schaffen/herstellen icin yanlis antonym)
    "in Trümmer legen", "zerschlagen", "zu Kleinholz verarbeiten",
    # Zamansal eslesimsizlik (Beständigkeit/Langlebigkeit icin yanlis)
    "Gleichzeitigkeit", "Nebenläufigkeit", "Nichtsequentialität",
    # NGO <-> Regierung zayif antonym, diger kelimeler icin tamamen yanlis
    # (sadece Regierung/Exekutive icin birakilacak, diger tum kelimelerden silinecek)
    # --> Asagida bağlama gore ele alinıyor
    # Slang / muphemizm karisikligi
    "wie eine Nutte",
    # Anlamsiz eslesme
    "dolce far niente",  # sadece italyanca deyim, Almanca antonym degil
    "plain vanilla",     # ingilizce slang
    # Yanlis eslesmis degerler (grün != erfahren context hatasi kaldirildi,
    # cunku grun=toy -> erfahren=deneyimli aslında doğru antonym)
}

# ── Belirli kelime bazli kötü eslesmeler ──────────────────────────────────────
# (word_lower -> silinecek antonym degerleri)
WORD_SPECIFIC_BAD = {
    # Eingang/Eintritt/Zugang -> Ausgang dogru AMA Gate/Flugsteig yanlis
    # (yukardaki BAD_ANTONYM_VALUES zaten Gate/Flugsteig'i kaldiriyor)

    # "arbeiten" icin "in Trümmer legen" yanlis (yukarda BAD_ANTONYM_VALUES'da)

    # Bestandigkeit/Langlebigkeit icin "Gleichzeitigkeit" yanlis (yukarda)

    # Regierung/Exekutive/Verwaltung/Obrigkeit -> NGO zayif antonym
    # Sadece bu kelimeler icin NGO'yu kaldiriyoruz:
    "verwaltung": {"Nichtregierungsorganisation", "NGO", "nichtstaatliche Organisation"},
    "obrigkeit":  {"Nichtregierungsorganisation", "NGO", "nichtstaatliche Organisation"},

    # "Phase" elektrik baglami: Nichtleiter makul (Leiter de var zaten)
    # Kaldir: "Isoliermaterial" (bu malzeme, antonym degil)
    "phase": {"Isoliermaterial"},

    # Sauber -> schrecklich yanlis (sauber = temiz, schrecklich degil)
    "sauber": {"schrecklich", "grausam", "fürchterlich"},

    # einzigartig -> schrecklich yanlis (einzigartig = essizkendine özgü, degil karşıtı)
    "einzigartig": {"schrecklich", "grausam", "fürchterlich"},

    # Apart -> gebürtig yanlis (apart = çekici, gebürtig = doğuştan)
    "apart": {"gebürtig", "ansässig", "ortsansässig"},

    # Bestandigkeit -> Gleichzeitigkeit yanlis (yukarda BAD_ANTONYM_VALUES'da)

    # Langlebigkeit -> Gleichzeitigkeit yanlis
    "langlebigkeit": {"Gleichzeitigkeit", "Nebenläufigkeit", "Nichtsequentialität"},

    # Seher -> Nichtswisser yanlis (seher = kahin, nichtswisser = cahil degil)
    "seher": {"Nichtswisser", "Nichtswissender", "Unwissender"},

    # Beweglichkeit -> Müßiggang yanlis (hareketlilik != tembellik)
    "beweglichkeit": {"Müßiggang", "dolce far niente", "Nichtstun"},

    # Meister -> Nichtswisser yanlis (usta != cahil)
    "meister": {"Nichtswisser", "Nichtswissender", "Unwissender"},

    # Akzeptanz/Aufnahme/Annahme -> Vogel-Strauß-Politik yanlis
    "akzeptanz":  {"Vogel-Strauß-Politik", "Ignorieren"},
    "aufnahme":   {"Vogel-Strauß-Politik", "Ignorieren"},
    "annahme":    {"Vogel-Strauß-Politik", "Ignorieren"},

    # Regelmäßig -> undeutlich yanlis (düzenli != belirsiz)
    "regelmäßig": {"undeutlich", "unklar", "schemenhaft"},

    # Heftig -> undeutlich yanlis (şiddetli != belirsiz)
    "heftig": {"undeutlich", "unklar", "schemenhaft"},

    # Jung -> erfahren YANLIS (genç != deneyimli; grün/unbedarft için dogru ama jung için degil)
    "jung": {"erfahren", "bewandert", "professionell"},

    # Weltweit/Global/International -> landesweit yanlis (dünya çapı != ülke çapı)
    "weltweit":      {"landauf, landab", "landesweit", "überall im Land"},
    "global":        {"landauf, landab", "landesweit", "überall im Land"},
    "international": {"landauf, landab", "landesweit", "überall im Land"},

    # Locker -> durcheinander yanlis (rahat != karışık)
    "locker": {"durcheinander", "ruhelos", "zappelig"},

    # Dringend -> forsch/souverän yanlis (acil != özgüvenli)
    "dringend": {"forsch", "souverän", "selbstbewusst"},

    # Zuverlässigkeit -> Fragwürdigkeit (güvenilirlik != sorgulanabilirlik, Zweifelhaftigkeit birakilabilir)
    "zuverlässigkeit": {"Fragwürdigkeit"},

    # Scharf -> unschön yanlis (keskin != çirkin; sadece "çekici" anlamı için olabilir ama silik)
    "scharf": {"unschön", "reizlos", "ungestalt"},

    # Beständigkeit -> yanlışlar (yukarda BAD_ANTONYM_VALUES'da)
    "beständigkeit": {"Gleichzeitigkeit", "Nebenläufigkeit", "Nichtsequentialität"},
}

# ── Tamamen silinecek kelimeler (tüm zit_anlamlilar yanlis) ───────────────────
WORDS_TO_CLEAR_ALL = {
    # Abfahren/Abfliegen -> erreichen, sich nähern (bunlar antonym degil, karşıt eylem)
    "abfahren", "abfliegen",
    # Schal -> durchdacht (sıkıcı != düşünceli/karmaşık — yanlis synset)
    "schal",
    # Normal/schlicht/einfach/gewöhnlich -> originell (bunlar zıt ama
    # "eigenartig, eigen" gürültü; sadece originell kalabilir ama hepsi silinsin)
    # NOT: bu kelimeler için antonym aslında "außergewöhnlich/besonders" olmalı
    # OdeNet'in önerisi yanlış yönde değil ama kalitesiz — temizle
    # "normal", "schlicht",  # bunları koru çünkü originell makul
    # Bestandigkeit
    "beständigkeit",
    "langlebigkeit",
}


def clean_antonyms(word: str, antonyms: list) -> list:
    word_lower = word.lower().strip()

    # Tamamen silinecek kelimeler
    if word_lower in WORDS_TO_CLEAR_ALL:
        return []

    cleaned = []
    word_specific = WORD_SPECIFIC_BAD.get(word_lower, set())

    for ant in antonyms:
        ant_str = str(ant).strip()
        # Global kötü değerler
        if ant_str in BAD_ANTONYM_VALUES:
            continue
        # Kelime bazlı kötü değerler
        if ant_str in word_specific:
            continue
        cleaned.append(ant_str)

    return cleaned


def main():
    print("Sozluk yukleniyor...", flush=True)
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))

    total_with_zit = 0
    cleared_all = 0
    reduced = 0
    unchanged = 0

    for rec in data:
        zit = rec.get("zit_anlamlilar")
        if not zit or not isinstance(zit, list):
            continue
        total_with_zit += 1

        word = rec.get("almanca", "")
        cleaned = clean_antonyms(word, zit)

        if not cleaned:
            del rec["zit_anlamlilar"]
            cleared_all += 1
            print(f"  SILINDI [{word}] <- {zit}", flush=True)
        elif len(cleaned) < len(zit):
            removed = [v for v in zit if v not in cleaned]
            rec["zit_anlamlilar"] = cleaned
            reduced += 1
            print(f"  KISALTILDI [{word}]: silinen={removed}", flush=True)
        else:
            unchanged += 1

    print(f"\n{'='*55}", flush=True)
    print(f"Toplam zit_anlamlilar olan kayit : {total_with_zit}", flush=True)
    print(f"Tamamen silindi                  : {cleared_all}", flush=True)
    print(f"Kisaltildi (bazi degerler silindi): {reduced}", flush=True)
    print(f"Degismedi                        : {unchanged}", flush=True)
    print(f"{'='*55}", flush=True)

    DICT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Kaydedildi.", flush=True)


if __name__ == "__main__":
    main()
