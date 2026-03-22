#!/usr/bin/env python
"""Generate curated technical entries from public mein-autolexikon slugs."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM_PATH = PROJECT_ROOT / "data" / "interim" / "mein_autolexikon_terms.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "manual" / "mein_autolexikon_curated_terms.json"

CURATED_TERMS = [
    ("abgasanlage", "Abgasanlage", "egzoz sistemi"),
    ("abgaskruemmer", "Abgaskrümmer", "egzoz manifoldu"),
    ("abgasnorm-euro-6", "Abgasnorm Euro 6", "Euro 6 emisyon normu"),
    ("abgastemperatursensor", "Abgastemperatursensor", "egzoz sıcaklık sensörü"),
    ("befestigungstechnik", "Befestigungstechnik", "bağlantı tekniği"),
    ("breitbandsonde", "Breitbandsonde", "geniş bant lambda sensörü"),
    ("diesel-partikelfilter", "Diesel-Partikelfilter", "dizel partikül filtresi"),
    ("endschalldaempfer", "Endschalldämpfer", "arka susturucu"),
    ("lambdasonde", "Lambdasonde", "lambda sensörü"),
    ("ottopartikelfilter", "Ottopartikelfilter", "benzin partikül filtresi"),
    ("schalldaempfer", "Schalldämpfer", "susturucu"),
    ("scr-katalysator", "SCR-Katalysator", "SCR katalizörü"),
    ("sprungsonde", "Sprungsonde", "dar bant lambda sensörü"),
    ("achsmanschette", "Achsmanschette", "aks körüğü"),
    ("aggregatetrieb", "Aggregatetrieb", "yardımcı ünite tahriki"),
    ("antriebswelle", "Antriebswelle", "tahrik mili"),
    ("batteriekuehlung-in-elektro-fahrzeugen", "Batteriekühlung in Elektro-Fahrzeugen", "elektrikli araçlarda batarya soğutması"),
    ("benzin-direkteinspritzung", "Benzin-Direkteinspritzung", "benzin direkt enjeksiyonu"),
    ("brennstoffzelle", "Brennstoffzelle", "yakıt hücresi"),
    ("differential", "Differential", "diferansiyel"),
    ("e-fuels", "E-Fuels", "sentetik yakıtlar"),
    ("eachse", "E-Achse", "elektrikli aks"),
    ("elektroauto-batterie-akku", "Elektroauto-Batterie/Akku", "elektrikli araç bataryası"),
    ("elektromotor-bev", "Elektromotor BEV", "bataryalı elektrikli araç motoru"),
    ("generatorfreilauf", "Generatorfreilauf", "alternatör serbest kavraması"),
    ("hybridantrieb", "Hybridantrieb", "hibrit tahrik"),
    ("hydraulische-kupplungsbetaetigung", "Hydraulische Kupplungsbetätigung", "hidrolik debriyaj kumandası"),
    ("keilriemen", "Keilriemen", "V kayışı"),
    ("keilrippenriemen", "Keilrippenriemen", "kanallı kayış"),
    ("kettentrieb", "Kettentrieb", "zincir tahriki"),
    ("kolben", "Kolben", "piston"),
    ("kraftstoffpumpe", "Kraftstoffpumpe", "yakıt pompası"),
    ("kuehlfluessigkeit", "Kühlflüssigkeit", "soğutma sıvısı"),
    ("kurbeltrieb", "Kurbeltrieb", "krank mekanizması"),
    ("ladeluftkuehler", "Ladeluftkühler", "şarj havası soğutucusu"),
    ("leistungselektronik", "Leistungselektronik", "güç elektroniği"),
    ("luftmassenmesser", "Luftmassenmesser", "hava kütle ölçer"),
    ("motorblock", "Motorblock", "motor bloğu"),
    ("motorlager", "Motorlager", "motor takozu"),
    ("motorsteuergeraet", "Motorsteuergerät", "motor kontrol ünitesi"),
    ("motorsteuerung", "Motorsteuerung", "motor kontrol sistemi"),
    ("nockenwelle", "Nockenwelle", "eksantrik mili"),
    ("oelpumpe", "Ölpumpe", "yağ pompası"),
    ("oelwanne", "Ölwanne", "yağ karteri"),
    ("ottomotor", "Ottomotor", "benzinli motor"),
    ("pleuelstange", "Pleuelstange", "biyel kolu"),
    ("radnabenantrieb", "Radnabenantrieb", "teker göbeği tahriki"),
    ("schwingungsdaempfer", "Schwingungsdämpfer", "titreşim sönümleyici"),
    ("schwungscheibe", "Schwungscheibe", "volan"),
    ("start-stopp-automatik", "Start-Stopp-Automatik", "start-stop otomatiği"),
    ("steuertrieb", "Steuertrieb", "zamanlama tahriki"),
    ("ventile", "Ventile", "supaplar"),
    ("wasserpumpe", "Wasserpumpe", "su pompası"),
    ("zahnriemen", "Zahnriemen", "triger kayışı"),
    ("zweimassenschwungrad", "Zweimassenschwungrad", "çift kütleli volan"),
    ("zylinderabschaltung", "Zylinderabschaltung", "silindir devre dışı bırakma"),
    ("zylinderkopfdichtung", "Zylinderkopfdichtung", "silindir kapak contası"),
    ("heckleuchte", "Heckleuchte", "arka lamba"),
    ("kurvenlicht", "Kurvenlicht", "viraj aydınlatması"),
    ("led-scheinwerfer", "LED-Scheinwerfer", "LED far"),
    ("nebelscheinwerfer", "Nebelscheinwerfer", "sis farı"),
    ("nebelschlussleuchte", "Nebelschlussleuchte", "arka sis lambası"),
    ("scheinwerferlampe", "Scheinwerferlampe", "far lambası"),
    ("scheinwerferreinigungsanlage", "Scheinwerferreinigungsanlage", "far yıkama sistemi"),
    ("tagfahrleuchte", "Tagfahrleuchte", "gündüz sürüş lambası"),
    ("zusatzscheinwerfer", "Zusatzscheinwerfer", "ek far"),
    ("abs-steuergeraet", "ABS-Steuergerät", "ABS kontrol ünitesi"),
    ("antiblockiersystem-abs", "Antiblockiersystem ABS", "ABS kilitlenme önleyici sistem"),
    ("bremsbacken", "Bremsbacken", "fren pabucu"),
    ("bremsbelag", "Bremsbelag", "fren balatası"),
    ("bremskraftverstaerker", "Bremskraftverstärker", "fren servosu"),
]


def load_slug_map() -> dict[str, str]:
    payload = json.loads(INTERIM_PATH.read_text(encoding="utf-8"))
    return {item["slug"]: item["url"] for item in payload.get("seeds", []) if item.get("slug") and item.get("url")}


def build_payload() -> dict:
    slug_map = load_slug_map()
    records = []

    for slug, almanca, turkce in CURATED_TERMS:
        records.append(
            {
                "almanca": almanca,
                "artikel": "",
                "turkce": turkce,
                "tur": "isim",
                "kaynak_url": slug_map.get(slug, ""),
            }
        )

    return {
        "source_name": "mein-autolexikon",
        "default_note": (
            "mein-autolexikon terim sayfalarindaki baslik ve slug alanlari uzerinden secilen teknik "
            "kayitlar manuel olarak normalize edildi; tam tanim metni yeniden dagitilmadi."
        ),
        "records": records,
    }


def main() -> None:
    payload = build_payload()
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"record_count": len(payload["records"]), "output": str(OUTPUT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
