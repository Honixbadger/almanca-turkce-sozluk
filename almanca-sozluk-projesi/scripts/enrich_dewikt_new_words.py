#!/usr/bin/env python3
"""dewiktionary.gz'den Türkçe çevirisi olan yeni Almanca kelimeleri sözlüğe ekler.

Çıkarılan bilgiler:
- almanca, artikel, turkce, tur
- tanim_almanca (gloss)
- ornek_almanca / ornekler
- telaffuz (IPA)
- genitiv_endung, cogul (isimler için)
- cekimler, prateritum, partizip2, perfekt_yardimci (fiiller için)
- kaynak, referans_linkler
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEWIKT_PATH = PROJECT_ROOT / "data" / "raw" / "downloads" / "dewiktionary.gz"

POS_MAP = {
    "noun": "isim",
    "verb": "fiil",
    "adj": "sıfat",
    "adv": "zarf",
    "phrase": "ifade",
    "intj": "ünlem",
    "prep": "edat",
    "conj": "bağlaç",
    "pron": "zamir",
    "name": "isim",
    "abbrev": "kısaltma",
    "num": "sayı",
    "particle": "parçacık",
}

# Türkçe çeviri kalite filtresi: bunlar varsa atla
BAD_TR_PATTERNS = re.compile(
    r"(http|www\.|\.de|\.com|\d{4}|[<>{}\[\]]|^\s*$)", re.I
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().casefold()


def is_valid_turkish(word: str) -> bool:
    if not word or len(word) > 60:
        return False
    if BAD_TR_PATTERNS.search(word):
        return False
    return True


def extract_artikel(forms: list) -> str:
    for form in forms:
        tags = form.get("tags", [])
        if "nominative" in tags and "singular" in tags:
            art = form.get("article", "")
            if art in ("der", "die", "das"):
                return art
    return ""


def extract_genitiv(forms: list) -> str:
    for form in forms:
        tags = form.get("tags", [])
        if "genitive" in tags and "singular" in tags:
            stem = form.get("form", "")
            return stem
    return ""


def extract_plural(forms: list) -> str:
    for form in forms:
        tags = form.get("tags", [])
        if "nominative" in tags and "plural" in tags:
            return form.get("form", "")
    return ""


def extract_ipa(sounds: list) -> str:
    for s in sounds:
        ipa = s.get("ipa", "")
        if ipa:
            # Köşeli parantezleri kaldır
            return ipa.strip("[]/ ")
    return ""


def extract_cekimler(forms: list) -> dict:
    """dewiktionary forms listesinden cekimler dict'i oluşturur."""
    praesens = {}
    prateritum = ""
    partizip2 = ""
    perfekt_aux = ""
    imperativ_parts = []

    PRONOUN_MAP = {
        "ich": "ich",
        "du": "du",
        "er": "er/sie/es",
        "sie": "er/sie/es",
        "es": "er/sie/es",
        "wir": "wir",
        "ihr": "ihr",
        "Sie": "sie/Sie",
    }

    for form in forms:
        tags = form.get("tags", [])
        f = form.get("form", "")
        pronouns = form.get("pronouns", [])

        # Präsens
        if "present" in tags and pronouns and "subjunctive" not in " ".join(tags):
            for pron in pronouns:
                slot = PRONOUN_MAP.get(pron)
                if slot and slot not in praesens:
                    praesens[slot] = f

        # Präteritum (ich-form, past, indicative)
        if "past" in tags and "ich" in pronouns and "subjunctive" not in " ".join(tags):
            if not prateritum:
                prateritum = f

        # Partizip II
        if "participle-2" in tags or ("participle" in tags and "perfect" in tags):
            if not partizip2:
                partizip2 = f

        # Auxiliary
        if "auxiliary" in tags and "perfect" in tags:
            if f in ("haben", "sein") and not perfekt_aux:
                perfekt_aux = f

        # Imperativ
        if "imperative" in tags:
            if "singular" in tags:
                imperativ_parts.insert(0, f.rstrip("!"))
            elif "plural" in tags:
                imperativ_parts.append(f.rstrip("!"))

    result = {}
    if praesens:
        result["präsens"] = praesens
    if prateritum:
        result["präteritum"] = prateritum
    if partizip2 and perfekt_aux:
        result["perfekt"] = f"{perfekt_aux} {partizip2}"
    elif partizip2:
        result["perfekt"] = partizip2
    if imperativ_parts:
        result["imperativ"] = ", ".join(imperativ_parts)

    return result


