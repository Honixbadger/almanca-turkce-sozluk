#!/usr/bin/env python3
"""
enrich_from_urls.py
===================
Güvenilir Almanca Wikipedia sayfalarından kelime çekerek dictionary.json'u
zenginleştirir.

Kaynak: Alman Wikipedia (CC BY-SA 3.0), WikDict (de-tr çeviri veritabanı)
Yöntem:
  1. Seçilmiş Wikipedia DE URL'lerini çeker
  2. Görünür metni ayıklar (VisibleTextExtractor)
  3. WikDict SQLite veritabanında çeviri arar
  4. Sıkı filtreleme uygular (WikDict çevirisi olan, en az 2 kez geçen)
  5. Sözlükte zaten var olanları atlar
  6. İki konumdaki dictionary.json dosyasını günceller

Çalıştır:
  python scripts/enrich_from_urls.py
"""

import json
import re
import sqlite3
import sys
import unicodedata
import urllib.parse as _up
import urllib.request as _ur
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

# grammar_utils yoksa sessizce devam et
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
        STARK_VERBS,
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
# URL listesi — 150+ güvenilir Almanca Wikipedia sayfası
# ---------------------------------------------------------------------------
SOURCE_URLS = [
    # --- Politika & Devlet ---
    "https://de.wikipedia.org/wiki/Bundesregierung_(Deutschland)",
    "https://de.wikipedia.org/wiki/Demokratie",
    "https://de.wikipedia.org/wiki/Grundgesetz_für_die_Bundesrepublik_Deutschland",
    "https://de.wikipedia.org/wiki/Bürgerrecht",
    "https://de.wikipedia.org/wiki/Bundesrat_(Deutschland)",
    "https://de.wikipedia.org/wiki/Wahlrecht_(Deutschland)",
    "https://de.wikipedia.org/wiki/Volksabstimmung",
    "https://de.wikipedia.org/wiki/Partei_(Politik)",
    "https://de.wikipedia.org/wiki/Opposition_(Politik)",
    "https://de.wikipedia.org/wiki/Koalition_(Politik)",
    "https://de.wikipedia.org/wiki/Bürgermeister",
    "https://de.wikipedia.org/wiki/Landtag",
    "https://de.wikipedia.org/wiki/Verwaltung_(Deutschland)",
    "https://de.wikipedia.org/wiki/Einwohnermeldeamt",
    "https://de.wikipedia.org/wiki/Staatsangehörigkeit",

    # --- Hukuk ---
    "https://de.wikipedia.org/wiki/Gericht",
    "https://de.wikipedia.org/wiki/Vertrag",
    "https://de.wikipedia.org/wiki/Strafrecht_(Deutschland)",
    "https://de.wikipedia.org/wiki/Zivilrecht_(Deutschland)",
    "https://de.wikipedia.org/wiki/Rechtsanwalt",
    "https://de.wikipedia.org/wiki/Notar",
    "https://de.wikipedia.org/wiki/Klage_(Recht)",
    "https://de.wikipedia.org/wiki/Urteil_(Recht)",
    "https://de.wikipedia.org/wiki/Strafe",
    "https://de.wikipedia.org/wiki/Datenschutz",
    "https://de.wikipedia.org/wiki/Urheberrecht",
    "https://de.wikipedia.org/wiki/Mietrecht_(Deutschland)",
    "https://de.wikipedia.org/wiki/Arbeitsrecht_(Deutschland)",

    # --- Ekonomi & İş ---
    "https://de.wikipedia.org/wiki/Wirtschaft_Deutschlands",
    "https://de.wikipedia.org/wiki/Arbeitsmarkt",
    "https://de.wikipedia.org/wiki/Steuer",
    "https://de.wikipedia.org/wiki/Einkommensteuer_(Deutschland)",
    "https://de.wikipedia.org/wiki/Umsatzsteuer_(Deutschland)",
    "https://de.wikipedia.org/wiki/Versicherung_(Wirtschaft)",
    "https://de.wikipedia.org/wiki/Immobilie",
    "https://de.wikipedia.org/wiki/Unternehmen",
    "https://de.wikipedia.org/wiki/Aktie",
    "https://de.wikipedia.org/wiki/Bank",
    "https://de.wikipedia.org/wiki/Kredit",
    "https://de.wikipedia.org/wiki/Inflation",
    "https://de.wikipedia.org/wiki/Arbeitslosigkeit",
    "https://de.wikipedia.org/wiki/Mindestlohn",
    "https://de.wikipedia.org/wiki/Gewerkschaft",
    "https://de.wikipedia.org/wiki/Rente_(Altersvorsorge)",
    "https://de.wikipedia.org/wiki/Insolvenz",
    "https://de.wikipedia.org/wiki/Buchhaltung",
    "https://de.wikipedia.org/wiki/Handel",
    "https://de.wikipedia.org/wiki/Export",
    "https://de.wikipedia.org/wiki/Import",
    "https://de.wikipedia.org/wiki/Markt",
    "https://de.wikipedia.org/wiki/Werbung",
    "https://de.wikipedia.org/wiki/Marketing",

    # --- Sağlık & Tıp ---
    "https://de.wikipedia.org/wiki/Gesundheitssystem",
    "https://de.wikipedia.org/wiki/Krankenversicherung_(Deutschland)",
    "https://de.wikipedia.org/wiki/Ernährung",
    "https://de.wikipedia.org/wiki/Impfung",
    "https://de.wikipedia.org/wiki/Krankenhaus",
    "https://de.wikipedia.org/wiki/Arzt",
    "https://de.wikipedia.org/wiki/Apotheke",
    "https://de.wikipedia.org/wiki/Krankheit",
    "https://de.wikipedia.org/wiki/Infektion",
    "https://de.wikipedia.org/wiki/Medikament",
    "https://de.wikipedia.org/wiki/Chirurgie",
    "https://de.wikipedia.org/wiki/Notaufnahme",
    "https://de.wikipedia.org/wiki/Diabetes_mellitus",
    "https://de.wikipedia.org/wiki/Herz-Kreislauf-Erkrankung",
    "https://de.wikipedia.org/wiki/Psychische_Störung",
    "https://de.wikipedia.org/wiki/Allergie",
    "https://de.wikipedia.org/wiki/Physiotherapie",
    "https://de.wikipedia.org/wiki/Zahnmedizin",
    "https://de.wikipedia.org/wiki/Schlaf",

    # --- Çevre & Enerji ---
    "https://de.wikipedia.org/wiki/Klimawandel",
    "https://de.wikipedia.org/wiki/Nachhaltigkeit",
    "https://de.wikipedia.org/wiki/Erneuerbare_Energie",
    "https://de.wikipedia.org/wiki/Solarenergie",
    "https://de.wikipedia.org/wiki/Windenergie",
    "https://de.wikipedia.org/wiki/Umweltverschmutzung",
    "https://de.wikipedia.org/wiki/Recycling",
    "https://de.wikipedia.org/wiki/Abfall",
    "https://de.wikipedia.org/wiki/Trinkwasser",
    "https://de.wikipedia.org/wiki/Waldsterben",
    "https://de.wikipedia.org/wiki/Artenschutz",
    "https://de.wikipedia.org/wiki/Kohlendioxid",
    "https://de.wikipedia.org/wiki/Treibhausgas",
    "https://de.wikipedia.org/wiki/Elektromobilität",
    "https://de.wikipedia.org/wiki/Atomkraft",

    # --- Teknoloji & Dijital ---
    "https://de.wikipedia.org/wiki/Digitalisierung",
    "https://de.wikipedia.org/wiki/Künstliche_Intelligenz",
    "https://de.wikipedia.org/wiki/Internet",
    "https://de.wikipedia.org/wiki/Mobiltelefon",
    "https://de.wikipedia.org/wiki/Computerprogramm",
    "https://de.wikipedia.org/wiki/Datenbank",
    "https://de.wikipedia.org/wiki/Cloud_Computing",
    "https://de.wikipedia.org/wiki/Cybersicherheit",
    "https://de.wikipedia.org/wiki/Robotik",
    "https://de.wikipedia.org/wiki/Blockchain",
    "https://de.wikipedia.org/wiki/Halbleiter",
    "https://de.wikipedia.org/wiki/Drucker_(Gerät)",
    "https://de.wikipedia.org/wiki/Betriebssystem",

    # --- Eğitim ---
    "https://de.wikipedia.org/wiki/Bildungssystem_in_Deutschland",
    "https://de.wikipedia.org/wiki/Universität",
    "https://de.wikipedia.org/wiki/Berufsausbildung",
    "https://de.wikipedia.org/wiki/Bibliothek",
    "https://de.wikipedia.org/wiki/Schule",
    "https://de.wikipedia.org/wiki/Gymnasium_(Deutschland)",
    "https://de.wikipedia.org/wiki/Hochschule",
    "https://de.wikipedia.org/wiki/Studium",
    "https://de.wikipedia.org/wiki/Stipendium",
    "https://de.wikipedia.org/wiki/Prüfung",
    "https://de.wikipedia.org/wiki/Zeugnis",
    "https://de.wikipedia.org/wiki/Alphabetisierung",

    # --- Göç & Toplum ---
    "https://de.wikipedia.org/wiki/Migration_(Soziologie)",
    "https://de.wikipedia.org/wiki/Integration_(Soziologie)",
    "https://de.wikipedia.org/wiki/Einbürgerung",
    "https://de.wikipedia.org/wiki/Flüchtling",
    "https://de.wikipedia.org/wiki/Asylrecht_(Deutschland)",
    "https://de.wikipedia.org/wiki/Diskriminierung",
    "https://de.wikipedia.org/wiki/Rassismus",
    "https://de.wikipedia.org/wiki/Gleichstellung_(Recht)",
    "https://de.wikipedia.org/wiki/Armut",
    "https://de.wikipedia.org/wiki/Soziale_Ungleichheit",

    # --- Günlük Yaşam ---
    "https://de.wikipedia.org/wiki/Wohnen",
    "https://de.wikipedia.org/wiki/Öffentlicher_Personennahverkehr",
    "https://de.wikipedia.org/wiki/Supermarkt",
    "https://de.wikipedia.org/wiki/Restaurant",
    "https://de.wikipedia.org/wiki/Küche_(Haushalt)",
    "https://de.wikipedia.org/wiki/Lebensmittel",
    "https://de.wikipedia.org/wiki/Bekleidung",
    "https://de.wikipedia.org/wiki/Einkaufen",
    "https://de.wikipedia.org/wiki/Haushalt_(Lebensgemeinschaft)",
    "https://de.wikipedia.org/wiki/Miete",
    "https://de.wikipedia.org/wiki/Nebenkosten",
    "https://de.wikipedia.org/wiki/Haushaltsgerät",
    "https://de.wikipedia.org/wiki/Möbel",
    "https://de.wikipedia.org/wiki/Garten",

    # --- Ulaşım ---
    "https://de.wikipedia.org/wiki/Straßenverkehr",
    "https://de.wikipedia.org/wiki/Führerschein",
    "https://de.wikipedia.org/wiki/Fahrrad",
    "https://de.wikipedia.org/wiki/Deutsche_Bahn",
    "https://de.wikipedia.org/wiki/Flughafen",
    "https://de.wikipedia.org/wiki/Schiff",
    "https://de.wikipedia.org/wiki/Autobahn",
    "https://de.wikipedia.org/wiki/Kraftfahrzeug",
    "https://de.wikipedia.org/wiki/Tankstelle",

    # --- Kültür & Sanat ---
    "https://de.wikipedia.org/wiki/Musik",
    "https://de.wikipedia.org/wiki/Theater",
    "https://de.wikipedia.org/wiki/Film",
    "https://de.wikipedia.org/wiki/Malerei",
    "https://de.wikipedia.org/wiki/Literatur",
    "https://de.wikipedia.org/wiki/Museum",
    "https://de.wikipedia.org/wiki/Bibliothek",
    "https://de.wikipedia.org/wiki/Fotografie",
    "https://de.wikipedia.org/wiki/Architektur",
    "https://de.wikipedia.org/wiki/Mode",
    "https://de.wikipedia.org/wiki/Tanz",

    # --- Spor ---
    "https://de.wikipedia.org/wiki/Fußball",
    "https://de.wikipedia.org/wiki/Olympische_Spiele",
    "https://de.wikipedia.org/wiki/Schwimmen_(Sport)",
    "https://de.wikipedia.org/wiki/Leichtathletik",
    "https://de.wikipedia.org/wiki/Basketball",
    "https://de.wikipedia.org/wiki/Tennis",
    "https://de.wikipedia.org/wiki/Ski_Alpin",
    "https://de.wikipedia.org/wiki/Kampfsport",
    "https://de.wikipedia.org/wiki/Fitness",

    # --- Bilim ---
    "https://de.wikipedia.org/wiki/Physik",
    "https://de.wikipedia.org/wiki/Chemie",
    "https://de.wikipedia.org/wiki/Biologie",
    "https://de.wikipedia.org/wiki/Mathematik",
    "https://de.wikipedia.org/wiki/Astronomie",
    "https://de.wikipedia.org/wiki/Geologie",
    "https://de.wikipedia.org/wiki/Genetik",
    "https://de.wikipedia.org/wiki/Evolution",
    "https://de.wikipedia.org/wiki/Forschung",
    "https://de.wikipedia.org/wiki/Experiment",

    # --- Doğa & Coğrafya ---
    "https://de.wikipedia.org/wiki/Wald",
    "https://de.wikipedia.org/wiki/Fluss",
    "https://de.wikipedia.org/wiki/Berg",
    "https://de.wikipedia.org/wiki/Meer",
    "https://de.wikipedia.org/wiki/Tier",
    "https://de.wikipedia.org/wiki/Pflanze",
    "https://de.wikipedia.org/wiki/Vogel",
    "https://de.wikipedia.org/wiki/Klima",
    "https://de.wikipedia.org/wiki/Wetter",
    "https://de.wikipedia.org/wiki/Landwirtschaft",
    "https://de.wikipedia.org/wiki/Forstwirtschaft",

    # --- Aile & İlişkiler ---
    "https://de.wikipedia.org/wiki/Familie",
    "https://de.wikipedia.org/wiki/Ehe",
    "https://de.wikipedia.org/wiki/Scheidung",
    "https://de.wikipedia.org/wiki/Kindheit",
    "https://de.wikipedia.org/wiki/Jugendalter",
    "https://de.wikipedia.org/wiki/Alter_(Lebensphase)",
    "https://de.wikipedia.org/wiki/Erziehung",

    # --- Din & Felsefe ---
    "https://de.wikipedia.org/wiki/Religion",
    "https://de.wikipedia.org/wiki/Christentum",
    "https://de.wikipedia.org/wiki/Islam",
    "https://de.wikipedia.org/wiki/Philosophie",
    "https://de.wikipedia.org/wiki/Ethik",

    # --- Medya & İletişim ---
    "https://de.wikipedia.org/wiki/Zeitung",
    "https://de.wikipedia.org/wiki/Fernsehen",
    "https://de.wikipedia.org/wiki/Radio",
    "https://de.wikipedia.org/wiki/Soziale_Medien",
    "https://de.wikipedia.org/wiki/Journalismus",
    "https://de.wikipedia.org/wiki/Kommunikation",
    "https://de.wikipedia.org/wiki/Sprache",

    # --- Mimari & İnşaat ---
    "https://de.wikipedia.org/wiki/Bau",
    "https://de.wikipedia.org/wiki/Wohngebäude",
    "https://de.wikipedia.org/wiki/Renovierung",
    "https://de.wikipedia.org/wiki/Heizung",
    "https://de.wikipedia.org/wiki/Dämmung",

    # --- Yiyecek & İçecek ---
    "https://de.wikipedia.org/wiki/Brot",
    "https://de.wikipedia.org/wiki/Käse",
    "https://de.wikipedia.org/wiki/Gemüse",
    "https://de.wikipedia.org/wiki/Obst",
    "https://de.wikipedia.org/wiki/Fisch",
    "https://de.wikipedia.org/wiki/Wein",
    "https://de.wikipedia.org/wiki/Bier",
    "https://de.wikipedia.org/wiki/Kaffee",
    "https://de.wikipedia.org/wiki/Gewürz",

    # --- Meslekler ---
    "https://de.wikipedia.org/wiki/Ingenieur",
    "https://de.wikipedia.org/wiki/Lehrer",
    "https://de.wikipedia.org/wiki/Pflege_(Beruf)",
    "https://de.wikipedia.org/wiki/Architekt",
    "https://de.wikipedia.org/wiki/Koch_(Beruf)",
    "https://de.wikipedia.org/wiki/Feuerwehr",
    "https://de.wikipedia.org/wiki/Polizei",
    "https://de.wikipedia.org/wiki/Soldat",

    # --- Finans & Banka ---
    "https://de.wikipedia.org/wiki/Sparkasse",
    "https://de.wikipedia.org/wiki/Kontoführung",
    "https://de.wikipedia.org/wiki/Hypothek",
    "https://de.wikipedia.org/wiki/Fonds",
    "https://de.wikipedia.org/wiki/Zinsen",
    "https://de.wikipedia.org/wiki/Dividende",
    "https://de.wikipedia.org/wiki/Währung",

    # --- Psikoloji & Davranış ---
    "https://de.wikipedia.org/wiki/Psychologie",
    "https://de.wikipedia.org/wiki/Emotion",
    "https://de.wikipedia.org/wiki/Motivation",
    "https://de.wikipedia.org/wiki/Stress",
    "https://de.wikipedia.org/wiki/Kommunikation",
    "https://de.wikipedia.org/wiki/Konflikt",
    "https://de.wikipedia.org/wiki/Verhalten",

    # --- Tarih ---
    "https://de.wikipedia.org/wiki/Zweiter_Weltkrieg",
    "https://de.wikipedia.org/wiki/Weimarer_Republik",
    "https://de.wikipedia.org/wiki/Deutsche_Wiedervereinigung",
    "https://de.wikipedia.org/wiki/Kalter_Krieg",
    "https://de.wikipedia.org/wiki/Nationalsozialismus",

    # --- Ek teknik konular ---
    "https://de.wikipedia.org/wiki/Telekommunikation",
    "https://de.wikipedia.org/wiki/Elektrizität",
    "https://de.wikipedia.org/wiki/Maschinenbau",
    "https://de.wikipedia.org/wiki/Chemische_Industrie",
    "https://de.wikipedia.org/wiki/Pharmakologie",
    "https://de.wikipedia.org/wiki/Nanotechnologie",
]

