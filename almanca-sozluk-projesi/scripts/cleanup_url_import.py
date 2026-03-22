#!/usr/bin/env python3
"""
cleanup_url_import.py
=====================
URL-import ile eklenen kayıtları kalite filtrelerinden geçirir,
kötü olanları kaldırır.
"""
import json
import sys
import unicodedata
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_SCRIPTS_DIR = Path(__file__).resolve().parent
DICT_PATHS = [
    _SCRIPTS_DIR.parent / "output" / "dictionary.json",
]

# URL-import kaydını bu marker'la tespit ediyoruz
URL_IMPORT_MARKER = "Wikipedia DE"

# Kaldırılacak kelime listeleri
MONTHS_DE = {
    "januar", "februar", "märz", "april", "mai", "juni", "juli",
    "august", "september", "oktober", "november", "dezember",
}
DAYS_DE = {
    "montag", "dienstag", "mittwoch", "donnerstag",
    "freitag", "samstag", "sonntag",
}

# Almancada sıkça geçen ama sözlükte yeri olmayan işlev kelimeleri
FUNCTION_WORDS = {
    # Preposizioni/Konjunktionen die nicht rausgefiltert wurden
    "seit", "statt", "samt", "wobei", "wobei", "sowie", "gemäß",
    "laut", "zufolge", "mithilfe", "anstatt", "anstelle",
    "sofern", "solange", "sobald", "nachdem", "bevor",
    "wohingegen", "obwohl", "während", "falls", "gegenüber",
    "innerhalb", "außerhalb", "oberhalb", "unterhalb",
    "bezüglich", "hinsichtlich", "entsprechend", "aufgrund",
    "hierbei", "hiervon", "hierfür", "hierdurch", "hieraus",
    "hierzu", "hierüber", "hierunter", "hieran", "hierin",
    "daraus", "dabei", "daran", "darin", "darauf", "darüber",
    "darunter", "dafür", "dagegen", "dadurch", "dahinter",
    "daher", "damals", "dazu", "deswegen", "trotzdem", "dennoch",
    "jedoch", "allerdings", "außerdem", "zudem", "ebenfalls",
    "bereits", "schon", "immer", "noch", "dann", "zwar", "zuerst",
    "zuletzt", "endlich", "plötzlich", "sofort", "bisher", "seitdem",
    "meistens", "manchmal", "selten", "häufig", "weitgehend",
    "insbesondere", "insgesamt", "grundsätzlich", "demnach",
    "demzufolge", "demgegenüber", "diesbezüglich", "inwieweit",
    "inwiefern", "infolge", "infolgedessen", "somit", "folglich",
    "hingegen", "vielmehr", "andererseits", "einerseits",
    "nämlich", "schließlich", "letztlich", "letztendlich",
    "insofern", "sofern", "soweit", "sowohl", "weder", "entweder",
    "zumindest", "mindestens", "höchstens", "wenigstens",
    "tatsächlich", "eigentlich", "offenbar", "offensichtlich",
    "anscheinend", "möglicherweise", "wahrscheinlich", "vermutlich",
    "jedenfalls", "ohnehin", "sowieso", "gleichwohl", "indessen",
    "indes", "derweil", "unterdessen", "währenddessen", "zwischenzeitlich",
    "seither", "fortan", "hinfort", "nunmehr", "demnächst",
    # Yaygın kısaltmalar
    "usw", "bzw", "evtl", "ggf", "inkl", "exkl", "sog",
    # Çok yaygın Wikipedia metinlerinde geçen ama sözlükte yeri olmayan
    "wurde", "wurden", "haben", "hatte", "hatten", "worden", "worden",
    "können", "konnte", "konnten", "müssen", "musste", "mussten",
    "werden", "wird", "wurde", "würde", "sollen", "sollte",
    "wollen", "wollte", "dürfen", "durfte", "mögen", "mochte",
}

# Kesinlikle özel isim/yer adı olan kelimeler (tespit edilenler)
PROPER_NOUNS = {
    "berlin", "münchen", "hamburg", "köln", "frankfurt", "stuttgart",
    "düsseldorf", "dortmund", "essen", "leipzig", "bremen", "dresden",
    "hannover", "nürnberg", "duisburg", "bochum", "wuppertal",
    "deutschland", "österreich", "schweiz", "europa", "brüssel",
    "paris", "london", "washington", "peking", "tokio", "moskau",
    "bundestag", "bundesrat", "bundesverfassungsgericht",
    "grundgesetz", "bundeskanzler", "bundesminister",
    # Yaygın Alman özel isimleri (Wikipedia'da çok geçer)
    "friedrich", "schmidt", "müller", "wagner", "schulz", "klein",
    "braun", "hoffmann", "schäfer", "becker", "zimmermann",
    "krause", "lange", "köhler", "maier", "mayer", "lehmann",
    "neumann", "schwarz", "walter", "richter", "wolf", "schroder",
}

