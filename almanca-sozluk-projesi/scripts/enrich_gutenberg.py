#!/usr/bin/env python3
"""
enrich_gutenberg.py
===================
Project Gutenberg'deki Almanca eserlerden sözlüğü zenginleştirir.

  1. YENİ KELİMELER: Almanca edebi metinlerden WikDict çevirisi olan kelimeleri ekler.
  2. MEVCUT KAYITLARI ZENGİNLEŞTİR:
     - Edebi metinlerden örnek cümleler ekler (ornek_almanca boşsa).
     - WikDict'teki yeni Türkçe anlamları ekler.
  3. Gutendex API ile ek kitap keşfi yapar (sayfa sayfa).

Kaynak: Project Gutenberg (Kamu Malı), WikDict de-tr veritabanı
Çalıştır: python scripts/enrich_gutenberg.py
"""

import json
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.parse as _up
import urllib.request as _ur
from collections import Counter
from pathlib import Path

try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from grammar_utils import (
        classify_verb_type,
        detect_verb_type_from_text,
        detect_article_from_context,
        lemmatize_verb,
        lemmatize_adjective,
        lemmatize_noun,
        guess_pos as _guess_pos_advanced,
        translation_quality_score,
        is_trennbar,
        enrich_record_grammar,
    )
    _GRAMMAR_UTILS_AVAILABLE = True
except ImportError:
    _GRAMMAR_UTILS_AVAILABLE = False

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent

DICT_PATHS = [
    PROJECT_ROOT / "output" / "dictionary.json",
]
WIKDICT_PATH = PROJECT_ROOT / "data" / "raw" / "downloads" / "de-tr.sqlite3"

# ---------------------------------------------------------------------------
# Gutendex API — Almanca kitap keşfi
# ---------------------------------------------------------------------------
GUTENDEX_API = "https://gutendex.com/books/?languages=de&mime_type=text%2Fplain"

