#!/usr/bin/env python
"""Build normalized German-Turkish dictionary outputs from public sources."""

from __future__ import annotations

import csv
import gzip
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from build_definition_index import main as build_definition_index
except ModuleNotFoundError:
    from scripts.build_definition_index import main as build_definition_index


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
OUTPUT_DIR = PROJECT_ROOT / "output"
MANUAL_DIR = DATA_DIR / "manual"
RECORD_ENRICHMENTS_PATH = MANUAL_DIR / "record_enrichments.json"
TRANSLATION_REVIEW_PATH = MANUAL_DIR / "translation_reviews.json"

TRWIKTIONARY_PATH = RAW_DIR / "downloads" / "trwiktionary.gz"
DEWIKTIONARY_PATH = RAW_DIR / "downloads" / "dewiktionary.gz"
WIKDICT_PATH = RAW_DIR / "downloads" / "de-tr.sqlite3"
AUTOLEXIKON_TERMS_PATH = INTERIM_DIR / "autolexikon_terms.json"
MEIN_AUTOLEXIKON_TERMS_PATH = INTERIM_DIR / "mein_autolexikon_terms.json"

TARGET_RECORD_COUNT = 4200

POS_MAP = {
    "noun": "isim",
    "verb": "fiil",
    "adj": "sıfat",
    "adv": "zarf",
    "abbrev": "kısaltma",
    "phrase": "ifade",
    "num": "sayı",
    "pron": "zamir",
    "conj": "bağlaç",
    "particle": "edat",
    "intj": "ünlem",
}

GENERAL_POS_PRIORITY = {
    "isim": 0,
    "fiil": 1,
    "sıfat": 2,
    "kısaltma": 3,
    "zarf": 4,
    "ifade": 5,
    "sayı": 6,
    "zamir": 7,
    "bağlaç": 8,
    "edat": 9,
    "ünlem": 10,
}

POS_MAP = {
    "noun": "isim",
    "verb": "fiil",
    "adj": "sıfat",
    "adv": "zarf",
    "abbrev": "kısaltma",
    "phrase": "ifade",
    "num": "sayı",
    "pron": "zamir",
    "conj": "bağlaç",
    "particle": "edat",
    "intj": "ünlem",
}

GENERAL_POS_PRIORITY = {
    "isim": 0,
    "fiil": 1,
    "sıfat": 2,
    "kısaltma": 3,
    "zarf": 4,
    "ifade": 5,
    "sayı": 6,
    "zamir": 7,
    "bağlaç": 8,
    "edat": 9,
    "ünlem": 10,
}

AUTO_HINTS = (
    "abgas",
    "achse",
    "airbag",
    "antrieb",
    "auto",
    "batter",
    "benzin",
    "brems",
    "diesel",
    "differential",
    "fahr",
    "fahrzeug",
    "filter",
    "garage",
    "getrieb",
    "hybrid",
    "karos",
    "katalys",
    "klima",
    "kolben",
    "kraftstoff",
    "kuppl",
    "kurbel",
    "lenk",
    "licht",
    "luftfilter",
    "motor",
    "reifen",
    "scheibenbrem",
    "scheinwer",
    "stoßdämp",
    "turbo",
    "ventil",
    "vergaser",
    "zünd",
    "fahrerassist",
    "kfz",
)

DOMAIN_TRANSLATION_PREFERENCES = {
    "batterie": {"aku"},
    "getriebe": {"sanziman"},
    "scheinwerfer": {"far"},
    "turbolader": {"turbosarj"},
    "zuendspule": {"atesleme bobini"},
}

ABBREVIATION_HINTS = {
    "esp": {
        "de": "Elektronisches Stabilitätsprogramm",
        "tr": "elektronik stabilite programı",
        "desc": "Aracın savrulmasını azaltmak için fren ve motor torkuna müdahale eden denge kontrol sistemi.",
    },
    "elektronisches stabilitatsprogramm": {
        "de": "Elektronisches Stabilitätsprogramm",
        "tr": "elektronik stabilite programı",
        "desc": "Aracın savrulmasını azaltmak için fren ve motor torkuna müdahale eden denge kontrol sistemi.",
    },
    "abs": {
        "de": "Antiblockiersystem",
        "tr": "kilitlenme önleyici sistem",
        "desc": "Frenleme sırasında tekerleklerin kilitlenmesini önleyerek direksiyon hakimiyetini koruyan fren sistemi.",
    },
    "asr": {
        "de": "Antriebsschlupfregelung",
        "tr": "çekiş patinaj kontrolü",
        "desc": "Çekiş sırasında patinajı azaltmak için tekerlek torkunu ve frenlemeyi yöneten kontrol sistemi.",
    },
    "antiblockiersystem": {
        "de": "Antiblockiersystem",
        "tr": "kilitlenme önleyici sistem",
        "desc": "Frenleme sırasında tekerleklerin kilitlenmesini önleyerek direksiyon hakimiyetini koruyan fren sistemi.",
    },
    "gmr": {
        "de": "Giermomentregelung",
        "tr": "sapma momenti kontrolü",
        "desc": "Aracın dönme dengesini izleyip savrulmayı sınırlayan yön kararlılığı kontrolü.",
    },
    "amr": {
        "de": "Anisotrop-magnetoresistiv",
        "tr": "anizotrop manyetorezistif",
        "desc": "Manyetik alan değişimini direnç farkı üzerinden algılayan sensör teknolojisi.",
    },
    "amr sensor": {
        "de": "Anisotrop-magnetoresistiver Sensor",
        "tr": "anizotrop manyetorezistif sensör",
        "desc": "Manyetik kutup değişimlerini yüksek hassasiyetle algılayan hız veya konum sensörü.",
    },
    "can bus": {
        "de": "Controller Area Network",
        "tr": "kontrol alan ağı veri yolu",
        "desc": "Araçtaki elektronik kontrol üniteleri arasında veri alışverişi sağlayan haberleşme hattı.",
    },
    "lin bus": {
        "de": "Local Interconnect Network",
        "tr": "yerel ara bağlantı ağı veri yolu",
        "desc": "Düşük hızlı gövde ve konfor elektroniği bileşenlerini bağlayan seri haberleşme hattı.",
    },
    "most bus": {
        "de": "Media Oriented Systems Transport",
        "tr": "multimedya odaklı sistemler taşıma veri yolu",
        "desc": "Araç içi multimedya ve bilgi-eğlence bileşenleri arasında veri taşıyan ağ yapısı.",
    },
    "nox emission": {
        "de": "Stickoxid-Emission",
        "tr": "azot oksit emisyonu",
        "desc": "Yanma sırasında oluşan azot oksit gazlarının egzozdan atmosfere salınması.",
    },
    "co emission": {
        "de": "Kohlenmonoxid-Emission",
        "tr": "karbon monoksit emisyonu",
        "desc": "Eksik yanma sonucu oluşan karbon monoksit gazının egzozla dışarı atılması.",
    },
    "hc emission": {
        "de": "Kohlenwasserstoff-Emission",
        "tr": "hidrokarbon emisyonu",
        "desc": "Tam yanmamış yakıt bileşenlerinin egzoz gazı içinde dışarı verilmesi.",
    },
}

RELATED_TERM_GROUPS = [
    ["ESP", "Elektronisches Stabilitatsprogramm"],
    ["ABS", "Antiblockiersystem"],
    ["ASR", "Antriebsschlupfregelung"],
    ["GMR", "Giermomentregelung"],
    ["AMR-Sensor", "Anisotrop-magnetoresistiver Sensor"],
    ["CAN-Bus", "Controller Area Network"],
    ["LIN-Bus", "Local Interconnect Network"],
    ["MOST-Bus", "Media Oriented Systems Transport"],
    ["NOx-Emission", "Stickoxid-Emission"],
    ["CO-Emission", "Kohlenmonoxid-Emission"],
    ["HC-Emission", "Kohlenwasserstoff-Emission"],
    ["ADAS", "Advanced Driver Assistance Systems"],
    ["DPF", "Diesel-Partikelfilter"],
    ["EDC", "Electronic Damper Control"],
    ["EMB", "Electro Mechanical Brake"],
    ["EOBD", "European On-Board Diagnostics"],
    ["FC", "Fuel Cell"],
    ["FSI", "Fuel Stratified Injection"],
    ["HDI", "High-pressure Direct Injection"],
    ["IBS", "Intelligent Battery Sensor"],
    ["LPG", "Liquefied Petroleum Gas"],
    ["MAF", "Mass Air Flow"],
    ["PSI", "Pounds per Square Inch"],
    ["RDC", "Reifen Druck Control"],
    ["VNT", "Variable Nozzle Turbine"],
    ["VVT-i", "Variable Valve Timing-intelligent"],
    ["ÖPNV", "Öffentlicher Personennahverkehr"],
]

