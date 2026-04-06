# -*- coding: utf-8 -*-
"""
cleanup_wrong_inflected_forms.py
=================================
Yanlış etiketlenmiş çekimli sıfat ve fiil formlarını sözlükten temizler.

HEDEF:
  - tur=fiil ama aslında çekimli sıfat olan kayıtlar   (ör: "archäologischen", "ukrainischen")
  - tur=isim (artikel yok) ama çekimli sıfat olan kayıtlar (ör: "Politische", "Ukrainische")
  - tur=fiil ama hiç fiil olmayan (sıfat/zarf/edat) kayıtlar

STRATEJİ:
  1. Regex ile kesin çekimli sıfat formu tespiti: [kök][isch|lich|ig|los|haft|sam|bar|ell|al][e|en|em|er|es]
  2. Base formu sözlükte SIFAT olarak varsa → güvenli sil (veriyi canonical'a aktar)
  3. Base formu sözlükte yoksa ama word tur=fiil ve kesinlikle fiil değilse → sil
  4. tur=fiil ama mastar değil (sıfat/zarf/edat) → bilinen listeye göre etiket düzelt

GÜVENLİ LİSTE (asla silme):
  Gerçek Almanca fiil infinitivleri yanlışlıkla yakalanmasın diye özel kontrol.

Usage:
  python cleanup_wrong_inflected_forms.py [--dry-run]
"""
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

DICT_PATH = SCRIPTS_DIR.parent / "output" / "dictionary.json"

ADJECTIVE_TURS = {"sıfat", "sifat", "adjektiv", "adj", "sıfat (kısaltma)"}

# Çekimli sıfat pattern: kök (sıfat soneki ile biten) + çekim sonu
# Kurallar:
#   - Kök en az 3 karakter (Fisch→F+isch gibi kısa kökleri engelle)
#   - Sıfat sonekleri: isch, lich, ig, los, sam, bar  (ell/al/iv gibi ambiguous olanlar dahil değil)
#   - -haft için ayrı pattern: "schaft" içinde "haft" yakalanmasın (negatif lookbehind)
ADJ_FORM_PATTERN = re.compile(
    r'^(.{3,}?(?:isch|lich|ig|los|sam|bar))(e|en|em|er|es)$',
    re.IGNORECASE
)
ADJ_HAFT_PATTERN = re.compile(
    r'^(.{3,}?(?<!sc)haft)(e|en|em|er|es)$',
    re.IGNORECASE
)

# Bilinen gerçek fiiller - regex yanlışlıkla yakalayabileceği infinitivler
# (bu liste kapsamlı değil, sadece en sık karşılaşılanlar)
KNOWN_REAL_VERBS = frozenset({
    # -igen sonlu gerçek fiiller
    "einigen", "reinigen", "peinigen", "nötigen", "züchtigen", "benötigen",
    "ermächtigen", "beschuldigen", "entschuldigen", "beglaubigen", "bestätigen",
    "beteiligen", "berücksichtigen", "beeinträchtigen", "benachteiligen",
    "begünstigen", "entbündigen", "bescheinigen", "ermutigen", "entmutigen",
    "berichtigen", "bevorzugen", "beleidigen", "befähigen", "erzwingen",
    "entschädigen", "beabsichtigen", "überwältigen", "bewältigen",
    "begnadigen", "betäuben", "verpflichten", "verpflichtigen",
    "verewigen", "heiligen", "seligsprechen", "bevollmächtigen",
    # -lichen sonlu gerçek fiiller
    "ermöglichen", "verköstlichen", "veröffentlichen", "verdeutlichen",
    "vereinfachen", "erleichtern", "berichtigen", "verpflichten",
    "vergegenwärtigen",
    # -ischen sonlu gerçek fiiller (çok az)
    "wischen", "erfrischen", "auffrischen", "aufwischen", "zerwischen",
    # Diğer yaygın infinitivler
    "einsteigen", "aussteigen", "umsteigen", "anzeigen", "aufzeigen",
    "hinzeigen", "nachweisen", "aufweisen", "beweisen", "erweisen",
    "zeigen", "schweigen", "weichen", "streichen", "gleichen",
    "erschleichen", "weichen", "schleichen",
    "wiederherstellen", "sicherstellen", "vorstellen", "feststellen",
    "beteiligen", "erzielen", "fühlen", "kühlen",
})


