# enrich_odenet.py
# OdeNet (Open German WordNet) ile esanlamlilar ve zit_anlamlilar ekler.
# Lisans: OdeNet CC BY-SA 4.0 — https://github.com/hdaSprachtechnologie/odenet

import sys, re, json, unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import wn
except ImportError:
    print("pip install wn gerekli"); sys.exit(1)

DICT_PATH = Path("output/dictionary.json")
MAX_SYN = 5   # kelime başına max eş anlamlı
MAX_ANT = 3   # kelime başına max zıt anlamlı

# Çok uzun veya anlamsız synset üyeleri filtrele
def is_valid_lemma(s: str) -> bool:
    if len(s) < 2 or len(s) > 40:
        return False
    # Cümle gibi görünenler (boşluk 3+) atla
    if s.count(" ") > 2:
        return False
    return True


def strip_article(word: str) -> str:
    parts = word.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() in {"der", "die", "das"}:
        return parts[1]
    return word.strip()


def main():
    print("OdeNet yükleniyor...")
    try:
        de = wn.Wordnet("odenet:1.4")
    except Exception:
        print("OdeNet bulunamadı, indiriliyor...")
        wn.download("odenet:1.4")
        de = wn.Wordnet("odenet:1.4")
    print(f"  {len(list(de.synsets())):,} synset hazır\n")

    print("Sözlük yükleniyor...")
    d = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(d):,} kayıt\n")

    syn_added = 0
    ant_added = 0
    words_enriched = 0

    for i, rec in enumerate(d):
        raw = (rec.get("almanca") or "").strip()
        bare = strip_article(raw)
        if not bare:
            continue

        synonyms: list[str] = []
        antonyms: list[str] = []

        try:
            synsets = de.synsets(bare)
            if not synsets:
                # küçük harfle dene
                synsets = de.synsets(bare.lower())
        except Exception:
            synsets = []

        for ss in synsets:
            # Eş anlamlılar: aynı synset'teki diğer kelimeler
            for w in ss.words():
                lm = w.lemma()
                if lm == bare or lm == bare.lower():
                    continue
                if not is_valid_lemma(lm):
                    continue
                if lm not in synonyms:
                    synonyms.append(lm)

            # Zıt anlamlılar: sense-level antonym ilişkisi
            for w in ss.words():
                for sense in w.senses():
                    try:
                        ant_senses = sense.get_related("antonym")
                    except Exception:
                        ant_senses = []
                    for ant_sense in ant_senses:
                        try:
                            ant_lm = ant_sense.word().lemma()
                        except Exception:
                            continue
                        if is_valid_lemma(ant_lm) and ant_lm not in antonyms:
                            antonyms.append(ant_lm)

            # Synset-level antonym
            try:
                ant_synsets = ss.get_related("antonym")
            except Exception:
                ant_synsets = []
            for ant_ss in ant_synsets:
                for w in ant_ss.words():
                    lm = w.lemma()
                    if is_valid_lemma(lm) and lm not in antonyms:
                        antonyms.append(lm)

        # Kayıt güncelle
        changed = False
        if synonyms:
            rec["esanlamlilar"] = synonyms[:MAX_SYN]
            syn_added += 1
            changed = True
        if antonyms:
            rec["zit_anlamlilar"] = antonyms[:MAX_ANT]
            ant_added += 1
            changed = True
        if changed:
            words_enriched += 1

        if (i + 1) % 2000 == 0:
            print(f"  {i+1:,}/{len(d):,} işlendi... (eş:{syn_added} zıt:{ant_added})")

    print(f"\nSonuçlar:")
    print(f"  Eş anlamlı eklenen kelime  : {syn_added:,}")
    print(f"  Zıt anlamlı eklenen kelime : {ant_added:,}")
    print(f"  Toplam zenginleştirilen    : {words_enriched:,}")

    print("\nKaydediliyor...")
    DICT_PATH.write_text(
        json.dumps(d, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8"
    )
    print("Tamamlandı.")


if __name__ == "__main__":
    main()
