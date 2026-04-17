# 🇩🇪 Almanca–Türkçe Sözlük / German–Turkish Dictionary

> **[English below](#english) · Türkçe açıklama aşağıda**

**23.000+ kelimelik açık kaynak Almanca–Türkçe sözlük — masaüstü uygulaması ile.**

Wiktionary, WikDict, Project Gutenberg, Tatoeba ve Wikipedia gibi açık veri kaynaklarından derlenen; otomotiv ağırlıklı ama genel amaçlı bir Almanca–Türkçe sözlük projesi.

---

## ✨ Özellikler

| | |
|---|---|
| 📚 **23.300+ kelime** | İsim, fiil, sıfat, zarf, kısaltmalar |
| 🚗 **Otomotiv odaklı** | Şanzıman, motor, fren, şasi, elektronik |
| 🎓 **CEFR seviyeleri** | A1→C2 — Goethe-Institut referanslı |
| 📖 **Edebi kelimeler** | Goethe, Kafka, Schiller, Hesse ve diğerleri |
| 💬 **Örnek cümleler** | Gutenberg kitaplarından + Tatoeba çiftleri |
| 🇹🇷 **Türkçe çevirili cümleler** | 7.900+ cümlenin Türkçesi |
| 🔤 **Eş/Zıt anlamlılar** | OdeNet'ten 14.000+ eş, 700+ zıt |
| 🖼️ **Görsel önizleme** | Wikimedia görselleri |
| 🔍 **Almanca & Türkçe arama** | Tam eşleşme, önek ve içerik araması |
| 📝 **Almanca tanımlar** | 19.000+ kelimede de.Wiktionary tanımı |
| 🌐 **Çevrimdışı çalışır** | İnternet bağlantısı gerektirmez |

---

## 🚀 Kurulum ve Çalıştırma

### Gereksinimler

- Python 3.10+
- `pip install Pillow`

### Çalıştır

```bash
cd almanca-sozluk-projesi
python scripts/run_desktop_app.py
```

veya Windows'ta çift tıkla:

```
almanca-sozluk-projesi/launch_dictionary.cmd
```

---

## 📊 Veri Kaynakları

| Kaynak | Katkı | Lisans |
|--------|-------|--------|
| [WikDict](https://www.wikdict.com/) | Türkçe çeviriler | CC BY-SA 4.0 |
| [Wiktionary DE](https://de.wiktionary.org/) | Almanca tanımlar, artikel | CC BY-SA 3.0 |
| [Wikipedia DE](https://de.wikipedia.org/) | Örnek cümleler, görseller | CC BY-SA 3.0 |
| [Project Gutenberg](https://www.gutenberg.org/) | 205 edebi eser, örnek cümleler | Public Domain |
| [Tatoeba](https://tatoeba.org/) | 21.448 DE–TR cümle çifti | CC BY 2.0 FR |
| [OdeNet](https://github.com/hdaSprachtechnologie/odenet) | Eş/Zıt anlamlılar | CC BY-SA 4.0 |

---

## 📁 Yapı

```
almanca-sozluk-projesi/
├── output/dictionary.json       # 23.300+ kayıt
├── scripts/
│   ├── run_desktop_app.py       # Ana uygulama
│   ├── enrich_gutenberg.py      # Gutenberg zenginleştirme
│   ├── enrich_tatoeba.py        # Tatoeba entegrasyonu
│   ├── enrich_odenet.py         # OdeNet eş/zıt anlamlılar
│   ├── enrich_cefr.py           # CEFR seviye & Zipf skoru
│   └── enrich_dewiktionary_definitions.py
├── assets/branding/             # Logo dosyaları
├── ATTRIBUTION.md               # Tam kaynak listesi
└── build_exe.bat                # Windows EXE oluşturucu
```

---

## 📜 Lisans

**Veri:** [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
**Kod:** MIT License

Ayrıntılar için → [ATTRIBUTION.md](almanca-sozluk-projesi/ATTRIBUTION.md)

---

<a name="english"></a>

## 🇬🇧 English

### German–Turkish Dictionary — Open Source

A comprehensive **German ↔ Turkish dictionary** with 23,300+ entries, built from openly licensed sources.

**Key features:**
- 23,300+ entries — nouns, verbs, adjectives, adverbs, abbreviations
- Automotive focus (transmission, engine, brakes, chassis, electronics)
- CEFR levels A1–C2 (Goethe-Institut referenced)
- 7,900+ Turkish-translated example sentences
- 14,000+ synonyms and 700+ antonyms via OdeNet
- German definitions from de.Wiktionary (19,000+ entries)
- Offline-first desktop app (Tkinter, Windows/macOS/Linux)
- Web interface included

**Quick start:**

```bash
git clone https://github.com/Honixbadger/almanca-turkce-sozluk.git
cd almanca-turkce-sozluk/almanca-sozluk-projesi
pip install Pillow
python scripts/run_desktop_app.py
```

**Dictionary data** is at `almanca-sozluk-projesi/output/dictionary.json` — a JSON array, one entry per word. Full schema documented in [almanca-sozluk-projesi/README.md](almanca-sozluk-projesi/README.md).

**Data sources:**

| Source | Contribution | License |
|--------|-------------|---------|
| [WikDict](https://www.wikdict.com/) | Turkish translations | CC BY-SA 4.0 |
| [Wiktionary DE](https://de.wiktionary.org/) | German definitions, articles | CC BY-SA 3.0 |
| [Wikipedia DE](https://de.wikipedia.org/) | Example sentences | CC BY-SA 3.0 |
| [Project Gutenberg](https://www.gutenberg.org/) | 205 literary works | Public Domain |
| [Tatoeba](https://tatoeba.org/) | 21,448 DE–TR sentence pairs | CC BY 2.0 FR |
| [OdeNet](https://github.com/hdaSprachtechnologie/odenet) | Synonyms / antonyms | CC BY-SA 4.0 |

**License:** Data — [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) · Code — MIT

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).