# ---------------------------------------------------------------------------
# Stopword kümesi — tümü küçük harfe çevrilmiş (casefold)
# ---------------------------------------------------------------------------
_RAW_STOPWORDS = {
    # Temel
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
    # Sıfat çekimleri
    "gut", "gute", "guten", "gutem", "guter", "gutes",
    "groß", "große", "großen", "großem", "großer", "großes",
    "klein", "kleine", "kleinen", "kleinem", "kleiner", "kleines",
    "neu", "neue", "neuen", "neuem", "neuer", "neues",
    "alt", "alte", "alten", "altem", "alter", "altes",
    "lang", "lange", "langen", "langem", "langer", "langes",
    "kurz", "kurze", "kurzen", "kurzem", "kurzer", "kurzes",
    "viel", "viele", "vielen", "vielem", "vieler", "vieles",
    "wenig", "wenige", "wenigen", "wenigem", "weniger",
    "ganz", "ganze", "ganzen", "ganzem", "ganzer", "ganzes",
    "ander", "andere", "anderen", "anderem", "anderer", "anderes",
    "erst", "erste", "ersten", "erstem", "erster", "erstes",
    "letzt", "letzte", "letzten", "letztem", "letzter", "letztes",
    "recht", "rechte", "rechten",
    "wichtig", "wichtige", "wichtigen",
    "eigen", "eigene", "eigenen",
    "gleich", "gleiche", "gleichen",
    "bekannt", "bekannte", "bekannten",
    "jung", "junge", "jungen",
    "stark", "starke", "starken",
    "schwer", "schwere", "schweren",
    # Zarflar
    "immer", "schon", "nur", "gern", "gerne", "fast", "etwa", "eher",
    "daher", "damals", "dazu", "deswegen", "trotzdem", "dennoch",
    "jedoch", "allerdings", "außerdem", "zudem", "ebenfalls", "bereits",
    "meist", "meistens", "manchmal", "oft", "häufig", "selten",
    "früher", "später", "zuerst", "zuletzt", "endlich", "plötzlich",
    "sofort", "soeben", "bisher", "seitdem", "davor", "davon", "daran",
    "darin", "darauf", "darum", "darüber", "darunter", "dafür",
    "dagegen", "dadurch", "dahinter",
    # Modal fiiller
    "können", "konnte", "konntest", "konnten", "könnte", "könntest",
    "könnten", "müssen", "musste", "musstest", "mussten", "müsste",
    "müsstest", "müssten", "sollst", "sollen", "solltest", "sollten",
    "will", "willst", "wollen", "wollte", "wolltest", "wollten",
    "darf", "darfst", "dürfen", "durfte", "durftest", "durften",
    "dürfte", "dürftest", "dürften", "mag", "magst", "mögen",
    "mochte", "mochtest", "mochten", "möchte", "möchtest", "möchten",
    # sein/haben/werden
    "seid", "wäre", "wärst", "wären", "wärt", "sei", "seist", "seien",
    "habt", "hatten", "hattet", "hätte", "hättest", "hätten", "hättet",
    "gehabt", "werdet", "würde", "würdest", "würden", "würdet", "geworden",
    # Yaygın fiil çekimleri
    "geht", "ging", "gingen", "kommt", "kam", "kamen", "macht",
    "machte", "machten", "sagt", "sagte", "sagten", "gibt", "gab",
    "gaben", "steht", "stand", "standen", "liegt", "lag", "lagen",
    "sieht", "sah", "sahen", "nimmt", "nahm", "nahmen", "hält",
    "hielt", "hielten", "lässt", "ließ", "ließen", "bringt", "brachte",
    "brachten", "denkt", "dachte", "dachten", "weiß", "wusste",
    "wussten", "findet", "fand", "fanden", "zeigt", "zeigte", "zeigten",
    "spielt", "spielte", "spielten", "heißt", "hieß", "hießen",
    "bleibt", "blieb", "blieben",
    # Çok genel isimler
    "Jahr", "Jahre", "Jahren", "Zeit", "Zeiten", "Teil", "Teile",
    "Teilen", "Form", "Formen", "Typ", "Typen", "Art", "Arten",
    "Fall", "Fälle", "Punkt", "Punkte", "Zahl", "Zahlen",
    "Ende", "Anfang", "Bereich", "Bereiche", "Grund", "Gründe",
    "Beispiel", "Beispiele", "Ergebnis", "Ergebnisse", "Problem",
    "Probleme", "Frage", "Fragen", "Antwort", "Antworten",
    "Möglichkeit", "Möglichkeiten", "Bedeutung", "Bedeutungen",
    "Mensch", "Menschen", "Land", "Länder", "Ländern",
    "Stadt", "Städte", "Städten", "Welt", "Leben", "Lebens",
    "Weise", "Stelle", "Stellen", "Seite", "Seiten",
    # İngilizce
    "the", "and", "for", "that", "this", "with", "from", "are",
    "was", "has", "have", "been", "they", "them", "their", "about",
    "what", "which", "when", "where", "how", "can", "will", "not",
    "but", "more", "also", "some", "than", "then", "there", "here",
    "other", "used", "based", "see",
    # Aylar
    "januar", "februar", "märz", "april", "mai", "juni", "juli",
    "august", "september", "oktober", "november", "dezember",
    # Günler
    "montag", "dienstag", "mittwoch", "donnerstag",
    "freitag", "samstag", "sonntag",
    # Sıra sayıları
    "zweite", "zweiten", "zweitem", "zweiter", "zweites",
    "dritte", "dritten", "drittem", "dritter", "drittes",
    "vierte", "vierten", "fünfte", "fünften", "sechste", "sechsten",
    # Zamirler
    "unser", "unsere", "unseren", "unserem", "unserer",
    "eurem", "eurer", "jener", "jene", "jenen", "jenem",
    "jeden", "jedem", "mancher", "manche", "manchen",
    # Edatlar & bağlaçlar
    "obwohl", "während", "bevor", "nachdem", "sobald", "solange",
    "falls", "sofern", "wohingegen", "gegenüber",
    "innerhalb", "außerhalb", "oberhalb", "unterhalb",
    "anstatt", "anstelle", "aufgrund", "mithilfe",
    "bezüglich", "hinsichtlich", "laut", "gemäß", "zufolge",
    "entsprechend",
    # Ek işlev kelimeleri (önceki çalıştırmada geçenler)
    "seit", "statt", "samt", "wobei", "sowie", "hierbei", "hierzu",
    "daraus", "hiervon", "hierfür", "insgesamt", "insbesondere",
    "demnach", "demzufolge", "somit", "folglich", "hingegen",
    "vielmehr", "andererseits", "einerseits", "nämlich", "schließlich",
    "letztlich", "letztendlich", "insofern", "soweit", "sowohl",
    "weder", "entweder", "zumindest", "mindestens", "höchstens",
    "wenigstens", "tatsächlich", "eigentlich", "offenbar",
    "offensichtlich", "anscheinend", "möglicherweise", "wahrscheinlich",
    "vermutlich", "jedenfalls", "ohnehin", "sowieso", "gleichwohl",
    "indessen", "indes", "derweil", "unterdessen", "währenddessen",
    "seither", "fortan", "nunmehr", "grundsätzlich", "weitgehend",
    "infolge", "infolgedessen", "diesbezüglich", "inwieweit",
    "inwiefern", "anhand", "sodass", "sodaß",
    # Wikipedia meta kelimeleri
    "abschnitt", "artikel", "weblink", "weblinks", "literatur",
    "einzelnachweis", "einzelnachweise", "hauptartikel",
    "kategorie", "kategorien", "siehe",
    # Kısaltmalar
    "usw", "bzw", "evtl", "ggf", "inkl", "exkl", "sog", "bspw", "vgl",
}

