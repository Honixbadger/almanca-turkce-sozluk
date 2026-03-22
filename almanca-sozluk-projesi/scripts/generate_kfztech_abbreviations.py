#!/usr/bin/env python
"""Generate curated abbreviation entries from public kfztech abbreviation pages."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "manual" / "kfztech_abbreviations.json"

ABBREVIATIONS = [
    {
        "almanca": "ADAS",
        "turkce": "gelişmiş sürücü destek sistemleri",
        "aciklama_turkce": "Sürücüye algılama, uyarı ve müdahale desteği veren elektronik yardımcı sistemler bütünü.",
        "not": "Açılım: Advanced Driver Assistance Systems.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-A-AC.htm",
    },
    {
        "almanca": "DPF",
        "turkce": "dizel partikül filtresi",
        "aciklama_turkce": "Dizel egzozundaki kurum ve ince parçacıkları tutan filtre elemanı.",
        "not": "Açılım: Diesel-Partikelfilter.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-DK-DZ.htm",
    },
    {
        "almanca": "EDC",
        "turkce": "elektronik amortisör kontrolü",
        "aciklama_turkce": "Amortisör sertliğini sürüş koşullarına göre elektronik olarak ayarlayan sistem.",
        "not": "Açılım: Electronic Damper Control.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-E-EL.htm",
    },
    {
        "almanca": "EMB",
        "turkce": "elektromekanik fren",
        "aciklama_turkce": "Fren kuvvetini hidrolik yerine elektrikli aktüatörlerle oluşturan fren düzeni.",
        "not": "Açılım: Electro Mechanical Brake.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-EM-EZ.htm",
    },
    {
        "almanca": "EOBD",
        "turkce": "Avrupa araç üstü arıza teşhisi",
        "aciklama_turkce": "Motor ve emisyonla ilgili arızaları araç üzerinde izleyen standart teşhis sistemi.",
        "not": "Açılım: European On-Board Diagnostics.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-E-EL.htm",
    },
    {
        "almanca": "FC",
        "turkce": "yakıt hücresi",
        "aciklama_turkce": "Kimyasal enerjiyi doğrudan elektrik enerjisine dönüştüren güç üretim ünitesi.",
        "not": "Açılım: Fuel Cell.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-F.htm",
    },
    {
        "almanca": "FSI",
        "turkce": "katmanlı yakıt enjeksiyonu",
        "aciklama_turkce": "Yakıtı doğrudan yanma odasına tabakalı biçimde püskürten benzinli motor enjeksiyon sistemi.",
        "not": "Açılım: Fuel Stratified Injection.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-F.htm",
    },
    {
        "almanca": "HDI",
        "turkce": "yüksek basınçlı direkt enjeksiyon",
        "aciklama_turkce": "Yakıtın yüksek basınçla doğrudan silindire püskürtüldüğü enjeksiyon düzeni.",
        "not": "Açılım: High-pressure Direct Injection.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-H.htm",
    },
    {
        "almanca": "IBS",
        "turkce": "akıllı akü sensörü",
        "aciklama_turkce": "Akünün gerilim, akım ve sıcaklık durumunu ölçerek enerji yönetimine veri sağlayan sensör.",
        "not": "Açılım: Intelligent Battery Sensor.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-I.htm",
    },
    {
        "almanca": "LPG",
        "turkce": "sıvılaştırılmış petrol gazı",
        "aciklama_turkce": "Otomotivde alternatif yakıt olarak kullanılan propan-bütan temelli gaz karışımı.",
        "not": "Açılım: Liquefied Petroleum Gas.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-L.htm",
    },
    {
        "almanca": "MAF",
        "turkce": "kütle hava akış sensörü",
        "aciklama_turkce": "Motora giren havanın kütlesini ölçerek karışım ve enjeksiyon kontrolüne veri veren sensör.",
        "not": "Açılım: Mass Air Flow.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-M.htm",
    },
    {
        "almanca": "PSI",
        "turkce": "inç kare başına pound",
        "aciklama_turkce": "Özellikle lastik ve sistem basınçlarında kullanılan basınç birimi.",
        "not": "Açılım: Pounds per Square Inch.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-PK-Q.htm",
    },
    {
        "almanca": "RDC",
        "turkce": "lastik basınç kontrolü",
        "aciklama_turkce": "Lastik basıncını izleyip sürücüyü uyaran kontrol sistemi.",
        "not": "Açılım: Reifen Druck Control.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-R.htm",
    },
    {
        "almanca": "VNT",
        "turkce": "değişken nozullu türbin",
        "aciklama_turkce": "Egzoz gazı akışını ayarlanabilir kanatçıklarla yöneten turbo türbini.",
        "not": "Açılım: Variable Nozzle Turbine.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-V.htm",
    },
    {
        "almanca": "VVT-i",
        "turkce": "akıllı değişken supap zamanlaması",
        "aciklama_turkce": "Supap açılma zamanını motor yüküne ve devrine göre ayarlayan kumanda sistemi.",
        "not": "Açılım: Variable Valve Timing-intelligent.",
        "kaynak_url": "https://www.kfztech.de/abc/Abkuerzungs-ABC-V.htm",
    },
]


def build_payload() -> dict:
    records = []
    for item in ABBREVIATIONS:
        records.append(
            {
                "almanca": item["almanca"],
                "artikel": "",
                "turkce": item["turkce"],
                "aciklama_turkce": item["aciklama_turkce"],
                "tur": "kisaltma",
                "not": item["not"],
                "kaynak_url": item["kaynak_url"],
            }
        )

    return {
        "source_name": "kfztech",
        "default_note": (
            "kfztech Abkuerzungs-ABC sayfalarindaki kısaltmalar manuel olarak normalize edildi; "
            "Türkçe karşılık ve açıklama teknik bağlama göre eklendi."
        ),
        "records": records,
    }


def main() -> None:
    OUTPUT_PATH.write_text(json.dumps(build_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"record_count": len(ABBREVIATIONS), "output": str(OUTPUT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