CATEGORY_HINTS = {
    "otomotiv": [
        "abgas",
        "achse",
        "airbag",
        "antrieb",
        "automatikgetriebe",
        "automobil",
        "auto",
        "bremse",
        "brems",
        "can bus",
        "diesel",
        "fahrzeug",
        "federung",
        "getriebe",
        "karosserie",
        "kupplung",
        "lenkung",
        "motor",
        "nutzfahrzeug",
        "reifen",
        "sattelkupplung",
        "schalt",
        "turbolader",
        "yakit",
        "sanziman",
    ],
    "teknik": [
        "algorithm",
        "analyse",
        "anlage",
        "architektur",
        "bauteil",
        "komponent",
        "konstruk",
        "mechan",
        "modul",
        "regelung",
        "sensor",
        "signal",
        "sistem",
        "system",
        "technik",
        "technisch",
        "verfahren",
    ],
    "elektrik-elektronik": [
        "akku",
        "batterie",
        "bus",
        "can",
        "controller",
        "elektr",
        "elektron",
        "kabel",
        "lin",
        "magnet",
        "most",
        "netz",
        "sensor",
        "spannung",
        "strom",
        "widerstand",
    ],
    "guvenlik": [
        "abs",
        "airbag",
        "antiblockier",
        "esp",
        "fahrstabil",
        "guvenlik",
        "sicherheit",
        "stabilit",
        "surucu guvenligi",
    ],
    "iktisat": [
        "angebot",
        "bank",
        "borsa",
        "ekonomi",
        "enflasyon",
        "finanz",
        "haushalt",
        "inflation",
        "kapital",
        "kredit",
        "markt",
        "oekonom",
        "preis",
        "rezession",
        "steuer",
        "wirtschaft",
        "zins",
    ],
    "saglik": [
        "arzt",
        "epidemi",
        "gesund",
        "hastalik",
        "impf",
        "klin",
        "krank",
        "medizin",
        "pandemi",
        "pandemie",
        "symptom",
        "terapi",
        "therap",
        "virus",
    ],
    "hukuk": [
        "anwalt",
        "ceza",
        "delikt",
        "gericht",
        "gesetz",
        "haftung",
        "hukuk",
        "jur",
        "klage",
        "mahkeme",
        "recht",
        "straf",
        "vertrag",
        "verordnung",
    ],
    "bilisim": [
        "algorithm",
        "api",
        "bilgisayar",
        "computer",
        "datenbank",
        "daten",
        "digital",
        "internet",
        "kuenstliche intelligenz",
        "netzwerk",
        "programm",
        "server",
        "software",
        "veri",
    ],
    "cevre": [
        "abgas",
        "cevre",
        "co2",
        "emisyon",
        "emission",
        "iklim",
        "klima",
        "nachhalt",
        "nox",
        "umwelt",
    ],
    "enerji": [
        "akku",
        "batterie",
        "enerji",
        "energie",
        "fuel cell",
        "kraftwerk",
        "solar",
        "stromerzeug",
        "wind",
        "yakit pili",
    ],
    "ulasim-lojistik": [
        "bahn",
        "bus",
        "flotte",
        "liefer",
        "logistik",
        "oepnv",
        "personennahverkehr",
        "shuttle",
        "tasima",
        "transport",
        "ulasim",
        "verkehr",
    ],
    "siyaset-yonetim": [
        "demokr",
        "hukumet",
        "minister",
        "parlament",
        "politik",
        "regierung",
        "secim",
        "staat",
        "verwaltung",
        "wahl",
    ],
    "egitim-bilim": [
        "akadem",
        "analyse",
        "arastirma",
        "bilim",
        "forschung",
        "modell",
        "okul",
        "schule",
        "studie",
        "teori",
        "theorie",
        "universit",
        "wissenschaft",
    ],
}

AUTOISH_SOURCE_HINTS = {
    "autolexikon",
    "mein-autolexikon",
    "kfztech",
    "nutzfahrzeugtechnik-buch",
    "open-access-vehicle-books",
}

TECHNICAL_SOURCE_HINTS = {
    "kfztech",
    "nutzfahrzeugtechnik-buch",
    "open-access-vehicle-books",
}

STRICT_CATEGORY_TOKEN_HINTS = {
    "gida": {
        "apfel",
        "banane",
        "bier",
        "brot",
        "butter",
        "chili",
        "ei",
        "fleisch",
        "gemuese",
        "gemuse",
        "kaffee",
        "kaese",
        "kartoffel",
        "kuchen",
        "milch",
        "obst",
        "pfeffer",
        "reis",
        "salat",
        "salz",
        "suppe",
        "tee",
        "tomate",
        "wein",
        "wurst",
        "zucker",
        "biber",
        "peynir",
        "sut",
        "kahve",
        "ekmek",
        "et",
        "pirinc",
        "domates",
        "sarap",
    },
    "giyim": {
        "bluse",
        "hemd",
        "hose",
        "jacke",
        "kleid",
        "mantel",
        "muetze",
        "rock",
        "schal",
        "schuh",
        "socke",
        "stiefel",
        "tasche",
        "tshirt",
        "ceket",
        "elbise",
        "gomlek",
        "ayakkabi",
        "sapka",
    },
    "ev-yasam": {
        "bett",
        "fenster",
        "gabel",
        "glas",
        "haus",
        "kissen",
        "kueche",
        "kuche",
        "lampe",
        "loeffel",
        "messer",
        "schluessel",
        "schrank",
        "stuhl",
        "tasse",
        "teller",
        "tisch",
        "topf",
        "tuer",
        "yastik",
        "masa",
        "sandalye",
        "pencere",
        "kapi",
        "mutfak",
    },
    "renk": {
        "blau",
        "braun",
        "gelb",
        "grau",
        "gruen",
        "orange",
        "rosa",
        "rot",
        "schwarz",
        "violett",
        "weiss",
        "mavi",
        "kirmizi",
        "yesil",
        "sari",
        "siyah",
        "beyaz",
        "gri",
    },
    "cografya": {
        "berg",
        "dorf",
        "fluss",
        "hafen",
        "insel",
        "kueste",
        "land",
        "meer",
        "region",
        "see",
        "stadt",
        "strand",
        "tal",
        "vulkan",
        "ada",
        "dag",
        "deniz",
        "gol",
        "nehir",
        "sehir",
        "koy",
        "bolge",
    },
    "hayvan-bitki": {
        "ahorn",
        "alge",
        "ameise",
        "baum",
        "baer",
        "biene",
        "birke",
        "blatt",
        "blume",
        "blute",
        "busch",
        "eiche",
        "ente",
        "farn",
        "fisch",
        "flora",
        "gans",
        "gras",
        "hase",
        "hirsch",
        "hund",
        "huhn",
        "insekt",
        "kaktus",
        "kaninchen",
        "katze",
        "kiefer",
        "kraut",
        "kuh",
        "lilie",
        "loewe",
        "moos",
        "palme",
        "pferd",
        "pilz",
        "pflanze",
        "rose",
        "schaf",
        "schmetterling",
        "spinne",
        "tier",
        "tiger",
        "tulpe",
        "vogel",
        "wald",
        "weide",
        "wolf",
        "ziege",
    },
    "iktisat": {"banka", "borsa", "ekonomi", "enflasyon", "inflation", "kapital", "kredit", "rezession"},
    "saglik": {"arzt", "doktor", "epidemi", "epidemie", "pandemi", "pandemie", "virus", "virüs"},
    "hukuk": {"anwalt", "delikt", "gericht", "gesetz", "hukuk", "kanun", "mahkeme", "recht", "sozlesme", "vertrag"},
    "bilisim": {"api", "bilgisayar", "computer", "datenbank", "internet", "server", "software", "yazilim"},
    "cevre": {"co2", "emisyon", "emission", "nox", "umwelt"},
    "enerji": {"akku", "batarya", "batterie", "energie", "enerji", "fuel", "solar"},
    "ulasim-lojistik": {"logistik", "lojistik", "oepnv", "tasima", "transport", "ulasim", "verkehr"},
    "siyaset-yonetim": {"demokratie", "hukumet", "parlament", "politik", "regierung", "staat"},
    "egitim-bilim": {"akademi", "arastirma", "bilim", "forschung", "okul", "schule", "studie", "universite", "wissenschaft"},
}

