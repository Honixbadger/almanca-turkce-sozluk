#!/usr/bin/env python3
"""
enrich_quality.py
=================
Sözlüğü iki yönde geliştirir:

  1. YENİ KELİMELER: Wikipedia DE + açık Almanca kaynaklardan WikDict çevirisi
     olan kelimeleri ekler (min_freq=1, WikDict teyidi yeterli).

  2. MEVCUT KAYITLARI ZENGİNLEŞTİR:
     - Eğer sözlükte var olan bir kelimenin WikDict'te kayıtta olmayan yeni
       bir Türkçe anlamı varsa, `turkce` alanına eklenir.
     - Kelimenin bulunduğu metinden kısa, temiz bir örnek cümle çıkarılarak
       `ornek_almanca` (boşsa) ve `ornekler` listesine eklenir.

URL havuzu: ~400 Wikipedia DE sayfası — otomotiv ağırlıklı, tarih + genel.

Kaynak: Wikipedia DE (CC BY-SA 3.0), WikDict de-tr veritabanı
Çalıştır: python scripts/enrich_quality.py
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
# URL havuzu — ~400 Wikipedia DE sayfası
# ---------------------------------------------------------------------------
SOURCE_URLS = [
    # ================================================================
    # OTOMOTİV — Motor & Tahrik
    # ================================================================
    "https://de.wikipedia.org/wiki/Kraftfahrzeug",
    "https://de.wikipedia.org/wiki/Verbrennungsmotor",
    "https://de.wikipedia.org/wiki/Ottomotor",
    "https://de.wikipedia.org/wiki/Dieselmotor",
    "https://de.wikipedia.org/wiki/Elektromotor",
    "https://de.wikipedia.org/wiki/Kurbelwelle",
    "https://de.wikipedia.org/wiki/Nockenwelle",
    "https://de.wikipedia.org/wiki/Kolben_(Technik)",
    "https://de.wikipedia.org/wiki/Zylinderkopf",
    "https://de.wikipedia.org/wiki/Motorblock",
    "https://de.wikipedia.org/wiki/Turbolader",
    "https://de.wikipedia.org/wiki/Verdichter",
    "https://de.wikipedia.org/wiki/Motorsteuerung",
    "https://de.wikipedia.org/wiki/Kraftstoffeinspritzung",
    "https://de.wikipedia.org/wiki/Einspritzanlage",
    "https://de.wikipedia.org/wiki/Vergaser",
    "https://de.wikipedia.org/wiki/Zündanlage",
    "https://de.wikipedia.org/wiki/Zündkerze",
    "https://de.wikipedia.org/wiki/Anlasser",
    "https://de.wikipedia.org/wiki/Lichtmaschine",
    "https://de.wikipedia.org/wiki/Keilriemen",
    "https://de.wikipedia.org/wiki/Steuerkette",
    "https://de.wikipedia.org/wiki/Steuerriemen",
    "https://de.wikipedia.org/wiki/Ventiltrieb",
    "https://de.wikipedia.org/wiki/Abgasanlage",
    "https://de.wikipedia.org/wiki/Abgasrückführung",
    "https://de.wikipedia.org/wiki/Katalysator",
    "https://de.wikipedia.org/wiki/Partikelfilter",
    "https://de.wikipedia.org/wiki/Abgas",

    # OTOMOTİV — Soğutma & Yağlama
    "https://de.wikipedia.org/wiki/Motork%C3%BChlung",
    "https://de.wikipedia.org/wiki/Motoröl",
    "https://de.wikipedia.org/wiki/Schmierung",
    "https://de.wikipedia.org/wiki/Kühlmittel",

    # OTOMOTİV — Şanzıman & Aktarma organları
    "https://de.wikipedia.org/wiki/Fahrzeuggetriebe",
    "https://de.wikipedia.org/wiki/Schaltgetriebe",
    "https://de.wikipedia.org/wiki/Automatikgetriebe",
    "https://de.wikipedia.org/wiki/Doppelkupplungsgetriebe",
    "https://de.wikipedia.org/wiki/Stufenlosgetriebe",
    "https://de.wikipedia.org/wiki/Kupplung",
    "https://de.wikipedia.org/wiki/Antriebswelle",
    "https://de.wikipedia.org/wiki/Gelenkwelle",
    "https://de.wikipedia.org/wiki/Differentialgetriebe",
    "https://de.wikipedia.org/wiki/Allradantrieb",
    "https://de.wikipedia.org/wiki/Vorderradantrieb",
    "https://de.wikipedia.org/wiki/Hinterradantrieb",

    # OTOMOTİV — Süspansiyon & Direksiyon
    "https://de.wikipedia.org/wiki/Radaufhängung",
    "https://de.wikipedia.org/wiki/Stoßdämpfer",
    "https://de.wikipedia.org/wiki/Schraubenfeder",
    "https://de.wikipedia.org/wiki/Luftfederung",
    "https://de.wikipedia.org/wiki/Stabilisator_(Automobil)",
    "https://de.wikipedia.org/wiki/Lenkung",
    "https://de.wikipedia.org/wiki/Servolenkung",
    "https://de.wikipedia.org/wiki/Lenkrad",
    "https://de.wikipedia.org/wiki/Spurstange",
    "https://de.wikipedia.org/wiki/Achse_(Maschinenelement)",
    "https://de.wikipedia.org/wiki/Starrachse",

    # OTOMOTİV — Fren sistemi
    "https://de.wikipedia.org/wiki/Bremse_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/Scheibenbremse",
    "https://de.wikipedia.org/wiki/Trommelbremse",
    "https://de.wikipedia.org/wiki/Bremsscheibe",
    "https://de.wikipedia.org/wiki/Bremsbelag",
    "https://de.wikipedia.org/wiki/Antiblockiersystem",
    "https://de.wikipedia.org/wiki/Fahrdynamikregelung",
    "https://de.wikipedia.org/wiki/Traktionskontrolle",

    # OTOMOTİV — Lastik & Jant
    "https://de.wikipedia.org/wiki/Reifen",
    "https://de.wikipedia.org/wiki/Reifenbezeichnung",
    "https://de.wikipedia.org/wiki/Felge",
    "https://de.wikipedia.org/wiki/Reifendruck",
    "https://de.wikipedia.org/wiki/Winterreifen",

    # OTOMOTİV — Kaporta & İç mekan
    "https://de.wikipedia.org/wiki/Karosserie",
    "https://de.wikipedia.org/wiki/Fahrzeugrahmen",
    "https://de.wikipedia.org/wiki/Selbsttragende_Karosserie",
    "https://de.wikipedia.org/wiki/Motorhaube",
    "https://de.wikipedia.org/wiki/Windschutzscheibe",
    "https://de.wikipedia.org/wiki/T%C3%BCr",
    "https://de.wikipedia.org/wiki/Kofferraum",
    "https://de.wikipedia.org/wiki/Armaturenbrett",
    "https://de.wikipedia.org/wiki/Tachometer",
    "https://de.wikipedia.org/wiki/Fahrzeugbeleuchtung",
    "https://de.wikipedia.org/wiki/Rücklicht",
    "https://de.wikipedia.org/wiki/Airbag",
    "https://de.wikipedia.org/wiki/Sicherheitsgurt",

    # OTOMOTİV — Yakıt & Enerji
    "https://de.wikipedia.org/wiki/Kraftstoff",
    "https://de.wikipedia.org/wiki/Benzin",
    "https://de.wikipedia.org/wiki/Dieselkraftstoff",
    "https://de.wikipedia.org/wiki/Flüssiggas",
    "https://de.wikipedia.org/wiki/Tankstelle",

    # OTOMOTİV — Elektrikli & Hibrit
    "https://de.wikipedia.org/wiki/Elektromobilität",
    "https://de.wikipedia.org/wiki/Elektrofahrzeug",
    "https://de.wikipedia.org/wiki/Hybridfahrzeug",
    "https://de.wikipedia.org/wiki/Brennstoffzelle",
    "https://de.wikipedia.org/wiki/Lithium-Ionen-Akkumulator",
    "https://de.wikipedia.org/wiki/Ladesäule",
    "https://de.wikipedia.org/wiki/Rekuperation",

    # OTOMOTİV — Sürücü destek sistemleri
    "https://de.wikipedia.org/wiki/Fahrassistenzsystem",
    "https://de.wikipedia.org/wiki/Tempomat",
    "https://de.wikipedia.org/wiki/Totwinkelassistent",
    "https://de.wikipedia.org/wiki/Spurhalteassistent",
    "https://de.wikipedia.org/wiki/Notbremsassistent",
    "https://de.wikipedia.org/wiki/Einparkhilfe",
    "https://de.wikipedia.org/wiki/Autonomes_Fahren",
    "https://de.wikipedia.org/wiki/Satellitennavigation",

    # OTOMOTİV — Araç türleri & segmentler
    "https://de.wikipedia.org/wiki/Fahrzeugsegment",
    "https://de.wikipedia.org/wiki/Limousine",
    "https://de.wikipedia.org/wiki/Kombilimousine",
    "https://de.wikipedia.org/wiki/SUV",
    "https://de.wikipedia.org/wiki/Cabriolet",
    "https://de.wikipedia.org/wiki/Coup%C3%A9",
    "https://de.wikipedia.org/wiki/Pickup-Truck",
    "https://de.wikipedia.org/wiki/Van",
    "https://de.wikipedia.org/wiki/Sportwagen",
    "https://de.wikipedia.org/wiki/Nutzfahrzeug",
    "https://de.wikipedia.org/wiki/Lastkraftwagen",
    "https://de.wikipedia.org/wiki/Omnibus",
    "https://de.wikipedia.org/wiki/Motorrad",

    # OTOMOTİV — Hukuki & teknik düzenlemeler
    "https://de.wikipedia.org/wiki/Kfz-Versicherung",
    "https://de.wikipedia.org/wiki/Hauptuntersuchung",
    "https://de.wikipedia.org/wiki/Kraftfahrzeugzulassung",
    "https://de.wikipedia.org/wiki/Kraftfahrzeugsteuer",
    "https://de.wikipedia.org/wiki/Stra%C3%9Fenverkehrs-Ordnung",
    "https://de.wikipedia.org/wiki/Autobahn",
    "https://de.wikipedia.org/wiki/Bundesstra%C3%9Fe",
    "https://de.wikipedia.org/wiki/Verkehrszeichen_(Deutschland)",
    "https://de.wikipedia.org/wiki/F%C3%BChrerschein",
    "https://de.wikipedia.org/wiki/Fahrschule",
    "https://de.wikipedia.org/wiki/Kraftfahrzeugmechatroniker",

    # OTOMOTİV — Markalar & tarih
    "https://de.wikipedia.org/wiki/Volkswagen",
    "https://de.wikipedia.org/wiki/BMW",
    "https://de.wikipedia.org/wiki/Mercedes-Benz",
    "https://de.wikipedia.org/wiki/Audi",
    "https://de.wikipedia.org/wiki/Porsche",
    "https://de.wikipedia.org/wiki/Opel",
    "https://de.wikipedia.org/wiki/Geschichte_des_Automobils",

    # ================================================================
    # TARİH
    # ================================================================
    "https://de.wikipedia.org/wiki/Erster_Weltkrieg",
    "https://de.wikipedia.org/wiki/Zweiter_Weltkrieg",
    "https://de.wikipedia.org/wiki/Weimarer_Republik",
    "https://de.wikipedia.org/wiki/Deutsche_Wiedervereinigung",
    "https://de.wikipedia.org/wiki/Kalter_Krieg",
    "https://de.wikipedia.org/wiki/Nationalsozialismus",
    "https://de.wikipedia.org/wiki/Berliner_Mauer",
    "https://de.wikipedia.org/wiki/R%C3%B6misches_Reich",
    "https://de.wikipedia.org/wiki/Mittelalter",
    "https://de.wikipedia.org/wiki/Renaissance",
    "https://de.wikipedia.org/wiki/Reformation",
    "https://de.wikipedia.org/wiki/Aufkl%C3%A4rung",
    "https://de.wikipedia.org/wiki/Industrielle_Revolution",
    "https://de.wikipedia.org/wiki/Kolonialismus",
    "https://de.wikipedia.org/wiki/Franz%C3%B6sische_Revolution",
    "https://de.wikipedia.org/wiki/Russische_Revolution",
    "https://de.wikipedia.org/wiki/Deutsche_Teilung",
    "https://de.wikipedia.org/wiki/Otto_von_Bismarck",
    "https://de.wikipedia.org/wiki/Karl_der_Gro%C3%9Fe",
    "https://de.wikipedia.org/wiki/Dreißigjähriger_Krieg",
    "https://de.wikipedia.org/wiki/Osmanisches_Reich",
    "https://de.wikipedia.org/wiki/Byzantinisches_Reich",
    "https://de.wikipedia.org/wiki/Antikes_Griechenland",
    "https://de.wikipedia.org/wiki/Kreuzzüge",
    "https://de.wikipedia.org/wiki/Beulenpest",
    "https://de.wikipedia.org/wiki/Sklaverei",

    # ================================================================
    # POLİTİKA & DEVLET
    # ================================================================
    "https://de.wikipedia.org/wiki/Bundesregierung_(Deutschland)",
    "https://de.wikipedia.org/wiki/Demokratie",
    "https://de.wikipedia.org/wiki/Grundgesetz_f%C3%BCr_die_Bundesrepublik_Deutschland",
    "https://de.wikipedia.org/wiki/Bundesrat_(Deutschland)",
    "https://de.wikipedia.org/wiki/Wahlrecht_(Deutschland)",
    "https://de.wikipedia.org/wiki/Volksabstimmung",
    "https://de.wikipedia.org/wiki/Partei_(Politik)",
    "https://de.wikipedia.org/wiki/Koalition_(Politik)",
    "https://de.wikipedia.org/wiki/Bürgermeister",
    "https://de.wikipedia.org/wiki/Landtag",
    "https://de.wikipedia.org/wiki/Staatsangehörigkeit",
    "https://de.wikipedia.org/wiki/Diplomatie",
    "https://de.wikipedia.org/wiki/Internationale_Beziehungen",
    "https://de.wikipedia.org/wiki/NATO",
    "https://de.wikipedia.org/wiki/Europ%C3%A4ische_Union",
    "https://de.wikipedia.org/wiki/Vereinte_Nationen",

    # ================================================================
    # HUKUK
    # ================================================================
    "https://de.wikipedia.org/wiki/Gericht",
    "https://de.wikipedia.org/wiki/Vertrag",
    "https://de.wikipedia.org/wiki/Strafrecht_(Deutschland)",
    "https://de.wikipedia.org/wiki/Zivilrecht_(Deutschland)",
    "https://de.wikipedia.org/wiki/Rechtsanwalt",
    "https://de.wikipedia.org/wiki/Klage_(Zivilprozess)",
    "https://de.wikipedia.org/wiki/Urteil_(Recht)",
    "https://de.wikipedia.org/wiki/Datenschutz",
    "https://de.wikipedia.org/wiki/Urheberrecht",
    "https://de.wikipedia.org/wiki/Mietrecht",
    "https://de.wikipedia.org/wiki/Arbeitsrecht_(Deutschland)",
    "https://de.wikipedia.org/wiki/Steuerhinterziehung",

    # ================================================================
    # EKONOMİ & İŞ
    # ================================================================
    "https://de.wikipedia.org/wiki/Wirtschaft_Deutschlands",
    "https://de.wikipedia.org/wiki/Arbeitsmarkt",
    "https://de.wikipedia.org/wiki/Steuer",
    "https://de.wikipedia.org/wiki/Einkommensteuer_(Deutschland)",
    "https://de.wikipedia.org/wiki/Umsatzsteuer_(Deutschland)",
    "https://de.wikipedia.org/wiki/Versicherung",
    "https://de.wikipedia.org/wiki/Immobilie",
    "https://de.wikipedia.org/wiki/Unternehmen",
    "https://de.wikipedia.org/wiki/Aktie",
    "https://de.wikipedia.org/wiki/Kredit",
    "https://de.wikipedia.org/wiki/Inflation",
    "https://de.wikipedia.org/wiki/Arbeitslosigkeit",
    "https://de.wikipedia.org/wiki/Mindestlohn",
    "https://de.wikipedia.org/wiki/Gewerkschaft",
    "https://de.wikipedia.org/wiki/Altersrente",
    "https://de.wikipedia.org/wiki/Insolvenz",
    "https://de.wikipedia.org/wiki/Buchhaltung",
    "https://de.wikipedia.org/wiki/Handel",
    "https://de.wikipedia.org/wiki/Export",
    "https://de.wikipedia.org/wiki/Import",
    "https://de.wikipedia.org/wiki/Marketing",
    "https://de.wikipedia.org/wiki/Wertpapierb%C3%B6rse",
    "https://de.wikipedia.org/wiki/Globalisierung",

    # ================================================================
    # TEKNOLOJİ & MÜHENDİSLİK
    # ================================================================
    "https://de.wikipedia.org/wiki/Maschinenbau",
    "https://de.wikipedia.org/wiki/Elektrotechnik",
    "https://de.wikipedia.org/wiki/Informatik",
    "https://de.wikipedia.org/wiki/K%C3%BCnstliche_Intelligenz",
    "https://de.wikipedia.org/wiki/Robotik",
    "https://de.wikipedia.org/wiki/3D-Druck",
    "https://de.wikipedia.org/wiki/Telekommunikation",
    "https://de.wikipedia.org/wiki/Internet",
    "https://de.wikipedia.org/wiki/Halbleiter",
    "https://de.wikipedia.org/wiki/Solarzelle",
    "https://de.wikipedia.org/wiki/Windenergie",
    "https://de.wikipedia.org/wiki/Kernenergie",
    "https://de.wikipedia.org/wiki/Elektrizit%C3%A4t",
    "https://de.wikipedia.org/wiki/Hydraulik",
    "https://de.wikipedia.org/wiki/Pneumatik",
    "https://de.wikipedia.org/wiki/Schweißen",
    "https://de.wikipedia.org/wiki/Gie%C3%9Ferei",
    "https://de.wikipedia.org/wiki/Zerspanung",
    "https://de.wikipedia.org/wiki/Werkzeugmaschine",
    "https://de.wikipedia.org/wiki/Nanotechnologie",

    # ================================================================
    # SAĞLIK & TIP
    # ================================================================
    "https://de.wikipedia.org/wiki/Gesundheitssystem",
    "https://de.wikipedia.org/wiki/Gesetzliche_Krankenversicherung",
    "https://de.wikipedia.org/wiki/Ernährung",
    "https://de.wikipedia.org/wiki/Impfung",
    "https://de.wikipedia.org/wiki/Krankenhaus",
    "https://de.wikipedia.org/wiki/Herzerkrankung",
    "https://de.wikipedia.org/wiki/Diabetes_mellitus",
    "https://de.wikipedia.org/wiki/Krebs_(Medizin)",
    "https://de.wikipedia.org/wiki/Chirurgie",
    "https://de.wikipedia.org/wiki/Pharmakologie",
    "https://de.wikipedia.org/wiki/Psychiatrie",
    "https://de.wikipedia.org/wiki/Nervensystem",

    # ================================================================
    # BİLİM
    # ================================================================
    "https://de.wikipedia.org/wiki/Physik",
    "https://de.wikipedia.org/wiki/Chemie",
    "https://de.wikipedia.org/wiki/Biologie",
    "https://de.wikipedia.org/wiki/Mathematik",
    "https://de.wikipedia.org/wiki/Astronomie",
    "https://de.wikipedia.org/wiki/Geologie",
    "https://de.wikipedia.org/wiki/Genetik",
    "https://de.wikipedia.org/wiki/Evolution",
    "https://de.wikipedia.org/wiki/Thermodynamik",
    "https://de.wikipedia.org/wiki/Mechanik",
    "https://de.wikipedia.org/wiki/Elektromagnetismus",
    "https://de.wikipedia.org/wiki/Quantenmechanik",

    # ================================================================
    # DOĞA & ÇEVRE
    # ================================================================
    "https://de.wikipedia.org/wiki/Klimawandel",
    "https://de.wikipedia.org/wiki/Umweltschutz",
    "https://de.wikipedia.org/wiki/Nachhaltigkeit",
    "https://de.wikipedia.org/wiki/Wald",
    "https://de.wikipedia.org/wiki/Landwirtschaft",
    "https://de.wikipedia.org/wiki/Meeresverschmutzung",
    "https://de.wikipedia.org/wiki/Artensterben",
    "https://de.wikipedia.org/wiki/Erneuerbare_Energie",

    # ================================================================
    # EĞİTİM & KÜLTÜR
    # ================================================================
    "https://de.wikipedia.org/wiki/Bildungssystem_in_Deutschland",
    "https://de.wikipedia.org/wiki/Universit%C3%A4t",
    "https://de.wikipedia.org/wiki/Berufsausbildung",
    "https://de.wikipedia.org/wiki/Musik",
    "https://de.wikipedia.org/wiki/Theater",
    "https://de.wikipedia.org/wiki/Film",
    "https://de.wikipedia.org/wiki/Architektur",
    "https://de.wikipedia.org/wiki/Literatur",
    "https://de.wikipedia.org/wiki/Philosophie",
    "https://de.wikipedia.org/wiki/Sprache",
    "https://de.wikipedia.org/wiki/Journalismus",
    "https://de.wikipedia.org/wiki/Soziale_Medien",

    # ================================================================
    # GÜNDELİK HAYAT
    # ================================================================
    "https://de.wikipedia.org/wiki/Wohnung",
    "https://de.wikipedia.org/wiki/Miete",
    "https://de.wikipedia.org/wiki/Haushaltsf%C3%BChrung",
    "https://de.wikipedia.org/wiki/Einkaufen",
    "https://de.wikipedia.org/wiki/Supermarkt",
    "https://de.wikipedia.org/wiki/Kochen",
    "https://de.wikipedia.org/wiki/Brot",
    "https://de.wikipedia.org/wiki/Wein",
    "https://de.wikipedia.org/wiki/Bier",
    "https://de.wikipedia.org/wiki/Sport",
    "https://de.wikipedia.org/wiki/Fu%C3%9Fball",
    "https://de.wikipedia.org/wiki/Reisen",
    "https://de.wikipedia.org/wiki/Tourismus",
    "https://de.wikipedia.org/wiki/Hotel",
    "https://de.wikipedia.org/wiki/Flughafen",
    "https://de.wikipedia.org/wiki/Deutsche_Bahn",
    "https://de.wikipedia.org/wiki/Fahrrad",
    "https://de.wikipedia.org/wiki/Familie",
    "https://de.wikipedia.org/wiki/Kindheit",
    "https://de.wikipedia.org/wiki/Erziehung",
    "https://de.wikipedia.org/wiki/Arbeit_(Wirtschaft)",
    "https://de.wikipedia.org/wiki/Beruf",
    "https://de.wikipedia.org/wiki/Ehrenamt",

    # GÜNLÜK HAYAT — Ek konular
    "https://de.wikipedia.org/wiki/Wohnung",
    "https://de.wikipedia.org/wiki/Miete",
    "https://de.wikipedia.org/wiki/Nachbarschaft",
    "https://de.wikipedia.org/wiki/Einkaufen",
    "https://de.wikipedia.org/wiki/Lebensmittel",
    "https://de.wikipedia.org/wiki/Ern%C3%A4hrung",
    "https://de.wikipedia.org/wiki/Gesundheit",
    "https://de.wikipedia.org/wiki/Krankenhaus",
    "https://de.wikipedia.org/wiki/Arzt",
    "https://de.wikipedia.org/wiki/Apotheke",
    "https://de.wikipedia.org/wiki/Medikament",
    "https://de.wikipedia.org/wiki/Schule",
    "https://de.wikipedia.org/wiki/Universit%C3%A4t",
    "https://de.wikipedia.org/wiki/Studium",
    "https://de.wikipedia.org/wiki/Berufsausbildung",
    "https://de.wikipedia.org/wiki/Praktikum",
    "https://de.wikipedia.org/wiki/Bewerbung",
    "https://de.wikipedia.org/wiki/Arbeitsvertrag",
    "https://de.wikipedia.org/wiki/K%C3%BCndigung",
    "https://de.wikipedia.org/wiki/Urlaub",
    "https://de.wikipedia.org/wiki/Reisepass",
    "https://de.wikipedia.org/wiki/Beh%C3%B6rde",
    "https://de.wikipedia.org/wiki/Personalausweis",
    "https://de.wikipedia.org/wiki/Meldepflicht",
    "https://de.wikipedia.org/wiki/Steuererkl%C3%A4rung",
    "https://de.wikipedia.org/wiki/Bank",
    "https://de.wikipedia.org/wiki/Konto",
    "https://de.wikipedia.org/wiki/Kredit",
    "https://de.wikipedia.org/wiki/Zinsen",
    "https://de.wikipedia.org/wiki/Spareinlage",
    "https://de.wikipedia.org/wiki/Rente",
    "https://de.wikipedia.org/wiki/Rentenversicherung",

    # TEKNOLOJİ & BİLİM
    "https://de.wikipedia.org/wiki/Computer",
    "https://de.wikipedia.org/wiki/Software",
    "https://de.wikipedia.org/wiki/Betriebssystem",
    "https://de.wikipedia.org/wiki/Datenbank",
    "https://de.wikipedia.org/wiki/Programmierung",
    "https://de.wikipedia.org/wiki/K%C3%BCnstliche_Intelligenz",
    "https://de.wikipedia.org/wiki/Maschinelles_Lernen",
    "https://de.wikipedia.org/wiki/Internet",
    "https://de.wikipedia.org/wiki/Mobiltelefon",
    "https://de.wikipedia.org/wiki/Elektrizit%C3%A4t",
    "https://de.wikipedia.org/wiki/Batterie_(Elektrotechnik)",
    "https://de.wikipedia.org/wiki/Solarzelle",
    "https://de.wikipedia.org/wiki/Windenergie",
    "https://de.wikipedia.org/wiki/Kernenergie",
    "https://de.wikipedia.org/wiki/Klimawandel",
    "https://de.wikipedia.org/wiki/Umweltverschmutzung",
    "https://de.wikipedia.org/wiki/Recycling",
    "https://de.wikipedia.org/wiki/Nachhaltigkeit",

    # KÜLTÜR & TARİH
    "https://de.wikipedia.org/wiki/Musik",
    "https://de.wikipedia.org/wiki/Klassische_Musik",
    "https://de.wikipedia.org/wiki/Theater",
    "https://de.wikipedia.org/wiki/Film",
    "https://de.wikipedia.org/wiki/Literatur",
    "https://de.wikipedia.org/wiki/Malerei",
    "https://de.wikipedia.org/wiki/Architektur",
    "https://de.wikipedia.org/wiki/Museum",
    "https://de.wikipedia.org/wiki/Demokratie",
    "https://de.wikipedia.org/wiki/Bundesrepublik_Deutschland",
    "https://de.wikipedia.org/wiki/Europ%C3%A4ische_Union",
    "https://de.wikipedia.org/wiki/Zweiter_Weltkrieg",
    "https://de.wikipedia.org/wiki/Reformation",
    "https://de.wikipedia.org/wiki/Industrielle_Revolution",

    # OTOMOTİV — Düzeltilmiş URL'ler
    "https://de.wikipedia.org/wiki/Kupplung",
    "https://de.wikipedia.org/wiki/Stabilisator_(Automobil)",
    "https://de.wikipedia.org/wiki/Lenkung",
    "https://de.wikipedia.org/wiki/Achse_(Maschinenelement)",
    "https://de.wikipedia.org/wiki/Bremse_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/T%C3%BCr",
]

# ---------------------------------------------------------------------------
# Stopword kümesi — tümü casefold
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
    # Sıfatlar
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
    # sein/haben/werden çekimleri
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
    # Aylar & Günler (casefold ile aşağıda handle edilir)
    "januar", "februar", "märz", "april", "mai", "juni", "juli",
    "august", "september", "oktober", "november", "dezember",
    "montag", "dienstag", "mittwoch", "donnerstag",
    "freitag", "samstag", "sonntag",
    # Sıra sayıları
    "zweite", "zweiten", "zweitem", "zweiter", "zweites",
    "dritte", "dritten", "drittem", "dritter", "drittes",
    "vierte", "vierten", "fünfte", "fünften",
    # Edatlar & bağlaçlar
    "obwohl", "während", "bevor", "nachdem", "sobald", "solange",
    "falls", "sofern", "wohingegen", "gegenüber",
    "innerhalb", "außerhalb", "oberhalb", "unterhalb",
    "anstatt", "anstelle", "aufgrund", "mithilfe",
    "bezüglich", "hinsichtlich", "laut", "gemäß", "zufolge",
    "entsprechend", "seit", "statt", "samt", "wobei", "sowie",
    "hierbei", "hierzu", "daraus", "hiervon", "hierfür",
    "insgesamt", "insbesondere", "demnach", "demzufolge", "somit",
    "folglich", "hingegen", "vielmehr", "andererseits", "einerseits",
    "nämlich", "schließlich", "letztlich", "letztendlich", "insofern",
    "soweit", "sowohl", "weder", "entweder", "zumindest", "mindestens",
    "höchstens", "wenigstens", "tatsächlich", "eigentlich", "offenbar",
    "offensichtlich", "anscheinend", "möglicherweise", "wahrscheinlich",
    "vermutlich", "jedenfalls", "ohnehin", "sowieso", "gleichwohl",
    "indessen", "indes", "derweil", "unterdessen", "währenddessen",
    "seither", "fortan", "nunmehr", "grundsätzlich", "weitgehend",
    "infolge", "infolgedessen", "diesbezüglich", "inwieweit",
    "inwiefern", "anhand", "sodass",
    # Wikipedia meta
    "abschnitt", "artikel", "weblink", "weblinks", "literatur",
    "einzelnachweis", "einzelnachweise", "hauptartikel",
    "kategorie", "kategorien", "siehe",
    # Kısaltmalar
    "usw", "bzw", "evtl", "ggf", "inkl", "exkl", "sog", "bspw", "vgl",
}
GERMAN_STOPWORDS_CF: frozenset = frozenset(s.casefold() for s in _RAW_STOPWORDS)

_PROPER_NOUNS_CF: frozenset = frozenset({
    "berlin", "münchen", "hamburg", "köln", "frankfurt", "stuttgart",
    "düsseldorf", "dortmund", "essen", "leipzig", "bremen", "dresden",
    "hannover", "nürnberg", "duisburg", "bochum", "wuppertal", "bonn",
    "mannheim", "karlsruhe", "freiburg", "augsburg", "wiesbaden",
    "deutschland", "österreich", "schweiz", "europa", "brüssel",
    "paris", "london", "washington", "peking", "tokio", "moskau",
    "beijing", "new", "york", "united", "states",
    "müller", "schmidt", "schneider", "fischer", "weber", "meyer",
    "wagner", "becker", "schulz", "hoffmann", "schäfer", "koch",
    "bauer", "richter", "wolf", "schröder", "neumann",
    "schwarz", "zimmermann", "braun", "krüger", "hartmann", "lange",
    "werner", "lehmann", "walter", "maier", "mayer", "köhler",
    "krause", "steiner", "jung", "roth", "vogel", "schumacher",
    "friedrich", "johannes", "wilhelm", "wolfgang", "heinrich",
    "thomas", "michael", "stefan", "andreas", "christian",
    "markus", "matthias", "sebastian", "tobias", "alexander",
    "christoph", "samuel", "peter", "hans", "otto", "karl",
    # Araba markaları — özel isim
    "volkswagen", "mercedes", "bmw", "audi", "porsche", "opel",
    "ford", "toyota", "honda", "hyundai", "renault", "peugeot",
    "fiat", "volvo", "tesla", "ferrari", "lamborghini", "nissan",
    "mazda", "subaru", "suzuki", "mitsubishi", "skoda", "seat",
})

# ---------------------------------------------------------------------------
# Token regex
# ---------------------------------------------------------------------------
TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß]{3,}(?:-[A-Za-zÄÖÜäöüß]{2,})*")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])")

# ---------------------------------------------------------------------------
# HTML metin ayıklayıcı (aynı VisibleTextExtractor)
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
        "cookie", "banner", "advertisement",
        "breadcrumb", "pagination", "menu", "dropdown",
        "related", "recommendation", "teaser",
    }
    SKIP_IDS = {
        "toc", "references", "catlinks", "mw-navigation", "p-search",
        "nav", "footer", "header", "sidebar", "menu", "cookie-banner",
    }

    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.main_depth = 0
        self.all_chunks: list = []
        self.main_chunks: list = []

    def _should_skip_attrs(self, attrs: list) -> bool:
        attr_dict = dict(attrs)
        el_id = attr_dict.get("id", "")
        el_classes = set((attr_dict.get("class", "") or "").split())
        return el_id in self.SKIP_IDS or bool(el_classes & self.SKIP_CLASSES)

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS or self._should_skip_attrs(attrs):
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in self.MAIN_TAGS:
            self.main_depth += 1
        if tag in self.BLOCK_TAGS:
            self._append_break()

    def handle_endtag(self, tag):
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag in self.MAIN_TAGS and self.main_depth:
            self.main_depth -= 1
        if tag in self.BLOCK_TAGS:
            self._append_break()

    def handle_data(self, data):
        if self.skip_depth:
            return
        cleaned = data.strip()
        if not cleaned:
            return
        self.all_chunks.append(cleaned)
        if self.main_depth:
            self.main_chunks.append(cleaned)

    def _append_break(self):
        self.all_chunks.append("\n")
        if self.main_depth:
            self.main_chunks.append("\n")

    def get_text(self) -> str:
        def _join(chunks):
            parts = []
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
# URL encoding
# ---------------------------------------------------------------------------
def fix_url_encoding(url: str) -> str:
    parts = _up.urlsplit(url)
    # Decode any existing percent-encoding first, then re-encode cleanly to avoid double-encoding
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
    """Metni cümlelere böl."""
    raw = SENT_SPLIT_RE.split(text)
    # Ayrıca \n ile de böl
    sentences = []
    for chunk in raw:
        for line in chunk.split("\n"):
            line = line.strip()
            if line:
                sentences.append(line)
    return sentences


def find_example_sentence(sentences: list, bare_word: str) -> str:
    """bare_word'ü içeren kısa ve temiz bir cümle bul."""
    bare_cf = bare_word.casefold()
    good = []
    for sent in sentences:
        sent = sent.strip()
        if bare_cf not in sent.casefold():
            continue
        # Uzunluk filtresi
        if not (45 <= len(sent) <= 280):
            continue
        # Çok fazla sayı/parantez içermesin
        if sent.count("[") + sent.count("{") + sent.count("(") > 4:
            continue
        # Çok fazla rakam içermesin (tablo verisi olabilir)
        digit_ratio = sum(1 for c in sent if c.isdigit()) / max(len(sent), 1)
        if digit_ratio > 0.2:
            continue
        good.append(sent)

    if not good:
        return ""
    # En kısa ama anlamlı (en az 4 token) olanı seç
    good.sort(key=len)
    for sent in good:
        if len(TOKEN_RE.findall(sent)) >= 4:
            return sent
    return good[0] if good else ""


