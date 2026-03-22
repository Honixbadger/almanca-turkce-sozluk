# 🇩🇪 Almanca-Türkçe Sözlük

**18.000+ kelimelik açık kaynak Almanca-Türkçe sözlük — masaüstü uygulaması ile.**

Wiktionary, Wikipedia, WikDict ve Project Gutenberg gibi açık kaynaklardan derlenen, otomotiv ağırlıklı ama genel amaçlı bir Almanca-Türkçe sözlük projesi.

---

## ✨ Özellikler

- **18.000+ kelime** — isim, fiil, sıfat, zarf, kısaltmalar
- **Otomotiv odaklı** — şanzıman, motor, fren, şasi, elektronik terimleri
- **CEFR seviyeleri** (A1/A2/B1/B2) — Goethe-Institut referanslı
- **Edebi kelimeler** — Goethe, Kafka, Schiller, Hesse ve diğer klasiklerden
- **Örnek cümleler** — Wikipedia ve Gutenberg metinlerinden alınmış
- **Türkçe & Almanca arama** — tam eşleşme, ön ek ve içerik araması
- **Görsel önizleme** — kelimelere ait Wikimedia görselleri
- **Tkinter masaüstü uygulaması** — Windows/Linux/macOS
- **Kaynak izleme** — her kaydın kaynağı belgelenmiş
- **Çevrimdışı çalışır** — internet bağlantısı gerektirmez

---

## 🚀 Hızlı Başlangıç

### Gereksinimler

```
Python 3.10+
tkinter (Python ile birlikte gelir)
Pillow       ← görsel önizleme için
requests     ← görsel indirme için (isteğe bağlı)
pdfplumber   ← PDF içe aktarma için (isteğe bağlı)
```

```bash
pip install -r requirements-desktop.txt
```

### Uygulamayı Çalıştırma

```bash
python scripts/run_desktop_app.py
```

### İlk Kurulum (Veri İndirme)

Sözlük verisi (`output/dictionary.json`) repoda hazır olarak bulunmaktadır.

WikDict veritabanını ayrıca indirmeniz gerekir (zenginleştirme scriptleri için):

```bash
python scripts/fetch_sources.py
```

Bu komut `data/raw/downloads/` altına WikDict SQLite dosyasını indirir (~10 MB).

---

## ⚙️ Ayarlar

1. `data/manual/desktop_settings.template.json` dosyasını kopyalayın:
   ```bash
   cp data/manual/desktop_settings.template.json data/manual/desktop_settings.json
   ```
2. `desktop_settings.json` dosyasını açın ve isteğe bağlı API anahtarlarını girin:
   - `llm_api_key`: [Groq API](https://console.groq.com/) anahtarınız (AI açıklama özelliği için)
   - `libretranslate_api_key`: LibreTranslate anahtarınız (isteğe bağlı)

> ⚠️ `desktop_settings.json` `.gitignore`'a eklenmiştir — API anahtarlarınız güvende.

---

## 📁 Proje Yapısı

```
almanca-sozluk-projesi/
├── output/
│   ├── dictionary.json          # Ana sözlük verisi (18K+ kayıt)
│   └── word_images/             # Kelime görseli önbelleği (gitignore'da)
├── scripts/
│   ├── run_desktop_app.py       # 🖥️ Ana uygulama — buradan çalıştırın
│   ├── enrich_quality.py        # Wikipedia'dan zenginleştirme
│   ├── enrich_gutenberg.py      # Gutenberg'den zenginleştirme
│   ├── build_dictionary.py      # Sözlük inşa scripti
│   ├── grammar_utils.py         # Dilbilgisi yardımcıları
│   └── ...
├── data/
│   ├── manual/
│   │   ├── desktop_settings.template.json  # ← Bunu kopyalayın
│   │   ├── kfztech_terms.json
│   │   └── ...
│   └── raw/downloads/           # WikDict SQLite (gitignore'da)
├── assets/
│   ├── branding/                # Logo dosyaları
│   └── trees/                   # Dekoratif görseller
├── ATTRIBUTION.md               # Veri kaynakları ve lisanslar
├── LICENSE                      # CC BY-SA 4.0 (veri) + MIT (kod)
└── requirements-desktop.txt
```

---

## 🔧 Zenginleştirme Scriptleri

Sözlüğü yeni kelimeler ve örnek cümlelerle zenginleştirmek için:

```bash
# Wikipedia'dan zenginleştir (~400 sayfa, ~1 saat)
python scripts/enrich_quality.py

# Project Gutenberg'den zenginleştir (~120 kitap, ~2 saat)
python scripts/enrich_gutenberg.py
```

---

## 📊 Veri Formatı

Her sözlük kaydı (`output/dictionary.json`) şu alanları içerir:

| Alan | Açıklama | Örnek |
|------|----------|-------|
| `almanca` | Almanca sözcük | `"Kupplung"` |
| `artikel` | Artikel (isimler için) | `"die"` |
| `turkce` | Türkçe karşılık(lar) | `"debriyaj"` |
| `tur` | Sözcük türü | `"isim"` |
| `kategoriler` | Konu kategorileri | `["otomotiv"]` |
| `seviye` | CEFR seviyesi | `"A2"` |
| `ornek_almanca` | Örnek cümle (Almanca) | `"Die Kupplung..."` |
| `ornekler` | Örnek cümle listesi | `[{"almanca": ...}]` |
| `kaynak` | Veri kaynağı | `"WikDict; Wikipedia DE"` |
| `referans_linkler` | Duden/DWDS/Wiktionary | `{"duden": "..."}` |

---

## 📜 Lisans

**Veri:** [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
**Kod:** MIT License

Veri kaynakları: Wiktionary (CC BY-SA 3.0), WikDict (CC BY-SA 4.0),
Wikipedia DE (CC BY-SA 3.0), Project Gutenberg (Public Domain).

Ayrıntılar için → [ATTRIBUTION.md](ATTRIBUTION.md)

---

## 🤝 Katkı

Pull request ve issue'larla katkıda bulunabilirsiniz.

Yeni kelime eklemek için uygulamayı çalıştırın ve "Yeni Kelime" formunu kullanın —
girişler `data/manual/user_entries.json` dosyasına kaydedilir.