# ---------------------------------------------------------------------------
# Bilinen Almanca klasikler — (id, başlık, yazar)
# Büyük koleksiyon, ~120+ eser
# ---------------------------------------------------------------------------
CURATED_BOOKS = [
    # ===== GOETHE =====
    (2229,  "Faust - Der Tragödie erster Teil", "Goethe"),
    (6031,  "Faust - Der Tragödie zweiter Teil", "Goethe"),
    (2407,  "Die Leiden des jungen Werthers", "Goethe"),
    (2054,  "Iphigenie auf Tauris", "Goethe"),
    (2070,  "Egmont", "Goethe"),
    (2226,  "Die Wahlverwandtschaften", "Goethe"),
    (2408,  "Götz von Berlichingen", "Goethe"),
    (2438,  "Torquato Tasso", "Goethe"),
    (2071,  "Hermann und Dorothea", "Goethe"),
    (42683, "Wilhelm Meisters Lehrjahre", "Goethe"),
    (2073,  "Reineke Fuchs", "Goethe"),

    # ===== SCHILLER =====
    (6789,  "Die Räuber", "Schiller"),
    (6788,  "Wilhelm Tell", "Schiller"),
    (2817,  "Kabale und Liebe", "Schiller"),
    (6962,  "Don Carlos", "Schiller"),
    (6790,  "Maria Stuart", "Schiller"),
    (6791,  "Die Jungfrau von Orleans", "Schiller"),
    (6792,  "Die Braut von Messina", "Schiller"),
    (2078,  "Wallenstein - Wallensteins Lager", "Schiller"),
    (2079,  "Wallenstein - Die Piccolomini", "Schiller"),
    (2080,  "Wallenstein - Wallensteins Tod", "Schiller"),
    (6793,  "Über die ästhetische Erziehung des Menschen", "Schiller"),

    # ===== LESSING =====
    (2490,  "Nathan der Weise", "Lessing"),
    (2489,  "Emilia Galotti", "Lessing"),
    (6787,  "Minna von Barnhelm", "Lessing"),
    (2491,  "Laokoon", "Lessing"),
    (6786,  "Hamburgische Dramaturgie", "Lessing"),

    # ===== KLEIST =====
    (2182,  "Der zerbrochne Krug", "Kleist"),
    (2183,  "Penthesilea", "Kleist"),
    (2181,  "Das Käthchen von Heilbronn", "Kleist"),
    (2184,  "Prinz Friedrich von Homburg", "Kleist"),
    (2185,  "Michael Kohlhaas", "Kleist"),
    (2186,  "Die Marquise von O", "Kleist"),
    (22365, "Das Erdbeben in Chili", "Kleist"),

    # ===== E.T.A. HOFFMANN =====
    (4683,  "Der Sandmann", "Hoffmann"),
    (22374, "Das Fräulein von Scuderi", "Hoffmann"),
    (22376, "Das öde Haus", "Hoffmann"),
    (22377, "Die Elixiere des Teufels", "Hoffmann"),
    (22379, "Meister Floh", "Hoffmann"),
    (4682,  "Lebens-Ansichten des Katers Murr", "Hoffmann"),

    # ===== KAFKA =====
    (22367, "Die Verwandlung", "Kafka"),
    (7849,  "Der Proceß", "Kafka"),
    (18066, "Das Schloß", "Kafka"),
    (11981, "In der Strafkolonie", "Kafka"),
    (36498, "Ein Landarzt", "Kafka"),
    (36499, "Das Urteil", "Kafka"),
    (36500, "Betrachtung", "Kafka"),

    # ===== THEODOR STORM =====
    (6993,  "Immensee", "Storm"),
    (44790, "Der Schimmelreiter", "Storm"),
    (30795, "Aquis submersus", "Storm"),
    (44791, "Hans und Heinz Kirch", "Storm"),
    (22384, "Ein Doppelgänger", "Storm"),
    (44792, "Carsten Curator", "Storm"),
    (44793, "Der Herr Etatsrat", "Storm"),

    # ===== THEODOR FONTANE =====
    (5765,  "Effi Briest", "Fontane"),
    (22413, "Irrungen, Wirrungen", "Fontane"),
    (22414, "Frau Jenny Treibel", "Fontane"),
    (44800, "Der Stechlin", "Fontane"),
    (22415, "Schach von Wuthenow", "Fontane"),
    (22416, "Cécile", "Fontane"),
    (22417, "Unwiederbringlich", "Fontane"),
    (22418, "Mathilde Möhring", "Fontane"),

    # ===== GOTTFRIED KELLER =====
    (2495,  "Der grüne Heinrich", "Keller"),
    (22387, "Romeo und Julia auf dem Dorfe", "Keller"),
    (22388, "Die Leute von Seldwyla", "Keller"),
    (22389, "Das Sinngedicht", "Keller"),
    (22390, "Martin Salander", "Keller"),

    # ===== ADALBERT STIFTER =====
    (22395, "Bunte Steine", "Stifter"),
    (22396, "Nachsommer", "Stifter"),
    (22397, "Witiko", "Stifter"),
    (22398, "Studien", "Stifter"),

    # ===== ARTHUR SCHNITZLER =====
    (29960, "Leutnant Gustl", "Schnitzler"),
    (22402, "Traumnovelle", "Schnitzler"),
    (22403, "Reigen", "Schnitzler"),
    (22404, "Der Weg ins Freie", "Schnitzler"),
    (22405, "Anatol", "Schnitzler"),

    # ===== STEFAN ZWEIG =====
    (22420, "Schachnovelle", "Zweig"),
    (22421, "Amok", "Zweig"),
    (22422, "Brief einer Unbekannten", "Zweig"),
    (22423, "Die Welt von Gestern", "Zweig"),
    (22424, "Sternstunden der Menschheit", "Zweig"),

    # ===== HESSE (frühe Werke) =====
    (2500,  "Siddhartha", "Hesse"),
    (24583, "Demian", "Hesse"),
    (22375, "Peter Camenzind", "Hesse"),
    (22372, "Unterm Rad", "Hesse"),
    (22373, "Gertrud", "Hesse"),
    (22406, "Knulp", "Hesse"),
    (22407, "Rosshalde", "Hesse"),

    # ===== RILKE =====
    (22399, "Die Aufzeichnungen des Malte Laurids Brigge", "Rilke"),
    (2188,  "Das Stunden-Buch", "Rilke"),
    (2189,  "Das Buch der Bilder", "Rilke"),
    (22400, "Duineser Elegien", "Rilke"),

    # ===== BRECHT (frühe Werke) =====
    (22425, "Baal", "Brecht"),
    (22426, "Im Dickicht der Städte", "Brecht"),
    (22427, "Trommeln in der Nacht", "Brecht"),

    # ===== GRIMM =====
    (5765,  "Kinder- und Hausmärchen Bd.1", "Grimm"),
    (2591,  "Kinder- und Hausmärchen Bd.1 (alt)", "Grimm"),
    (5774,  "Deutsche Sagen", "Grimm"),
    (22426, "Märchen", "Grimm"),

    # ===== FELSEFİ & BİLİMSEL METİNLER =====
    (7205,  "Also sprach Zarathustra", "Nietzsche"),
    (4280,  "Kritik der reinen Vernunft", "Kant"),
    (2439,  "Die Welt als Wille und Vorstellung", "Schopenhauer"),
    (37269, "Jenseits von Gut und Böse", "Nietzsche"),
    (1998,  "Zur Genealogie der Moral", "Nietzsche"),
    (30759, "Kritik der praktischen Vernunft", "Kant"),
    (47419, "Grundlegung zur Metaphysik der Sitten", "Kant"),
    (2018,  "Phänomenologie des Geistes", "Hegel"),
    (4534,  "Der Ursprung der Arten", "Darwin (dt.)"),
    (6129,  "Dialektik der Aufklärung", "Adorno"),

    # ===== TARİHSEL METİNLER =====
    (2081,  "Geschichte des Dreißigjährigen Krieges", "Schiller"),
    (2082,  "Geschichte des Abfalls der vereinigten Niederlande", "Schiller"),
    (22410, "Deutsche Geschichte im Mittelalter", "Ranke"),

    # ===== BILIM KURGU & MACEREYazarları =====
    (22380, "Der Tunnel", "Kellermann"),
    (22381, "Die Stadt", "Hegeler"),

    # ===== KISA HİKAYE / NOVELLE =====
    (22385, "Novellen und Erzählungen", "Storm"),
    (22386, "Aus dem Leben eines Taugenichts", "Eichendorff"),
    (22391, "Das Wirtshaus im Spessart", "Hauff"),
    (22392, "Lichtenstein", "Hauff"),
    (22393, "Der Mann im Mond", "Hauff"),

    # ===== WIELAND =====
    (22394, "Geschichte des Agathon", "Wieland"),
    (22410, "Oberon", "Wieland"),

    # ===== KLASİK ALMAN ROMANI =====
    (22411, "Der Hungerpastor", "Raabe"),
    (22412, "Abu Telfan", "Raabe"),
    (22419, "Stopfkuchen", "Raabe"),
    (22408, "Soll und Haben", "Freytag"),
    (22409, "Die Ahnen", "Freytag"),
]