# Tümünü casefold et — böylece karşılaştırma her zaman doğru çalışır
GERMAN_STOPWORDS_CF: frozenset[str] = frozenset(
    s.casefold() for s in _RAW_STOPWORDS
)

# Bilinen özel isimler (yer adları, kişi adları) — casefold
_PROPER_NOUNS_CF: frozenset[str] = frozenset({
    "berlin", "münchen", "hamburg", "köln", "frankfurt", "stuttgart",
    "düsseldorf", "dortmund", "essen", "leipzig", "bremen", "dresden",
    "hannover", "nürnberg", "duisburg", "bochum", "wuppertal", "bonn",
    "mannheim", "karlsruhe", "freiburg", "augsburg", "wiesbaden",
    "deutschland", "österreich", "schweiz", "europa", "brüssel",
    "paris", "london", "washington", "peking", "tokio", "moskau",
    "beijing", "new", "york", "united", "states",
    # Kişi adları (yaygın Alman soyadları)
    "müller", "schmidt", "schneider", "fischer", "weber", "meyer",
    "wagner", "becker", "schulz", "hoffmann", "schäfer", "koch",
    "bauer", "richter", "klein", "wolf", "schröder", "neumann",
    "schwarz", "zimmermann", "braun", "krüger", "hartmann", "lange",
    "werner", "lehmann", "walter", "maier", "mayer", "köhler",
    "krause", "steiner", "jung", "roth", "vogel", "schumacher",
    # Yaygın Almanca ön adlar
    "friedrich", "johannes", "wilhelm", "wolfgang", "heinrich",
    "thomas", "michael", "stefan", "andreas", "christian",
    "markus", "matthias", "sebastian", "tobias", "alexander",
    "christoph", "samuel", "peter", "hans", "otto", "karl",
})

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------
TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß]{3,}(?:-[A-Za-zÄÖÜäöüß]{2,})*")


