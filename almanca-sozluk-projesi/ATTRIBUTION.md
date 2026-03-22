# Veri Kaynakları ve Atıflar

Bu proje, aşağıdaki açık kaynak veri ve araçlardan yararlanmaktadır.

---

## 1. Wiktionary / Vikisözlük (Kaikki.org üzerinden)

- **Kaynak:** [kaikki.org](https://kaikki.org/) — Wiktionary ham veri dökümleri
- **Dökümler:** `dewiktionary` (Almanca Vikisözlük), `trwiktionary` (Türkçe Vikisözlük)
- **Lisans:** [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)
- **Kullanım:** Almanca sözcüklerin Türkçe çevirileri ve dilbilgisi bilgileri

## 2. WikDict (de-tr)

- **Kaynak:** [wikdict.com](https://www.wikdict.com/)
- **İndirme:** [wikdict.com/dictionaries/sqlite](https://download.wikdict.com/dictionaries/sqlite/2/de-tr.sqlite3)
- **Lisans:** [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- **Kullanım:** Almanca→Türkçe çeviri güvenilirlik skoru ve yedek çeviri kaynağı

## 3. Wikipedia Almanca

- **Kaynak:** [de.wikipedia.org](https://de.wikipedia.org/)
- **Lisans:** [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)
- **Kullanım:** Bağlam bazlı kelime çıkarımı ve örnek cümleler

## 4. Project Gutenberg

- **Kaynak:** [gutenberg.org](https://www.gutenberg.org/)
- **Lisans:** Kamu Malı (Public Domain) — ABD'de telif hakkı süresi dolmuş eserler
- **Kullanım:** Almanca edebi metinlerden kelime ve örnek cümle çıkarımı
- **Başlıca Yazarlar:** Goethe, Schiller, Kafka, Fontane, Storm, Hesse, Kleist, Nietzsche ve diğerleri

## 5. Goethe-Institut Kelime Listeleri

- **Kaynak:** [goethe.de](https://www.goethe.de/de/spr/ueb/ger.html)
- **Kullanım:** A1/A2/B1 seviye bilgisi (kelime listelerinde referans olarak)
- **Not:** Kelimeler genel dil pratiğinin parçasıdır; CEFR seviyeleri atıf amaçlı kullanılmıştır.

## 6. Autolexikon.net / Mein-Autolexikon.de / KFZ-Tech.de

- **Kullanım:** Otomotiv terimleri için başlık referansı
- **Not:** Ham HTML dosyaları repoya dahil edilmemiştir; sadece dökümanlardan çıkarılan teknik terimler (facts) kullanılmıştır.

---

## Kullanılan Python Kütüphaneleri

| Kütüphane | Lisans |
|-----------|--------|
| tkinter | Python PSF License |
| requests | Apache 2.0 |
| pdfplumber | MIT |
| Pillow | HPND (PIL) |
| sqlite3 | Python PSF License |

---

## Lisans Uyumluluğu Özeti

| Veri Kaynağı | Lisans | Türev Çalışma İzni |
|---|---|---|
| Wiktionary | CC BY-SA 3.0 | ✅ Atıfla evet |
| WikDict | CC BY-SA 4.0 | ✅ Atıfla evet |
| Wikipedia DE | CC BY-SA 3.0 | ✅ Atıfla evet |
| Project Gutenberg | Public Domain | ✅ Serbest |
| Goethe-Institut | Eğitim materyali | ⚠️ Referans/atıf amaçlı |

Bu proje veritabanı **CC BY-SA 4.0** ile lisanslanmıştır (üst kümeli atıf şartı).