# Gutenberg URL kalıpları
def gutenberg_urls(book_id: int) -> list:
    """Bir kitap için olası metin URL'lerini döndür."""
    return [
        f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt",
        f"https://www.gutenberg.org/files/{book_id}/{book_id}-0.txt",
        f"https://www.gutenberg.org/files/{book_id}/{book_id}.txt",
        f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}-0.txt",
    ]

# ---------------------------------------------------------------------------
# Stopword kümesi — enrich_quality.py ile aynı + edebi kelimeler
# ---------------------------------------------------------------------------
_RAW_STOPWORDS = {
    "aber", "alle", "allem", "allen", "aller", "alles", "als", "also",
    "am", "an", "auch", "auf", "aus", "bei", "beim", "bin", "bis",
    "bist", "da", "dabei", "damit", "danach", "dann", "das", "dass",
    "dein", "deine", "dem", "den", "denn", "der", "des", "dessen",
    "deshalb", "die", "dies", "diese", "dieser", "dieses", "doch",
    "dort", "du", "durch", "ein", "eine", "einem", "einen", "einer",
    "eines", "er", "es", "etwas", "euch", "euer", "eure", "für",
    "gegen", "gewesen", "hab", "habe", "haben", "hat", "hatte",
    "hattest", "hier", "hin", "hinter", "ich", "ihr", "ihre", "im",
    "in", "indem", "ins", "ist", "jede", "jeder", "jedes", "jetzt",
    "kann", "kannst", "kein", "keine", "mit", "muss", "musst", "nach",
    "neben", "nicht", "noch", "nun", "oder", "ohne", "sehr", "sein",
    "seine", "sich", "sie", "sind", "so", "solche", "soll", "sollte",
    "sondern", "sonst", "über", "um", "und", "uns", "unter", "vom",
    "von", "vor", "war", "waren", "warst", "was", "weg", "weil",
    "weiter", "welche", "welcher", "wenn", "wer", "werde", "werden",
    "wie", "wieder", "wir", "wird", "wirst", "wo", "wurde", "wurden",
    "zu", "zum", "zur", "zwar", "zwischen",
    # Edebi / anlatı metinlerine özgü fazladan stopwordler
    "sagte", "sprach", "fragte", "rief", "antwortete", "flüsterte",
    "lachte", "weinte", "dachte", "glaubte", "schien", "wurde",
    "hatte", "nahm", "ging", "kam", "stand", "sah", "hörte",
    "wollte", "konnte", "sollte", "durfte", "mochte",
    "fort", "zurück", "heraus", "hinaus", "herein", "hinein",
    "oben", "unten", "links", "rechts", "vorn", "hinten",
    "heute", "gestern", "morgen", "abend", "nacht",
    "herr", "frau", "fräulein", "doktor",
    # Modal/aux
    "können", "konnte", "konnten", "müssen", "musste", "mussten",
    "sollen", "sollten", "wollen", "wollten", "dürfen", "durften",
    "mögen", "mochten",
    # sein/haben çekimleri
    "seid", "wäre", "wären", "sei", "habt", "hatten", "hätte",
    "hätten", "gehabt", "würde", "würden", "geworden",
    # Çok genel isimler
    "jahr", "jahre", "jahren", "zeit", "zeiten", "teil", "teile",
    "form", "typ", "art", "arten", "fall", "fälle", "punkt", "punkte",
    "zahl", "zahlen", "ende", "anfang", "bereich", "grund",
    "beispiel", "frage", "fragen", "antwort", "möglichkeit",
    "mensch", "menschen", "land", "länder", "stadt", "städte",
    "welt", "leben", "weise", "stelle", "seite",
    "mann", "frau", "kind", "kinder", "vater", "mutter",
    "haus", "tür", "hand", "kopf", "auge", "augen",
    # Aylar & Günler
    "januar", "februar", "märz", "april", "mai", "juni", "juli",
    "august", "september", "oktober", "november", "dezember",
    "montag", "dienstag", "mittwoch", "donnerstag",
    "freitag", "samstag", "sonntag",
    # Edatlar & bağlaçlar
    "obwohl", "während", "bevor", "nachdem", "sobald", "solange",
    "falls", "sofern", "gegenüber", "innerhalb", "außerhalb",
    "anstatt", "aufgrund", "mithilfe", "bezüglich", "laut", "gemäß",
    "entsprechend", "seit", "statt", "samt", "wobei", "sowie",
    "insgesamt", "insbesondere", "demnach", "demzufolge", "somit",
    "folglich", "hingegen", "vielmehr", "nämlich", "schließlich",
    "letztlich", "tatsächlich", "eigentlich", "offenbar",
    "wahrscheinlich", "jedenfalls", "ohnehin", "sowieso",
    # Kısaltmalar
    "usw", "bzw", "evtl", "ggf", "inkl", "exkl", "bspw", "vgl",
    # İngilizce (bazı eski kitaplarda olabilir)
    "the", "and", "for", "that", "this", "with", "from",
}
GERMAN_STOPWORDS_CF: frozenset = frozenset(s.casefold() for s in _RAW_STOPWORDS)