# ---------------------------------------------------------------------------
# HTML metin ayıklayıcı
# ---------------------------------------------------------------------------
class VisibleTextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "address", "article", "blockquote", "br", "div",
        "figcaption", "h1", "h2", "h3", "h4", "h5", "h6",
        "li", "main", "p", "section", "td", "th", "tr",
    }
    SKIP_TAGS = {
        "head", "script", "style", "noscript", "svg", "canvas",
        "nav", "footer", "header", "aside", "button", "form",
        "input", "select", "textarea", "figure",
    }
    MAIN_TAGS = {"main", "article"}
    SKIP_CLASSES = {
        "references", "reflist", "reference", "footnotes",
        "toc", "toccolours", "mw-references-wrap",
        "navbox", "navbox-inner", "navbox-group",
        "mw-editsection", "mw-jump-link",
        "sidebar", "sistersitebox", "noprint",
        "catlinks", "printfooter",
        "cookie", "banner", "advertisement", "ad", "ads",
        "breadcrumb", "pagination", "menu", "dropdown",
        "related", "recommendation", "teaser",
    }
    SKIP_IDS = {
        "toc", "references", "catlinks", "mw-navigation", "p-search",
        "nav", "footer", "header", "sidebar", "menu", "cookie-banner",
        "related-articles", "breadcrumb",
    }

    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.main_depth = 0
        self.all_chunks: list[str] = []
        self.main_chunks: list[str] = []

    def _should_skip_attrs(self, attrs: list) -> bool:
        attr_dict = dict(attrs)
        el_id = attr_dict.get("id", "")
        el_classes = set((attr_dict.get("class", "") or "").split())
        if el_id in self.SKIP_IDS:
            return True
        if el_classes & self.SKIP_CLASSES:
            return True
        return False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.SKIP_TAGS or self._should_skip_attrs(attrs):
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in self.MAIN_TAGS:
            self.main_depth += 1
        if tag in self.BLOCK_TAGS:
            self._append_break()

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag in self.MAIN_TAGS and self.main_depth:
            self.main_depth -= 1
        if tag in self.BLOCK_TAGS:
            self._append_break()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        cleaned = data.strip()
        if not cleaned:
            return
        self.all_chunks.append(cleaned)
        if self.main_depth:
            self.main_chunks.append(cleaned)

    def _append_break(self) -> None:
        self.all_chunks.append("\n")
        if self.main_depth:
            self.main_chunks.append("\n")

    def get_text(self) -> str:
        def _join(chunks: list[str]) -> str:
            parts: list[str] = []
            for chunk in chunks:
                if chunk == "\n":
                    if parts and parts[-1] != "\n":
                        parts.append("\n")
                else:
                    stripped = chunk.strip()
                    if stripped:
                        parts.append(stripped)
            return " ".join(p for p in parts).strip()

        main_text = _join(self.main_chunks)
        body_text = _join(self.all_chunks)
        chosen = main_text if len(main_text) >= 200 else body_text
        chosen = re.sub(r"[ \t]{2,}", " ", chosen)
        chosen = re.sub(r"\n{3,}", "\n\n", chosen)
        return chosen.strip()


