# 🇩🇪 Almanca–Türkçe Sözlük

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
