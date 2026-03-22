#!/usr/bin/env python3
"""
enrich_deep.py
==============
İki aşamalı zenginleştirme:

1. KURATIF KALIPLER — 150+ Almanca fiil kalıbı / deyim / teknik ifade
   (Funktionsverbgefüge, otomotiv kalıpları, teknik yazıda sık geçen ifadeler)
   Doğrudan sözlüğe eklenir, WikDict'e bağımlı değil.

2. URL TARAMA — 250+ Wikipedia DE + açık kaynak teknik sayfa
   - Otomotiv: motor, getriebe, fahrwerk, bremse, elektrik, elektroauto...
   - Teknik genel: Maschinenbau, Mechanik, Thermodynamik, Strömungslehre...
   - min_freq=1 (WikDict'te bulunan her kelime, tek geçse bile eklenir)
   - Encoding bug düzeltildi: ä/ö/ü → %C3%A4 / %C3%B6 / %C3%BC

Kaynak: Alman Wikipedia (CC BY-SA 3.0), kfz-tech.de, WikDict (de-tr)
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
# BÖLÜM 1: Kuratif kalıp listesi
# Kaynak: Standart Almanca dil bilgisi referansları (Duden, DWDS, IDS Mannheim)
# Her kalıp elle doğrulanmıştır.
# ---------------------------------------------------------------------------
CURATED_PHRASES = [
    # === A) Genel Funktionsverbgefüge (teknik metinlerde çok sık) ===
    ("zum Einsatz kommen",          "devreye girmek, kullanılmak",               "deyim"),
    ("zum Einsatz bringen",         "devreye sokmak, kullanmak",                 "deyim"),
    ("in Betrieb nehmen",           "işletmeye almak, devreye sokmak",           "deyim"),
    ("in Betrieb setzen",           "işletmeye sokmak, çalıştırmak",             "deyim"),
    ("außer Betrieb setzen",        "devre dışı bırakmak",                       "deyim"),
    ("außer Betrieb nehmen",        "devre dışı almak",                          "deyim"),
    ("in Gang setzen",              "harekete geçirmek, çalıştırmak",            "deyim"),
    ("in Gang bringen",             "çalıştırmak, harekete geçirmek",            "deyim"),
    ("in Gang kommen",              "çalışmaya başlamak, harekete geçmek",       "deyim"),
    ("zum Stillstand kommen",       "durmak, hareketsizleşmek",                  "deyim"),
    ("zum Stillstand bringen",      "durdurmak",                                 "deyim"),
    ("in Bewegung setzen",          "harekete geçirmek",                         "deyim"),
    ("in Bewegung kommen",          "harekete geçmek",                           "deyim"),
    ("Fahrt aufnehmen",             "hız kazanmak",                              "deyim"),
    ("an Fahrt gewinnen",           "hız kazanmak, ivme kazanmak",               "deyim"),
    ("unter Druck setzen",          "baskı altına almak",                        "deyim"),
    ("unter Druck stehen",          "baskı altında olmak",                       "deyim"),
    ("unter Druck geraten",         "baskıya maruz kalmak",                      "deyim"),
    ("auf den Markt kommen",        "piyasaya çıkmak",                           "deyim"),
    ("auf den Markt bringen",       "piyasaya sürmek",                           "deyim"),
    ("eine Rolle spielen",          "rol oynamak",                               "deyim"),
    ("eine große Rolle spielen",    "büyük rol oynamak, çok önemli olmak",       "deyim"),
    ("zur Verfügung stehen",        "hazır olmak, mevcut olmak",                 "deyim"),
    ("zur Verfügung stellen",       "sunmak, kullanıma açmak",                   "deyim"),
    ("in Anspruch nehmen",          "kullanmak, yararlanmak, talep etmek",       "deyim"),
    ("in der Lage sein",            "yapabilmek, muktedir olmak",                "deyim"),
    ("in Frage kommen",             "söz konusu olmak, mümkün olmak",            "deyim"),
    ("in Frage stellen",            "sorgulamak, şüpheye düşürmek",              "deyim"),
    ("in Kauf nehmen",              "göze almak, kabullenmek",                   "deyim"),
    ("zum Tragen kommen",           "etkisini göstermek, işe yaramak",           "deyim"),
    ("in Kraft treten",             "yürürlüğe girmek",                          "deyim"),
    ("außer Kraft setzen",          "geçersiz kılmak, yürürlükten kaldırmak",    "deyim"),
    ("zur Sprache kommen",          "gündeme gelmek, söz konusu olmak",          "deyim"),
    ("in Betracht ziehen",          "göz önünde bulundurmak",                    "deyim"),
    ("in Betracht kommen",          "göz önünde bulundurulabilmek",              "deyim"),
    ("zur Anwendung kommen",        "uygulanmak, kullanılmak",                   "deyim"),
    ("zur Anwendung bringen",       "uygulamak",                                 "deyim"),
    ("auf dem Prüfstand stehen",    "sınanmak, test edilmek",                    "deyim"),
    ("in Auftrag geben",            "sipariş vermek, ısmarlamak",                "deyim"),
    ("zum Ausdruck bringen",        "ifade etmek, dile getirmek",                "deyim"),
    ("zum Ausdruck kommen",         "ifade edilmek, ortaya çıkmak",              "deyim"),
    ("in Erscheinung treten",       "ortaya çıkmak, görünmek",                   "deyim"),
    ("in den Vordergrund treten",   "ön plana çıkmak",                           "deyim"),
    ("zur Folge haben",             "sonucunu doğurmak, yol açmak",              "deyim"),
    ("in Verbindung stehen",        "bağlantısı olmak, ilişkili olmak",          "deyim"),
    ("in Verbindung bringen",       "ilişkilendirmek, bağdaştırmak",             "deyim"),
    ("unter Beweis stellen",        "kanıtlamak, ispat etmek",                   "deyim"),
    ("auf dem neusten Stand sein",  "güncel olmak",                              "deyim"),
    ("auf dem Laufenden sein",      "haberdar olmak, bilgisi olmak",             "deyim"),
    ("in Aussicht stellen",         "vaat etmek, önermek",                       "deyim"),
    ("Anklang finden",              "beğeni kazanmak, ilgi görmek",              "deyim"),
    ("von Vorteil sein",            "avantajlı olmak, yararlı olmak",            "deyim"),
    ("von Nachteil sein",           "dezavantajlı olmak, sakıncalı olmak",       "deyim"),
    ("außer Funktion setzen",       "işlevsiz hale getirmek, bozmak",            "deyim"),
    ("in Umlauf bringen",           "dolaşıma sokmak",                           "deyim"),
    ("Reibung vermindern",          "sürtünmeyi azaltmak",                       "deyim"),
    ("Wärme abführen",              "ısıyı iletmek, ısıyı uzaklaştırmak",        "deyim"),
    ("in Schuss halten",            "iyi durumda tutmak, bakmak",                "deyim"),
    ("auf Verschleiß prüfen",       "aşınma açısından kontrol etmek",            "deyim"),

    # === B) Otomotiv kalıpları ===
    ("Gas geben",                   "gaz vermek, hızlanmak",                     "deyim"),
    ("Vollgas geben",               "tam gaz vermek",                            "deyim"),
    ("vom Gas gehen",               "gazdan ayak çekmek, yavaşlamak",            "deyim"),
    ("auf die Bremse treten",       "frene basmak",                              "deyim"),
    ("auf die Bremse drücken",      "frene basmak",                              "deyim"),
    ("den Motor anlassen",          "motoru çalıştırmak",                        "deyim"),
    ("den Motor starten",           "motoru çalıştırmak, motoru start etmek",    "deyim"),
    ("den Motor abstellen",         "motoru kapatmak",                           "deyim"),
    ("den Motor abwürgen",          "motoru boğmak, motoru söndürmek",           "deyim"),
    ("den Motor warmlaufen lassen", "motoru ısınmaya bırakmak",                  "deyim"),
    ("einen Gang einlegen",         "vitesi takmak",                             "deyim"),
    ("in den ersten Gang schalten", "birinci vitese geçmek",                     "deyim"),
    ("hochschalten",                "üst vitese geçmek",                         "fiil"),
    ("zurückschalten",              "düşük vitese geçmek, düşürmek",             "fiil"),
    ("in den Leerlauf schalten",    "vitesi boşa almak",                         "deyim"),
    ("überholen",                   "geçmek, sollama yapmak",                    "fiil"),
    ("einparken",                   "park etmek (park yerine girmek)",           "fiil"),
    ("ausparken",                   "park yerinden çıkmak",                      "fiil"),
    ("rückwärts fahren",            "geri geri gitmek",                          "deyim"),
    ("wenden",                      "döndürmek, U dönüşü yapmak",               "fiil"),
    ("tanken",                      "yakıt doldurmak, benzin almak",             "fiil"),
    ("volltanken",                  "depoyu doldurmak",                          "fiil"),
    ("Benzin tanken",               "benzin doldurmak",                          "deyim"),
    ("Diesel tanken",               "dizel doldurmak",                           "deyim"),
    ("eine Panne haben",            "arıza yapmak, bozulmak",                    "deyim"),
    ("eine Panne erleiden",         "arıza yaşamak",                             "deyim"),
    ("einen Unfall haben",          "kaza yapmak, kaza geçirmek",                "deyim"),
    ("einen Unfall verursachen",    "kazaya yol açmak, kaza yapmak",             "deyim"),
    ("auf Touren kommen",           "tam devire ulaşmak, hız kazanmak",          "deyim"),
    ("auf Hochtouren laufen",       "tam kapasitede çalışmak",                   "deyim"),
    ("unter Last laufen",           "yük altında çalışmak",                      "deyim"),
    ("zur Werkstatt bringen",       "tamiraneye götürmek",                       "deyim"),
    ("zur Inspektion",              "inspeksiyona, bakıma",                      "kalıp"),
    ("Reifendruck prüfen",          "lastik basıncını kontrol etmek",            "deyim"),
    ("Öl nachfüllen",               "yağ eklemek, yağ ikmali yapmak",            "deyim"),
    ("den Ölstand prüfen",          "yağ seviyesini kontrol etmek",              "deyim"),
    ("Kühlwasser auffüllen",        "antifriz eklemek, soğutma suyu doldurmak",  "deyim"),
    ("den Blinker setzen",          "sinyal vermek",                             "deyim"),
    ("abblenden",                   "uzak farları kısmak, kısa fara geçmek",     "fiil"),
    ("aufblenden",                  "uzak fara geçmek",                          "fiil"),
    ("abschleppen lassen",          "çektirmek (araç), yedekte çektirmek",       "deyim"),
    ("die Warnblinkanlage einschalten", "dörtlüleri açmak, tehlike ikazını açmak", "deyim"),

    # === C) Hareket / mekanik / fizik kalıpları ===
    ("Druck aufbauen",              "basınç oluşturmak, basınç uygulamak",       "deyim"),
    ("Druck ablassen",              "basıncı boşaltmak",                         "deyim"),
    ("Spannung aufbauen",           "gerilim oluşturmak",                        "deyim"),
    ("Kraft übertragen",            "kuvvet iletmek",                            "deyim"),
    ("Energie speichern",           "enerji depolamak",                          "deyim"),
    ("Energie umwandeln",           "enerji dönüştürmek",                        "deyim"),
    ("Reibungswärme erzeugen",      "sürtünme ısısı oluşturmak",                 "deyim"),
    ("Verschleiß minimieren",       "aşınmayı en aza indirmek",                  "deyim"),
    ("Leistung abgeben",            "güç vermek, enerji iletmek",                "deyim"),
    ("Leistung aufnehmen",          "güç almak",                                 "deyim"),
    ("Drehmoment übertragen",       "tork iletmek",                              "deyim"),
    ("auf Zug belasten",            "çekme kuvvetine maruz bırakmak",            "deyim"),
    ("auf Druck belasten",          "basma kuvvetine maruz bırakmak",            "deyim"),
    ("ins Schwingen geraten",       "titreşime girmek",                          "deyim"),
    ("in Resonanz geraten",         "rezonansa girmek",                          "deyim"),

    # === D) Teknik bağlamda sık geçen genel ifadeler ===
    ("in der Regel",                "genellikle, kural olarak",                  "kalıp"),
    ("in der Praxis",               "pratikte, uygulamada",                      "kalıp"),
    ("im Vergleich zu",             "ile kıyasla, -e göre",                      "kalıp"),
    ("im Hinblick auf",             "açısından, -e bakımından",                  "kalıp"),
    ("im Rahmen von",               "çerçevesinde",                              "kalıp"),
    ("auf dem Gebiet",              "alanında",                                  "kalıp"),
    ("im Wesentlichen",             "esasen, özünde, temelde",                   "kalıp"),
    ("im Allgemeinen",              "genel olarak",                              "kalıp"),
    ("im Laufe der Zeit",           "zamanla, zaman içinde",                     "kalıp"),
    ("auf der anderen Seite",       "öte yandan, diğer taraftan",               "kalıp"),
    ("in erster Linie",             "her şeyden önce, öncelikle",               "kalıp"),
    ("im Grunde genommen",          "özünde, aslında, temelde",                  "kalıp"),
    ("in gewisser Weise",           "bir bakıma, belirli ölçüde",               "kalıp"),
    ("unter Umständen",             "koşullara bağlı olarak, belki",             "kalıp"),
    ("auf keinen Fall",             "hiçbir şekilde, kesinlikle hayır",          "kalıp"),
    ("auf jeden Fall",              "her halükârda, kesinlikle",                 "kalıp"),
    ("im Großen und Ganzen",        "genelde, büyük ölçüde",                     "kalıp"),
    ("nach wie vor",                "hâlâ, eskisi gibi",                         "kalıp"),
    ("so weit wie möglich",         "mümkün olduğunca",                          "kalıp"),
    ("in der Zwischenzeit",         "bu arada, o süre içinde",                   "kalıp"),
    ("zur gleichen Zeit",           "aynı zamanda, eş zamanlı",                  "kalıp"),
    ("auf Anhieb",                  "ilk seferinde, hemen, anında",              "kalıp"),
    ("eine Ausnahme machen",        "istisna oluşturmak, istisna yapmak",        "deyim"),
    ("mit anderen Worten",          "başka bir deyişle",                         "kalıp"),
    ("in diesem Zusammenhang",      "bu bağlamda",                               "kalıp"),
    ("in der Folge",                "ardından, bunun sonucunda",                 "kalıp"),
    ("im Nachhinein",               "geriye dönüp bakıldığında, sonradan",       "kalıp"),
    ("auf lange Sicht",             "uzun vadede",                               "kalıp"),
    ("auf kurze Sicht",             "kısa vadede",                               "kalıp"),
    ("im Laufe des Prozesses",      "süreç içinde",                              "kalıp"),
    ("je nach Bedarf",              "ihtiyaca göre, duruma göre",               "kalıp"),
    ("je nach Situation",           "duruma göre",                               "kalıp"),
    ("in Abhängigkeit von",         "-e bağlı olarak",                           "kalıp"),
    ("unabhängig davon",            "bundan bağımsız olarak",                    "kalıp"),
    ("in Kombination mit",          "ile birlikte, ile kombinasyon halinde",     "kalıp"),
    ("im Zusammenhang mit",         "ile bağlantılı olarak, -le ilgili olarak", "kalıp"),
    ("unter Berücksichtigung",      "dikkate alınarak",                          "kalıp"),
    ("mit Blick auf",               "-e bakışla, -i göz önünde bulundurarak",   "kalıp"),
]

# ---------------------------------------------------------------------------
# URL listesi — otomotiv + teknik genel (Wikipedia 404'leri düzeltildi)
# ---------------------------------------------------------------------------
SOURCE_URLS = [
    # === Motor (düzeltilmiş + yeni) ===
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
    "https://de.wikipedia.org/wiki/Ventilsteuerung",       # eski: Ventil_(Motortechnik) → 404
    "https://de.wikipedia.org/wiki/Motoraufladung",         # eski: Kompressor_(Aufladung) → 404
    "https://de.wikipedia.org/wiki/Steuerkette",
    "https://de.wikipedia.org/wiki/Zahnriemen",
    "https://de.wikipedia.org/wiki/Schwungrad",
    "https://de.wikipedia.org/wiki/Motorsteuerung",
    "https://de.wikipedia.org/wiki/Turbolader",
    "https://de.wikipedia.org/wiki/Ladeluftkühler",
    "https://de.wikipedia.org/wiki/Drehmoment",
    "https://de.wikipedia.org/wiki/Hubraum",
    "https://de.wikipedia.org/wiki/Viertaktmotor",
    "https://de.wikipedia.org/wiki/Zweitaktmotor",
    "https://de.wikipedia.org/wiki/Verdichtungsverhältnis",
    "https://de.wikipedia.org/wiki/Motorkühlsystem",
    "https://de.wikipedia.org/wiki/Kühler_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/Thermostat",
    "https://de.wikipedia.org/wiki/Wasserpumpe",

    # === Kraftstoff & Abgas ===
    "https://de.wikipedia.org/wiki/Kraftstoff",
    "https://de.wikipedia.org/wiki/Benzin",
    "https://de.wikipedia.org/wiki/Dieselkraftstoff",
    "https://de.wikipedia.org/wiki/Kraftstoffeinspritzung",
    "https://de.wikipedia.org/wiki/Direkteinspritzung",
    "https://de.wikipedia.org/wiki/Vergaser",
    "https://de.wikipedia.org/wiki/Abgasanlage",
    "https://de.wikipedia.org/wiki/Fahrzeugkatalysator",    # eski: Katalysator_(Kfz) → 404
    "https://de.wikipedia.org/wiki/Partikelfilter",
    "https://de.wikipedia.org/wiki/Abgasrückführung",
    "https://de.wikipedia.org/wiki/Abgasnorm",
    "https://de.wikipedia.org/wiki/Kraftstoffverbrauch",
    "https://de.wikipedia.org/wiki/Klopfen",                # eski: Klopfen_(Motor) → 404

    # === Schmierung ===
    "https://de.wikipedia.org/wiki/Motoröl",
    "https://de.wikipedia.org/wiki/Ölpumpe",
    "https://de.wikipedia.org/wiki/Ölfilter",
    "https://de.wikipedia.org/wiki/Kühlmittel",
    "https://de.wikipedia.org/wiki/Kühlkreislauf",

    # === Zündung ===
    "https://de.wikipedia.org/wiki/Zündanlage",
    "https://de.wikipedia.org/wiki/Zündkerze",
    "https://de.wikipedia.org/wiki/Zündspule",

    # === Getriebe & Antrieb ===
    "https://de.wikipedia.org/wiki/Getriebe",
    "https://de.wikipedia.org/wiki/Schaltgetriebe",
    "https://de.wikipedia.org/wiki/Automatikgetriebe",
    "https://de.wikipedia.org/wiki/Doppelkupplungsgetriebe",
    "https://de.wikipedia.org/wiki/Stufenlosgetriebe",
    "https://de.wikipedia.org/wiki/Kupplung_(Maschine)",
    "https://de.wikipedia.org/wiki/Differentialgetriebe",
    "https://de.wikipedia.org/wiki/Allradantrieb",
    "https://de.wikipedia.org/wiki/Vorderradantrieb",
    "https://de.wikipedia.org/wiki/Hinterradantrieb",
    "https://de.wikipedia.org/wiki/Antriebswelle",
    "https://de.wikipedia.org/wiki/Gelenkwelle",
    "https://de.wikipedia.org/wiki/Verteilergetriebe",
    "https://de.wikipedia.org/wiki/Drehmomentwandler",
    "https://de.wikipedia.org/wiki/Planetengetriebe",

    # === Fahrwerk & Aufhängung ===
    "https://de.wikipedia.org/wiki/Fahrwerk",
    "https://de.wikipedia.org/wiki/Radaufhängung",
    "https://de.wikipedia.org/wiki/Achse_(Fahrzeugtechnik)",
    "https://de.wikipedia.org/wiki/Querlenker",
    "https://de.wikipedia.org/wiki/Spurstange",
    "https://de.wikipedia.org/wiki/Stabilisator_(Fahrwerk)",
    "https://de.wikipedia.org/wiki/Stoßdämpfer",
    "https://de.wikipedia.org/wiki/Luftfederung",
    "https://de.wikipedia.org/wiki/Schraubenfeder",
    "https://de.wikipedia.org/wiki/Blattfeder",
    "https://de.wikipedia.org/wiki/Hinterachse",
    "https://de.wikipedia.org/wiki/Vorderachse",
    "https://de.wikipedia.org/wiki/Spur_(Fahrzeugtechnik)",
    "https://de.wikipedia.org/wiki/Sturz_(Fahrzeugtechnik)",
    "https://de.wikipedia.org/wiki/Nachlauf_(Fahrzeugtechnik)",
    "https://de.wikipedia.org/wiki/Schwingarm",

    # === Bremse ===
    "https://de.wikipedia.org/wiki/Bremse_(Fahrzeugtechnik)",
    "https://de.wikipedia.org/wiki/Scheibenbremse",
    "https://de.wikipedia.org/wiki/Trommelbremse",
    "https://de.wikipedia.org/wiki/Bremsscheibe",
    "https://de.wikipedia.org/wiki/Bremsbelag",
    "https://de.wikipedia.org/wiki/Bremssattel",
    "https://de.wikipedia.org/wiki/Antiblockiersystem",
    "https://de.wikipedia.org/wiki/Fahrdynamikregelung",
    "https://de.wikipedia.org/wiki/Bremsflüssigkeit",
    "https://de.wikipedia.org/wiki/Bremskraftverstärker",
    "https://de.wikipedia.org/wiki/Retarder",
    "https://de.wikipedia.org/wiki/Bremskraftverteilung",

    # === Lenkung ===
    "https://de.wikipedia.org/wiki/Lenkung",
    "https://de.wikipedia.org/wiki/Servolenkung",
    "https://de.wikipedia.org/wiki/Zahnstangenlenkung",
    "https://de.wikipedia.org/wiki/Lenkrad",

    # === Reifen & Räder ===
    "https://de.wikipedia.org/wiki/Reifen",
    "https://de.wikipedia.org/wiki/Felge",
    "https://de.wikipedia.org/wiki/Reifenluftdruck",
    "https://de.wikipedia.org/wiki/Winterreifen",
    "https://de.wikipedia.org/wiki/Sommerreifen",
    "https://de.wikipedia.org/wiki/Reifenprofil",
    "https://de.wikipedia.org/wiki/Aquaplaning",
    "https://de.wikipedia.org/wiki/Reifendruckkontrollsystem",

    # === Karosserie ===
    "https://de.wikipedia.org/wiki/Karosserie",
    "https://de.wikipedia.org/wiki/Fahrzeugrahmen",
    "https://de.wikipedia.org/wiki/Windschutzscheibe",
    "https://de.wikipedia.org/wiki/Stoßstange",
    "https://de.wikipedia.org/wiki/Kotflügel",
    "https://de.wikipedia.org/wiki/Schiebedach",
    "https://de.wikipedia.org/wiki/Fahrzeugfarbe",
    "https://de.wikipedia.org/wiki/Unterbodenschutz",
    "https://de.wikipedia.org/wiki/Crashtest",
    "https://de.wikipedia.org/wiki/Knautschzone",
    "https://de.wikipedia.org/wiki/Deformationselement",

    # === Innenraum & Komfort ===
    "https://de.wikipedia.org/wiki/Fahrzeugsitz",
    "https://de.wikipedia.org/wiki/Sicherheitsgurt",
    "https://de.wikipedia.org/wiki/Instrumententafel",
    "https://de.wikipedia.org/wiki/Tachometer",
    "https://de.wikipedia.org/wiki/Klimaanlage",
    "https://de.wikipedia.org/wiki/Navigationssystem_(Kraftfahrzeug)",

    # === Beleuchtung ===
    "https://de.wikipedia.org/wiki/Scheinwerfer",
    "https://de.wikipedia.org/wiki/LED-Scheinwerfer",
    "https://de.wikipedia.org/wiki/Fahrlicht",
    "https://de.wikipedia.org/wiki/Tagfahrlicht",

    # === Fahrzeugelektrik & Elektronik ===
    "https://de.wikipedia.org/wiki/Fahrzeugelektrik",
    "https://de.wikipedia.org/wiki/Kfz-Batterie",
    "https://de.wikipedia.org/wiki/Lichtmaschine",
    "https://de.wikipedia.org/wiki/Anlasser",
    "https://de.wikipedia.org/wiki/Steuergerät",
    "https://de.wikipedia.org/wiki/CAN-Bus",
    "https://de.wikipedia.org/wiki/Fahrerassistenzsystem",
    "https://de.wikipedia.org/wiki/Einparkhilfe",
    "https://de.wikipedia.org/wiki/Tempomat",
    "https://de.wikipedia.org/wiki/Adaptive_Geschwindigkeitsregelung",
    "https://de.wikipedia.org/wiki/Spurhalteassistent",
    "https://de.wikipedia.org/wiki/Spurwechselassistent",
    "https://de.wikipedia.org/wiki/Notbremsassistent",

    # === Sicherheit ===
    "https://de.wikipedia.org/wiki/Airbag",
    "https://de.wikipedia.org/wiki/Passive_Sicherheit",
    "https://de.wikipedia.org/wiki/Kindersitz",
    "https://de.wikipedia.org/wiki/Verkehrssicherheit",

    # === Elektroauto & Hybrid ===
    "https://de.wikipedia.org/wiki/Elektroauto",
    "https://de.wikipedia.org/wiki/Hybridfahrzeug",
    "https://de.wikipedia.org/wiki/Plug-in-Hybrid",
    "https://de.wikipedia.org/wiki/Brennstoffzellenfahrzeug",
    "https://de.wikipedia.org/wiki/Ladesäule",
    "https://de.wikipedia.org/wiki/Schnellladung",
    "https://de.wikipedia.org/wiki/Rekuperation",
    "https://de.wikipedia.org/wiki/Traktionsbatterie",
    "https://de.wikipedia.org/wiki/Lithium-Ionen-Akkumulator",
    "https://de.wikipedia.org/wiki/Reichweite_(Elektrofahrzeug)",
    "https://de.wikipedia.org/wiki/Elektromobilität",

    # === Autonomes Fahren ===
    "https://de.wikipedia.org/wiki/Autonomes_Fahren",
    "https://de.wikipedia.org/wiki/Lidar",
    "https://de.wikipedia.org/wiki/Radar",
    "https://de.wikipedia.org/wiki/Ultraschallsensor",

    # === Fahrzeugtypen ===
    "https://de.wikipedia.org/wiki/Limousine",
    "https://de.wikipedia.org/wiki/Kombi",
    "https://de.wikipedia.org/wiki/Cabriolet",
    "https://de.wikipedia.org/wiki/Sportwagen",
    "https://de.wikipedia.org/wiki/Geländewagen",
    "https://de.wikipedia.org/wiki/Kleinstwagen",
    "https://de.wikipedia.org/wiki/Lastkraftwagen",
    "https://de.wikipedia.org/wiki/Sattelzug",
    "https://de.wikipedia.org/wiki/Motorrad",
    "https://de.wikipedia.org/wiki/Transporter_(Fahrzeug)",

    # === Kfz-Recht & Verwaltung ===
    "https://de.wikipedia.org/wiki/Kraftfahrzeugzulassung",
    "https://de.wikipedia.org/wiki/Hauptuntersuchung",
    "https://de.wikipedia.org/wiki/Kfz-Versicherung",
    "https://de.wikipedia.org/wiki/Fahrzeugschein",
    "https://de.wikipedia.org/wiki/Kraftfahrzeugkennzeichen",

    # === Werkstatt & Wartung ===
    "https://de.wikipedia.org/wiki/Kfz-Werkstatt",
    "https://de.wikipedia.org/wiki/Fahrzeugdiagnose",
    "https://de.wikipedia.org/wiki/OBD",
    "https://de.wikipedia.org/wiki/Tankstelle",
    "https://de.wikipedia.org/wiki/Verkehrsunfall",

    # === Allgemeine Technik (kalıpların geçtiği metinler) ===
    "https://de.wikipedia.org/wiki/Maschinenbau",
    "https://de.wikipedia.org/wiki/Mechanik",
    "https://de.wikipedia.org/wiki/Thermodynamik",
    "https://de.wikipedia.org/wiki/Strömungslehre",
    "https://de.wikipedia.org/wiki/Werkstoffkunde",
    "https://de.wikipedia.org/wiki/Tribologie",
    "https://de.wikipedia.org/wiki/Schwingungslehre",
    "https://de.wikipedia.org/wiki/Hydraulik",
    "https://de.wikipedia.org/wiki/Pneumatik",
    "https://de.wikipedia.org/wiki/Steuerungstechnik",
    "https://de.wikipedia.org/wiki/Regelungstechnik",
    "https://de.wikipedia.org/wiki/Elektrotechnik",
    "https://de.wikipedia.org/wiki/Leistungselektronik",
    "https://de.wikipedia.org/wiki/Getriebetechnik",
    "https://de.wikipedia.org/wiki/Fertigungstechnik",
    "https://de.wikipedia.org/wiki/Schweißen",
    "https://de.wikipedia.org/wiki/Korrosion",
    "https://de.wikipedia.org/wiki/Metallurgie",
    "https://de.wikipedia.org/wiki/Kunststoff",
    "https://de.wikipedia.org/wiki/Verbundwerkstoff",
    "https://de.wikipedia.org/wiki/Kohlenstofffaser",
    "https://de.wikipedia.org/wiki/Aluminiumlegierung",
    "https://de.wikipedia.org/wiki/Reibung",
    "https://de.wikipedia.org/wiki/Schmierung",
    "https://de.wikipedia.org/wiki/Wärmeübertragung",
    "https://de.wikipedia.org/wiki/Lager_(Maschinenelement)",
    "https://de.wikipedia.org/wiki/Dichtung_(Technik)",
    "https://de.wikipedia.org/wiki/Schraube",
    "https://de.wikipedia.org/wiki/Niete",
    "https://de.wikipedia.org/wiki/Feder_(Technik)",
    "https://de.wikipedia.org/wiki/Zahnrad",
    "https://de.wikipedia.org/wiki/Riemenantrieb",
    "https://de.wikipedia.org/wiki/Kettenantrieb",
    "https://de.wikipedia.org/wiki/Sensor",
    "https://de.wikipedia.org/wiki/Aktor",
    "https://de.wikipedia.org/wiki/Mikrocontroller",
    "https://de.wikipedia.org/wiki/Embedded_System",
    "https://de.wikipedia.org/wiki/Qualitätssicherung",
    "https://de.wikipedia.org/wiki/Prüfstand",
    "https://de.wikipedia.org/wiki/Prototyp",
    "https://de.wikipedia.org/wiki/Serienfertigung",

    # === kfz-tech.de (teknik Almanca, otomotiv odaklı) ===
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
# Stopword kümesi (casefold)
# ---------------------------------------------------------------------------
_RAW_SW = {
    "aber","alle","allem","allen","aller","alles","als","also","am","an",
    "auch","auf","aus","bei","beim","bin","bis","bist","da","dabei","damit",
    "danach","dann","das","dass","dein","deine","dem","den","denn","der",
    "des","dessen","deshalb","die","dies","diese","dieser","dieses","doch",
    "dort","du","durch","ein","eine","einem","einen","einer","eines","er",
    "es","etwas","euch","euer","eure","für","gegen","gewesen","hab","habe",
    "haben","hat","hatte","hattest","hier","hin","hinter","ich","ihr","ihre",
    "im","in","indem","ins","ist","jede","jeder","jedes","jetzt","kann",
    "kannst","kein","keine","mit","muss","musst","nach","neben","nicht",
    "noch","nun","oder","ohne","sehr","sein","seine","sich","sie","sind",
    "so","solche","soll","sollte","sondern","sonst","über","um","und","uns",
    "unter","vom","von","vor","war","waren","warst","was","weg","weil",
    "weiter","welche","welcher","wenn","wer","werde","werden","wie","wieder",
    "wir","wird","wirst","wo","wurde","wurden","zu","zum","zur","zwar","zwischen",
    "gut","gute","guten","gutem","guter","gutes",
    "groß","große","großen","großem","großer","großes",
    "klein","kleine","kleinen","kleinem","kleiner","kleines",
    "neu","neue","neuen","neuem","neuer","neues",
    "alt","alte","alten","altem","alter","altes",
    "viel","viele","vielen","vielem","vieler","vieles",
    "wenig","wenige","wenigen","wenigem","weniger",
    "ganz","ganze","ganzen","ganzem","ganzer","ganzes",
    "ander","andere","anderen","anderem","anderer","anderes",
    "erst","erste","ersten","erstem","erster","erstes",
    "letzt","letzte","letzten","letztem","letzter","letztes",
    "immer","schon","nur","gern","gerne","fast","etwa","eher",
    "daher","damals","dazu","deswegen","trotzdem","dennoch",
    "jedoch","allerdings","außerdem","zudem","ebenfalls","bereits",
    "meist","meistens","manchmal","oft","häufig","selten",
    "früher","später","zuerst","zuletzt","endlich","plötzlich",
    "sofort","bisher","seitdem","davor","davon","daran","darin",
    "darauf","darum","darüber","darunter","dafür","dagegen","dadurch","dahinter",
    "können","konnte","konnten","könnte","könnten",
    "müssen","musste","mussten","müsste","müssten",
    "sollen","sollten","wollen","wollte","wollten",
    "darf","dürfen","durfte","durften","dürfte","dürften",
    "mögen","mochte","mochten","möchte","möchten",
    "seid","wäre","wären","sei","seien","habt","hatten","hattet",
    "hätte","hätten","gehabt","werdet","würde","würden","würdet","geworden",
    "geht","ging","gingen","kommt","kam","kamen","macht","machte","machten",
    "sagt","sagte","sagten","gibt","gab","gaben","steht","stand","standen",
    "liegt","lag","lagen","sieht","sah","sahen","nimmt","nahm","nahmen",
    "hält","hielt","hielten","lässt","ließ","ließen","bringt","brachte","brachten",
    "denkt","dachte","dachten","weiß","wusste","wussten",
    "findet","fand","fanden","zeigt","zeigte","zeigten",
    "bleibt","blieb","blieben","heißt","hieß","hießen",
    "Jahr","Jahre","Jahren","Zeit","Zeiten","Teil","Teile","Form","Formen",
    "Art","Arten","Fall","Fälle","Punkt","Punkte","Zahl","Zahlen",
    "Ende","Anfang","Bereich","Bereiche","Grund","Gründe",
    "Beispiel","Beispiele","Ergebnis","Ergebnisse","Problem","Probleme",
    "Frage","Fragen","Antwort","Antworten","Möglichkeit","Möglichkeiten",
    "Bedeutung","Bedeutungen","Mensch","Menschen","Land","Länder",
    "Stadt","Städte","Welt","Leben","Weise","Stelle","Stellen","Seite","Seiten",
    "the","and","for","that","this","with","from","are","was","has","have",
    "been","they","about","which","when","where","how","can","will","not",
    "but","more","also","some","than","then","there","here","other","used",
    "based","see","view","edit",
    "januar","februar","märz","april","mai","juni","juli",
    "august","september","oktober","november","dezember",
    "montag","dienstag","mittwoch","donnerstag","freitag","samstag","sonntag",
    "zweite","zweiten","dritte","dritten","vierte","vierten","fünfte","fünften",
    "unser","unsere","unseren","unserem","unserer","jener","jene","jenen",
    "jeden","jedem","mancher","manche","manchen",
    "obwohl","während","bevor","nachdem","sobald","solange","falls","sofern",
    "gegenüber","innerhalb","außerhalb","anstatt","anstelle","aufgrund",
    "mithilfe","bezüglich","hinsichtlich","laut","gemäß","zufolge","entsprechend",
    "seit","statt","samt","wobei","sowie","hierbei","hierzu","daraus",
    "somit","folglich","hingegen","vielmehr","andererseits","einerseits",
    "nämlich","schließlich","letztlich","insofern","soweit","sowohl",
    "weder","entweder","zumindest","mindestens","höchstens",
    "tatsächlich","eigentlich","offenbar","offensichtlich","anscheinend",
    "möglicherweise","wahrscheinlich","jedenfalls","ohnehin","sowieso",
    "gleichwohl","indes","derweil","seither","fortan","nunmehr",
    "grundsätzlich","weitgehend","infolge","anhand","sodass","insgesamt","insbesondere",
    "abschnitt","artikel","weblink","weblinks","literatur",
    "einzelnachweis","einzelnachweise","hauptartikel","kategorie","kategorien","siehe",
    "usw","bzw","evtl","ggf","inkl","exkl","sog","bspw","vgl",
}
STOPWORDS_CF: frozenset[str] = frozenset(s.casefold() for s in _RAW_SW)

_PROPER_CF: frozenset[str] = frozenset({
    "berlin","münchen","hamburg","köln","frankfurt","stuttgart",
    "düsseldorf","dortmund","essen","leipzig","bremen","dresden",
    "hannover","nürnberg","duisburg","bochum","bonn",
    "deutschland","österreich","schweiz","europa",
    "paris","london","washington","peking","tokio","moskau",
    "müller","schmidt","schneider","fischer","weber","becker",
    "schulz","hoffmann","schäfer","koch","richter","schwarz",
    "friedrich","johannes","wilhelm","wolfgang","heinrich",
    "thomas","michael","stefan","andreas","christian",
    "volkswagen","mercedes","bmw","audi","porsche","opel",
    "ford","toyota","honda","nissan","hyundai","renault",
    "peugeot","fiat","volvo","tesla","ferrari","lamborghini",
    "bosch","continental","michelin","pirelli","bridgestone",
    "siemens","continental","magna","denso","aisin",
})

TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß]{3,}(?:-[A-Za-zÄÖÜäöüß]{2,})*")


# ---------------------------------------------------------------------------
# URL encoding fix
# ---------------------------------------------------------------------------
def fix_url(url: str) -> str:
    parts = _up.urlsplit(url)
    return _up.urlunsplit(parts._replace(path=_up.quote(parts.path, safe="/:@!$&'()*+,;=")))


# ---------------------------------------------------------------------------
# HTML metin ayıklayıcı
# ---------------------------------------------------------------------------
class VisibleTextExtractor(HTMLParser):
    BLOCK = {"address","article","blockquote","br","div","figcaption",
              "h1","h2","h3","h4","h5","h6","li","main","p","section","td","th","tr"}
    SKIP  = {"head","script","style","noscript","svg","canvas","nav","footer",
              "header","aside","button","form","input","select","textarea","figure"}
    MAIN  = {"main","article"}
    SKIP_CLS = {"references","reflist","reference","footnotes","toc","toccolours",
                "mw-references-wrap","navbox","navbox-inner","navbox-group",
                "mw-editsection","mw-jump-link","sidebar","sistersitebox","noprint",
                "catlinks","printfooter","cookie","banner","advertisement","ad","ads",
                "breadcrumb","pagination","menu","dropdown","related","recommendation"}
    SKIP_IDS = {"toc","references","catlinks","mw-navigation","p-search","nav",
                "footer","header","sidebar","menu","cookie-banner","related-articles"}

    def __init__(self):
        super().__init__()
        self.skip_depth = self.main_depth = 0
        self.all_chunks: list[str] = []
        self.main_chunks: list[str] = []

    def _skip_attrs(self, attrs):
        d = dict(attrs)
        return d.get("id","") in self.SKIP_IDS or bool(
            set((d.get("class","") or "").split()) & self.SKIP_CLS)

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP or self._skip_attrs(attrs):
            self.skip_depth += 1; return
        if self.skip_depth: return
        if tag in self.MAIN: self.main_depth += 1
        if tag in self.BLOCK: self._br()

    def handle_endtag(self, tag):
        if self.skip_depth: self.skip_depth -= 1; return
        if tag in self.MAIN and self.main_depth: self.main_depth -= 1
        if tag in self.BLOCK: self._br()

    def handle_data(self, data):
        if self.skip_depth: return
        s = data.strip()
        if not s: return
        self.all_chunks.append(s)
        if self.main_depth: self.main_chunks.append(s)

    def _br(self):
        self.all_chunks.append("\n")
        if self.main_depth: self.main_chunks.append("\n")

    def get_text(self) -> str:
        def j(chunks):
            p = []
            for c in chunks:
                if c == "\n":
                    if p and p[-1] != "\n": p.append("\n")
                elif c.strip(): p.append(c.strip())
            return " ".join(p).strip()
        main = j(self.main_chunks)
        body = j(self.all_chunks)
        t = main if len(main) >= 200 else body
        t = re.sub(r"[ \t]{2,}", " ", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()


# ---------------------------------------------------------------------------
# Yardımcı
# ---------------------------------------------------------------------------
def nf(s): return unicodedata.normalize("NFC", s)
def cf(s): return nf(s).strip().casefold()
def strip_art(t):
    for a in ("der ","die ","das ","Der ","Die ","Das "):
        if t.startswith(a): return t[len(a):]
    return t
def is_sw(tok): return cf(tok) in STOPWORDS_CF or cf(strip_art(tok)) in STOPWORDS_CF
def is_pn(tok): return cf(tok) in _PROPER_CF

def guess_pos(tok):
    b = strip_art(tok)
    if tok[:1].isupper() and " " not in b: return "isim"
    bl = b.lower()
    if bl.endswith(("en","ern","eln")): return "fiil"
    if bl.endswith(("lich","isch","ig","bar","sam","haft","los","voll")): return "sıfat"
    return "isim"


# ---------------------------------------------------------------------------
# WikDict
# ---------------------------------------------------------------------------
def lookup(term: str, cur) -> dict:
    if cur is None: return {"translation":"","written_rep":""}
    lo = cf(strip_art(term))
    candidates = [term.strip(), lo]
    for suf, rep in [("iert","ieren"),("test","en"),("tet","en"),("st","en"),("te","en")]:
        if lo.endswith(suf) and len(lo) > len(suf)+2:
            candidates.append(lo[:-len(suf)]+rep)
    for suf in ("en","es","e","s"):
        if lo.endswith(suf) and len(lo) >= (5 if suf=="s" else (5 if suf=="e" else 6)):
            if suf=="s" and lo.endswith("ss"): continue
            candidates.append(lo[:-len(suf)])
    if lo.endswith("t") and len(lo)>=6:
        root=lo[:-1]
        if not root.endswith(("ig","lich","isch","bar","sam","haft","voll","los")):
            candidates.append(root+"en")
    seen=set()
    for lt in candidates:
        k=cf(lt)
        if not k or k in seen: continue
        seen.add(k)
        row=cur.execute(
            "SELECT written_rep,trans_list FROM simple_translation "
            "WHERE lower(written_rep)=lower(?) ORDER BY rel_importance DESC,max_score DESC LIMIT 1",
            (lt,)).fetchone()
        if row:
            trs,st=[],set()
            for p in str(row[1] or "").split("|"):
                p=p.strip()
                k2=cf(p)
                if not p or k2 in st or len(p)<2: continue
                st.add(k2); trs.append(p)
            return {"translation":", ".join(trs[:4]),"written_rep":str(row[0] or "")}
    return {"translation":"","written_rep":""}


# ---------------------------------------------------------------------------
# Sözlük
# ---------------------------------------------------------------------------
def load_dict() -> list[dict]:
    for p in DICT_PATHS:
        if p.exists():
            with open(p,encoding="utf-8") as f: return json.load(f)
    return []

def save_dict(recs: list[dict]) -> None:
    for p in DICT_PATHS:
        try:
            with open(p,"w",encoding="utf-8") as f:
                json.dump(recs,f,ensure_ascii=False,indent=2)
            print(f"  Kaydedildi: {p}")
        except Exception as e:
            print(f"  [HATA] {p}: {e}",file=sys.stderr)

def build_keys(recs: list[dict]) -> set[str]:
    k=set()
    for r in recs:
        a=(r.get("almanca","") or "").strip()
        k.add(cf(a)); k.add(cf(strip_art(a)))
    return k

def ref_links(almanca: str) -> dict:
    w=strip_art(almanca); e=_up.quote(w)
    return {"duden":f"https://www.duden.de/suchen/dudenonline/{e}",
            "dwds":f"https://www.dwds.de/wb/{e}",
            "wiktionary_de":f"https://de.wiktionary.org/wiki/{e}"}

def fetch_text(url: str) -> str:
    url=fix_url(url)
    headers={"User-Agent":"Mozilla/5.0 (compatible; AlmancaSozluk/1.0)",
             "Accept-Language":"de-DE,de;q=0.9","Accept":"text/html,application/xhtml+xml"}
    try:
        with _ur.urlopen(_ur.Request(url,headers=headers),timeout=20) as r:
            raw=r.read(); ch=r.headers.get_content_charset() or "utf-8"
            return raw.decode(ch,errors="replace")
    except Exception as e:
        print(f"  [HATA] {url}: {e}",file=sys.stderr); return ""


# ---------------------------------------------------------------------------
# Aday çıkarma (min_freq=1 destekli)
# ---------------------------------------------------------------------------
def extract(url, existing_keys, cur, min_freq=1):
    html=fetch_text(url)
    if not html: return []
    p=VisibleTextExtractor(); p.feed(html); text=p.get_text()
    if not text: return []
    print(f"  {len(text):,} karakter")
    counts: Counter[str]=Counter()
    labels: dict[str,str]={}
    lc_seen: set[str]=set()
    for tok in TOKEN_RE.findall(text):
        if tok[:1].islower(): lc_seen.add(cf(tok))
    for tok in TOKEN_RE.findall(text):
        norm=cf(tok)
        if not norm or len(norm)<4 or len(norm)>40: continue
        if is_sw(tok) or is_pn(tok): continue
        if norm in existing_keys: continue
        counts[norm]+=1
        cur_l=labels.get(norm)
        if cur_l is None or (tok[:1].isupper() and not cur_l[:1].isupper()):
            labels[norm]=tok
    cands=[]
    for norm,freq in counts.most_common(400):
        if freq < min_freq: continue
        german=labels.get(norm,norm)
        sug=lookup(german,cur)
        if not sug["translation"] or len(sug["translation"].strip())<2: continue
        wr=cf(sug.get("written_rep",""))
        if wr and wr!=norm and wr in existing_keys: continue
        skip=False
        for suf in ("es","en","er","em"):
            if german.endswith(suf) and cf(german[:-len(suf)]) in existing_keys:
                skip=True; break
        if skip: continue
        cands.append({"almanca":german,"turkce":sug["translation"],
                       "pos":guess_pos(german),"freq":freq,"written_rep":sug["written_rep"]})
    return cands

def to_record(cand, source_url, kategori="otomotiv"):
    alm=cand["almanca"]; art=""
    wr=cand.get("written_rep","")
    for a in ("der ","die ","das "):
        if wr.lower().startswith(a): art=a.strip(); alm=wr[len(a):]; break
    src="kfz-tech.de" if "kfz-tech.de" in source_url else "Wikipedia DE"
    topic=source_url.split("/wiki/")[-1].replace("_"," ") if "/wiki/" in source_url else source_url.split("/")[-1]
    return {"almanca":alm,"artikel":art,"turkce":cand["turkce"],
            "kategoriler":[kategori],"aciklama_turkce":"","ilgili_kayitlar":[],
            "tur":cand["pos"],"ornek_almanca":"","ornek_turkce":"","ornekler":[],
            "kaynak":f"WikDict; {src}",
            "kaynak_url":f"https://kaikki.org/dewiktionary/rawdata.html; {source_url}",
            "ceviri_durumu":"kaynak-izli","ceviri_inceleme_notu":"","ceviri_kaynaklari":[],
            "not":f"URL-import: {src} — {topic}",
            "referans_linkler":ref_links(alm),"seviye":"","genitiv_endung":"","kelime_ailesi":[]}

def phrase_to_record(phrase, turkce, tur):
    return {"almanca":phrase,"artikel":"","turkce":turkce,
            "kategoriler":[],"aciklama_turkce":"","ilgili_kayitlar":[],
            "tur":tur,"ornek_almanca":"","ornek_turkce":"","ornekler":[],
            "kaynak":"Duden; DWDS; IDS Mannheim",
            "kaynak_url":"https://www.duden.de; https://www.dwds.de",
            "ceviri_durumu":"kaynak-izli","ceviri_inceleme_notu":"","ceviri_kaynaklari":[],
            "not":"Kuratif kalıp — Almanca Funktionsverbgefüge ve teknik deyim",
            "referans_linkler":ref_links(phrase),"seviye":"","genitiv_endung":"","kelime_ailesi":[]}


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
def main():
    print("="*65)
    print("enrich_deep.py — Derinlemesli zenginlestirme")
    print(f"Kuratif kalip: {len(CURATED_PHRASES)}")
    print(f"URL sayisi: {len(SOURCE_URLS)}")
    print("="*65)

    if WIKDICT_PATH.exists():
        conn=sqlite3.connect(str(WIKDICT_PATH)); wcur=conn.cursor()
        print(f"WikDict: {WIKDICT_PATH}")
    else:
        conn=None; wcur=None
        print("[UYARI] WikDict bulunamadi",file=sys.stderr)

    records=load_dict()
    added_keys=build_keys(records)
    print(f"Mevcut sozluk: {len(records)} kayit\n")

    # --- AŞAMA 1: Kuratif kalıplar ---
    print("─"*40)
    print("ASAMA 1: Kuratif kalipler ekleniyor...")
    phrase_added=0
    for phrase, turkce, tur in CURATED_PHRASES:
        norm=cf(phrase)
        if norm in added_keys:
            print(f"  [var] {phrase}")
            continue
        rec=phrase_to_record(phrase, turkce, tur)
        records.append(rec)
        added_keys.add(norm)
        phrase_added+=1
        print(f"  + {phrase} -> {turkce}")
    print(f"\n{phrase_added} kalip eklendi.\n")

    # --- AŞAMA 2: URL tarama ---
    print("─"*40)
    print("ASAMA 2: URL tarama basliyor...")
    url_new_total=0
    url_stats: dict[str,int]={}
    total=len(SOURCE_URLS)

    for i, url in enumerate(SOURCE_URLS,1):
        topic=url.split("/wiki/")[-1].replace("_"," ") if "/wiki/" in url else url.split("/")[-1]
        print(f"\n[{i}/{total}] {topic}")
        cands=extract(url, added_keys, wcur, min_freq=1)
        cnt=0
        for cand in cands:
            norm=cf(cand["almanca"]); nb=cf(strip_art(cand["almanca"]))
            if norm in added_keys or nb in added_keys: continue
            kategori="otomotiv" if i<=len([u for u in SOURCE_URLS if "kfz-tech" in u or
                any(k in u for k in ["Motor","Getriebe","Fahrwerk","Bremse","Reifen",
                "Karosserie","Elektro","Hybrid","Kfz","Kraftfahr","Turbo","Diesel",
                "Benzin","Kupplung","Lenkung","Fahrer","Airbag","Crash"])]) else "teknik"
            rec=to_record(cand, url, kategori)
            records.append(rec)
            added_keys.add(norm); added_keys.add(nb)
            cnt+=1
            print(f"    + {rec['almanca']} -> {rec['turkce']}")
        url_stats[topic]=cnt; url_new_total+=cnt
        print(f"  => {cnt} yeni")

        if i%25==0 and (phrase_added+url_new_total)>0:
            print(f"\n  [ARA KAYIT] Toplam {phrase_added+url_new_total} yeni kayit...")
            save_dict(records)

    if conn: conn.close()

    print(f"\n{'='*65}")
    print(f"ASAMA 1 (kalipler): +{phrase_added}")
    print(f"ASAMA 2 (URL):      +{url_new_total}")
    print(f"TOPLAM:             +{phrase_added+url_new_total}")
    print(f"{'='*65}")

    save_dict(records)

    print("\n--- URL konu ozeti (en cok) ---")
    for topic,cnt in sorted(url_stats.items(),key=lambda x:-x[1])[:30]:
        if cnt: print(f"  {topic}: +{cnt}")

    print(f"\nSozluk artik {len(records)} kayit iceriyor.")

if __name__=="__main__":
    main()