# ---------------------------------------------------------------------------
# URL'den metin çek
# ---------------------------------------------------------------------------
def fix_url_encoding(url: str) -> str:
    """ä/ö/ü gibi karakterleri URL'de percent-encode et (ä → %C3%A4).
    Önce decode ederek zaten encode edilmiş URL'lerin çift-encode edilmesini önler."""
    parts = _up.urlsplit(url)
    decoded_path = _up.unquote(parts.path)
    encoded_path = _up.quote(decoded_path, safe="/:@!$&'()*+,;=")
    return _up.urlunsplit(parts._replace(path=encoded_path))

def fetch_text(url: str) -> str:
    url = fix_url_encoding(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AlmancaSozluk/1.0; educational use)",
        "Accept-Language": "de-DE,de;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }
    req = _ur.Request(url, headers=headers)
    try:
        with _ur.urlopen(req, timeout=20) as r:
            raw = r.read()
            charset = r.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
    except Exception as e:
        print(f"  [HATA] {url}: {e}", file=sys.stderr)
        return ""


# ---------------------------------------------------------------------------
# Metin normalleştirme
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
    token_cf = cf(token)
    base_cf = cf(strip_article(token))
    return token_cf in GERMAN_STOPWORDS_CF or base_cf in GERMAN_STOPWORDS_CF


