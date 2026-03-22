#!/usr/bin/env python3
"""
enrich_automotive.py
====================
Almanca otomotiv/araç teknik terimlerini Wikipedia DE ve açık kaynak
teknik makalelerden çekerek dictionary.json'a ekler.

Düzeltilen bug: URL içindeki ä/ö/ü harfleri artık düzgün percent-encode
ediliyor (ä → %C3%A4) — önceki çalıştırmada bu harfler ASCII hatasına
yol açıyordu.

Kaynak: Alman Wikipedia (CC BY-SA 3.0), kfz-tech.de, adac.de (herkese açık)
        WikDict (de-tr çeviri veritabanı)
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
# URL listesi — otomotiv & araç teknik terimleri
# ---------------------------------------------------------------------------
SOURCE_URLS = [
    # === Temel araç sistemleri ===
    "https://de.wikipedia.org/wiki/Kraftfahrzeug",
    "https://de.wikipedia.org/wiki/Kraftwagen",
    "https://de.wikipedia.org/wiki/Fahrzeugklasse",
    "https://de.wikipedia.org/wiki/Pkw",

    # === Motor ===
    "https://de.wikipedia.org/wiki/Verbrennungsmotor",
    "https://de.wikipedia.org/wiki/Ottomotor",
    "https://de.wikipedia.org/wiki/Dieselmotor",
    "https://de.wikipedia.org/wiki/Elektromotor",
    "https://de.wikipedia.org/wiki/Wankelmotor",
    "https://de.wikipedia.org/wiki/Kurbelwelle",
    "https://de.wikipedia.org/wiki/Nockenwelle",
    "https://de.wikipedia.org/wiki/Kolben_(Technik)",
    "https://de.wikipedia.org/wiki/Pleuelstange",
    "https://de.wikipedia.org/wiki/Zylinderkopf",
    "https://de.wikipedia.org/wiki/Motorblock",
    "https://de.wikipedia.org/wiki/Ventil_(Motortechnik)",
    "https://de.wikipedia.org/wiki/Steuerkette",
    "https://de.wikipedia.org/wiki/Zahnriemen",
    "https://de.wikipedia.org/wiki/Schwungrad",
    "https://de.wikipedia.org/wiki/Motorsteuerung",
    "https://de.wikipedia.org/wiki/Turbolader",
    "https://de.wikipedia.org/wiki/Kompressor_(Aufladung)",
    "https://de.wikipedia.org/wiki/Ladeluftkühler",
    "https://de.wikipedia.org/wiki/Drehmoment",
    "https://de.wikipedia.org/wiki/Leistung_(Physik)",
    "https://de.wikipedia.org/wiki/Hubraum",
    "https://de.wikipedia.org/wiki/Verdichtungsverhältnis",
    "https://de.wikipedia.org/wiki/Viertaktmotor",
    "https://de.wikipedia.org/wiki/Zweitaktmotor",

    # === Kraftstoff & Abgas ===
    "https://de.wikipedia.org/wiki/Kraftstoff",
    "https://de.wikipedia.org/wiki/Benzin",
    "https://de.wikipedia.org/wiki/Dieselkraftstoff",
    "https://de.wikipedia.org/wiki/Kraftstoffeinspritzung",
    "https://de.wikipedia.org/wiki/Direkteinspritzung",
    "https://de.wikipedia.org/wiki/Vergaser",
    "https://de.wikipedia.org/wiki/Kraftstoffpumpe",
    "https://de.wikipedia.org/wiki/Kraftstofffilter",
    "https://de.wikipedia.org/wiki/Abgasanlage",
    "https://de.wikipedia.org/wiki/Katalysator_(Kfz)",
    "https://de.wikipedia.org/wiki/Partikelfilter",
    "https://de.wikipedia.org/wiki/Abgasrückführung",
    "https://de.wikipedia.org/wiki/Abgasnorm",
    "https://de.wikipedia.org/wiki/Kraftstoffverbrauch",
    "https://de.wikipedia.org/wiki/Klopfen_(Motor)",

    # === Schmierung & Kühlung ===
    "https://de.wikipedia.org/wiki/Motoröl",
    "https://de.wikipedia.org/wiki/Ölwanne",
    "https://de.wikipedia.org/wiki/Ölpumpe",
    "https://de.wikipedia.org/wiki/Ölfilter",
    "https://de.wikipedia.org/wiki/Kühlsystem_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/Kühlmittel",
    "https://de.wikipedia.org/wiki/Kühler_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/Thermostat_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/Wasserpumpe_(Kraftfahrzeug)",

    # === Zündung ===
    "https://de.wikipedia.org/wiki/Zündanlage",
    "https://de.wikipedia.org/wiki/Zündkerze",
    "https://de.wikipedia.org/wiki/Zündspule",
    "https://de.wikipedia.org/wiki/Zündzeitpunkt",

    # === Getriebe & Antrieb ===
    "https://de.wikipedia.org/wiki/Getriebe_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/Schaltgetriebe",
    "https://de.wikipedia.org/wiki/Automatikgetriebe",
    "https://de.wikipedia.org/wiki/Doppelkupplungsgetriebe",
    "https://de.wikipedia.org/wiki/Stufenlosgetriebe",
    "https://de.wikipedia.org/wiki/Kupplung_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/Differentialgetriebe",
    "https://de.wikipedia.org/wiki/Allradantrieb",
    "https://de.wikipedia.org/wiki/Vorderradantrieb",
    "https://de.wikipedia.org/wiki/Hinterradantrieb",
    "https://de.wikipedia.org/wiki/Antriebswelle",
    "https://de.wikipedia.org/wiki/Gelenkwelle",
    "https://de.wikipedia.org/wiki/Gelenk_(Technik)",
    "https://de.wikipedia.org/wiki/Verteilergetriebe",

    # === Fahrwerk & Aufhängung ===
    "https://de.wikipedia.org/wiki/Fahrwerk",
    "https://de.wikipedia.org/wiki/Radaufhängung",
    "https://de.wikipedia.org/wiki/Achse_(Fahrzeugtechnik)",
    "https://de.wikipedia.org/wiki/Querlenker",
    "https://de.wikipedia.org/wiki/Spurstange",
    "https://de.wikipedia.org/wiki/Stabilisator_(Fahrwerk)",
    "https://de.wikipedia.org/wiki/Stoßdämpfer",
    "https://de.wikipedia.org/wiki/Feder_(Fahrwerk)",
    "https://de.wikipedia.org/wiki/Luftfederung",
    "https://de.wikipedia.org/wiki/Schraubenfeder",
    "https://de.wikipedia.org/wiki/Blattfeder",
    "https://de.wikipedia.org/wiki/McPherson-Federbein",
    "https://de.wikipedia.org/wiki/Doppelquerlenker-Achse",
    "https://de.wikipedia.org/wiki/Mehrlenker-Achse",
    "https://de.wikipedia.org/wiki/Hinterachse",
    "https://de.wikipedia.org/wiki/Vorderachse",
    "https://de.wikipedia.org/wiki/Spur_(Fahrzeugtechnik)",
    "https://de.wikipedia.org/wiki/Sturz_(Fahrzeugtechnik)",

    # === Bremse ===
    "https://de.wikipedia.org/wiki/Bremse_(Fahrzeugtechnik)",
    "https://de.wikipedia.org/wiki/Scheibenbremse",
    "https://de.wikipedia.org/wiki/Trommelbremse",
    "https://de.wikipedia.org/wiki/Bremsscheibe",
    "https://de.wikipedia.org/wiki/Bremsbelag",
    "https://de.wikipedia.org/wiki/Bremssattel",
    "https://de.wikipedia.org/wiki/Bremskraftverteilung",
    "https://de.wikipedia.org/wiki/Antiblockiersystem",
    "https://de.wikipedia.org/wiki/Fahrdynamikregelung",
    "https://de.wikipedia.org/wiki/Bremsflüssigkeit",
    "https://de.wikipedia.org/wiki/Handbremse",
    "https://de.wikipedia.org/wiki/Bremskraftverstärker",

    # === Lenkung ===
    "https://de.wikipedia.org/wiki/Lenkung",
    "https://de.wikipedia.org/wiki/Servolenkung",
    "https://de.wikipedia.org/wiki/Zahnstangenlenkung",
    "https://de.wikipedia.org/wiki/Lenkrad",
    "https://de.wikipedia.org/wiki/Lenkgetriebe",
    "https://de.wikipedia.org/wiki/Wendekreis",

    # === Reifen & Räder ===
    "https://de.wikipedia.org/wiki/Reifen",
    "https://de.wikipedia.org/wiki/Felge",
    "https://de.wikipedia.org/wiki/Reifenluftdruck",
    "https://de.wikipedia.org/wiki/Winterreifen",
    "https://de.wikipedia.org/wiki/Sommerreifen",
    "https://de.wikipedia.org/wiki/Reifenprofil",
    "https://de.wikipedia.org/wiki/Pannenschutz_(Reifen)",

    # === Karosserie ===
    "https://de.wikipedia.org/wiki/Karosserie",
    "https://de.wikipedia.org/wiki/Fahrzeugrahmen",
    "https://de.wikipedia.org/wiki/Selbsttragende_Karosserie",
    "https://de.wikipedia.org/wiki/Fahrzeugtür",
    "https://de.wikipedia.org/wiki/Motorhaube",
    "https://de.wikipedia.org/wiki/Kofferraum",
    "https://de.wikipedia.org/wiki/Windschutzscheibe",
    "https://de.wikipedia.org/wiki/Heckklappe",
    "https://de.wikipedia.org/wiki/Stoßstange",
    "https://de.wikipedia.org/wiki/Kotflügel",
    "https://de.wikipedia.org/wiki/Seitenspiegel",
    "https://de.wikipedia.org/wiki/Dach_(Fahrzeug)",
    "https://de.wikipedia.org/wiki/Schiebedach",
    "https://de.wikipedia.org/wiki/Fahrzeugfarbe",

    # === Innenraum & Komfort ===
    "https://de.wikipedia.org/wiki/Fahrzeuginnenraum",
    "https://de.wikipedia.org/wiki/Fahrzeugsitz",
    "https://de.wikipedia.org/wiki/Sicherheitsgurt",
    "https://de.wikipedia.org/wiki/Instrumententafel",
    "https://de.wikipedia.org/wiki/Armaturenbrett",
    "https://de.wikipedia.org/wiki/Tachometer",
    "https://de.wikipedia.org/wiki/Drehzahlmesser",
    "https://de.wikipedia.org/wiki/Klimaanlage",
    "https://de.wikipedia.org/wiki/Heizung_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/Navigationssystem_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/Lautsprecher_(Kraftfahrzeug)",

    # === Beleuchtung ===
    "https://de.wikipedia.org/wiki/Scheinwerfer_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/Nebelscheinwerfer",
    "https://de.wikipedia.org/wiki/LED-Scheinwerfer",
    "https://de.wikipedia.org/wiki/Blinker_(Licht)",
    "https://de.wikipedia.org/wiki/Rücklicht",
    "https://de.wikipedia.org/wiki/Bremsleuchte",

    # === Elektrik & Elektronik ===
    "https://de.wikipedia.org/wiki/Fahrzeugelektrik",
    "https://de.wikipedia.org/wiki/Kfz-Batterie",
    "https://de.wikipedia.org/wiki/Lichtmaschine",
    "https://de.wikipedia.org/wiki/Anlasser_(Motor)",
    "https://de.wikipedia.org/wiki/Steuergerät_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/CAN-Bus",
    "https://de.wikipedia.org/wiki/OBD",
    "https://de.wikipedia.org/wiki/Fahrassistenzsystem",
    "https://de.wikipedia.org/wiki/Einparkhilfe",
    "https://de.wikipedia.org/wiki/Tempomat",
    "https://de.wikipedia.org/wiki/Totwinkel-Assistent",

    # === Sicherheit ===
    "https://de.wikipedia.org/wiki/Airbag",
    "https://de.wikipedia.org/wiki/Passive_Sicherheit_(Fahrzeug)",
    "https://de.wikipedia.org/wiki/Aktive_Sicherheit_(Fahrzeug)",
    "https://de.wikipedia.org/wiki/Crashtest",
    "https://de.wikipedia.org/wiki/Knautschzone",
    "https://de.wikipedia.org/wiki/Kindersitz_(Kfz)",

    # === Elektroauto & Hybrid ===
    "https://de.wikipedia.org/wiki/Elektroauto",
    "https://de.wikipedia.org/wiki/Hybridfahrzeug",
    "https://de.wikipedia.org/wiki/Plug-in-Hybrid",
    "https://de.wikipedia.org/wiki/Brennstoffzellenfahrzeug",
    "https://de.wikipedia.org/wiki/Ladesäule",
    "https://de.wikipedia.org/wiki/Schnellladung_(Elektroauto)",
    "https://de.wikipedia.org/wiki/Rekuperation_(Energietechnik)",
    "https://de.wikipedia.org/wiki/Traktionsbatterie",

    # === Autonomes Fahren ===
    "https://de.wikipedia.org/wiki/Autonomes_Fahren",
    "https://de.wikipedia.org/wiki/Fahrerassistenzsystem",
    "https://de.wikipedia.org/wiki/Adaptive_Geschwindigkeitsregelung",
    "https://de.wikipedia.org/wiki/Spurhalteassistent",

    # === Fahrzeugtypen ===
    "https://de.wikipedia.org/wiki/Limousine",
    "https://de.wikipedia.org/wiki/Kombi",
    "https://de.wikipedia.org/wiki/Cabriolet",
    "https://de.wikipedia.org/wiki/Sportwagen",
    "https://de.wikipedia.org/wiki/Geländewagen",
    "https://de.wikipedia.org/wiki/SUV",
    "https://de.wikipedia.org/wiki/Minivan",
    "https://de.wikipedia.org/wiki/Kleinstwagen",
    "https://de.wikipedia.org/wiki/Lastkraftwagen",
    "https://de.wikipedia.org/wiki/Transporter_(Fahrzeug)",
    "https://de.wikipedia.org/wiki/Motorrad",
    "https://de.wikipedia.org/wiki/Bus_(Fahrzeug)",

    # === Kfz-Recht & Verwaltung ===
    "https://de.wikipedia.org/wiki/Kraftfahrzeugzulassung",
    "https://de.wikipedia.org/wiki/Hauptuntersuchung",
    "https://de.wikipedia.org/wiki/Kraftfahrzeugsteuer_(Deutschland)",
    "https://de.wikipedia.org/wiki/Kfz-Versicherung",
    "https://de.wikipedia.org/wiki/Fahrzeugbrief",
    "https://de.wikipedia.org/wiki/Fahrzeugschein",
    "https://de.wikipedia.org/wiki/Kraftfahrzeugkennzeichen_(Deutschland)",
    "https://de.wikipedia.org/wiki/Führerschein",

    # === Werkstatt & Wartung ===
    "https://de.wikipedia.org/wiki/Kfz-Werkstatt",
    "https://de.wikipedia.org/wiki/Inspektion_(Kfz)",
    "https://de.wikipedia.org/wiki/Ölwechsel",
    "https://de.wikipedia.org/wiki/Reifenwechsel",
    "https://de.wikipedia.org/wiki/Fahrzeugdiagnose",

    # === Tankstelle & Infrastruktur ===
    "https://de.wikipedia.org/wiki/Tankstelle",
    "https://de.wikipedia.org/wiki/Autobahn",
    "https://de.wikipedia.org/wiki/Straße",
    "https://de.wikipedia.org/wiki/Parkhaus",
    "https://de.wikipedia.org/wiki/Garage_(Gebäude)",

    # === Unfall & Sicherheit ===
    "https://de.wikipedia.org/wiki/Verkehrsunfall",
    "https://de.wikipedia.org/wiki/Haftpflicht",
    "https://de.wikipedia.org/wiki/Pannenhilfe",
    "https://de.wikipedia.org/wiki/Abschleppen_(Fahrzeug)",

    # === Kfz-tech.de açık kaynak teknik sayfalar ===
    "https://www.kfz-tech.de/Getriebearten.htm",
    "https://www.kfz-tech.de/Bremsen.htm",
    "https://www.kfz-tech.de/Motor.htm",
    "https://www.kfz-tech.de/Fahrwerk.htm",
    "https://www.kfz-tech.de/Kraftstoffanlage.htm",
    "https://www.kfz-tech.de/Elektrik.htm",
    "https://www.kfz-tech.de/Lenkung.htm",
    "https://www.kfz-tech.de/Kupplung.htm",
    "https://www.kfz-tech.de/Karosserie.htm",
    "https://www.kfz-tech.de/Kühlung.htm",
    "https://www.kfz-tech.de/Schmierung.htm",
    "https://www.kfz-tech.de/Zündung.htm",
    "https://www.kfz-tech.de/Abgasanlage.htm",
    "https://www.kfz-tech.de/Reifen.htm",
]

# ---------------------------------------------------------------------------
# Stopword kümesi — casefold (önceki versiyon + düzeltmeler)
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
    "immer", "schon", "nur", "gern", "gerne", "fast", "etwa", "eher",
    "daher", "damals", "dazu", "deswegen", "trotzdem", "dennoch",
    "jedoch", "allerdings", "außerdem", "zudem", "ebenfalls", "bereits",
    "meist", "meistens", "manchmal", "oft", "häufig", "selten",
    "früher", "später", "zuerst", "zuletzt", "endlich", "plötzlich",
    "sofort", "soeben", "bisher", "seitdem", "davor", "davon", "daran",
    "darin", "darauf", "darum", "darüber", "darunter", "dafür",
    "dagegen", "dadurch", "dahinter",
    "können", "konnte", "konnten", "könnte", "könnten",
    "müssen", "musste", "mussten", "müsste", "müssten",
    "sollen", "sollten", "wollen", "wollte", "wollten",
    "darf", "dürfen", "durfte", "durften", "dürfte", "dürften",
    "mögen", "mochte", "mochten", "möchte", "möchten",
    "seid", "wäre", "wären", "wärt", "sei", "seien",
    "habt", "hatten", "hattet", "hätte", "hätten", "gehabt",
    "werdet", "würde", "würden", "würdet", "geworden",
    "geht", "ging", "gingen", "kommt", "kam", "kamen",
    "macht", "machte", "machten", "sagt", "sagte", "sagten",
    "gibt", "gab", "gaben", "steht", "stand", "standen",
    "liegt", "lag", "lagen", "sieht", "sah", "sahen",
    "nimmt", "nahm", "nahmen", "hält", "hielt", "hielten",
    "lässt", "ließ", "ließen", "bringt", "brachte", "brachten",
    "denkt", "dachte", "dachten", "weiß", "wusste", "wussten",
    "findet", "fand", "fanden", "zeigt", "zeigte", "zeigten",
    "bleibt", "blieb", "blieben", "heißt", "hieß", "hießen",
    "Jahr", "Jahre", "Jahren", "Zeit", "Zeiten", "Teil", "Teile",
    "Form", "Formen", "Art", "Arten", "Fall", "Fälle",
    "Punkt", "Punkte", "Zahl", "Zahlen", "Ende", "Anfang",
    "Bereich", "Bereiche", "Grund", "Gründe",
    "Beispiel", "Beispiele", "Ergebnis", "Ergebnisse",
    "Problem", "Probleme", "Frage", "Fragen",
    "Antwort", "Antworten", "Möglichkeit", "Möglichkeiten",
    "Bedeutung", "Bedeutungen", "Mensch", "Menschen",
    "Land", "Länder", "Stadt", "Städte", "Welt", "Leben",
    "Weise", "Stelle", "Stellen", "Seite", "Seiten",
    "the", "and", "for", "that", "this", "with", "from", "are",
    "was", "has", "have", "been", "they", "about", "which",
    "when", "where", "how", "can", "will", "not", "but",
    "more", "also", "some", "than", "then", "there", "here",
    "other", "used", "based", "see", "view", "edit",
    "januar", "februar", "märz", "april", "mai", "juni", "juli",
    "august", "september", "oktober", "november", "dezember",
    "montag", "dienstag", "mittwoch", "donnerstag",
    "freitag", "samstag", "sonntag",
    "zweite", "zweiten", "dritte", "dritten", "vierte", "vierten",
    "fünfte", "fünften", "sechste", "sechsten",
    "unser", "unsere", "unseren", "unserem", "unserer",
    "jener", "jene", "jenen", "jeden", "jedem",
    "obwohl", "während", "bevor", "nachdem", "sobald", "solange",
    "falls", "sofern", "gegenüber", "innerhalb", "außerhalb",
    "anstatt", "anstelle", "aufgrund", "mithilfe",
    "bezüglich", "hinsichtlich", "laut", "gemäß", "zufolge",
    "entsprechend", "seit", "statt", "samt", "wobei", "sowie",
    "hierbei", "hierzu", "daraus", "somit", "folglich", "hingegen",
    "vielmehr", "andererseits", "einerseits", "nämlich", "schließlich",
    "letztlich", "insofern", "soweit", "sowohl", "weder", "entweder",
    "zumindest", "mindestens", "höchstens", "tatsächlich", "eigentlich",
    "offenbar", "offensichtlich", "anscheinend", "möglicherweise",
    "wahrscheinlich", "jedenfalls", "ohnehin", "sowieso", "gleichwohl",
    "indes", "derweil", "seither", "fortan", "nunmehr", "grundsätzlich",
    "weitgehend", "infolge", "infolgedessen", "anhand", "sodass",
    "insgesamt", "insbesondere", "demnach",
    "abschnitt", "artikel", "weblink", "weblinks", "literatur",
    "einzelnachweis", "einzelnachweise", "hauptartikel",
    "kategorie", "kategorien", "siehe",
    "usw", "bzw", "evtl", "ggf", "inkl", "exkl", "sog", "bspw", "vgl",
}
GERMAN_STOPWORDS_CF: frozenset[str] = frozenset(s.casefold() for s in _RAW_STOPWORDS)

_PROPER_NOUNS_CF: frozenset[str] = frozenset({
    "berlin", "münchen", "hamburg", "köln", "frankfurt", "stuttgart",
    "düsseldorf", "dortmund", "essen", "leipzig", "bremen", "dresden",
    "hannover", "nürnberg", "duisburg", "bochum", "bonn",
    "deutschland", "österreich", "schweiz", "europa",
    "paris", "london", "washington", "peking", "tokio", "moskau",
    "müller", "schmidt", "schneider", "fischer", "weber", "becker",
    "schulz", "hoffmann", "schäfer", "koch", "richter", "schwarz",
    "friedrich", "johannes", "wilhelm", "wolfgang", "heinrich",
    "thomas", "michael", "stefan", "andreas", "christian",
    "volkswagen", "mercedes", "bmw", "audi", "porsche", "opel",
    "ford", "toyota", "honda", "nissan", "hyundai", "renault",
    "peugeot", "fiat", "volvo", "tesla", "ferrari", "lamborghini",
    "bosch", "continental", "michelin", "pirelli", "bridgestone",
})

TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß]{3,}(?:-[A-Za-zÄÖÜäöüß]{2,})*")


# ---------------------------------------------------------------------------
# BUG FIX: URL'deki umlauts'u percent-encode et
# ---------------------------------------------------------------------------
def fix_url_encoding(url: str) -> str:
    """
    ä → %C3%A4, ö → %C3%B6, ü → %C3%BC vb.
    Önceki çalıştırmada bu hata yüzünden 20+ URL atlanmıştı.
    """
    parts = _up.urlsplit(url)
    encoded_path = _up.quote(parts.path, safe="/:@!$&'()*+,;=")
    return _up.urlunsplit(parts._replace(path=encoded_path))


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
        return el_id in self.SKIP_IDS or bool(el_classes & self.SKIP_CLASSES)

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
                    s = chunk.strip()
                    if s:
                        parts.append(s)
            return " ".join(p for p in parts).strip()

        main_text = _join(self.main_chunks)
        body_text = _join(self.all_chunks)
        chosen = main_text if len(main_text) >= 200 else body_text
        chosen = re.sub(r"[ \t]{2,}", " ", chosen)
        chosen = re.sub(r"\n{3,}", "\n\n", chosen)
        return chosen.strip()


# ---------------------------------------------------------------------------
# URL'den metin çek — encoding fix dahil
# ---------------------------------------------------------------------------
def fetch_text(url: str) -> str:
    url = fix_url_encoding(url)   # <-- BUG FIX burada
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
# Yardımcı fonksiyonlar
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

def guess_pos(token: str) -> str:
    base = strip_article(token)
    if token[:1].isupper() and " " not in base:
        return "isim"
    bl = base.lower()
    if bl.endswith(("en", "ern", "eln")):
        return "fiil"
    if bl.endswith(("lich", "isch", "ig", "bar", "sam", "haft", "los", "voll")):
        return "sıfat"
    return "isim"


# ---------------------------------------------------------------------------
# WikDict çeviri arama
# ---------------------------------------------------------------------------
def lookup_translation(term: str, cursor: sqlite3.Cursor | None) -> dict:
    if cursor is None:
        return {"translation": "", "written_rep": ""}

    lower = cf(strip_article(term))
    lookup_terms: list[str] = [term.strip(), lower]

    for suffix, repl in [("iert", "ieren"), ("test", "en"), ("tet", "en"),
                          ("st", "en"), ("te", "en")]:
        if lower.endswith(suffix) and len(lower) > len(suffix) + 2:
            lookup_terms.append(lower[: -len(suffix)] + repl)
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
            translations: list[str] = []
            seen_tr: set[str] = set()
            for part in str(row[1] or "").split("|"):
                p = part.strip()
                k = cf(p)
                if not p or k in seen_tr or len(p) < 2:
                    continue
                seen_tr.add(k)
                translations.append(p)
            return {
                "translation": ", ".join(translations[:4]),
                "written_rep": str(row[0] or ""),
            }
    return {"translation": "", "written_rep": ""}


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
            print(f"  [HATA kaydet] {p}: {e}", file=sys.stderr)

def build_existing_keys(records: list[dict]) -> set[str]:
    keys: set[str] = set()
    for r in records:
        a = (r.get("almanca", "") or "").strip()
        keys.add(cf(a))
        keys.add(cf(strip_article(a)))
    return keys

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
) -> list[dict]:
    html = fetch_text(url)
    if not html:
        return []
    parser = VisibleTextExtractor()
    parser.feed(html)
    text = parser.get_text()
    if not text:
        return []
    print(f"  Metin: {len(text):,} karakter")

    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    lowercase_seen: set[str] = set()

    for token in TOKEN_RE.findall(text):
        if token[:1].islower():
            lowercase_seen.add(cf(token))

    for token in TOKEN_RE.findall(text):
        norm = cf(token)
        if not norm or len(norm) < 4 or len(norm) > 40:
            continue
        if is_stopword(token) or is_proper_noun(token):
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
        if not sug["translation"] or len(sug["translation"].strip()) < 2:
            continue
        wr_key = cf(sug.get("written_rep", ""))
        if wr_key and wr_key != norm and wr_key in existing_keys:
            continue
        # Çekim formu filtresi
        skip = False
        for suffix in ("es", "en", "er", "em"):
            if german.endswith(suffix):
                base_try = german[: -len(suffix)]
                if cf(base_try) in existing_keys:
                    skip = True
                    break
        if skip:
            continue
        candidates.append({
            "almanca": german,
            "turkce": sug["translation"],
            "pos": guess_pos(german),
            "freq": freq,
            "written_rep": sug["written_rep"],
        })
    return candidates


def candidate_to_record(cand: dict, source_url: str) -> dict:
    almanca = cand["almanca"]
    artikel = ""
    wr = cand.get("written_rep", "")
    for art in ("der ", "die ", "das "):
        if wr.lower().startswith(art):
            artikel = art.strip()
            almanca = wr[len(art):]
            break
    topic = source_url.split("/wiki/")[-1].replace("_", " ")
    source_label = "kfz-tech.de" if "kfz-tech.de" in source_url else "Wikipedia DE"
    return {
        "almanca": almanca,
        "artikel": artikel,
        "turkce": cand["turkce"],
        "kategoriler": ["otomotiv"],
        "aciklama_turkce": "",
        "ilgili_kayitlar": [],
        "tur": cand["pos"],
        "ornek_almanca": "",
        "ornek_turkce": "",
        "ornekler": [],
        "kaynak": f"WikDict; {source_label}",
        "kaynak_url": f"https://kaikki.org/dewiktionary/rawdata.html; {source_url}",
        "ceviri_durumu": "kaynak-izli",
        "ceviri_inceleme_notu": "",
        "ceviri_kaynaklari": [],
        "not": f"URL-import: otomotiv — {topic}",
        "referans_linkler": build_ref_links(almanca),
        "seviye": "",
        "genitiv_endung": "",
        "kelime_ailesi": [],
    }


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 65)
    print("enrich_automotive.py — Almanca otomotiv terim zenginlestirme")
    print(f"URL sayisi: {len(SOURCE_URLS)}")
    print("BUG FIX: umlaut URL encoding duzeltildi (a/o/u -> percent-encode)")
    print("=" * 65)

    if WIKDICT_PATH.exists():
        conn = sqlite3.connect(str(WIKDICT_PATH))
        cursor = conn.cursor()
        print(f"WikDict: {WIKDICT_PATH}")
    else:
        conn = None
        cursor = None
        print(f"[UYARI] WikDict bulunamadi", file=sys.stderr)

    records = load_dictionary()
    existing_keys = build_existing_keys(records)
    print(f"Mevcut sozluk: {len(records)} kayit\n")

    all_new: list[dict] = []
    added_keys: set[str] = set(existing_keys)
    url_stats: dict[str, int] = {}
    total = len(SOURCE_URLS)

    for i, url in enumerate(SOURCE_URLS, 1):
        topic = url.split("/wiki/")[-1].replace("_", " ") if "/wiki/" in url else url.split("/")[-1]
        print(f"\n[{i}/{total}] {topic}")
        candidates = extract_candidates(url, added_keys, cursor, min_freq=2)
        url_new = 0
        for cand in candidates:
            norm = cf(cand["almanca"])
            norm_base = cf(strip_article(cand["almanca"]))
            if norm in added_keys or norm_base in added_keys:
                continue
            rec = candidate_to_record(cand, url)
            all_new.append(rec)
            added_keys.add(norm)
            added_keys.add(norm_base)
            url_new += 1
            print(f"    + {rec['almanca']} -> {rec['turkce']}")
        url_stats[topic] = url_new
        print(f"  => {url_new} yeni kelime")

        if i % 20 == 0 and all_new:
            print(f"\n  [ARA KAYIT] {len(all_new)} kayit...")
            save_dictionary(records + all_new)

    if conn:
        conn.close()

    print(f"\n{'='*65}")
    print(f"TOPLAM YENI OTOMOTIV TERIMI: {len(all_new)}")
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

    print(f"\nToplam {len(all_new)} otomotiv terimi eklendi.")
    print(f"Sozluk artik {len(records)} kayit iceriyor.")


if __name__ == "__main__":
    main()