STRICT_CATEGORY_SUBSTRING_HINTS = {
    "gida": (
        "lebensmittel",
        "nahrungs",
        "gewuerz",
        "getraenk",
        "gemuese",
    ),
    "giyim": (),
    "ev-yasam": (),
    "renk": (),
    "cografya": (),
    "hayvan-bitki": (),
    "otomotiv": (
        "abgas",
        "achs",
        "airbag",
        "antrieb",
        "automatikgetriebe",
        "brems",
        "diesel",
        "fahrzeug",
        "federung",
        "getriebe",
        "karosser",
        "kuppl",
        "lenk",
        "motor",
        "nutzfahrzeug",
        "reifen",
        "sattelkupplung",
        "turbolader",
    ),
    "teknik": (
        "algorithm",
        "architektur",
        "bauteil",
        "komponent",
        "konstruk",
        "modul",
        "regelung",
        "sensor",
        "signal",
        "system",
        "technik",
        "verfahren",
    ),
    "elektrik-elektronik": (
        "akku",
        "batterie",
        "can bus",
        "can-bus",
        "controller area network",
        "datenbus",
        "elektr",
        "elektron",
        "kabel",
        "lin bus",
        "lin-bus",
        "most bus",
        "most-bus",
        "spannung",
        "strom",
        "widerstand",
    ),
    "guvenlik": (
        "airbag",
        "antiblockier",
        "fahrstabil",
        "guvenlik",
        "sicherheit",
        "stabilitaet",
        "stabilit",
    ),
    "iktisat": (
        "finanz",
        "wirtschaft",
        "steuer",
        "zins",
    ),
    "saglik": (
        "gesund",
        "impf",
        "klin",
        "krank",
        "medizin",
        "symptom",
        "therap",
    ),
    "hukuk": (
        "haftung",
        "jur",
        "klage",
        "straf",
        "verordnung",
    ),
    "bilisim": (
        "algorithmus",
        "datenbank",
        "kuenstliche intelligenz",
        "netzwerk",
    ),
    "cevre": (
        "abgas",
        "iklim",
        "klima",
        "nachhalt",
    ),
    "enerji": (
        "kraftwerk",
        "stromerzeug",
        "yakit pili",
    ),
    "ulasim-lojistik": (
        "personennahverkehr",
        "shuttle",
    ),
    "siyaset-yonetim": (
        "demokr",
        "minister",
        "secim",
        "verwaltung",
        "wahl",
    ),
    "egitim-bilim": (
        "analyse",
        "modell",
        "teori",
        "theorie",
    ),
}

TURKISH_SUBSTRING_FIXES = {
    "d?n??": "dönüş",
    "d?nme": "dönme",
    "oran?": "oranı",
    "aktar?m": "aktarım",
    "modulasy?n?": "modülasyonu",
    "bağlantısi": "bağlantısı",
    "kitabinin": "kitabının",
    "daraltildi": "daraltıldı",
}

TURKISH_WORD_FIXES = {
    "surucu": "sürücü",
    "ag": "ağ",
    "gosterge": "gösterge",
    "gecidi": "geçidi",
    "modulu": "modülü",
    "dusurucusu": "düşürücüsü",
    "genislik": "genişlik",
    "hizi": "hızı",
    "siniri": "sınırı",
}


@dataclass
class SeedInfo:
    canonical: str
    sources: set[str]
    urls: set[str]
    raw_terms: set[str]