_PROPER_NOUNS_CF: frozenset = frozenset({
    "berlin", "münchen", "hamburg", "köln", "frankfurt", "stuttgart",
    "düsseldorf", "dortmund", "essen", "leipzig", "bremen", "dresden",
    "hannover", "nürnberg", "duisburg", "bochum", "wuppertal", "bonn",
    "mannheim", "karlsruhe", "freiburg", "augsburg", "wiesbaden",
    "deutschland", "österreich", "schweiz", "europa", "brüssel",
    "paris", "london", "washington", "peking", "tokio", "moskau",
    "preußen", "sachsen", "bayern", "schwaben", "österreich",
    "rhein", "elbe", "donau", "main", "oder",
    # Yaygın Alman isimleri
    "müller", "schmidt", "schneider", "fischer", "weber", "meyer",
    "wagner", "becker", "schulz", "hoffmann", "schäfer", "koch",
    "bauer", "richter", "wolf", "schröder", "neumann",
    "schwarz", "zimmermann", "braun", "krüger", "hartmann", "lange",
    "werner", "lehmann", "walter", "maier", "mayer", "köhler",
    "krause", "steiner", "jung", "roth", "vogel",
    "friedrich", "johannes", "wilhelm", "wolfgang", "heinrich",
    "thomas", "michael", "stefan", "andreas", "christian",
    "markus", "matthias", "sebastian", "tobias", "alexander",
    "christoph", "samuel", "peter", "hans", "otto", "karl",
    "faust", "mephisto", "margarete", "gretchen", "werther",
    "hamlet", "ophelia", "romeo", "julia",
    "gottfried", "adalbert", "theodor", "arthur", "stefan",
    "goethe", "schiller", "kafka", "hesse", "fontane", "storm",
    "rilke", "kleist", "hoffmann", "nietzsche", "kant", "hegel",
    "grimm", "keller", "stifter", "zweig", "schnitzler",
})

# ---------------------------------------------------------------------------
# Token regex
# ---------------------------------------------------------------------------
TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß]{3,}(?:-[A-Za-zÄÖÜäöüß]{2,})*")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])")

# ---------------------------------------------------------------------------
# Gutenberg başlık/bitiş temizleyici
# ---------------------------------------------------------------------------
GUTENBERG_START_MARKERS = [
    "*** START OF THE PROJECT GUTENBERG EBOOK",
    "*** START OF THIS PROJECT GUTENBERG EBOOK",
    "***START OF THE PROJECT GUTENBERG EBOOK",
    "*END*THE SMALL PRINT",
    "Ende der kleinen Druckausgabe",
]
GUTENBERG_END_MARKERS = [
    "*** END OF THE PROJECT GUTENBERG EBOOK",
    "*** END OF THIS PROJECT GUTENBERG EBOOK",
    "***END OF THE PROJECT GUTENBERG EBOOK",
    "End of the Project Gutenberg EBook",
    "End of Project Gutenberg",
]

def strip_gutenberg_boilerplate(text: str) -> str:
    """Gutenberg başlık ve bitiş boilerplate'ini kaldır."""
    start_pos = 0
    for marker in GUTENBERG_START_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            # Marker'dan sonraki satır başına git
            line_end = text.find("\n", idx)
            if line_end != -1:
                start_pos = line_end + 1
            break

    end_pos = len(text)
    for marker in GUTENBERG_END_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            end_pos = idx
            break

    return text[start_pos:end_pos].strip()


# ---------------------------------------------------------------------------
# Normalleştirme yardımcıları
# ---------------------------------------------------------------------------
def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)

def cf(s: str) -> str:
    return nfc(s).strip().casefold()

def strip_article(term: str) -> str:
    for art in ("der ", "die ", "das ", "Der ", "Die ", "Das "):
        if term.startswith(art):
            return term[len(art):]
    return term

def is_stopword(token: str) -> bool:
    return cf(token) in GERMAN_STOPWORDS_CF or cf(strip_article(token)) in GERMAN_STOPWORDS_CF

def is_proper_noun(token: str) -> bool:
    return cf(token) in _PROPER_NOUNS_CF


# ---------------------------------------------------------------------------
# WikDict çeviri arama
# ---------------------------------------------------------------------------
def lookup_translation(term: str, cursor) -> dict:
    if cursor is None:
        return {"translation": "", "written_rep": ""}

    lower = cf(strip_article(term))
    lookup_terms = [term.strip(), lower]

    for suffix, replacement in [
        ("iert", "ieren"), ("test", "en"), ("tet", "en"),
        ("st", "en"), ("te", "en"),
    ]:
        if lower.endswith(suffix) and len(lower) > len(suffix) + 2:
            lookup_terms.append(lower[: -len(suffix)] + replacement)

    if lower.endswith("en") and len(lower) >= 6:
        lookup_terms.append(lower[:-2])
    if lower.endswith("es") and len(lower) >= 6:
        lookup_terms.append(lower[:-2])
    if lower.endswith("e") and len(lower) >= 5:
        lookup_terms.append(lower[:-1])
    if lower.endswith("s") and not lower.endswith("ss") and len(lower) >= 5:
        lookup_terms.append(lower[:-1])
    if lower.endswith("t") and len(lower) >= 6:
        root = lower[:-1]
        if not root.endswith(("ig", "lich", "isch", "bar", "sam", "haft", "voll", "los")):
            lookup_terms.append(root + "en")

    seen: set = set()
    for lt in lookup_terms:
        nlt = cf(lt)
        if not nlt or nlt in seen:
            continue
        seen.add(nlt)
        row = cursor.execute(
            """
            SELECT written_rep, trans_list
            FROM simple_translation
            WHERE lower(written_rep) = lower(?)
            ORDER BY rel_importance DESC, max_score DESC
            LIMIT 1
            """,
            (lt,),
        ).fetchone()
        if row:
            translations = []
            seen_tr: set = set()
            for part in str(row[1] or "").split("|"):
                cleaned = part.strip()
                key = cf(cleaned)
                if not cleaned or key in seen_tr or len(cleaned) < 2:
                    continue
                seen_tr.add(key)
                translations.append(cleaned)
            return {
                "translation": ", ".join(translations[:4]),
                "written_rep": str(row[0] or ""),
            }
    return {"translation": "", "written_rep": ""}


