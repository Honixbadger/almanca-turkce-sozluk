# Katkıda Bulunma / Contributing

> **[English below](#english)**

---

## Türkçe

Katkılarınız için teşekkürler! Bu proje açık kaynak topluluğuyla büyümektedir.

### Nasıl Katkıda Bulunabilirsiniz?

#### 1. Eksik Kelime veya Hatalı Çeviri Bildirme
[Issue açın](https://github.com/Honixbadger/almanca-turkce-sozluk/issues/new/choose) ve şablonu doldurun.

#### 2. Yeni Kelime Ekleme
- Uygulamayı çalıştırın (`python almanca-sozluk-projesi/scripts/run_desktop_app.py`)
- "Yeni Kelime" formunu kullanarak kelimeyi ekleyin
- Oluşan `data/manual/user_entries.json` dosyasını Pull Request ile gönderin

#### 3. Veri Kalitesini İyileştirme
- `almanca-sozluk-projesi/output/dictionary.json` dosyasını doğrudan düzenleyin
- Değişikliğin nedenini commit mesajında açıklayın
- PR açın

#### 4. Kod Katkısı
- Repo'yu fork'layın
- Feature branch oluşturun: `git checkout -b fix/yanlis-ceviri`
- Değişikliklerinizi commit edin
- PR gönderin

### Veri Formatı

Her sözlük kaydı şu alanları içerir:

```json
{
  "almanca": "Kupplung",
  "artikel": "die",
  "turkce": "debriyaj",
  "tur": "isim",
  "kategoriler": ["otomotiv"],
  "seviye": "B1",
  "ornekler": [
    {
      "almanca": "Die Kupplung ist defekt.",
      "turkce": "Debriyaj arızalı.",
      "kaynak": "Kullanıcı katkısı"
    }
  ],
  "kaynak": "Kullanıcı katkısı",
  "not": ""
}
```

**Zorunlu alanlar:** `almanca`, `turkce`, `tur`  
**Geçerli `tur` değerleri:** `isim`, `fiil`, `sıfat`, `zarf`, `ifade`, `edat`, `zamir`, `bağlaç`, `ünlem`, `kısaltma`  
**Geçerli `seviye` değerleri:** `A1`, `A2`, `B1`, `B2`, `C1`, `C2`

### Commit Mesajı Kuralları

```
[konu]: kısa açıklama

Örnekler:
fix: "schauen" fiilinin çevirisi düzeltildi
add: otomotiv terimleri eklendi (20 kelime)
quality: eksik artikel'lar tamamlandı
```

---

<a name="english"></a>

## English

Thank you for contributing! This project grows with the open-source community.

### Ways to Contribute

#### 1. Report a Missing Word or Wrong Translation
[Open an issue](https://github.com/Honixbadger/almanca-turkce-sozluk/issues/new/choose) and fill in the template.

#### 2. Add New Words
- Run the app: `python almanca-sozluk-projesi/scripts/run_desktop_app.py`
- Use the "New Word" form to add entries
- Submit the resulting `data/manual/user_entries.json` via Pull Request

#### 3. Improve Data Quality
- Edit `almanca-sozluk-projesi/output/dictionary.json` directly
- Explain the reason for change in your commit message
- Open a PR

#### 4. Code Contributions
- Fork the repository
- Create a feature branch: `git checkout -b fix/wrong-translation`
- Commit your changes
- Submit a PR

### Data Format

Each dictionary entry has these fields:

```json
{
  "almanca": "Kupplung",
  "artikel": "die",
  "turkce": "clutch",
  "tur": "isim",
  "kategoriler": ["otomotiv"],
  "seviye": "B1",
  "ornekler": [
    {
      "almanca": "Die Kupplung ist defekt.",
      "turkce": "The clutch is broken.",
      "kaynak": "User contribution"
    }
  ],
  "kaynak": "User contribution",
  "not": ""
}
```

**Required fields:** `almanca`, `turkce`, `tur`  
**Valid `tur` values:** `isim`, `fiil`, `sıfat`, `zarf`, `ifade`, `edat`, `zamir`, `bağlaç`, `ünlem`, `kısaltma`  
**Valid `seviye` values:** `A1`, `A2`, `B1`, `B2`, `C1`, `C2`

### Commit Message Format

```
[type]: short description

Examples:
fix: corrected translation for "schauen"
add: added 20 automotive terms
quality: filled in missing articles (Artikel)
```

### Code of Conduct

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.