def is_proper_noun(token: str) -> bool:
    return cf(token) in _PROPER_NOUNS_CF


# ---------------------------------------------------------------------------
# WikDict çeviri arama
# ---------------------------------------------------------------------------
def lookup_translation(term: str, cursor: sqlite3.Cursor | None) -> dict:
    if cursor is None:
        return {"translation": "", "written_rep": ""}

    lower = cf(strip_article(term))
    lookup_terms = [term.strip(), lower]

    # Çekim formu soyutlama
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

    seen: set[str] = set()
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
            seen_tr: set[str] = set()
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
# Geliştirilmiş lemmatizasyon — WikDict araması öncesi temel form bul
# ---------------------------------------------------------------------------
def _get_lookup_variants(token: str) -> list[str]:
    """
    Bir token için WikDict'te aranacak form listesi döndür.
    Önce temel form, sonra alternatifler.
    """
    variants: list[str] = [token]

    if _GRAMMAR_UTILS_AVAILABLE:
        t_lower = token.lower()
        # Fiil lemmatizasyonu
        if not token[:1].isupper():
            inf = lemmatize_verb(token)
            if inf and inf != token:
                variants.append(inf)
            # -ieren fiilleri için ek varyant
            if t_lower.endswith("iert"):
                variants.append(t_lower[:-4] + "ieren")
        # İsim lemmatizasyonu
        elif token[:1].isupper():
            base = lemmatize_noun(token)
            if base and base != strip_article(token):
                variants.append(base)
            # Sıfat mı? (büyük harf ama sıfat gibi görünüyor)
            adj_base = lemmatize_adjective(token)
            if adj_base and adj_base != token.lower():
                variants.append(adj_base.capitalize())

    # Mevcut suffix stripping (yedek)
    lower = cf(strip_article(token))
    for suffix, replacement in [
        ("iert", "ieren"), ("test", "en"), ("tet", "en"),
        ("st", "en"), ("te", "en"),
    ]:
        if lower.endswith(suffix) and len(lower) > len(suffix) + 2:
            variants.append(lower[: -len(suffix)] + replacement)

    # Tekrarları kaldır ama sırayı koru
    seen: set[str] = set()
    result: list[str] = []
    for v in variants:
        k = cf(v)
        if k not in seen:
            seen.add(k)
            result.append(v)
    return result


