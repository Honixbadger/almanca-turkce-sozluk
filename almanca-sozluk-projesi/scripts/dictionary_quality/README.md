# Dictionary Quality Scripts

Bu klasördeki araçlar `dictionary.json` içindeki belirli hata ailelerine tek tek odaklanır. Her script mümkün olduğunca tek sorumluluk taşır; çoğu araç önce rapor üretir, ardından istenirse düzeltme uygular.

Varsayılan yaklaşım:

- önce `--report-path` ile rapor üret
- sonra küçük bir alt kümede dene
- en son `--in-place --apply-fixes` ile gerçek dosyaya uygula

Ortak kullanım örnekleri:

```powershell
python scripts/dictionary_quality/fix_non_german_examples.py --dict-path output/dictionary.json --report-path output/quality_reports/non_german.json
python scripts/dictionary_quality/fix_fragment_examples.py --dict-path output/dictionary.json --report-path output/quality_reports/fragments.json --apply-fixes --drop-nested --output-path output/dictionary.fragments.cleaned.json
python scripts/dictionary_quality/fix_esanlamlilar_links.py --dict-path output/dictionary.json --report-path output/quality_reports/esanlam.json --apply-fixes --require-existing-target --require-reciprocal --in-place
```

Araç listesi:

- `quality_common.py`: ortak yardımcı fonksiyonlar
- `build_quality_snapshot.py`: kalan sorunların kaba fotoğrafını çıkarır
- `fix_non_german_examples.py`: Almanca olmayan örnekleri işaretler ve isterse temizler
- `fix_fragment_examples.py`: kırpık veya yarım örnekleri bulur
- `fix_turkish_encoding_artifacts.py`: `??`, mojibake ve bozuk karakterleri temizlemeye çalışır
- `fix_turkish_foreign_residue.py`: Türkçe alanlara sızmış İngilizce artıklarını ayıklar
- `fix_top_example_lemma_mismatch.py`: üst örneği lemma ile uyuşmayan kayıtları bulur
- `fix_category_sense_mismatches.py`: kategori ile açıklama/anlam uyumsuzluklarını raporlar
- `fix_example_translation_drift.py`: örnek çevirisi ana karşılıktan ciddi sapmış kayıtları bulur
- `fix_esanlamlilar_links.py`: `esanlamlilar` alanında kırık hedef, self-loop ve karşılıksız ilişki temizliği yapar
- `fix_zit_anlamlilar_links.py`: `zit_anlamlilar` alanı için benzer bütünlük kontrolü yapar
- `fix_relation_target_integrity.py`: `sinonim` ve `antonim` gibi güvenilir alanlarda kırık hedefleri ve self-loop'ları temizler

Notlar:

- Scriptler yalnızca standart Python kütüphanesini kullanır.
- `--in-place` kullanıldığında otomatik yedek oluşturulur.
- Büyük temizliklerde scriptleri tek tek çalıştırmak, hepsini körlemesine aynı anda uygulamaktan daha güvenlidir.