# ---------------------------------------------------------------------------
# POS tahmini
# ---------------------------------------------------------------------------
def guess_pos(token: str, text_context: str = "") -> str:
    if _GRAMMAR_UTILS_AVAILABLE:
        return _guess_pos_advanced(token, text_context)
    base = strip_article(token)
    if token[:1].isupper() and " " not in base:
        return "isim"
    base_l = base.lower()
    if base_l.endswith(("en", "ern", "eln")):
        return "fiil"
    if base_l.endswith(("lich", "isch", "ig", "bar", "sam", "haft", "los", "voll")):
        return "sıfat"
    return "isim"


# ---------------------------------------------------------------------------
# Referans linkleri
# ---------------------------------------------------------------------------
def build_ref_links(almanca: str) -> dict:
    word = strip_article(almanca)
    enc = _up.quote(word)
    return {
        "duden": f"https://www.duden.de/suchen/dudenonline/{enc}",
        "dwds": f"https://www.dwds.de/wb/{enc}",
        "wiktionary_de": f"https://de.wiktionary.org/wiki/{enc}",
    }


# ---------------------------------------------------------------------------
# Cümle çıkarma
# ---------------------------------------------------------------------------
def split_sentences(text: str) -> list:
    raw = SENT_SPLIT_RE.split(text)
    sentences = []
    for chunk in raw:
        for line in chunk.split("\n"):
            line = line.strip()
            if line:
                sentences.append(line)
    return sentences


def find_example_sentence(sentences: list, bare_word: str) -> str:
    bare_cf = bare_word.casefold()
    good = []
    for sent in sentences:
        sent = sent.strip()
        if bare_cf not in sent.casefold():
            continue
        if not (40 <= len(sent) <= 260):
            continue
        if sent.count("[") + sent.count("{") + sent.count("(") > 3:
            continue
        digit_ratio = sum(1 for c in sent if c.isdigit()) / max(len(sent), 1)
        if digit_ratio > 0.15:
            continue
        # Edebi cümlelerde tırnak işaretleri kabul edilebilir
        good.append(sent)

    if not good:
        return ""
    good.sort(key=len)
    for sent in good:
        if len(TOKEN_RE.findall(sent)) >= 4:
            return sent
    return good[0] if good else ""


# ---------------------------------------------------------------------------
# Yeni anlam tespiti
# ---------------------------------------------------------------------------
def find_new_meanings(existing_turkce: str, wikdict_translation: str) -> list:
    if not wikdict_translation:
        return []

    existing_parts: set = set()
    for part in re.split(r"[;,|/]", existing_turkce or ""):
        p = part.strip().casefold()
        if p and len(p) > 1:
            existing_parts.add(p)
        for word in p.split():
            if len(word) > 2:
                existing_parts.add(word)

    new_meanings = []
    for tr in wikdict_translation.split(", "):
        tr = tr.strip()
        if not tr or len(tr) < 2:
            continue
        tr_cf = tr.casefold()
        if tr_cf in existing_parts:
            continue
        tr_words = set(w for w in tr_cf.split() if len(w) > 2)
        if tr_words and tr_words.issubset(existing_parts):
            continue
        if tr[:1].isupper() and len(tr) > 3:
            continue
        new_meanings.append(tr)

    return new_meanings[:3]


# ---------------------------------------------------------------------------
# Sözlük yükleme / kaydetme
# ---------------------------------------------------------------------------
def load_dictionary() -> list:
    for p in DICT_PATHS:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return []


def save_dictionary(records: list) -> None:
    for p in DICT_PATHS:
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            print(f"  Kaydedildi: {p}")
        except Exception as e:
            print(f"  [HATA] {p}: {e}", file=sys.stderr)


def build_existing_keys(records: list) -> set:
    keys: set = set()
    for r in records:
        almanca = (r.get("almanca", "") or "").strip()
        keys.add(cf(almanca))
        keys.add(cf(strip_article(almanca)))
    return keys


def build_record_index(records: list) -> dict:
    idx: dict = {}
    for i, r in enumerate(records):
        almanca = (r.get("almanca", "") or "").strip()
        if almanca:
            idx[cf(almanca)] = i
            idx[cf(strip_article(almanca))] = i
    return idx