# Türkçe çeviri olarak kabul edilmeyecek içerikler
BAD_TURKISH_PATTERNS = [
    # Almanca kelimenin kendisi gibi görünen çeviriler (loanword değilse)
]


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def casefold_de(s: str) -> str:
    return nfc(s).strip().casefold()


def is_url_import(rec: dict) -> bool:
    kaynak = rec.get("kaynak", "") or ""
    return URL_IMPORT_MARKER in kaynak


def should_remove(rec: dict, existing_base_keys: set[str]) -> tuple[bool, str]:
    almanca = (rec.get("almanca", "") or "").strip()
    turkce = (rec.get("turkce", "") or "").strip()
    cf = casefold_de(almanca)

    # 1. Ay adı
    if cf in MONTHS_DE:
        return True, f"ay adi: {almanca}"

    # 2. Gün adı
    if cf in DAYS_DE:
        return True, f"gun adi: {almanca}"

    # 3. İşlev kelimesi
    if cf in FUNCTION_WORDS:
        return True, f"islev kelimesi: {almanca}"

    # 4. Bilinen özel isim
    if cf in PROPER_NOUNS:
        return True, f"ozel isim: {almanca}"

    # 5. Çevirisi boş
    if not turkce:
        return True, f"cevirisi yok: {almanca}"

    # 6. Çeviri == Almanca (sadece loanword değilse — 5 harften uzun tamamen aynı)
    if casefold_de(turkce) == cf and len(cf) > 5:
        return True, f"ceviri=almanca: {almanca}"

    # 7. Türkçe çeviri çok kısa (1-2 karakter)
    if len(turkce.strip()) < 3:
        return True, f"ceviri cok kisa: {almanca} -> {turkce}"

    # 8. Almanca çok kısa (3 karakter) — zaten 4 min var ama
    if len(almanca) < 4:
        return True, f"almanca cok kisa: {almanca}"

    # 9. Genitive/plural inflected formu: almanca büyük harfle bitiyorsa ve base var
    # Örnek: "Bundestages" → base "Bundestag" zaten sözlükte
    for suffix in ("es", "en", "er", "em"):
        if almanca.endswith(suffix) and len(almanca) > len(suffix) + 3:
            base = almanca[: -len(suffix)]
            if casefold_de(base) in existing_base_keys:
                return True, f"cekim formu: {almanca} (base={base})"

    # 10. "s" ile biten genitiv formu (Kanzlers, Tages)
    if almanca.endswith("s") and not almanca.endswith("ss") and len(almanca) > 5:
        base = almanca[:-1]
        if casefold_de(base) in existing_base_keys:
            return True, f"genitif-s: {almanca} (base={base})"

    return False, ""


def main() -> None:
    print("cleanup_url_import.py - URL-import kayit temizligi")
    print("=" * 55)

    # Yükle
    src = DICT_PATHS[0]
    with open(src, encoding="utf-8") as f:
        records: list[dict] = json.load(f)
    print(f"Toplam kayit: {len(records)}")

    # Mevcut tüm anahtarlar (URL-import olmayanlar dahil)
    url_records = [r for r in records if is_url_import(r)]
    base_records = [r for r in records if not is_url_import(r)]
    print(f"  URL-import: {len(url_records)}")
    print(f"  Onceden var olan: {len(base_records)}")

    # Tüm kelimelerin casefold kümesi (base records)
    existing_base_keys: set[str] = set()
    for r in records:  # tüm kayıtlar, URL-import dahil (kendi kendini test etmiyoruz)
        a = (r.get("almanca", "") or "").strip()
        existing_base_keys.add(casefold_de(a))

    removed = []
    kept = list(base_records)

    for rec in url_records:
        rm, reason = should_remove(rec, existing_base_keys)
        if rm:
            removed.append((rec.get("almanca", ""), reason))
        else:
            kept.append(rec)

    print(f"\nKaldirilacak: {len(removed)}")
    print(f"Tutulacak: {len(kept)}")

    for almanca, reason in sorted(removed):
        print(f"  - {almanca}: {reason}")

    # Kaydet
    for path in DICT_PATHS:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(kept, f, ensure_ascii=False, indent=2)
        print(f"\nKaydedildi: {path}")

    print(f"\nSonuc: {len(records)} -> {len(kept)} kayit ({len(removed)} kaldirildi)")


if __name__ == "__main__":
    main()