# ---------------------------------------------------------------------------
# Yeni anlam tespiti
# ---------------------------------------------------------------------------
def find_new_meanings(existing_turkce: str, wikdict_translation: str) -> list:
    """WikDict'teki çevirilerde mevcut turkce alanında olmayan yenileri bul."""
    if not wikdict_translation:
        return []

    # Mevcut anlamları normalize et
    existing_parts: set = set()
    for part in re.split(r"[;,|/]", existing_turkce or ""):
        p = part.strip().casefold()
        if p and len(p) > 1:
            existing_parts.add(p)
        # Kısmi eşleşme için: kelimeler
        for word in p.split():
            if len(word) > 2:
                existing_parts.add(word)

    new_meanings = []
    for tr in wikdict_translation.split(", "):
        tr = tr.strip()
        if not tr or len(tr) < 2:
            continue
        tr_cf = tr.casefold()
        # Zaten var mı?
        if tr_cf in existing_parts:
            continue
        # Kelime bazında örtüşme var mı?
        tr_words = set(w for w in tr_cf.split() if len(w) > 2)
        if tr_words and tr_words.issubset(existing_parts):
            continue
        # Almanca kelimesi gibi görünüyor (büyük harf)?  atla (çeviri değil)
        if tr[:1].isupper() and len(tr) > 3:
            continue
        new_meanings.append(tr)

    return new_meanings[:3]  # Maksimum 3 yeni anlam


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
    """cf(almanca) ve cf(bare) → kayıt indeksi eşlemesi."""
    idx: dict = {}
    for i, r in enumerate(records):
        almanca = (r.get("almanca", "") or "").strip()
        if almanca:
            idx[cf(almanca)] = i
            idx[cf(strip_article(almanca))] = i
    return idx