# ---------------------------------------------------------------------------
# Kitap metni indir
# ---------------------------------------------------------------------------
def fetch_book_text(book_id: int, title: str) -> str:
    """Gutenberg'den kitap metnini indir (birden fazla URL kalıbı dene)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AlmancaSozluk/1.0; educational use)",
        "Accept": "text/plain; charset=utf-8",
    }
    urls = gutenberg_urls(book_id)
    for url in urls:
        try:
            req = _ur.Request(url, headers=headers)
            with _ur.urlopen(req, timeout=30) as r:
                raw = r.read()
                # Encoding tespiti
                charset = r.headers.get_content_charset() or "utf-8"
                # Gutenberg genellikle UTF-8 veya ISO-8859-1
                try:
                    text = raw.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    try:
                        text = raw.decode("utf-8", errors="replace")
                    except Exception:
                        text = raw.decode("latin-1", errors="replace")
                if len(text) > 1000:
                    return text
        except Exception as e:
            continue
    return ""


# ---------------------------------------------------------------------------
# Gutendex API ile ek kitap keşfi
# ---------------------------------------------------------------------------
def fetch_gutendex_books(max_pages: int = 5) -> list:
    """Gutendex API'den Almanca kitapların (id, title) listesini çek."""
    books = []
    url = GUTENDEX_API
    page = 0
    while url and page < max_pages:
        try:
            req = _ur.Request(url, headers={"User-Agent": "AlmancaSozluk/1.0"})
            with _ur.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            for book in data.get("results", []):
                book_id = book.get("id")
                title = book.get("title", "")
                authors = book.get("authors", [])
                author = authors[0].get("name", "") if authors else ""
                if book_id and title:
                    books.append((book_id, title, author))
            url = data.get("next", "")
            page += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"  [Gutendex HATA]: {e}", file=sys.stderr)
            break
    return books


# ---------------------------------------------------------------------------
# Yeni aday çıkarma
# ---------------------------------------------------------------------------
def extract_candidates(
    text: str,
    existing_keys: set,
    cursor,
    source_label: str,
    min_freq: int = 2,
) -> list:
    if not text:
        return []

    counts: Counter = Counter()
    labels: dict = {}
    lowercase_seen: set = set()

    for token in TOKEN_RE.findall(text):
        if token[:1].islower():
            lowercase_seen.add(cf(token))

    for token in TOKEN_RE.findall(text):
        norm = cf(token)
        if not norm or len(norm) < 4 or len(norm) > 40:
            continue
        if is_stopword(token):
            continue
        if is_proper_noun(token):
            continue
        if norm in existing_keys:
            continue
        counts[norm] += 1
        cur = labels.get(norm)
        if cur is None or (token[:1].isupper() and not cur[:1].isupper()):
            labels[norm] = token

    candidates = []
    for norm, freq in counts.most_common(500):
        if freq < min_freq:
            continue
        german = labels.get(norm, norm)
        sug = lookup_translation(german, cursor)

        if not sug["translation"]:
            continue
        if len(sug["translation"].strip()) < 2:
            continue

        wr_key = cf(sug.get("written_rep", ""))
        if wr_key and wr_key != norm and wr_key in existing_keys:
            continue

        for suffix in ("es", "en", "er", "em"):
            if german.endswith(suffix):
                base_try = german[: -len(suffix)]
                if cf(base_try) in existing_keys:
                    sug["translation"] = ""
                    break
        if not sug["translation"]:
            continue

        candidates.append({
            "almanca": german,
            "turkce": sug["translation"],
            "pos": guess_pos(german),
            "freq": freq,
            "written_rep": sug["written_rep"],
        })

    return candidates


# ---------------------------------------------------------------------------
# Mevcut kayıt güncellemeleri
# ---------------------------------------------------------------------------
def find_updates(
    text: str,
    sentences: list,
    records: list,
    record_index: dict,
    cursor,
    processed_indices: set,
) -> list:
    results = []
    seen_in_text: set = set()

    for token in TOKEN_RE.findall(text):
        norm = cf(token)
        bare = cf(strip_article(token))

        idx = record_index.get(norm) or record_index.get(bare)
        if idx is None:
            continue
        if idx in processed_indices or idx in seen_in_text:
            continue
        seen_in_text.add(idx)

        record = records[idx]
        almanca = record.get("almanca", "") or ""
        bare_word = strip_article(almanca)

        example = ""
        existing_example = record.get("ornek_almanca", "") or ""
        if not existing_example:
            example = find_example_sentence(sentences, bare_word)

        new_meanings: list = []
        wikdict_result = lookup_translation(almanca, cursor)
        if wikdict_result["translation"]:
            new_meanings = find_new_meanings(
                record.get("turkce", "") or "",
                wikdict_result["translation"],
            )

        if example or new_meanings:
            results.append((idx, example, new_meanings))

    return results