def build_entry(word: str, dw: dict, tr_word: str) -> dict:
    pos_raw = dw.get("pos", "")
    tur = POS_MAP.get(pos_raw, "belirsiz")
    forms = dw.get("forms", [])
    sounds = dw.get("sounds", [])
    senses = dw.get("senses", [])

    artikel = extract_artikel(forms) if tur == "isim" else ""
    ipa = extract_ipa(sounds)

    # Tanım (ilk gloss)
    tanim = ""
    if senses:
        glosses = senses[0].get("glosses", [])
        tanim = glosses[0] if glosses else ""

    # Örnek cümleler
    ornekler = []
    for sense in senses[:3]:
        for ex in sense.get("examples", [])[:2]:
            txt = ex.get("text", "").strip()
            if txt and len(txt) < 300:
                ornekler.append({
                    "almanca": txt,
                    "turkce": "",
                    "kaynak": "deWiktionary",
                    "not": ex.get("ref", ""),
                    "etiket_turkce": "",
                })

    entry: dict = {
        "almanca": word,
        "artikel": artikel,
        "turkce": tr_word,
        "tur": tur,
        "kategoriler": [],
        "seviye": "",
        "tanim_almanca": tanim,
        "aciklama_turkce": "",
        "ornekler": ornekler,
        "ornek_almanca": ornekler[0]["almanca"] if ornekler else "",
        "ornek_turkce": "",
        "kaynak": "Wiktionary DE (CC BY-SA 3.0)",
        "kaynak_url": f"https://kaikki.org/dewiktionary/rawdata.html",
        "ceviri_durumu": "kaynak-izli",
        "ceviri_kaynaklari": [],
        "referans_linkler": {
            "duden": f"https://www.duden.de/suchen/dudenonline/{word}",
            "dwds": f"https://www.dwds.de/wb/{word}",
            "wiktionary_de": f"https://de.wiktionary.org/wiki/{word}",
        },
        "not": "",
        "kelime_ailesi": [],
        "ilgili_kayitlar": [],
        "zipf_skoru": 0.0,
        "genitiv_endung": "",
        "telaffuz": ipa,
        "esanlamlilar": [],
        "sinonim": [],
        "anlamlar": [],
        "fiil_kaliplari": [],
    }

    if ipa:
        entry["telaffuz"] = ipa

    if tur == "isim":
        entry["genitiv_endung"] = extract_genitiv(forms)
        plural = extract_plural(forms)
        if plural:
            entry["cogul"] = plural

    if tur == "fiil":
        cekimler = extract_cekimler(forms)
        if cekimler:
            entry["cekimler"] = cekimler
            entry["prateritum"] = cekimler.get("präteritum", "")
            entry["partizip2"] = ""
            # Partizip2'yi forms'dan çıkar
            for form in forms:
                tags = form.get("tags", [])
                if "participle-2" in tags or ("participle" in tags and "perfect" in tags):
                    entry["partizip2"] = form.get("form", "")
                    break
            # Perfekt yardımcısı
            for form in forms:
                tags = form.get("tags", [])
                if "auxiliary" in tags and form.get("form") in ("haben", "sein"):
                    entry["perfekt_yardimci"] = form.get("form", "")
                    break

    return entry


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dict", default=str(DEFAULT_DICT_PATH))
    parser.add_argument("--dump", default=str(DEWIKT_PATH))
    parser.add_argument("--dry-run", action="store_true", help="Sözlüğü değiştirmeden rapor üret")
    parser.add_argument("--limit", type=int, default=0, help="Eklenecek maks kelime sayısı (0=sınırsız)")
    args = parser.parse_args(argv)

    dict_path = Path(args.dict)
    dump_path = Path(args.dump)

    print(f"Sözlük yükleniyor: {dict_path}")
    with open(dict_path, encoding="utf-8") as f:
        dictionary: list[dict] = json.load(f)

    existing_words = {e.get("almanca", "").lower() for e in dictionary}
    print(f"Mevcut kayıt: {len(dictionary)}")

    print(f"Dump taranıyor: {dump_path}")
    new_entries: list[dict] = []
    skipped_exists = 0
    skipped_no_tr = 0
    skipped_bad_tr = 0
    skipped_filter = 0
    de_total = 0

    with gzip.open(dump_path, "rt", encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("lang_code") != "de":
                continue
            de_total += 1

            word = entry.get("word", "").strip()
            if not word:
                continue

            # Temel filtreler
            if word.lower() in existing_words:
                skipped_exists += 1
                continue
            if len(word) < 3 or len(word) > 45:
                skipped_filter += 1
                continue
            # Boşluklu ifadeler için en fazla 3 token
            if len(word.split()) > 3:
                skipped_filter += 1
                continue
            # Sadece rakam veya özel karakter içeren kelimeleri atla
            if re.match(r"^[\d\W]+$", word):
                skipped_filter += 1
                continue

            # Türkçe çeviri ara
            tr_translations = [
                t for t in entry.get("translations", [])
                if t.get("lang_code") == "tr"
            ]
            if not tr_translations:
                skipped_no_tr += 1
                continue

            # En iyi Türkçe çeviriyi seç (kısa ve temiz)
            tr_word = ""
            for t in tr_translations:
                candidate = t.get("word", "").strip()
                if is_valid_turkish(candidate):
                    tr_word = candidate
                    break
            if not tr_word:
                skipped_bad_tr += 1
                continue

            new_entries.append(build_entry(word, entry, tr_word))
            existing_words.add(word.lower())

            if args.limit and len(new_entries) >= args.limit:
                break

    print(f"\nTaranan Almanca kelime : {de_total:,}")
    print(f"Zaten mevcut           : {skipped_exists:,}")
    print(f"Türkçe çeviri yok      : {skipped_no_tr:,}")
    print(f"Kötü çeviri            : {skipped_bad_tr:,}")
    print(f"Format filtresi        : {skipped_filter:,}")
    print(f"Eklenecek yeni kelime  : {len(new_entries):,}")

    # Tür dağılımı
    pos_dist: dict[str, int] = {}
    for e in new_entries:
        pos_dist[e["tur"]] = pos_dist.get(e["tur"], 0) + 1
    print("\nTür dağılımı:")
    for tur, cnt in sorted(pos_dist.items(), key=lambda x: -x[1]):
        print(f"  {tur:<12} {cnt:>5}")

    if args.dry_run:
        print("\n[dry-run] Sözlük değiştirilmedi.")
        return

    # Yedek al
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = dict_path.with_name(f"dictionary.backup.dewikt-new-words-{ts}.json")
    shutil.copy2(dict_path, backup)
    print(f"\nYedek: {backup.name}")

    # Sözlüğe ekle
    dictionary.extend(new_entries)

    with open(dict_path, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=2)

    print(f"Sözlük güncellendi: {len(dictionary):,} kayıt ({len(dictionary) - (len(dictionary) - len(new_entries)):+,})")


if __name__ == "__main__":
    main()
