# enrich_cefr.py
# zipf_skoru ve seviye (A1-C2) alanlarını doldurur.
# Kaynak 1: Goethe Institut kelime listesi (A1/A2/B1) — GitHub
# Kaynak 2: wordfreq Zipf skoru — B2/C1/C2 tahmini
# Goethe listesi çakışırsa öncelik alır.

import sys, re, json, unicodedata, time
from pathlib import Path

try:
    import requests
except ImportError:
    print("pip install requests gerekli"); sys.exit(1)

try:
    from wordfreq import zipf_frequency
except ImportError:
    print("pip install wordfreq gerekli"); sys.exit(1)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH = Path("output/dictionary.json")

# ── Goethe listesi indirme ────────────────────────────────────────────────────

BASE_URL = "https://raw.githubusercontent.com/ilkermeliksitki/goethe-institute-wordlist/main"
LETTERS = "abcdefghijklmnopqrstuvwxyz"
LEVELS = ["a1", "a2", "b1"]

# sprach-o-mat (A1/A2/B1 stems, MIT lisansı) — yedek kaynak
SPRACH_O_MAT_URL = (
    "https://raw.githubusercontent.com/technologiestiftung/sprach-o-mat/main/"
    "dictionary_a1a2b1_onlystems.csv"
)


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().casefold()


def strip_article(word: str) -> str:
    parts = word.strip().split(" ", 1)
    if len(parts) == 2 and normalize(parts[0]) in {"der", "die", "das"}:
        return parts[1]
    return word.strip()


def extract_base(raw: str) -> str:
    """TSV'deki 'der Abend, -e' → 'Abend', 'abbiegen (biegt ab,...)' → 'abbiegen'"""
    raw = raw.strip()
    raw = strip_article(raw)
    # Parantez ve virgülden önce dur
    raw = re.split(r"[,(]", raw)[0].strip()
    return raw


def fetch_goethe() -> dict[str, str]:
    """Return {normalized_word: level_str} e.g. {'abend': 'A1'}"""
    word_level: dict[str, str] = {}
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 almanca-sozluk-enricher"

    total_files = 0
    total_words = 0

    for lvl in LEVELS:
        for letter in LETTERS:
            url = f"{BASE_URL}/{lvl}/{letter}.tsv"
            try:
                r = session.get(url, timeout=10)
                if r.status_code == 404:
                    continue
                if r.status_code != 200:
                    time.sleep(1)
                    continue
                for line in r.text.splitlines():
                    parts = line.split("\t")
                    if not parts:
                        continue
                    base = extract_base(parts[0])
                    if len(base) < 2:
                        continue
                    key = normalize(base)
                    if key and key not in word_level:
                        word_level[key] = lvl.upper()
                        total_words += 1
                total_files += 1
            except Exception:
                pass
            time.sleep(0.05)  # rate limiting

    print(f"Goethe (ilkermeliksitki): {total_files} dosya, {total_words} kelime")

    # Yedek: sprach-o-mat stems
    try:
        r = session.get(SPRACH_O_MAT_URL, timeout=15)
        if r.status_code == 200:
            extra = 0
            for line in r.text.splitlines()[1:]:  # header skip
                parts = line.split(",")
                if len(parts) < 3:
                    continue
                lvl_raw = parts[1].strip().upper()
                stem = parts[2].strip().strip('"')
                if lvl_raw not in {"A1", "A2", "B1"} or len(stem) < 2:
                    continue
                key = normalize(stem)
                if key and key not in word_level:
                    word_level[key] = lvl_raw
                    extra += 1
            print(f"sprach-o-mat yedek: +{extra} ek kelime")
    except Exception as e:
        print(f"sprach-o-mat indirilemedi: {e}")

    return word_level


# ── Zipf → CEFR tahmini ──────────────────────────────────────────────────────

def zipf_to_cefr(z: float) -> str:
    if z >= 5.5:
        return "A1"
    if z >= 4.5:
        return "A2"
    if z >= 3.5:
        return "B1"
    if z >= 2.5:
        return "B2"
    if z >= 1.5:
        return "C1"
    return "C2"


# ── Ana iş ───────────────────────────────────────────────────────────────────

def main():
    print("Goethe listeleri indiriliyor...")
    goethe = fetch_goethe()
    print(f"Toplam Goethe kelime sayısı: {len(goethe):,}\n")

    print("Sözlük yükleniyor...")
    d = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(d):,} kayıt")

    goethe_hits = 0
    wordfreq_hits = 0
    zero_freq = 0

    for rec in d:
        raw = (rec.get("almanca") or "").strip()
        bare = strip_article(raw)
        if not bare:
            continue

        key = normalize(bare)

        # wordfreq Zipf skoru (de)
        z = zipf_frequency(bare, "de")
        if z == 0:
            # Bileşik kelime veya nadir — küçük harfle dene
            z = zipf_frequency(bare.lower(), "de")
        rec["zipf_skoru"] = round(z, 2)

        # CEFR seviyesi
        if key in goethe:
            rec["seviye"] = goethe[key]
            goethe_hits += 1
        else:
            # Normalize edilmemiş versiyonu da dene (artikel çıkartılmış)
            key2 = normalize(bare.lower())
            if key2 in goethe:
                rec["seviye"] = goethe[key2]
                goethe_hits += 1
            else:
                if z > 0:
                    rec["seviye"] = zipf_to_cefr(z)
                    wordfreq_hits += 1
                else:
                    rec["seviye"] = "C2"  # bilinmiyor → en nadir
                    zero_freq += 1

    print(f"\nSonuçlar:")
    print(f"  Goethe listesinden seviye atanan : {goethe_hits:,}")
    print(f"  wordfreq'ten seviye atanan       : {wordfreq_hits:,}")
    print(f"  Sıfır frekans (C2 atandı)        : {zero_freq:,}")

    # Seviye dağılımı
    from collections import Counter
    dist = Counter(rec.get("seviye", "?") for rec in d)
    for lvl in ["A1", "A2", "B1", "B2", "C1", "C2"]:
        print(f"  {lvl}: {dist.get(lvl, 0):,}")

    print("\nKaydediliyor...")
    DICT_PATH.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("Tamamlandi.")


if __name__ == "__main__":
    main()