# ---------------------------------------------------------------------------
# Sözlük yükleme / kaydetme
# ---------------------------------------------------------------------------
def load_dictionary() -> list[dict]:
    for p in DICT_PATHS:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return []


def save_dictionary(records: list[dict]) -> None:
    for p in DICT_PATHS:
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            print(f"  Kaydedildi: {p}")
        except Exception as e:
            print(f"  [HATA] {p}: {e}", file=sys.stderr)


def build_existing_keys(records: list[dict]) -> set[str]:
    keys: set[str] = set()
    for r in records:
        almanca = (r.get("almanca", "") or "").strip()
        keys.add(cf(almanca))
        keys.add(cf(strip_article(almanca)))
    return keys


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
# Bir URL'den aday çıkar
# ---------------------------------------------------------------------------
def extract_candidates(
    url: str,
    existing_keys: set[str],
    cursor: sqlite3.Cursor | None,
    min_freq: int = 2,
) -> tuple[list[dict], str]:
    """Döndürür: (aday listesi, sayfa metni)"""
    html = fetch_text(url)
    if not html:
        return [], ""

    parser = VisibleTextExtractor()
    parser.feed(html)
    text = parser.get_text()
    if not text:
        return [], ""

    print(f"  Metin: {len(text):,} karakter")

    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    lowercase_seen: set[str] = set()

    for token in TOKEN_RE.findall(text):
        if token[:1].islower():
            lowercase_seen.add(cf(token))

    for token in TOKEN_RE.findall(text):
        norm = cf(token)
        if not norm or len(norm) < 4 or len(norm) > 35:
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
    for norm, freq in counts.most_common(300):
        if freq < min_freq:
            continue
        german = labels.get(norm, norm)
        sug = lookup_translation(german, cursor)

        if not sug["translation"]:
            continue

        # Çeviri çok kısa mı? (< 3 karakter) — ama tek heceli meşru kelimeler olabilir
        if len(sug["translation"].strip()) < 2:
            continue

        # WikDict kanonik formu zaten sözlükte mi?
        wr_key = cf(sug.get("written_rep", ""))
        if wr_key and wr_key != norm and wr_key in existing_keys:
            continue

        # Çekim formunu atla: kanonik form başka bir kelimeyle eşleşiyor
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
            "pos": guess_pos(german, text),
            "freq": freq,
            "written_rep": sug["written_rep"],
        })

    return candidates, text


