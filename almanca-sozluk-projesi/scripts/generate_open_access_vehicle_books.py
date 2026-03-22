#!/usr/bin/env python
"""Generate phrase and term entries from public open-access vehicle books."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "manual" / "open_access_vehicle_books.json"

AUTONOMES_FAHREN_URL = "https://link.springer.com/book/10.1007/978-3-658-16268-9"
SHUTTLEBUSSE_URL = "https://link.springer.com/book/10.1007/978-3-658-45154-7"

RECORDS = [
    {
        "almanca": "Autonomes Fahren",
        "turkce": "otonom sürüş",
        "tur": "ifade",
        "kaynak_url": AUTONOMES_FAHREN_URL,
    },
    {
        "almanca": "Rechtliche Aspekte des autonomen Fahrens",
        "turkce": "otonom sürüşün hukuki yönleri",
        "tur": "ifade",
        "kaynak_url": AUTONOMES_FAHREN_URL,
    },
    {
        "almanca": "Ökonomische Aspekte des autonomen Fahrens",
        "turkce": "otonom sürüşün ekonomik yönleri",
        "tur": "ifade",
        "kaynak_url": AUTONOMES_FAHREN_URL,
    },
    {
        "almanca": "Räumliche Aspekte des autonomen Fahrens",
        "turkce": "otonom sürüşün mekânsal yönleri",
        "tur": "ifade",
        "kaynak_url": AUTONOMES_FAHREN_URL,
    },
    {
        "almanca": "Anwendungsfelder des autonomen Fahrens",
        "turkce": "otonom sürüşün uygulama alanları",
        "tur": "ifade",
        "kaynak_url": AUTONOMES_FAHREN_URL,
    },
    {
        "almanca": "Autonome Personenbeförderung",
        "turkce": "otonom yolcu taşımacılığı",
        "tur": "ifade",
        "kaynak_url": AUTONOMES_FAHREN_URL,
    },
    {
        "almanca": "Autonome Güterbeförderung",
        "turkce": "otonom yük taşımacılığı",
        "tur": "ifade",
        "kaynak_url": AUTONOMES_FAHREN_URL,
    },
    {
        "almanca": "Neue Mobilitätskonzepte",
        "turkce": "yeni mobilite konseptleri",
        "tur": "ifade",
        "kaynak_url": AUTONOMES_FAHREN_URL,
    },
    {
        "almanca": "Verkehrsmanagement",
        "turkce": "trafik yönetimi",
        "tur": "isim",
        "kaynak_url": AUTONOMES_FAHREN_URL,
    },
    {
        "almanca": "Verkehrssteuerung",
        "turkce": "trafik yönlendirmesi",
        "tur": "isim",
        "kaynak_url": AUTONOMES_FAHREN_URL,
    },
    {
        "almanca": "Konnektivitätsveränderung",
        "turkce": "bağlanırlık değişimi",
        "tur": "isim",
        "kaynak_url": AUTONOMES_FAHREN_URL,
    },
    {
        "almanca": "Mobilitätswahrnehmung",
        "turkce": "mobilite algısı",
        "tur": "isim",
        "kaynak_url": AUTONOMES_FAHREN_URL,
    },
    {
        "almanca": "Autonome Shuttlebusse im ÖPNV",
        "turkce": "toplu taşımada otonom shuttle otobüsler",
        "tur": "ifade",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "ÖPNV",
        "turkce": "toplu taşıma",
        "tur": "kisaltma",
        "not": "Açılım: Öffentlicher Personennahverkehr.",
        "aciklama_turkce": "Kent içi ve yakın çevrede düzenli toplu yolcu taşımacılığı sistemi.",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Öffentlicher Personennahverkehr",
        "turkce": "kamusal yakın mesafe yolcu taşımacılığı",
        "tur": "ifade",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Autonomer Shuttlebus",
        "turkce": "otonom shuttle otobüs",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Mobilitätsdienstleistung",
        "turkce": "mobilite hizmeti",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Betriebsgebiet",
        "turkce": "işletme bölgesi",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Linienbetrieb",
        "turkce": "hat işletimi",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Bedarfsverkehr",
        "turkce": "talep odaklı ulaşım",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Flottensteuerung",
        "turkce": "filo yönetimi",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Betriebskonzept",
        "turkce": "işletme konsepti",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Sicherheitskonzept",
        "turkce": "güvenlik konsepti",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Nutzerakzeptanz",
        "turkce": "kullanıcı kabulü",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Betriebsüberwachung",
        "turkce": "işletme izleme",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Fernüberwachung",
        "turkce": "uzaktan izleme",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Hinderniserkennung",
        "turkce": "engel algılama",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Umfelderfassung",
        "turkce": "çevre algılama",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Betriebserprobung",
        "turkce": "işletme denemesi",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
    {
        "almanca": "Einführungsstrategie",
        "turkce": "devreye alma stratejisi",
        "tur": "isim",
        "kaynak_url": SHUTTLEBUSSE_URL,
    },
]


def build_payload() -> dict:
    records = []
    for record in RECORDS:
        item = {
            "almanca": record["almanca"],
            "artikel": "",
            "turkce": record["turkce"],
            "tur": record["tur"],
            "kaynak_url": record["kaynak_url"],
        }
        if record.get("not"):
            item["not"] = record["not"]
        if record.get("aciklama_turkce"):
            item["aciklama_turkce"] = record["aciklama_turkce"]
        records.append(item)

    return {
        "source_name": "open-access-vehicle-books",
        "default_note": (
            "Açık erişimli Springer kitaplarının kamuya açık bölüm başlıkları ve kavramları "
            "üzerinden manuel olarak normalize edildi."
        ),
        "records": records,
    }


def main() -> None:
    payload = build_payload()
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"record_count": len(payload["records"]), "output": str(OUTPUT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