# ---------------------------------------------------------------------------
# Aday → kayıt dönüştürme
# ---------------------------------------------------------------------------
def candidate_to_record(cand: dict, book_title: str, author: str, text: str = "") -> dict:
    almanca = cand["almanca"]
    artikel = ""
    wr = cand.get("written_rep", "")

    for art in ("der ", "die ", "das "):
        if wr.lower().startswith(art):
            artikel = art.strip()
            almanca = wr[len(art):]
            break

    if not artikel and text and _GRAMMAR_UTILS_AVAILABLE:
        detected = detect_article_from_context(almanca, text)
        if detected:
            artikel = detected

    pos = cand.get("pos", guess_pos(almanca))

    verb_typ = ""
    trennbar = ""
    if pos == "fiil" and _GRAMMAR_UTILS_AVAILABLE:
        verb_typ = classify_verb_type(almanca)
        if not verb_typ and text:
            verb_typ = detect_verb_type_from_text(almanca, text)
        if is_trennbar(almanca):
            trennbar = "trennbar"

    quality = 1.0
    if _GRAMMAR_UTILS_AVAILABLE:
        quality = translation_quality_score(cand["turkce"], almanca)

    rec: dict = {
        "almanca": almanca,
        "artikel": artikel,
        "turkce": cand["turkce"],
        "kategoriler": [],
        "aciklama_turkce": "",
        "ilgili_kayitlar": [],
        "tur": pos,
        "ornek_almanca": "",
        "ornek_turkce": "",
        "ornekler": [],
        "kaynak": f"WikDict; Project Gutenberg — {author}",
        "kaynak_url": f"https://kaikki.org/dewiktionary/rawdata.html; https://www.gutenberg.org",
        "ceviri_durumu": "kaynak-izli",
        "ceviri_inceleme_notu": "" if quality >= 0.6 else "çeviri kalitesi düşük — kontrol et",
        "ceviri_kaynaklari": [],
        "not": f"Gutenberg-import: {book_title} ({author})",
        "referans_linkler": build_ref_links(almanca),
        "seviye": "",
        "genitiv_endung": "",
        "kelime_ailesi": [],
    }
    if verb_typ:
        rec["verb_typ"] = verb_typ
    if trennbar:
        rec["trennbar"] = trennbar
    return rec