# ---------------------------------------------------------------------------
# Aday → sözlük kaydı (gramer bilgileriyle zenginleştirilmiş)
# ---------------------------------------------------------------------------
def candidate_to_record(cand: dict, source_url: str, text: str = "") -> dict:
    almanca = cand["almanca"]
    artikel = ""
    wr = cand.get("written_rep", "")

    # 1. WikDict written_rep'ten artikel çek
    for art in ("der ", "die ", "das "):
        if wr.lower().startswith(art):
            artikel = art.strip()
            almanca = wr[len(art):]
            break

    # 2. Metinden artikel dene (grammar_utils)
    if not artikel and text and _GRAMMAR_UTILS_AVAILABLE:
        detected = detect_article_from_context(almanca, text)
        if detected:
            artikel = detected

    pos = cand.get("pos", guess_pos(almanca))

    # 3. Fiil tipi tespiti
    verb_typ = ""
    trennbar = ""
    if pos == "fiil" and _GRAMMAR_UTILS_AVAILABLE:
        verb_typ = classify_verb_type(almanca)
        if not verb_typ and text:
            verb_typ = detect_verb_type_from_text(almanca, text)
        if is_trennbar(almanca):
            trennbar = "trennbar"

    # 4. Çeviri kalite skoru (çok düşükse not düş)
    quality = 1.0
    if _GRAMMAR_UTILS_AVAILABLE:
        quality = translation_quality_score(cand["turkce"], almanca)

    topic = source_url.split("/wiki/")[-1].replace("_", " ")
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
        "kaynak": "WikDict; Wikipedia DE",
        "kaynak_url": f"https://kaikki.org/dewiktionary/rawdata.html; {source_url}",
        "ceviri_durumu": "kaynak-izli",
        "ceviri_inceleme_notu": "" if quality >= 0.6 else "çeviri kalitesi düşük — kontrol et",
        "ceviri_kaynaklari": [],
        "not": f"URL-import: Wikipedia DE — {topic}",
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
# Ana akış
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 65)
    print("enrich_from_urls.py — Wikipedia DE kaynaklı sozluk zenginlestirme")
    print(f"URL sayisi: {len(SOURCE_URLS)}")
    print("=" * 65)

    if WIKDICT_PATH.exists():
        conn = sqlite3.connect(str(WIKDICT_PATH))
        cursor = conn.cursor()
        print(f"WikDict: {WIKDICT_PATH}")
    else:
        conn = None
        cursor = None
        print(f"[UYARI] WikDict bulunamadi: {WIKDICT_PATH}", file=sys.stderr)

    records = load_dictionary()
    existing_keys = build_existing_keys(records)
    print(f"Mevcut sozluk: {len(records)} kayit, {len(existing_keys)} benzersiz anahtar\n")

    all_new: list[dict] = []
    added_keys: set[str] = set(existing_keys)
    url_stats: dict[str, int] = {}
    total_urls = len(SOURCE_URLS)

    for i, url in enumerate(SOURCE_URLS, 1):
        topic = url.split("/wiki/")[-1].replace("_", " ")
        print(f"\n[{i}/{total_urls}] {topic}")
        candidates, page_text = extract_candidates(url, added_keys, cursor, min_freq=2)
        url_new = 0
        for cand in candidates:
            norm = cf(cand["almanca"])
            norm_base = cf(strip_article(cand["almanca"]))
            if norm in added_keys or norm_base in added_keys:
                continue
            rec = candidate_to_record(cand, url, text=page_text)
            all_new.append(rec)
            added_keys.add(norm)
            added_keys.add(norm_base)
            url_new += 1
            print(f"    + {rec['almanca']} -> {rec['turkce']}")
        url_stats[topic] = url_new
        print(f"  => {url_new} yeni kelime")

        # Her 20 URL'de bir ara kaydet
        if i % 20 == 0 and all_new:
            print(f"\n  [ARA KAYIT] {len(all_new)} yeni kayit kaydediliyor...")
            save_dictionary(records + all_new)

    if conn:
        conn.close()

    print(f"\n{'='*65}")
    print(f"TOPLAM YENI KELIME: {len(all_new)}")
    print(f"{'='*65}")

    if not all_new:
        print("Eklenecek yeni kelime yok.")
        return

    records.extend(all_new)
    save_dictionary(records)

    print("\n--- Konu bazli ozet ---")
    for topic, count in url_stats.items():
        if count:
            print(f"  {topic}: +{count}")

    print(f"\nToplam {len(all_new)} yeni kelime eklendi.")
    print(f"Sozluk artik {len(records)} kayit iceriyor.")


if __name__ == "__main__":
    main()
