# enrich_morphology.py
# dewiktionary dump'ından cogul (Nominativ Plural) ve eksik artikel ekler.
# Kaynak: de.Wiktionary CC BY-SA 3.0

import sys, re, gzip, json, unicodedata
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH   = Path("output/dictionary.json")
WIKT_PATH   = Path("data/raw/downloads/dewiktionary.gz")


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().casefold()


def strip_article(word: str) -> str:
    parts = word.strip().split(" ", 1)
    if len(parts) == 2 and normalize(parts[0]) in {"der", "die", "das"}:
        return parts[1]
    return word.strip()


def build_wiktionary_index() -> dict[str, dict]:
    """
    Returns {normalized_bare_word: {"artikel": str|None, "cogul": str|None}}
    Öncelik: nominative singular article → artikel
             nominative plural form      → cogul
    """
    index: dict[str, dict] = {}

    print("dewiktionary.gz taranıyor...")
    processed = 0
    with gzip.open(str(WIKT_PATH), "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("lang_code") != "de":
                continue

            word = (e.get("word") or "").strip()
            if not word:
                continue

            key = normalize(word)
            entry = index.setdefault(key, {"artikel": None, "cogul": None})

            for form in e.get("forms", []):
                tags = form.get("tags", [])
                form_str = (form.get("form") or "").strip()
                article   = (form.get("article") or "").strip().lower()

                # Artikel: nominative singular'dan article al
                if "nominative" in tags and "singular" in tags:
                    if article in {"der", "die", "das"} and not entry["artikel"]:
                        entry["artikel"] = article

                # Çoğul: nominative plural form
                if "nominative" in tags and "plural" in tags:
                    if form_str and form_str != word and not entry["cogul"]:
                        entry["cogul"] = form_str

            processed += 1
            if processed % 200_000 == 0:
                print(f"  {processed:,} kayıt işlendi...")

    filled = sum(1 for v in index.values() if v["artikel"] or v["cogul"])
    print(f"  Toplam: {processed:,} kayıt, {len(index):,} benzersiz kelime")
    print(f"  artikel veya cogul içeren: {filled:,}\n")
    return index


def main():
    wikt = build_wiktionary_index()

    print("Sözlük yükleniyor...")
    d = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(d):,} kayıt\n")

    artikel_added = 0
    cogul_added   = 0

    for rec in d:
        raw  = (rec.get("almanca") or "").strip()
        bare = strip_article(raw)
        if not bare:
            continue

        key  = normalize(bare)
        info = wikt.get(key)
        if not info:
            # Küçük harfli dene (fiil vs)
            info = wikt.get(normalize(bare.lower()))
        if not info:
            continue

        # Artikel: sadece eksikse ekle
        if info["artikel"] and not (rec.get("artikel") or "").strip():
            rec["artikel"] = info["artikel"]
            artikel_added += 1

        # Çoğul: her zaman güncelle (yeni alan)
        if info["cogul"] and not (rec.get("cogul") or "").strip():
            rec["cogul"] = info["cogul"]
            cogul_added += 1

    print("Sonuçlar:")
    print(f"  Artikel eklenen (eksik olan) : {artikel_added:,}")
    print(f"  Çoğul eklenen               : {cogul_added:,}")

    # Özet istatistik
    has_art = sum(1 for r in d if (r.get("artikel") or "").strip())
    has_cog = sum(1 for r in d if (r.get("cogul") or "").strip())
    print(f"\nGenel durum:")
    print(f"  Artikel olan kelime : {has_art:,} / {len(d):,}")
    print(f"  Çoğul olan kelime   : {has_cog:,} / {len(d):,}")

    print("\nKaydediliyor...")
    DICT_PATH.write_text(
        json.dumps(d, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print("Tamamlandı.")


if __name__ == "__main__":
    main()