def merge_into(canonical: dict, duplicate: dict) -> None:
    """Duplikattaki verileri canonical'a aktar (veri kaybını önle)."""
    # Örnek cümleler
    existing = {o.get("almanca", "") for o in canonical.get("ornekler", [])}
    for ornek in duplicate.get("ornekler", []):
        if ornek.get("almanca", "") and ornek["almanca"] not in existing:
            canonical.setdefault("ornekler", []).append(ornek)
            existing.add(ornek["almanca"])

    if not canonical.get("ornek_almanca") and duplicate.get("ornek_almanca"):
        canonical["ornek_almanca"] = duplicate["ornek_almanca"]
        canonical["ornek_turkce"] = duplicate.get("ornek_turkce", "")

    ilgili = set(canonical.get("ilgili_kayitlar", []))
    ilgili.update(duplicate.get("ilgili_kayitlar", []))
    canonical["ilgili_kayitlar"] = sorted(ilgili)

    kats = set(canonical.get("kategoriler", []))
    kats.update(duplicate.get("kategoriler", []))
    canonical["kategoriler"] = sorted(kats)

    if duplicate.get("not") and not canonical.get("not"):
        canonical["not"] = duplicate["not"]

    # Türkçe çevirileri birleştir
    existing_tr = {t.strip() for t in canonical.get("turkce", "").split(";") if t.strip()}
    for t in duplicate.get("turkce", "").split(";"):
        t = t.strip()
        if t:
            existing_tr.add(t)
    canonical["turkce"] = "; ".join(sorted(existing_tr))


def main(dry_run: bool = False) -> None:
    with open(DICT_PATH, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Toplam kayıt: {len(data)}")

    # Sıfat indexi (kanonik başvuru için)
    sifat_by_key: dict[str, dict] = {}
    for r in data:
        if r.get("tur", "").lower() in ADJECTIVE_TURS:
            sifat_by_key[r.get("almanca", "").strip().lower()] = r

    print(f"Sözlükte sıfat kaydı: {len(sifat_by_key)}")

    to_remove: set[int] = set()
    stat_merged = 0
    stat_deleted_orphan = 0

    for r in data:
        w = r.get("almanca", "").strip()
        tur = r.get("tur", "")
        art = r.get("artikel", "").strip()

        # Zaten sıfat etiketli → mevcut cleanup_inflected_adjectives.py halleder
        if tur.lower() in ADJECTIVE_TURS:
            continue

        # Artikelli kayıtlar gerçek isimdir → dokunma
        if art:
            continue

        # Bilinen gerçek fiiller → dokunma
        if w.lower() in KNOWN_REAL_VERBS:
            continue

        # Çekimli sıfat pattern kontrolü (iki pattern)
        m = ADJ_FORM_PATTERN.match(w) or ADJ_HAFT_PATTERN.match(w)
        if not m:
            continue

        base_lower = m.group(1).lower()

        # Base form sözlükte sıfat olarak var mı?
        if base_lower in sifat_by_key:
            canonical = sifat_by_key[base_lower]
            # Bu kaydın verisini canonical sıfata aktar
            if not dry_run:
                merge_into(canonical, r)
            print(f"  [BİRLEŞTİR] {w!r} (tur={tur!r}) → {canonical['almanca']!r} (sıfat)")
            to_remove.add(id(r))
            stat_merged += 1
        else:
            # Base form sözlükte yok: tur=fiil ise bu kayıt gürültü (orphan çekimli form)
            # tur=isim ve artikel yok ise de gürültü
            if tur in ("fiil", "isim"):
                print(f"  [SİL-ORPHAN] {w!r} (tur={tur!r}) → base {base_lower!r} sözlükte yok")
                to_remove.add(id(r))
                stat_deleted_orphan += 1

    new_data = [r for r in data if id(r) not in to_remove]

    print(f"\n{'='*60}")
    print(f"Özet:")
    print(f"  Sıfata birleştirilen çekimli form: {stat_merged}")
    print(f"  Silinen orphan çekimli form:       {stat_deleted_orphan}")
    print(f"  Toplam silinen:                    {len(to_remove)}")
    print(f"  Eski kayıt sayısı: {len(data)}")
    print(f"  Yeni kayıt sayısı: {len(new_data)}")

    if not dry_run:
        with open(DICT_PATH, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        print(f"  Kaydedildi: {DICT_PATH}")
    else:
        print("  [DRY RUN — dosya değiştirilmedi]")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
