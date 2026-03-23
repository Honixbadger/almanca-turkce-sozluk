# enrich_compound_split.py
# Almanca bileşik kelimeleri bileşenlerine ayırır ve `bilesen_kelimeler` alanı ekler.
# Yaklaşım: dewiktionary kelime listesini sözlük olarak kullanarak DP tabanlı bölme.
# Harici kütüphane gerekmez.

import sys, re, gzip, json, unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH = Path("output/dictionary.json")
WIKT_PATH = Path("data/raw/downloads/dewiktionary.gz")

# Almanca bileşik kelimelerde iki parça arasına giren Fugenelemente
FUGEN = ["", "s", "es", "en", "er", "e", "ens", "ns", "n"]

# Çok kısa veya anlamsız parçaları reddet
MIN_PART_LEN = 3


def normalize(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().casefold()


def strip_article(word: str) -> str:
    parts = word.strip().split(" ", 1)
    if len(parts) == 2 and normalize(parts[0]) in {"der", "die", "das"}:
        return parts[1]
    return word.strip()


def load_de_wordset() -> set[str]:
    """dewiktionary'den tüm Almanca kelimeleri yükle (casefolded)."""
    words: set[str] = set()
    print("dewiktionary kelime listesi yükleniyor...")
    with gzip.open(str(WIKT_PATH), "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("lang_code") != "de":
                continue
            w = (e.get("word") or "").strip()
            if len(w) >= MIN_PART_LEN:
                words.add(w.casefold())
    print(f"  {len(words):,} kelime yüklendi\n")
    return words


def try_split(word: str, wordset: set[str]) -> list[str] | None:
    """
    Kelimeyi iki veya üç anlamlı parçaya böl.
    Her bölme noktasında Fugenelemente dene.
    En uzun ilk parçayı tercih et (greedy).
    """
    wl = word.casefold()
    length = len(wl)

    # Sadece uzun kelimeleri işle
    if length < 7:
        return None

    best: list[str] | None = None

    # İki parçalı bölme: ilk parça en az MIN_PART_LEN, son parça en az MIN_PART_LEN
    for i in range(MIN_PART_LEN, length - MIN_PART_LEN + 1):
        left_cf = wl[:i]
        remainder = wl[i:]

        for fug in FUGEN:
            if not remainder.startswith(fug):
                continue
            right_cf = remainder[len(fug):]
            if len(right_cf) < MIN_PART_LEN:
                continue

            if left_cf in wordset and right_cf in wordset:
                # Orijinal büyük-küçük harf koru
                left_orig  = word[:i]
                right_orig = word[i + len(fug):]
                candidate = [left_orig, right_orig]
                # Daha uzun ilk parça → daha iyi
                if best is None or len(left_orig) > len(best[0]):
                    best = candidate

    return best


def main():
    wordset = load_de_wordset()

    print("Sözlük yükleniyor...")
    d = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(d):,} kayıt\n")

    added = 0
    skipped_short = 0
    skipped_simple = 0

    for rec in d:
        raw  = (rec.get("almanca") or "").strip()
        bare = strip_article(raw)
        if not bare or " " in bare:   # çok kelimeli girişleri atla
            continue

        # Zaten varsa güncelleme
        if rec.get("bilesen_kelimeler"):
            continue

        if len(bare) < 7:
            skipped_short += 1
            continue

        parts = try_split(bare, wordset)
        if parts and len(parts) >= 2:
            rec["bilesen_kelimeler"] = parts
            added += 1
        else:
            skipped_simple += 1

    print("Sonuçlar:")
    print(f"  Bileşen eklenen kelime   : {added:,}")
    print(f"  Kısa (< 7 harf) atlanan  : {skipped_short:,}")
    print(f"  Bölünemeyen              : {skipped_simple:,}")

    # Örnek çıktı
    samples = [(r["almanca"], r["bilesen_kelimeler"]) for r in d if r.get("bilesen_kelimeler")]
    print("\nÖrnek bölünmeler:")
    for w, parts in samples[:15]:
        print(f"  {w:25} → {' + '.join(parts)}")

    print("\nKaydediliyor...")
    DICT_PATH.write_text(
        json.dumps(d, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print("Tamamlandı.")


if __name__ == "__main__":
    main()
