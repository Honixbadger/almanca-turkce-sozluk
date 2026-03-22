#!/usr/bin/env python
"""Generate phrase-style truck-technology entries from curated book titles."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "manual" / "nutzfahrzeugtechnik_phrases.json"
SOURCE_URL = "https://doi.org/10.1007/978-3-658-09537-6"

PHRASE_TRANSLATIONS = [
    ("Einführung in die Nutzfahrzeugtechnik", "ticari araç tekniğine giriş"),
    ("Bedeutung der Nutzfahrzeugtechnik", "ticari araç tekniğinin önemi"),
    ("Entwicklungsschwerpunkte und künftige Konzepte", "gelişim odakları ve gelecekteki konseptler"),
    ("Typenbezeichnung von Lastkraftwagenfahrgestellen", "kamyon şasilerinin tip adlandırması"),
    ("Lastkraftwagenangebot nach Gewichtsklassen", "ağırlık sınıflarına göre kamyon seçenekleri"),
    ("Rechtliche Grundlagen, Vorschriften, Normen", "hukuki temeller, yönetmelikler ve normlar"),
    ("Entwicklungsschritte des Nutzfahrzeugs", "ticari aracın gelişim aşamaları"),
    ("Einfluss von Rahmenbedingungen", "çerçeve koşullarının etkisi"),
    ("Elektronik gewinnt stetig an Bedeutung", "elektroniğin önemi giderek artıyor"),
    ("Antrieb und Fahrleistung", "tahrik ve sürüş performansı"),
    ("Konzeption von Nutzfahrzeugen", "ticari araçların konsept tasarımı"),
    ("Zulässige Abmessungen und Gewichte", "izin verilen ölçüler ve ağırlıklar"),
    ("Internationale Richtlinien", "uluslararası yönergeler"),
    ("Nationale Normen, Vorschriften und Richtlinien", "ulusal normlar, yönetmelikler ve yönergeler"),
    ("Rechtliche Grundlagen", "hukuki temeller"),
    ("Allgemeine Abmessungen", "genel ölçüler"),
    ("Ausblick", "gelecek görünümü"),
    ("Fahrzeugbenennungen", "araç adlandırmaları"),
    ("Motoranordnungen", "motor yerleşimleri"),
    ("Transportaufgabe", "taşıma görevi"),
    ("Kundennutzen", "müşteri faydası"),
    ("Fahrgrenzen", "sürüş sınırları"),
    ("Freie Zugkraft", "kullanılabilir çekiş kuvveti"),
    ("Kraftbedarf eines Nutzfahrzeugs", "bir ticari aracın güç ihtiyacı"),
    ("Luftwiderstand, Aerodynamik des Nutzfahrzeuges", "hava direnci ve ticari aracın aerodinamiği"),
    ("Kurvenläufigkeit von Fahrzeugen und Fahrzeugkombinationen", "araçların ve araç kombinasyonlarının viraj kabiliyeti"),
    ("Verfahren zur Untersuchung der Kurvenläufigkeit", "viraj kabiliyetini inceleme yöntemleri"),
    ("Achslasten, Aufbaulänge und Nutzlastverteilung", "aks yükleri, üst yapı uzunluğu ve faydalı yük dağılımı"),
    ("Aufbaulänge und Nutzlastverteilung", "üst yapı uzunluğu ve faydalı yük dağılımı"),
    ("Fahrzeug- und Aufbaukonzept", "araç ve üst yapı konsepti"),
    ("Wechselaufbauten und Container", "değiştirilebilir üst yapılar ve konteynerler"),
    ("Höchstzulässige Abmessungen", "izin verilen azami ölçüler"),
    ("Überlange Fahrzeuge und Kombinationen", "aşırı uzun araçlar ve kombinasyonlar"),
    ("Anhänge- und Stützlasten", "çeki ve dikey yükler"),
    ("Höchstzulässige Gesamtgewichte", "izin verilen azami toplam ağırlıklar"),
    ("Höchstzulässige Achslasten", "izin verilen azami aks yükleri"),
    ("Entwicklungs- und Prüftechnik", "geliştirme ve test tekniği"),
    ("Aktive und passive Sicherheit", "aktif ve pasif güvenlik"),
    ("Berechnung zugverbindender Einrichtungen", "çeki bağlantı düzeneklerinin hesabı"),
    ("Bremsvorgang und Bremswirkung", "frenleme süreci ve fren etkisi"),
    ("Räder und Reifen", "jantlar ve lastikler"),
    ("Anhängerfahrgestell", "römork şasisi"),
    ("Gesetzliche Rahmenbedingungen", "yasal çerçeve koşulları"),
    ("Datenblatt, Fahrgestellzeichnung, Aufbaurichtlinien", "veri sayfası, şasi çizimi ve üst yapı yönergeleri"),
    ("Fahrerhaus", "sürücü kabini"),
    ("Korrosionsschutz", "korozyon koruması"),
    ("Ladungssicherung", "yük sabitleme"),
    ("Aufbauten", "üst yapılar"),
    ("Aufbaurichtlinien und Aufbaugenehmigung", "üst yapı yönergeleri ve üst yapı onayı"),
    ("Kofferaufbauten", "kapalı kasa üst yapılar"),
    ("Bemessung der Tragwerke", "taşıyıcı yapıların boyutlandırılması"),
    ("Belastungsfälle", "yükleme durumları"),
    ("Elastische Biegeverformungen in Nutzfahrzeugtragwerken", "ticari araç taşıyıcılarında elastik eğilme deformasyonları"),
    ("Gestaltung der Tragwerke", "taşıyıcı yapıların tasarımı"),
    ("Tragsystem Fahrgestellrahmen", "şasi çerçevesinin taşıyıcı sistemi"),
    ("Gestaltung von Lkw-Fahrgestellrahmen", "kamyon şasi çerçevelerinin tasarımı"),
    ("Q- und M-Linien am Balkenmodell", "kiriş modelindeki Q ve M çizgileri"),
    ("Hilfsrahmengestaltung", "yardımcı şase tasarımı"),
    ("Aufbauten ohne Hilfsrahmen", "yardımcı şasesiz üst yapılar"),
    ("Hilfsrahmen und Aufbaubefestigung", "yardımcı şase ve üst yapı bağlantısı"),
    ("Eisenwerkstoffe", "demir esaslı malzemeler"),
    ("Sandwichwerkstoffe", "sandviç yapı malzemeleri"),
    ("Alternative Antriebe im Nutzfahrzeugbereich", "ticari araç alanında alternatif tahrik sistemleri"),
    ("CO2-Gesetzgebung und Rahmenbedingungen On-Road", "yol araçlarında CO2 mevzuatı ve çerçeve koşulları"),
    ("Kurbelwellendichtringe für Nutzfahrzeug- und Industriedieselmotoren", "ticari araç ve endüstriyel dizel motorlar için krank mili keçeleri"),
    ("Betriebsweise des Dieselmotors", "dizel motorun çalışma biçimi"),
    ("Zusammenfassung und Ausblick", "özet ve gelecek görünümü"),
    ("Kraft- und Schmierstoffe", "yakıtlar ve yağlayıcılar"),
    ("Anforderungen an den Kraftstoff", "yakıta yönelik gereksinimler"),
    ("Öl- und Kühlkreislauf", "yağ ve soğutma devresi"),
    ("Anordnung der Hilfsaggregate und deren Antrieb", "yardımcı agregaların yerleşimi ve tahriki"),
    ("Zukünftige Entwicklungen", "gelecekteki gelişmeler"),
    ("Abgasreinigung beim Nutzfahrzeug-Dieselmotor", "ticari araç dizel motorunda egzoz gazı arıtımı"),
    ("NOx-, Partikel-, CO- und HC-Emissionen im Dieselmotor", "dizel motorda NOx, partikül, CO ve HC emisyonları"),
    ("Vorschriften zur Emissionsbegrenzung von Nutzfahrzeugmotoren", "ticari araç motorlarında emisyon sınırlandırma mevzuatı"),
    ("Einspritzung, Gemischbildung und Verbrennung", "enjeksiyon, karışım oluşumu ve yanma"),
    ("Einspritzsysteme für Nutzfahrzeugmotoren", "ticari araç motorları için enjeksiyon sistemleri"),
    ("Verbrennung im Dieselmotor", "dizel motorda yanma"),
    ("Thermodynamische Grundlagen des dieselmotorischen Arbeitsprozesses", "dizel motor çevriminin termodinamik temelleri"),
    ("Abgasnachbehandlungssysteme für Nutzfahrzeugmotoren", "ticari araç motorları için egzoz son işlem sistemleri"),
    ("Variationen der Abgasturbolader-Anpassung an den Motor", "egzoz turboşarjın motora uyarlanma varyasyonları"),
    ("Steuerung und Ventiltrieb", "kumanda ve supap mekanizması"),
    ("Zylinderkopf und Zylinderkopf-Dichtung", "silindir kapağı ve silindir kapak contası"),
    ("Anforderungsprofil für Kurbelwellendichtungen", "krank mili keçeleri için gereksinim profili"),
    ("Dynamik der Kurbelwellen in Dieselmotoren", "dizel motorlarda krank millerinin dinamiği"),
    ("Energierückgewinnungssysteme beim schweren Nutzfahrzeug", "ağır ticari araçta enerji geri kazanım sistemleri"),
    ("Einsparpotentiale durch Hybridisierung", "hibritleştirme ile tasarruf potansiyeli"),
    ("Grundsatzüberlegungen", "temel değerlendirmeler"),
    ("Auslegungskriterien", "tasarım kriterleri"),
    ("Ausgeführte Beispiele", "uygulanmış örnekler"),
    ("Bauform, Bauarten, Aufbau von Getrieben", "şanzımanların formu, türleri ve yapısı"),
    ("Konstruktive Getriebegrundkonzepte", "şanzımanların temel yapısal konseptleri"),
    ("Hydrodynamische Kupplungen und Wandler", "hidrodinamik kavramalar ve dönüştürücüler"),
    ("Aufbau des Antriebsstranges", "güç aktarım hattının yapısı"),
    ("Übergreifende Aspekte", "genel kapsayıcı yönler"),
    ("Elektromagnetische Verträglichkeit", "elektromanyetik uyumluluk"),
    ("Systeme", "sistemler"),
    ("Funktionen", "fonksiyonlar"),
    ("Basisfunktionen", "temel fonksiyonlar"),
    ("Schnittstellenfunktionen", "arayüz fonksiyonları"),
    ("Begriffsdefinition", "kavram tanımı"),
    ("Abgrenzung System Fahrzeug", "sistem ile araç arasındaki sınır tanımı"),
    ("Grundsätzliches", "temel ilkeler"),
    ("Standardfunktionen", "standart fonksiyonlar"),
    ("Bedien- und Anzeigesysteme", "kumanda ve gösterge sistemleri"),
    ("Brems- und Fahrwerksysteme", "fren ve yürüyen aksam sistemleri"),
    ("Informationsübertragung/Netzwerke", "bilgi aktarımı ve ağlar"),
    ("Energiebereitstellung und -verteilung", "enerji sağlama ve dağıtımı"),
]


def build_payload() -> dict:
    records = []
    for almanca, turkce in PHRASE_TRANSLATIONS:
        records.append(
            {
                "almanca": almanca,
                "artikel": "",
                "turkce": turkce,
                "tur": "ifade",
                "kaynak_url": SOURCE_URL,
            }
        )

    return {
        "source_name": "nutzfahrzeugtechnik-buch",
        "default_note": (
            "Kitap yer imi ve içerik başlıklarından çıkarılan ifade/kalıplar için "
            "Türkçe karşılık manuel olarak normalize edildi; tam metin yeniden dağıtılmadı."
        ),
        "records": records,
    }


def main() -> None:
    OUTPUT_PATH.write_text(json.dumps(build_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"record_count": len(PHRASE_TRANSLATIONS), "output": str(OUTPUT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
