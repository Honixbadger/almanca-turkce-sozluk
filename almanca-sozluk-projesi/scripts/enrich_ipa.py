# enrich_ipa.py
# DWDS API'sinden Almanca IPA telaffuz ekler.
# Endpoint: https://www.dwds.de/api/ipa?q=WORD
# Lisans: Olgusal fonetik veri — CC BY-SA uyumlu
# Kullanim: python scripts/enrich_ipa.py

import sys, re, json, time, unicodedata
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH   = Path("output/dictionary.json")
CHECKPOINT  = Path("data/manual/ipa_checkpoint.json")
BASE_URL    = "https://www.dwds.de/api/ipa?q={}"
DELAY_SEC   = 0.25   # DWDS'e nazik ol
BATCH_SAVE  = 500    # her N kelimede bir kaydet


def normalize(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().casefold()


def strip_article(word: str) -> str:
    parts = word.strip().split(" ", 1)
    if len(parts) == 2 and normalize(parts[0]) in {"der", "die", "das"}:
        return parts[1]
    return word.strip()


def fetch_ipa(word: str) -> str | None:
    from urllib.parse import quote
    url = BASE_URL.format(quote(word))
    req = Request(url, headers={"User-Agent": "almanca-sozluk-ipa-enricher/1.0"})
    try:
        with urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        # DWDS yanit formati: {"ipa": "/haʊs/", "status": "verified"} veya liste
        if isinstance(data, list) and data:
            data = data[0]
        if isinstance(data, dict):
            ipa = (data.get("ipa") or "").strip()
            if ipa and ipa not in ("-", ""):
                return ipa
    except (HTTPError, URLError, json.JSONDecodeError, Exception):
        pass
    return None


def load_checkpoint() -> set[str]:
    if CHECKPOINT.exists():
        try:
            return set(json.loads(CHECKPOINT.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def save_checkpoint(done: set[str]) -> None:
    CHECKPOINT.write_text(json.dumps(list(done), ensure_ascii=False), encoding="utf-8")


def main():
    print("Sözlük yükleniyor...")
    d = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(d):,} kayıt\n")

    done = load_checkpoint()
    print(f"  Önceki checkpoint: {len(done):,} kelime işlendi\n")

    added    = 0
    skipped  = 0
    errors   = 0
    total    = 0

    for i, rec in enumerate(d):
        raw  = (rec.get("almanca") or "").strip()
        bare = strip_article(raw)
        if not bare or " " in bare:
            continue

        # Zaten IPA varsa atla
        if (rec.get("telaffuz") or "").strip():
            skipped += 1
            continue

        # Checkpoint: daha önce denedik ve bulamadık
        if bare in done:
            continue

        ipa = fetch_ipa(bare)
        done.add(bare)
        total += 1

        if ipa:
            rec["telaffuz"] = ipa
            added += 1
        else:
            errors += 1

        time.sleep(DELAY_SEC)

        if total % BATCH_SAVE == 0:
            DICT_PATH.write_text(
                json.dumps(d, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            save_checkpoint(done)
            print(f"  {total:,} sorgu | +{added:,} IPA | {errors:,} bulunamadı")

    # Son kayıt
    DICT_PATH.write_text(
        json.dumps(d, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    save_checkpoint(done)

    print(f"\nSonuçlar:")
    print(f"  IPA eklenen kelime    : {added:,}")
    print(f"  Bulunamayan           : {errors:,}")
    print(f"  Zaten doluydu (atlandı): {skipped:,}")

    samples = [(r["almanca"], r["telaffuz"]) for r in d if r.get("telaffuz")]
    print("\nÖrnek telaffuzlar:")
    for w, ipa in samples[:12]:
        print(f"  {w:20} → {ipa}")

    print("\nTamamlandı.")


if __name__ == "__main__":
    main()