def fix_mojibake(text: str) -> str:
    if not text or ("Ã" not in text and "Â" not in text):
        return text
    try:
        return text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_key(text: str) -> str:
    text = fix_mojibake(text or "")
    text = unicodedata.normalize("NFKC", text).casefold()
    replacements = {
        "ä": "ae",
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "oe",
        "ş": "s",
        "ü": "ue",
        "ß": "ss",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = text.replace("&", " und ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return normalize_whitespace(text)


def key_variants(text: str) -> set[str]:
    base = normalize_key(text)
    variants = {base}
    compact = base.replace(" ", "")
    if compact:
        variants.add(compact)
    return {item for item in variants if item}


def normalize_translation_sources(raw_items: Iterable[dict] | None) -> list[dict]:
    results = []
    seen = set()
    for item in raw_items or []:
        if not isinstance(item, dict):
            continue
        ad = normalize_whitespace(fix_mojibake(item.get("ad", "")))
        url = normalize_whitespace(item.get("url", ""))
        note = normalize_whitespace(fix_mojibake(item.get("not", "")))
        key = (ad, url, note)
        if key in seen or not any(key):
            continue
        seen.add(key)
        results.append({"ad": ad or url, "url": url, "not": note})
    return results


def merge_translation_sources(*groups: Iterable[dict]) -> list[dict]:
    merged = []
    seen = set()
    for group in groups:
        for item in normalize_translation_sources(group):
            key = (item.get("ad", ""), item.get("url", ""), item.get("not", ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def slug_to_candidate(slug: str) -> str:
    slug = slug.replace(".html", "").strip("/")
    return normalize_whitespace(slug.replace("-", " ").replace("_", " "))


def split_translations(text: str) -> list[str]:
    text = fix_mojibake(text)
    text = text.replace(" / ", " | ")
    parts = re.split(r"\s*\|\s*|\s*;\s*", text)
    results = []
    for part in parts:
        part = normalize_whitespace(part)
        if part:
            results.append(part)
    return results


def shorten_translation(text: str) -> str:
    text = fix_mojibake(text)
    text = re.sub(r"^\([^)]*\)\s*", "", text)
    text = normalize_whitespace(text)
    if ":" in text:
        left, right = text.split(":", 1)
        if len(left) < 30 and any(ch.isupper() for ch in left):
            text = right.strip()
    text = split_translations(text)[0] if split_translations(text) else text
    pieces = [piece.strip() for piece in text.split(",") if piece.strip()]
    if len(pieces) > 3:
        text = ", ".join(pieces[:3])
    return text[:140].strip(" ,;")


def build_note(glosses: Iterable[str], wikdict_translation: str | None = None) -> str:
    cleaned = []
    for gloss in glosses:
        shortened = shorten_translation(gloss)
        if shortened:
            cleaned.append(shortened)
    unique = []
    seen = set()
    for item in cleaned:
        key = normalize_key(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    notes = []
    if len(unique) > 1:
        notes.append("Alternatif anlamlar: " + " | ".join(unique[1:4]))
    if wikdict_translation:
        primary = unique[0] if unique else ""
        if primary and normalize_key(primary) != normalize_key(wikdict_translation):
            notes.append(f"WikDict eşleşmesi: {wikdict_translation}")
    return " ; ".join(notes)


def extract_article(entry: dict) -> str:
    haystack = " | ".join(
        [
            " ".join(entry.get("tags") or []),
            " ".join(entry.get("categories") or []),
            " ".join(
                " ".join(form.get("tags") or []) + " " + " ".join(form.get("raw_tags") or [])
                for form in entry.get("forms") or []
            ),
        ]
    ).casefold()
    if "masculine" in haystack or "eril" in haystack:
        return "der"
    if "feminine" in haystack or "dişil" in haystack:
        return "die"
    if "neutral" in haystack or "nötr" in haystack:
        return "das"
    return ""


def extract_example(sense: dict) -> tuple[str, str]:
    for example in sense.get("examples") or []:
        text = normalize_whitespace(fix_mojibake(example.get("text", "")))
        translation = normalize_whitespace(fix_mojibake(example.get("translation", "")))
        if text and translation:
            return text, translation
    return "", ""


def is_autoish_entry(entry: dict, sense: dict | None = None, translation_text: str = "") -> bool:
    chunks = [
        entry.get("word", ""),
        " ".join(entry.get("categories") or []),
        " ".join(entry.get("topics") or []),
        translation_text,
    ]
    if sense:
        chunks.extend(
            [
                " ".join(sense.get("glosses") or []),
                " ".join(sense.get("categories") or []),
                " ".join(sense.get("topics") or []),
            ]
        )
    haystack = normalize_key(" ".join(fix_mojibake(chunk) for chunk in chunks if chunk))
    return any(fragment in haystack for fragment in AUTO_HINTS)


def is_autoish_term(text: str) -> bool:
    haystack = normalize_key(text)
    return any(fragment in haystack for fragment in AUTO_HINTS)


def score_domain_translation_candidate(entry: dict, sense: dict, translation: str, seed_info: SeedInfo | None) -> int:
    if not seed_info:
        return 0

    score = 0
    raw_tags = normalize_key(" ".join(sense.get("raw_tags") or []))
    topics = normalize_key(" ".join(sense.get("topics") or []))
    categories = normalize_key(" ".join(entry.get("categories") or []))
    word_key = normalize_key(entry.get("word", ""))
    translation_key = normalize_key(translation)

    if is_autoish_entry(entry, sense, translation):
        score += 8
    if any(token in raw_tags for token in ("fahrzeugbau", "kraftfahrzeug", "auto")):
        score += 8
    if any(token in topics for token in ("automobil", "transport", "vehicle")):
        score += 4
    if any(token in categories for token in ("fahrzeug", "auto", "kraftfahrzeug")):
        score += 2
    if translation_key in DOMAIN_TRANSLATION_PREFERENCES.get(word_key, set()):
        score += 10
    return score


def is_noise_seed(term: str, url: str) -> bool:
    key = normalize_key(term)
    noise_fragments = {
        "datenschutzerklaerung",
        "impressum",
        "buchstabe",
        "autohersteller",
        "laenderkennzeichen",
        "kfz kennzeichen",
        "verkehrszeichen",
        "hersteller",
        "firmen",
        "europa",
        "afrika",
        "asien",
        "australien",
        "ozeanien",
        "nordamerika",
        "mittelamerika",
        "suedamerika",
    }
    if any(fragment in key for fragment in noise_fragments):
        return True
    if "/kennzeichen/" in url or "/autohersteller/" in url:
        return True
    return False


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_example_payload(items: Iterable[dict] | None) -> list[dict]:
    examples: list[dict] = []
    for item in items or []:
        almanca = normalize_whitespace(fix_mojibake(item.get("almanca", "")))
        turkce = normalize_whitespace(fix_mojibake(item.get("turkce", "")))
        if not almanca and not turkce:
            continue
        examples.append(
            {
                "almanca": almanca,
                "turkce": turkce,
                "etiket_turkce": normalize_whitespace(fix_mojibake(item.get("etiket_turkce", ""))),
                "vurgu_de": normalize_whitespace(fix_mojibake(item.get("vurgu_de", ""))),
                "vurgu_tr": normalize_whitespace(fix_mojibake(item.get("vurgu_tr", ""))),
                "kaynak": normalize_whitespace(fix_mojibake(item.get("kaynak", ""))),
                "not": normalize_whitespace(fix_mojibake(item.get("not", ""))),
            }
        )
    return examples


def strip_translation_grammar(text: str) -> str:
    cleaned = re.sub(r"\[[^\]]+\]", "", text or "")
    cleaned = re.sub(r"^[,;:/\-\s]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ,;:")


def default_turkish_highlight(text: str) -> str:
    cleaned = strip_translation_grammar(text)
    if not cleaned:
        return ""
    first_chunk = re.split(r"[;,/|]", cleaned, maxsplit=1)[0]
    return normalize_whitespace(first_chunk)


def merge_example_payloads(primary: list[dict], secondary: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen = set()
    for item in primary + secondary:
        key = (
            normalize_key(item.get("almanca", "")),
            normalize_key(item.get("turkce", "")),
            normalize_key(item.get("etiket_turkce", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def build_default_examples(record: dict) -> list[dict]:
    examples = normalize_example_payload(record.get("ornekler", []))
    fallback_de = normalize_whitespace(record.get("ornek_almanca", ""))
    fallback_tr = normalize_whitespace(record.get("ornek_turkce", ""))
    if fallback_de or fallback_tr:
        fallback = {
            "almanca": fallback_de,
            "turkce": fallback_tr,
            "etiket_turkce": "",
            "vurgu_de": normalize_whitespace(record.get("almanca", "")),
            "vurgu_tr": default_turkish_highlight(record.get("turkce", "")),
            "kaynak": "; ".join(sorted(record.get("source_names", []))),
            "not": "",
        }
        examples = merge_example_payloads(examples, [fallback])
    return examples


def load_record_enrichments() -> dict[tuple[str, str, str], dict]:
    if not RECORD_ENRICHMENTS_PATH.exists():
        return {}

    payload = load_json(RECORD_ENRICHMENTS_PATH)
    enrichments: dict[tuple[str, str, str], dict] = {}
    for item in payload.get("record_enrichments", []):
        almanca = normalize_whitespace(fix_mojibake(item.get("almanca", "")))
        tur = canonicalize_pos_label(normalize_whitespace(fix_mojibake(item.get("tur", ""))))
        turkce = normalize_whitespace(fix_mojibake(item.get("turkce", "")))
        if not almanca or not tur or not turkce:
            continue
        key = (normalize_key(almanca), tur, normalize_key(turkce))
        enrichments[key] = {
            "replace_examples": bool(item.get("replace_examples")),
            "ornekler": normalize_example_payload(item.get("ornekler", [])),
            "not_ek": normalize_whitespace(fix_mojibake(item.get("not_ek", ""))),
        }
    return enrichments


def apply_record_enrichments(records: list[dict]) -> list[dict]:
    enrichments = load_record_enrichments()
    for record in records:
        record["ornekler"] = build_default_examples(record)
        key = (
            normalize_key(record.get("almanca", "")),
            canonicalize_pos_label(record.get("tur", "")),
            normalize_key(record.get("turkce", "")),
        )
        enrichment = enrichments.get(key)
        if not enrichment:
            continue
        if enrichment.get("replace_examples"):
            record["ornekler"] = list(enrichment["ornekler"])
        else:
            record["ornekler"] = merge_example_payloads(record["ornekler"], enrichment["ornekler"])

        note_suffix = enrichment.get("not_ek", "")
        if note_suffix:
            current_note = normalize_whitespace(record.get("not", ""))
            if note_suffix not in current_note:
                record["not"] = f"{current_note} ; {note_suffix}".strip(" ;")
    return records


def load_translation_reviews() -> dict[tuple[str, str], dict]:
    if not TRANSLATION_REVIEW_PATH.exists():
        return {}

    payload = load_json(TRANSLATION_REVIEW_PATH)
    reviews: dict[tuple[str, str], dict] = {}
    for item in payload.get("translation_reviews", []):
        almanca = normalize_whitespace(fix_mojibake(item.get("almanca", "")))
        tur = canonicalize_pos_label(item.get("tur", ""))
        if not almanca or not tur:
            continue
        reviews[(normalize_key(almanca), tur)] = {
            "turkce": normalize_whitespace(fix_mojibake(item.get("turkce", ""))),
            "aciklama_turkce": normalize_whitespace(fix_mojibake(item.get("aciklama_turkce", ""))),
            "ceviri_durumu": normalize_whitespace(fix_mojibake(item.get("ceviri_durumu", "manuel-dogrulandi"))),
            "ceviri_inceleme_notu": normalize_whitespace(fix_mojibake(item.get("ceviri_inceleme_notu", ""))),
            "ceviri_kaynaklari": normalize_translation_sources(item.get("ceviri_kaynaklari")),
        }
    return reviews


def apply_translation_reviews(records: list[dict]) -> list[dict]:
    reviews = load_translation_reviews()
    for record in records:
        record.setdefault("ceviri_kaynaklari", [])
        record.setdefault("ceviri_durumu", "kaynak-izli")
        record.setdefault("ceviri_inceleme_notu", "")

        term_key = normalize_key(record.get("almanca", ""))
        review = reviews.get((term_key, canonicalize_pos_label(record.get("tur", ""))))
        if not review:
            for (review_term_key, _), candidate in reviews.items():
                if review_term_key == term_key:
                    review = candidate
                    break
        if not review:
            continue

        if review.get("turkce"):
            record["turkce"] = review["turkce"]
        if review.get("aciklama_turkce"):
            record["aciklama_turkce"] = review["aciklama_turkce"]
        if review.get("ceviri_durumu"):
            record["ceviri_durumu"] = review["ceviri_durumu"]
        if review.get("ceviri_inceleme_notu"):
            record["ceviri_inceleme_notu"] = review["ceviri_inceleme_notu"]
        record["ceviri_kaynaklari"] = merge_translation_sources(
            record.get("ceviri_kaynaklari"),
            review.get("ceviri_kaynaklari"),
        )
    return records


FORM_GLOSS_OVERRIDES = {
    "abgebremst": {
        "turkce": "frenlenmiş, yavaşlatılmış",
        "not": "Form açıklaması yerine kullanım değeri taşıyan sıfat çevirisi verildi.",
        "source_name": "manual-curated",
    }
}


def is_form_gloss_translation(text: str) -> bool:
    normalized = fix_mojibake(text or "").casefold()
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "i̇": "i",
        "ş": "s",
        "â": "a",
        "î": "i",
        "û": "u",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalize_whitespace(re.sub(r"[^a-z0-9+]+", " ", normalized))

    if not normalized or normalized.startswith("+"):
        return False

    direct_prefixes = (
        "cogul ad cekimi",
        "cogul isim cekimi",
        "cogul cekimi",
        "tekil cekimi",
    )
    direct_fragments = (
        " sozcugunun cogul cekimi",
        " sozcugunun gerund cekimi",
        " sozcugunun gecmis zaman ortac cekimi",
        " sozcugunun ortac cekimi",
        " sozcugunun eskimis yazilisi",
        "eskimis yazilisi",
        " gerund cekimi",
        " ortac cekimi",
        " cogulu",
    )

    if any(normalized.startswith(prefix) for prefix in direct_prefixes):
        return True
    if normalized.endswith("cekimi") and any(
        marker in normalized for marker in ("cogul", "tekil", "ortac", "gerund", "zaman")
    ):
        return True
    if "sozcugunun" in normalized and any(marker in normalized for marker in ("cekimi", "cogulu", "yazilisi")):
        return True
    if any(fragment in normalized for fragment in direct_fragments):
        return True
    return False


def clean_form_gloss_records(records: list[dict]) -> tuple[list[dict], Counter]:
    cleaned: list[dict] = []
    counters = Counter()

    for record in records:
        override = FORM_GLOSS_OVERRIDES.get(normalize_key(record.get("almanca", "")))
        if override and is_form_gloss_translation(record.get("turkce", "")):
            record["turkce"] = fix_mojibake(override["turkce"])
            note_prefix = fix_mojibake(override["not"])
            record["not"] = f"{note_prefix} ; {record['not']}".strip(" ;")
            record["source_names"].add(override["source_name"])
            counters["form_gloss_overrides_applied"] += 1
            cleaned.append(record)
            continue

        if is_form_gloss_translation(record.get("turkce", "")):
            counters["form_gloss_records_dropped"] += 1
            continue

        cleaned.append(record)

    return cleaned, counters


def load_seed_map() -> dict[str, SeedInfo]:
    sources = [
        ("autolexikon", load_json(AUTOLEXIKON_TERMS_PATH).get("seeds", [])),
        ("mein-autolexikon", load_json(MEIN_AUTOLEXIKON_TERMS_PATH).get("seeds", [])),
    ]
    seed_map: dict[str, SeedInfo] = {}

    for source_name, items in sources:
        for item in items:
            raw_term = fix_mojibake(item.get("term", ""))
            url = item.get("url", "")
            if not raw_term or not url or is_noise_seed(raw_term, url):
                continue

            candidates = [raw_term]
            slug = item.get("slug")
            if slug:
                candidates.append(slug_to_candidate(slug))

            for candidate in candidates:
                for key in key_variants(candidate):
                    if key not in seed_map:
                        seed_map[key] = SeedInfo(
                            canonical=candidate,
                            sources=set(),
                            urls=set(),
                            raw_terms=set(),
                        )
                    seed_map[key].sources.add(source_name)
                    seed_map[key].urls.add(url)
                    seed_map[key].raw_terms.add(raw_term)
    return seed_map


def load_manual_records() -> tuple[list[dict], Counter]:
    records: list[dict] = []
    counters = Counter()

    for path in sorted(MANUAL_DIR.glob("*.json")):
        payload = load_json(path)
        source_name = normalize_whitespace(payload.get("source_name", path.stem))
        default_note = normalize_whitespace(payload.get("default_note", ""))
        counter_key = "manual_" + normalize_key(source_name).replace(" ", "_") + "_records"

        for item in payload.get("records", []):
            almanca = normalize_whitespace(fix_mojibake(item.get("almanca", "")))
            turkce = normalize_whitespace(fix_mojibake(item.get("turkce", "")))
            aciklama_turkce = normalize_whitespace(fix_mojibake(item.get("aciklama_turkce", "")))
            tur = normalize_whitespace(fix_mojibake(item.get("tur", "")))
            if not almanca or not turkce or not tur:
                continue

            kaynak_url = normalize_whitespace(item.get("kaynak_url", ""))
            note = normalize_whitespace(fix_mojibake(item.get("not", "") or default_note))
            source_urls = {kaynak_url} if kaynak_url else set()

            records.append(
                {
                    "almanca": almanca,
                    "artikel": normalize_whitespace(fix_mojibake(item.get("artikel", ""))),
                    "turkce": turkce,
                    "aciklama_turkce": aciklama_turkce,
                    "tur": tur,
                    "ornek_almanca": "",
                    "ornek_turkce": "",
                    "kaynak": "",
                    "kaynak_url": "",
                    "not": note,
                    "source_names": {source_name},
                    "source_urls": source_urls,
                    "ceviri_kaynaklari": normalize_translation_sources(item.get("ceviri_kaynaklari")),
                    "ceviri_durumu": normalize_whitespace(fix_mojibake(item.get("ceviri_durumu", "kaynak-izli"))),
                    "ceviri_inceleme_notu": normalize_whitespace(fix_mojibake(item.get("ceviri_inceleme_notu", ""))),
                    "seed_match": False,
                    "autoish": True,
                    "wikdict_fallback": False,
                }
            )
            counters[counter_key] += 1

    return merge_records(records), counters


def count_unique_seeds(seed_map: dict[str, SeedInfo]) -> int:
    seen = set()
    for info in seed_map.values():
        seen.add(
            (
                tuple(sorted(info.urls)),
                tuple(sorted(info.raw_terms)),
            )
        )
    return len(seen)


def merge_seed_infos(seed_infos: Iterable[SeedInfo]) -> SeedInfo | None:
    items = list(seed_infos)
    if not items:
        return None
    return SeedInfo(
        canonical=items[0].canonical,
        sources=set().union(*(info.sources for info in items)),
        urls=set().union(*(info.urls for info in items)),
        raw_terms=set().union(*(info.raw_terms for info in items)),
    )


def seed_info_matches_word(word: str, seed_info: SeedInfo) -> bool:
    raw_terms = {normalize_whitespace(fix_mojibake(item)) for item in seed_info.raw_terms}
    if word in raw_terms:
        return True
    if not word[:1].islower():
        return True
    return any(candidate[:1].islower() for candidate in raw_terms if candidate)


def build_seed_info(word: str, entry_keys: Iterable[str], seed_map: dict[str, SeedInfo]) -> SeedInfo | None:
    seed_infos = [seed_map[key] for key in entry_keys if key in seed_map]
    exact_matches = [info for info in seed_infos if seed_info_matches_word(word, info)]
    return merge_seed_infos(exact_matches)


def load_wikdict_index() -> dict[str, dict]:
    conn = sqlite3.connect(WIKDICT_PATH)
    cursor = conn.cursor()
    index: dict[str, dict] = {}
    for written_rep, trans_list, max_score, rel_importance in cursor.execute(
        "select written_rep, trans_list, max_score, rel_importance from simple_translation"
    ):
        if not written_rep or not trans_list:
            continue
        score = float(max_score or 0) + float(rel_importance or 0)
        payload = {
            "written_rep": fix_mojibake(written_rep),
            "trans_list": fix_mojibake(trans_list),
            "score": score,
        }
        for key in key_variants(written_rep):
            current = index.get(key)
            if current is None or score > current["score"]:
                index[key] = payload
    conn.close()
    return index


def map_pos(pos: str) -> str:
    return POS_MAP.get(pos, "")


def canonicalize_pos_label(value: str) -> str:
    value = normalize_whitespace(fix_mojibake(value))
    replacements = {
        "sifat": "sıfat",
        "sÄ±fat": "sıfat",
        "kısaltma": "kısaltma",
        "kisaltma": "kısaltma",
        "kÄ±saltma": "kısaltma",
        "sayı": "sayı",
        "sayi": "sayı",
        "sayÄ±": "sayı",
        "bağlaç": "bağlaç",
        "baglac": "bağlaç",
        "baÄŸlaÃ§": "bağlaç",
        "ünlem": "ünlem",
        "unlem": "ünlem",
        "Ã¼nlem": "ünlem",
    }
    return replacements.get(value, value)


def entry_is_form_only(entry: dict) -> bool:
    if entry.get("form_of") or entry.get("alt_of"):
        return True
    categories = " | ".join(entry.get("categories") or []).casefold()
    return "çekim" in categories


def record_priority(record: dict) -> tuple:
    return (
        0 if record["seed_match"] else 1,
        0 if record["autoish"] else 1,
        0 if record["ornek_almanca"] else 1,
        GENERAL_POS_PRIORITY.get(record["tur"], 99),
        len(record["almanca"]),
    )


def normalize_turkish_merge_key(text: str) -> str:
    return normalize_key(normalize_turkish_text(text)).replace(" ", "")


def merge_records(records: Iterable[dict]) -> list[dict]:
    merged: dict[tuple[str, str, str], dict] = {}
    for record in records:
        key = (normalize_key(record["almanca"]), record["tur"], normalize_turkish_merge_key(record["turkce"]))
        existing = merged.get(key)
        if existing is None:
            merged[key] = record
            continue

        existing["source_names"].update(record["source_names"])
        existing["source_urls"].update(record["source_urls"])
        existing["ceviri_kaynaklari"] = merge_translation_sources(
            existing.get("ceviri_kaynaklari"),
            record.get("ceviri_kaynaklari"),
        )
        existing["ceviri_durumu"] = existing.get("ceviri_durumu") or record.get("ceviri_durumu", "kaynak-izli")
        if len(record.get("ceviri_inceleme_notu", "")) > len(existing.get("ceviri_inceleme_notu", "")):
            existing["ceviri_inceleme_notu"] = record.get("ceviri_inceleme_notu", "")
        if not existing["ornek_almanca"] and record["ornek_almanca"]:
            existing["ornek_almanca"] = record["ornek_almanca"]
            existing["ornek_turkce"] = record["ornek_turkce"]
        if len(record.get("aciklama_turkce", "")) > len(existing.get("aciklama_turkce", "")):
            existing["aciklama_turkce"] = record["aciklama_turkce"]
        if not existing["artikel"] and record["artikel"]:
            existing["artikel"] = record["artikel"]
        if len(record["not"]) > len(existing["not"]):
            existing["not"] = record["not"]
        existing["seed_match"] = existing["seed_match"] or record["seed_match"]
        existing["autoish"] = existing["autoish"] or record["autoish"]
    results = []
    for record in merged.values():
        record["kaynak"] = "; ".join(sorted(record["source_names"]))
        record["kaynak_url"] = "; ".join(sorted(record["source_urls"]))
        results.append(record)
    return results


def annotate_abbreviations(records: list[dict]) -> list[dict]:
    for record in records:
        hint = ABBREVIATION_HINTS.get(normalize_key(record["almanca"]))
        if not hint:
            continue
        prefix = f"Açılım: {hint['de']}. Türkçe karşılığı: {hint['tr']}."
        if hint.get("desc") and not record.get("aciklama_turkce"):
            record["aciklama_turkce"] = hint["desc"]
        if record["not"]:
            if prefix not in record["not"]:
                record["not"] = prefix + " " + record["not"]
        else:
            record["not"] = prefix
    return records


def normalize_turkish_text(text: str) -> str:
    if not text:
        return text

    result = text
    for source, target in TURKISH_SUBSTRING_FIXES.items():
        result = result.replace(source, target)

    for source, target in TURKISH_WORD_FIXES.items():
        result = re.sub(rf"\b{re.escape(source)}\b", target, result)

    return result


def polish_turkish_fields(records: list[dict]) -> list[dict]:
    for record in records:
        for key in ("turkce", "aciklama_turkce", "ornek_turkce", "not"):
            record[key] = normalize_turkish_text(record.get(key, ""))
    return records


def tokenize_normalized_text(*values: str) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        normalized = normalize_key(value)
        if not normalized:
            continue
        tokens.update(normalized.split())
    return tokens


def contains_any_fragment(text: str, fragments: Iterable[str]) -> bool:
    return any(fragment in text for fragment in fragments)


def is_low_value_abbreviation(record: dict) -> bool:
    source_names = set(record.get("source_names", set()))
    if source_names & AUTOISH_SOURCE_HINTS:
        return False
    if record.get("autoish"):
        return False

    word = record.get("almanca", "")
    translation = normalize_key(record.get("turkce", ""))
    note = normalize_key(record.get("not", ""))
    tur = canonicalize_pos_label(record.get("tur", ""))

    abbreviation_markers = (
        "kisaltmasi",
        "kavraminin kisaltmasi",
        "kelimesinin kisaltmasi",
        "akronimi",
    )
    translation_marks_abbrev = any(marker in translation for marker in abbreviation_markers)
    note_marks_abbrev = any(marker in note for marker in abbreviation_markers)
    uppercase_short = bool(re.fullmatch(r"[A-ZÄÖÜẞ0-9-]{2,8}", word))

    return tur == "kisaltma" or translation_marks_abbrev or note_marks_abbrev or uppercase_short


def filter_low_value_records(records: list[dict]) -> tuple[list[dict], Counter]:
    counters = Counter()
    kept = []

    for record in records:
        if is_low_value_abbreviation(record):
            counters["low_value_abbreviation_records_dropped"] += 1
            continue
        kept.append(record)

    return kept, counters


def annotate_categories(records: list[dict]) -> list[dict]:
    for record in records:
        source_names = set(record.get("source_names", set()))
        primary_text = normalize_key(
            " ".join(
                [
                    record.get("almanca", ""),
                    record.get("turkce", ""),
                    record.get("aciklama_turkce", ""),
                    " ".join(record.get("ilgili_kayitlar", [])),
                ]
            )
        )
        primary_tokens = tokenize_normalized_text(
            record.get("almanca", ""),
            record.get("turkce", ""),
            record.get("aciklama_turkce", ""),
            " ".join(record.get("ilgili_kayitlar", [])),
        )

        selected: list[str] = []

        if source_names & AUTOISH_SOURCE_HINTS:
            selected.append("otomotiv")

        technical_signal = (
            bool(source_names & TECHNICAL_SOURCE_HINTS)
            or contains_any_fragment(primary_text, STRICT_CATEGORY_SUBSTRING_HINTS["teknik"])
            or bool(primary_tokens & STRICT_CATEGORY_TOKEN_HINTS.get("teknik", set()))
        )
        if technical_signal and ("otomotiv" in selected or record.get("tur") == "kısaltma"):
            selected.append("teknik")

        for category in (
            "gida",
            "giyim",
            "ev-yasam",
            "renk",
            "cografya",
            "hayvan-bitki",
            "elektrik-elektronik",
            "guvenlik",
            "iktisat",
            "saglik",
            "hukuk",
            "bilisim",
            "cevre",
            "enerji",
            "ulasim-lojistik",
            "siyaset-yonetim",
            "egitim-bilim",
        ):
            token_hints = STRICT_CATEGORY_TOKEN_HINTS.get(category, set())
            substring_hints = STRICT_CATEGORY_SUBSTRING_HINTS.get(category, ())
            token_hit = bool(primary_tokens & token_hints)
            substring_hit = contains_any_fragment(primary_text, substring_hints)
            if token_hit or substring_hit:
                selected.append(category)

        if "otomotiv" in selected and contains_any_fragment(
            primary_text, STRICT_CATEGORY_SUBSTRING_HINTS["elektrik-elektronik"]
        ):
            selected.append("elektrik-elektronik")

        if "otomotiv" in selected and contains_any_fragment(
            primary_text, STRICT_CATEGORY_SUBSTRING_HINTS["guvenlik"]
        ):
            selected.append("guvenlik")

        if "otomotiv" in selected and contains_any_fragment(
            primary_text, STRICT_CATEGORY_SUBSTRING_HINTS["cevre"]
        ):
            selected.append("cevre")

        if not selected:
            selected = ["genel"]

        ordered = [
            category
            for category in (
                "otomotiv",
                "teknik",
                "gida",
                "giyim",
                "ev-yasam",
                "renk",
                "cografya",
                "hayvan-bitki",
                "elektrik-elektronik",
                "guvenlik",
                "ulasim-lojistik",
                "cevre",
                "enerji",
                "iktisat",
                "saglik",
                "hukuk",
                "bilisim",
                "siyaset-yonetim",
                "egitim-bilim",
                "genel",
            )
            if category in selected
        ]
        record["kategoriler"] = ordered

    return records


def link_related_terms(records: list[dict]) -> list[dict]:
    by_key = {normalize_key(record["almanca"]): record for record in records}

    for record in records:
        record["ilgili_kayitlar"] = []

    for group in RELATED_TERM_GROUPS:
        existing = [name for name in group if normalize_key(name) in by_key]
        for name in existing:
            record = by_key[normalize_key(name)]
            related = [other for other in existing if normalize_key(other) != normalize_key(name)]
            record["ilgili_kayitlar"] = sorted(set(record.get("ilgili_kayitlar", [])) | set(related))

    return records


def parse_trwiktionary(seed_map: dict[str, SeedInfo], wikdict_index: dict[str, dict]) -> tuple[list[dict], list[dict], Counter]:
    domain_records: list[dict] = []
    general_records: list[dict] = []
    counters = Counter()

    with gzip.open(TRWIKTIONARY_PATH, "rt", encoding="utf-8") as fh:
        for line in fh:
            entry = json.loads(line)
            if entry.get("lang_code") != "de":
                continue
            if entry.get("pos") == "name":
                continue
            if entry_is_form_only(entry):
                continue

            tur = map_pos(entry.get("pos", ""))
            if not tur:
                continue

            word = fix_mojibake(entry.get("word", ""))
            if not word:
                continue

            entry_keys = key_variants(word)
            seed_info = build_seed_info(word, entry_keys, seed_map)
            artikel = extract_article(entry) if tur == "isim" else ""

            for sense in entry.get("senses") or []:
                glosses = sense.get("glosses") or []
                if not glosses:
                    continue
                turkce = shorten_translation(glosses[0])
                if not turkce:
                    continue

                example_de, example_tr = extract_example(sense)
                wikdict_translation = None
                wikdict_match = next((wikdict_index[key] for key in entry_keys if key in wikdict_index), None)
                if wikdict_match:
                    wikdict_translation = shorten_translation(wikdict_match["trans_list"])

                sense_autoish = is_autoish_entry(entry, sense, turkce)
                term_autoish = is_autoish_term(word)
                if seed_info and not (term_autoish or (sense_autoish and len(normalize_key(word)) > 4)):
                    continue

                source_names = {"trwiktionary"}
                source_urls = {"https://kaikki.org/trwiktionary/rawdata.html"}
                if seed_info:
                    source_names.update(seed_info.sources)
                    source_urls.update(seed_info.urls)

                note = build_note(glosses, wikdict_translation)

                record = {
                    "almanca": word,
                    "artikel": artikel,
                    "turkce": turkce,
                    "aciklama_turkce": "",
                    "tur": tur,
                    "ornek_almanca": example_de,
                    "ornek_turkce": example_tr,
                    "kaynak": "",
                    "kaynak_url": "",
                    "not": note,
                    "source_names": source_names,
                    "source_urls": source_urls,
                    "ceviri_kaynaklari": [],
                    "ceviri_durumu": "kaynak-izli",
                    "ceviri_inceleme_notu": "",
                    "seed_match": bool(seed_info),
                    "autoish": bool(seed_info) or sense_autoish,
                    "wikdict_fallback": False,
                }

                if seed_info:
                    domain_records.append(record)
                    counters["trwiktionary_seed_records"] += 1
                else:
                    general_records.append(record)
                    counters["trwiktionary_general_records"] += 1

                if tur in {"fiil", "isim", "sıfat"}:
                    break

    return merge_records(domain_records), merge_records(general_records), counters


def parse_dewiktionary(seed_map: dict[str, SeedInfo]) -> tuple[list[dict], list[dict], Counter]:
    domain_records: list[dict] = []
    general_records: list[dict] = []
    counters = Counter()

    with gzip.open(DEWIKTIONARY_PATH, "rt", encoding="utf-8") as fh:
        for line in fh:
            entry = json.loads(line)
            if entry.get("lang_code") != "de":
                continue
            if entry.get("pos") == "name":
                continue
            if entry_is_form_only(entry):
                continue

            tur = map_pos(entry.get("pos", ""))
            if not tur:
                continue

            word = fix_mojibake(entry.get("word", ""))
            if not word:
                continue

            entry_keys = key_variants(word)
            seed_info = build_seed_info(word, entry_keys, seed_map)

            grouped_translations: dict[str, list[str]] = defaultdict(list)
            for translation in entry.get("translations") or []:
                if translation.get("lang_code") != "tr":
                    continue
                translated_word = shorten_translation(translation.get("word", ""))
                if translated_word:
                    grouped_translations[translation.get("sense_index") or "0"].append(translated_word)
            if not grouped_translations:
                continue

            senses_by_index = {
                str(sense.get("sense_index") or "0"): sense
                for sense in entry.get("senses") or []
            }

            ordered_translations = list(grouped_translations.items())
            if seed_info:
                ordered_translations.sort(
                    key=lambda item: score_domain_translation_candidate(
                        entry,
                        senses_by_index.get(str(item[0]), {}),
                        item[1][0] if item[1] else "",
                        seed_info,
                    ),
                    reverse=True,
                )

            artikel = extract_article(entry) if tur == "isim" else ""
            for sense_index, translations in ordered_translations:
                unique_translations = []
                seen = set()
                for item in translations:
                    key = normalize_key(item)
                    if key in seen:
                        continue
                    seen.add(key)
                    unique_translations.append(item)
                if not unique_translations:
                    continue

                sense = senses_by_index.get(str(sense_index), {})
                example_de, example_tr = extract_example(sense)
                note = ""
                if len(unique_translations) > 1:
                    note = "Alternatif anlamlar: " + " | ".join(unique_translations[1:4])

                sense_autoish = is_autoish_entry(entry, sense, unique_translations[0])
                term_autoish = is_autoish_term(word)
                if seed_info and not (term_autoish or (sense_autoish and len(normalize_key(word)) > 4)):
                    continue

                source_names = {"dewiktionary"}
                source_urls = {"https://kaikki.org/dewiktionary/rawdata.html"}
                if seed_info:
                    source_names.update(seed_info.sources)
                    source_urls.update(seed_info.urls)

                record = {
                    "almanca": word,
                    "artikel": artikel,
                    "turkce": unique_translations[0],
                    "aciklama_turkce": "",
                    "tur": tur,
                    "ornek_almanca": example_de,
                    "ornek_turkce": example_tr,
                    "kaynak": "",
                    "kaynak_url": "",
                    "not": note,
                    "source_names": source_names,
                    "source_urls": source_urls,
                    "ceviri_kaynaklari": [],
                    "ceviri_durumu": "kaynak-izli",
                    "ceviri_inceleme_notu": "",
                    "seed_match": bool(seed_info),
                    "autoish": bool(seed_info) or sense_autoish,
                    "wikdict_fallback": False,
                }

                if seed_info:
                    domain_records.append(record)
                    counters["dewiktionary_seed_records"] += 1
                else:
                    general_records.append(record)
                    counters["dewiktionary_general_records"] += 1

                if tur in {"fiil", "isim", "sıfat"}:
                    break

    return merge_records(domain_records), merge_records(general_records), counters


def build_wikdict_seed_fallbacks(
    seed_map: dict[str, SeedInfo],
    wikdict_index: dict[str, dict],
    existing_domain_records: list[dict],
) -> tuple[list[dict], Counter]:
    counters = Counter()
    covered_keys = {variant for record in existing_domain_records for variant in key_variants(record["almanca"])}
    records = []
    for key, seed_info in seed_map.items():
        if key in covered_keys:
            continue
        match = wikdict_index.get(key)
        if not match:
            continue

        translations = split_translations(match["trans_list"])
        if not translations:
            continue

        turkce = shorten_translation(translations[0])
        term_autoish = is_autoish_term(match["written_rep"])
        translation_autoish = is_autoish_term(turkce)
        if not (translation_autoish or (term_autoish and len(normalize_key(match["written_rep"])) >= 8)):
            continue
        note = ""
        if len(translations) > 1:
            note = "Alternatif anlamlar: " + " | ".join(shorten_translation(item) for item in translations[1:4])

        records.append(
            {
                "almanca": match["written_rep"],
                "artikel": "",
                "turkce": turkce,
                "aciklama_turkce": "",
                "tur": "belirsiz",
                "ornek_almanca": "",
                "ornek_turkce": "",
                "kaynak": "",
                "kaynak_url": "",
                "not": note,
                "source_names": set(seed_info.sources) | {"wikdict"},
                "source_urls": set(seed_info.urls) | {"https://download.wikdict.com/dictionaries/sqlite/2/"},
                "ceviri_kaynaklari": [],
                "ceviri_durumu": "kaynak-izli",
                "ceviri_inceleme_notu": "",
                "seed_match": True,
                "autoish": True,
                "wikdict_fallback": True,
            }
        )
        counters["wikdict_seed_fallbacks"] += 1
    return merge_records(records), counters


def finalize_records(domain_records: list[dict], general_records: list[dict], wikdict_fallbacks: list[dict]) -> tuple[list[dict], Counter]:
    counters = Counter()
    ordered_domain = sorted(
        merge_records(domain_records + wikdict_fallbacks),
        key=lambda item: record_priority(item),
    )
    final_records = list(ordered_domain)
    counters["domain_record_count"] = len(ordered_domain)

    seen_keys = {
        (normalize_key(item["almanca"]), item["tur"], normalize_turkish_merge_key(item["turkce"]))
        for item in final_records
    }

    for record in sorted(general_records, key=lambda item: record_priority(item)):
        key = (normalize_key(record["almanca"]), record["tur"], normalize_turkish_merge_key(record["turkce"]))
        if key in seen_keys:
            continue
        final_records.append(record)
        seen_keys.add(key)
        if len(final_records) >= TARGET_RECORD_COUNT:
            break

    counters["final_record_count"] = len(final_records)
    counters["general_records_used"] = max(0, len(final_records) - len(ordered_domain))
    return final_records, counters


def write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "almanca",
        "artikel",
        "turkce",
        "kategoriler",
        "aciklama_turkce",
        "ilgili_kayitlar",
        "tur",
        "ornek_almanca",
        "ornek_turkce",
        "ornekler_json",
        "kaynak",
        "kaynak_url",
        "ceviri_durumu",
        "ceviri_inceleme_notu",
        "ceviri_kaynaklari_json",
        "not",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            payload = {key: row.get(key, "") for key in fieldnames}
            if isinstance(payload.get("kategoriler"), list):
                payload["kategoriler"] = " ; ".join(payload["kategoriler"])
            if isinstance(payload.get("ilgili_kayitlar"), list):
                payload["ilgili_kayitlar"] = " ; ".join(payload["ilgili_kayitlar"])
            payload["ornekler_json"] = json.dumps(row.get("ornekler", []), ensure_ascii=False)
            payload["ceviri_kaynaklari_json"] = json.dumps(row.get("ceviri_kaynaklari", []), ensure_ascii=False)
            writer.writerow(payload)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            payload = {
                "almanca": row["almanca"],
                "artikel": row["artikel"],
                "turkce": row["turkce"],
                "kategoriler": row.get("kategoriler", []),
                "aciklama_turkce": row.get("aciklama_turkce", ""),
                "ilgili_kayitlar": row.get("ilgili_kayitlar", []),
                "tur": row["tur"],
                "ornek_almanca": row["ornek_almanca"],
                "ornek_turkce": row["ornek_turkce"],
                "ornekler": row.get("ornekler", []),
                "kaynak": row["kaynak"],
                "kaynak_url": row.get("kaynak_url", ""),
                "ceviri_durumu": row.get("ceviri_durumu", ""),
                "ceviri_inceleme_notu": row.get("ceviri_inceleme_notu", ""),
                "ceviri_kaynaklari": row.get("ceviri_kaynaklari", []),
                "not": row["not"],
            }
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_json(path: Path, rows: list[dict]) -> None:
    payload = [
        {
            "almanca": row["almanca"],
            "artikel": row["artikel"],
            "turkce": row["turkce"],
            "kategoriler": row.get("kategoriler", []),
            "aciklama_turkce": row.get("aciklama_turkce", ""),
            "ilgili_kayitlar": row.get("ilgili_kayitlar", []),
            "tur": row["tur"],
            "ornek_almanca": row["ornek_almanca"],
            "ornek_turkce": row["ornek_turkce"],
            "ornekler": row.get("ornekler", []),
            "kaynak": row["kaynak"],
            "kaynak_url": row.get("kaynak_url", ""),
            "ceviri_durumu": row.get("ceviri_durumu", ""),
            "ceviri_inceleme_notu": row.get("ceviri_inceleme_notu", ""),
            "ceviri_kaynaklari": row.get("ceviri_kaynaklari", []),
            "not": row["not"],
        }
        for row in rows
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_summary(path: Path, rows: list[dict], build_counters: Counter, seed_map: dict[str, SeedInfo]) -> None:
    source_counter = Counter()
    pos_counter = Counter()
    category_counter = Counter()
    review_counter = Counter()
    autoish_count = 0
    for row in rows:
        for source_name in row["source_names"]:
            source_counter[source_name] += 1
        pos_counter[canonicalize_pos_label(row["tur"])] += 1
        for category in row.get("kategoriler", []):
            category_counter[category] += 1
        review_counter[row.get("ceviri_durumu", "kaynak-izli")] += 1
        if row.get("autoish"):
            autoish_count += 1

    summary = {
        "record_count": len(rows),
        "seed_term_count": count_unique_seeds(seed_map),
        "autoish_record_count": autoish_count,
        "sources": source_counter,
        "parts_of_speech": pos_counter,
        "categories": category_counter,
        "translation_reviews": review_counter,
        "build_counters": build_counters,
    }
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def write_summary_markdown(path: Path, rows: list[dict], build_counters: Counter) -> None:
    source_counter = Counter()
    for row in rows:
        for source_name in row["source_names"]:
            source_counter[source_name] += 1

    lines = [
        "# Kaynak Ozeti",
        "",
        f"Toplam kayit: `{len(rows)}`",
        "",
        "Acik kaynak katkisinin kayit bazli ozeti:",
        "",
        "| Kaynak | Kayda katkisi |",
        "| --- | ---: |",
    ]

    for source_name, count in source_counter.most_common():
        lines.append(f"| {source_name} | {count} |")

    lines.extend(
        [
            "",
            "Not:",
            "",
            f"- Bu sayilar toplandiginda `{len(rows)}` etmez; cunku tek bir kayit birden fazla kaynaga dayanabilir.",
            f"- Otomotiv ve teknik alan kayitlari (manuel kaynaklar dahil): `{build_counters['domain_record_count']}`",
        ]
    )
    for key, count in sorted(build_counters.items()):
        if key.startswith("manual_") and key.endswith("_records"):
            source_label = key[len("manual_") : -len("_records")].replace("_", "-")
            lines.append(f"- {source_label} uzerinden manuel eklenen kayit sayisi: `{count}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    seed_map = load_seed_map()
    unique_seed_total = count_unique_seeds(seed_map)
    manual_records, manual_counters = load_manual_records()
    wikdict_index = load_wikdict_index()
    tr_domain_records, tr_general_records, tr_counters = parse_trwiktionary(seed_map, wikdict_index)
    de_domain_records, de_general_records, de_counters = parse_dewiktionary(seed_map)
    combined_domain_records = merge_records(tr_domain_records + de_domain_records + manual_records)
    combined_general_records = merge_records(tr_general_records + de_general_records)
    filtered_domain_records, domain_filter_counters = filter_low_value_records(combined_domain_records)
    filtered_general_records, general_filter_counters = filter_low_value_records(combined_general_records)
    filtered_domain_records, domain_form_gloss_counters = clean_form_gloss_records(filtered_domain_records)
    filtered_general_records, general_form_gloss_counters = clean_form_gloss_records(filtered_general_records)
    wikdict_fallbacks, fallback_counters = build_wikdict_seed_fallbacks(
        seed_map,
        wikdict_index,
        filtered_domain_records,
    )
    final_records, final_counters = finalize_records(
        filtered_domain_records,
        filtered_general_records,
        wikdict_fallbacks,
    )
    final_records = annotate_abbreviations(final_records)
    final_records = link_related_terms(final_records)
    final_records = apply_translation_reviews(final_records)
    final_records = polish_turkish_fields(final_records)
    final_records = annotate_categories(final_records)
    final_records = apply_record_enrichments(final_records)

    build_counters = (
        tr_counters
        + de_counters
        + manual_counters
        + domain_filter_counters
        + general_filter_counters
        + domain_form_gloss_counters
        + general_form_gloss_counters
        + fallback_counters
        + final_counters
    )
    write_csv(OUTPUT_DIR / "dictionary.csv", final_records)
    write_jsonl(OUTPUT_DIR / "dictionary.jsonl", final_records)
    write_json(OUTPUT_DIR / "dictionary.json", final_records)
    write_summary(OUTPUT_DIR / "source_summary.json", final_records, build_counters, seed_map)
    write_summary_markdown(OUTPUT_DIR / "source_summary.md", final_records, build_counters)
    build_definition_index()

    unmatched_seed_count = len(seed_map) - len(
        {normalize_key(row["almanca"]) for row in final_records if row["seed_match"]}
    )
    interim_stats = {
        "seed_term_count": unique_seed_total,
        "domain_records_before_fill": len(filtered_domain_records) + len(wikdict_fallbacks),
        "general_records_available": len(filtered_general_records),
        "unmatched_seed_count": unmatched_seed_count,
    }
    (INTERIM_DIR / "build_stats.json").write_text(
        json.dumps(interim_stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "record_count": len(final_records),
                "seed_term_count": unique_seed_total,
                "domain_records": len(filtered_domain_records),
                "wikdict_fallbacks": len(wikdict_fallbacks),
                "general_records_used": final_counters["general_records_used"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