# ---------------------------------------------------------------------------
# Yeni aday çıkarma (min_freq=1)
# ---------------------------------------------------------------------------
def extract_candidates(
    url: str,
    text: str,
    existing_keys: set,
    cursor,
    min_freq: int = 1,
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
# Mevcut kayıtlar için güncelleme tespiti
# ---------------------------------------------------------------------------
def find_updates(
    text: str,
    sentences: list,
    records: list,
    record_index: dict,
    cursor,
    processed_indices: set,
) -> list:
    """
    Returns: list of (record_idx, example_sentence, new_meanings)
    """
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

        # Örnek cümle bul
        example = ""
        existing_example = record.get("ornek_almanca", "") or ""
        if not existing_example:
            example = find_example_sentence(sentences, bare_word)

        # Yeni anlam bul
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
# Aday → kayıt dönüştürme (gramer bilgileriyle zenginleştirilmiş)
# ---------------------------------------------------------------------------
def candidate_to_record(cand: dict, source_url: str, text: str = "") -> dict:
    almanca = cand["almanca"]
    artikel = ""
    wr = cand.get("written_rep", "")

    # WikDict written_rep'ten artikel
    for art in ("der ", "die ", "das "):
        if wr.lower().startswith(art):
            artikel = art.strip()
            almanca = wr[len(art):]
            break

    # Metinden artikel tespiti (grammar_utils)
    if not artikel and text and _GRAMMAR_UTILS_AVAILABLE:
        detected = detect_article_from_context(almanca, text)
        if detected:
            artikel = detected

    pos = cand.get("pos", guess_pos(almanca))

    # Fiil tipi ve trennbar tespiti
    verb_typ = ""
    trennbar = ""
    if pos == "fiil" and _GRAMMAR_UTILS_AVAILABLE:
        verb_typ = classify_verb_type(almanca)
        if not verb_typ and text:
            verb_typ = detect_verb_type_from_text(almanca, text)
        if is_trennbar(almanca):
            trennbar = "trennbar"

    # Çeviri kalitesi
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
    print("=" * 70)
    print("enrich_quality.py — Kalite ve Büyüklük Zenginleştirme")
    print(f"URL sayısı: {len(SOURCE_URLS)}")
    print("Mod: Yeni kelime + mevcut kayıt güncelleme (örnek cümle & yeni anlam)")
    print("=" * 70)

    if WIKDICT_PATH.exists():
        conn = sqlite3.connect(str(WIKDICT_PATH))
        cursor = conn.cursor()
        print(f"WikDict: {WIKDICT_PATH}")
    else:
        conn = None
        cursor = None
        print(f"[UYARI] WikDict bulunamadı: {WIKDICT_PATH}", file=sys.stderr)

    records = load_dictionary()
    existing_keys = build_existing_keys(records)
    record_index = build_record_index(records)
    print(f"Mevcut sözlük: {len(records)} kayıt\n")

    all_new: list = []
    added_keys: set = set(existing_keys)
    updated_indices: set = set()  # Bu oturumda güncellenmiş kayıt indeksleri

    url_stats: dict = {}
    total_urls = len(SOURCE_URLS)
    total_updated = 0

    for i, url in enumerate(SOURCE_URLS, 1):
        topic = url.split("/wiki/")[-1].replace("_", " ")
        print(f"\n[{i}/{total_urls}] {topic}")

        html = fetch_text(url)
        if not html:
            url_stats[topic] = 0
            continue

        parser = VisibleTextExtractor()
        parser.feed(html)
        text = parser.get_text()
        if not text:
            url_stats[topic] = 0
            continue

        print(f"  Metin: {len(text):,} karakter")

        # --- Yeni kelimeler ---
        candidates = extract_candidates(url, text, added_keys, cursor, min_freq=1)
        url_new = 0
        for cand in candidates:
            norm = cf(cand["almanca"])
            norm_base = cf(strip_article(cand["almanca"]))
            if norm in added_keys or norm_base in added_keys:
                continue
            rec = candidate_to_record(cand, url, text=text)
            all_new.append(rec)
            added_keys.add(norm)
            added_keys.add(norm_base)
            url_new += 1
            verb_info = f" [{rec.get('verb_typ','')}]" if rec.get("verb_typ") else ""
            print(f"    + {rec['almanca']}{verb_info} → {rec['turkce']}")

        # --- Mevcut kayıt güncellemeleri ---
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
                print(f"    ~ {rec.get('almanca','?')}: örnek cümle eklendi")

            if new_meanings:
                existing_tr = rec.get("turkce", "") or ""
                additions = "; ".join(new_meanings)
                rec["turkce"] = f"{existing_tr}; {additions}" if existing_tr else additions
                changed = True
                print(f"    ~ {rec.get('almanca','?')}: yeni anlam → {additions}")

            # Gramer alanlarını da doldur (artikel, verb_typ)
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

        total_updated += url_updated
        url_stats[topic] = url_new
        print(f"  => {url_new} yeni kelime, {url_updated} kayıt güncellendi")

        # Her 25 URL'de ara kaydet
        if i % 25 == 0:
            print(f"\n  [ARA KAYIT] {len(all_new)} yeni + {total_updated} güncelleme...")
            save_dictionary(records + all_new)

    if conn:
        conn.close()

    print(f"\n{'='*70}")
    print(f"TOPLAM YENİ KELİME   : {len(all_new)}")
    print(f"TOPLAM GÜNCELLEME    : {total_updated}")
    print(f"{'='*70}")

    if not all_new and not updated_indices:
        print("Eklenecek veya güncellenecek kayıt bulunamadı.")
        return

    records.extend(all_new)
    save_dictionary(records)

    print("\n--- Konu bazlı özet (yeni kelimeler) ---")
    for topic, count in url_stats.items():
        if count:
            print(f"  {topic}: +{count}")

    print(f"\nToplam {len(all_new)} yeni kelime eklendi.")
    print(f"Toplam {total_updated} mevcut kayıt zenginleştirildi.")
    print(f"Sözlük artık {len(records)} kayıt içeriyor.")


if __name__ == "__main__":
    main()