# ---------------------------------------------------------------------------
# Tek kitabı işle
# ---------------------------------------------------------------------------
def process_book(
    book_id: int,
    title: str,
    author: str,
    records: list,
    existing_keys: set,
    added_keys: set,
    record_index: dict,
    updated_indices: set,
    cursor,
    all_new: list,
) -> tuple:
    """Kitabı işle. (url_new, url_updated) döndür."""
    print(f"\n  Kitap #{book_id}: {title} ({author})")
    raw_text = fetch_book_text(book_id, title)
    if not raw_text:
        print(f"    [ATLA] İndirilemiyor.")
        return 0, 0

    text = strip_gutenberg_boilerplate(raw_text)
    char_count = len(text)
    print(f"    Metin: {char_count:,} karakter")

    if char_count < 2000:
        print(f"    [ATLA] Metin çok kısa.")
        return 0, 0

    # Aday kelimeler
    candidates = extract_candidates(
        text, added_keys, cursor,
        source_label=title, min_freq=2
    )
    url_new = 0
    for cand in candidates:
        norm = cf(cand["almanca"])
        norm_base = cf(strip_article(cand["almanca"]))
        if norm in added_keys or norm_base in added_keys:
            continue
        rec = candidate_to_record(cand, title, author, text=text)
        all_new.append(rec)
        added_keys.add(norm)
        added_keys.add(norm_base)
        url_new += 1
        verb_info = f" [{rec.get('verb_typ','')}]" if rec.get("verb_typ") else ""
        print(f"    + {rec['almanca']}{verb_info} → {rec['turkce']}")

    # Mevcut kayıt güncellemeleri
    sentences = split_sentences(text)
    updates = find_updates(
        text, sentences, records, record_index, cursor, updated_indices
    )

    url_updated = 0
    for rec_idx, example, new_meanings in updates:
        rec = records[rec_idx]
        changed = False

        if example and not (rec.get("ornek_almanca") or ""):
            rec["ornek_almanca"] = example
            if "ornekler" not in rec or not isinstance(rec["ornekler"], list):
                rec["ornekler"] = []
            rec["ornekler"].append({"almanca": example, "turkce": ""})
            changed = True
            print(f"    ~ {rec.get('almanca','?')}: örnek cümle (edebiyat)")

        if new_meanings:
            existing_tr = rec.get("turkce", "") or ""
            additions = "; ".join(new_meanings)
            rec["turkce"] = f"{existing_tr}; {additions}" if existing_tr else additions
            changed = True
            print(f"    ~ {rec.get('almanca','?')}: yeni anlam → {additions}")

        if _GRAMMAR_UTILS_AVAILABLE:
            before_artikel = rec.get("artikel", "")
            before_vt = rec.get("verb_typ", "")
            enrich_record_grammar(rec, text)
            if rec.get("artikel") != before_artikel and rec.get("artikel"):
                changed = True
            if rec.get("verb_typ") != before_vt and rec.get("verb_typ"):
                changed = True

        if changed:
            updated_indices.add(rec_idx)
            url_updated += 1

    print(f"    => {url_new} yeni kelime, {url_updated} kayıt güncellendi")
    return url_new, url_updated


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
def main() -> None:
    start_time = time.time()
    MAX_RUNTIME_SECONDS = 7200  # 120 dakika (2 saat)

    print("=" * 70)
    print("enrich_gutenberg.py — Project Gutenberg Zenginleştirme")
    print(f"Hedef çalışma süresi: {MAX_RUNTIME_SECONDS // 60} dakika")
    print("=" * 70)

    if WIKDICT_PATH.exists():
        conn = sqlite3.connect(str(WIKDICT_PATH))
        cursor = conn.cursor()
        print(f"WikDict: {WIKDICT_PATH}")
    else:
        conn = None
        cursor = None
        print(f"[UYARI] WikDict bulunamadı!", file=sys.stderr)

    records = load_dictionary()
    existing_keys = build_existing_keys(records)
    record_index = build_record_index(records)
    print(f"Mevcut sözlük: {len(records)} kayıt\n")

    all_new: list = []
    added_keys: set = set(existing_keys)
    updated_indices: set = set()
    total_new = 0
    total_updated = 0
    processed_ids: set = set()

    # -----------------------------------------------------------------------
    # FAZA 1: Seçilmiş klasik eserler
    # -----------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"FAZA 1: Seçilmiş {len(CURATED_BOOKS)} Almanca klasik eser")
    print(f"{'='*70}")

    for i, (book_id, title, author) in enumerate(CURATED_BOOKS, 1):
        elapsed = time.time() - start_time
        if elapsed >= MAX_RUNTIME_SECONDS:
            print(f"\n[SÜRE DOLDU] {elapsed/60:.1f} dakika çalıştı.")
            break

        if book_id in processed_ids:
            continue
        processed_ids.add(book_id)

        print(f"\n[{i}/{len(CURATED_BOOKS)}] Süre: {elapsed/60:.1f}dk")
        url_new, url_updated = process_book(
            book_id, title, author,
            records, existing_keys, added_keys,
            record_index, updated_indices, cursor, all_new
        )
        total_new += url_new
        total_updated += url_updated

        # Her 10 kitapta ara kaydet
        if i % 10 == 0:
            elapsed = time.time() - start_time
            print(f"\n  [ARA KAYIT] {len(all_new)} yeni + {total_updated} güncelleme | Süre: {elapsed/60:.1f}dk")
            save_dictionary(records + all_new)

        time.sleep(1.0)  # Gutenberg'e nazik ol

    # -----------------------------------------------------------------------
    # FAZA 2: Gutendex API ile keşfedilen kitaplar (kalan süre varsa)
    # -----------------------------------------------------------------------
    elapsed = time.time() - start_time
    if elapsed < MAX_RUNTIME_SECONDS - 300:  # En az 5 dakika kaldıysa
        remaining = MAX_RUNTIME_SECONDS - elapsed
        print(f"\n{'='*70}")
        print(f"FAZA 2: Gutendex API keşfi (kalan süre: {remaining/60:.1f}dk)")
        print(f"{'='*70}")

        discovered = fetch_gutendex_books(max_pages=10)
        print(f"  {len(discovered)} kitap keşfedildi.")

        phase2_count = 0
        for book_id, title, author in discovered:
            elapsed = time.time() - start_time
            if elapsed >= MAX_RUNTIME_SECONDS:
                break
            if book_id in processed_ids:
                continue
            processed_ids.add(book_id)

            phase2_count += 1
            print(f"\n[Faza2-{phase2_count}] Süre: {elapsed/60:.1f}dk")
            url_new, url_updated = process_book(
                book_id, title, author,
                records, existing_keys, added_keys,
                record_index, updated_indices, cursor, all_new
            )
            total_new += url_new
            total_updated += url_updated

            if phase2_count % 10 == 0:
                elapsed = time.time() - start_time
                print(f"\n  [ARA KAYIT] {len(all_new)} yeni + {total_updated} güncelleme | Süre: {elapsed/60:.1f}dk")
                save_dictionary(records + all_new)

            time.sleep(1.0)

    # -----------------------------------------------------------------------
    # FAZA 3: Kalan süre varsa Gutendex'ten daha fazla kitap
    # -----------------------------------------------------------------------
    elapsed = time.time() - start_time
    if elapsed < MAX_RUNTIME_SECONDS - 180:
        remaining = MAX_RUNTIME_SECONDS - elapsed
        print(f"\n{'='*70}")
        print(f"FAZA 3: Daha fazla Gutendex sayfası (kalan: {remaining/60:.1f}dk)")
        print(f"{'='*70}")

        extra_books = fetch_gutendex_books(max_pages=20)
        phase3_count = 0
        for book_id, title, author in extra_books:
            elapsed = time.time() - start_time
            if elapsed >= MAX_RUNTIME_SECONDS:
                break
            if book_id in processed_ids:
                continue
            processed_ids.add(book_id)

            phase3_count += 1
            print(f"\n[Faza3-{phase3_count}] Süre: {elapsed/60:.1f}dk")
            url_new, url_updated = process_book(
                book_id, title, author,
                records, existing_keys, added_keys,
                record_index, updated_indices, cursor, all_new
            )
            total_new += url_new
            total_updated += url_updated

            if phase3_count % 10 == 0:
                save_dictionary(records + all_new)

            time.sleep(1.0)

    # -----------------------------------------------------------------------
    # Final kayıt
    # -----------------------------------------------------------------------
    if conn:
        conn.close()

    elapsed = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"TOPLAM SÜRE          : {elapsed/60:.1f} dakika")
    print(f"TOPLAM İŞLENEN KİTAP: {len(processed_ids)}")
    print(f"TOPLAM YENİ KELİME   : {len(all_new)}")
    print(f"TOPLAM GÜNCELLEME    : {total_updated}")
    print(f"{'='*70}")

    records.extend(all_new)
    save_dictionary(records)

    print(f"\nToplam {len(all_new)} yeni kelime eklendi.")
    print(f"Toplam {total_updated} mevcut kayıt zenginleştirildi.")
    print(f"Sözlük artık {len(records)} kayıt içeriyor.")


if __name__ == "__main__":
    main()
