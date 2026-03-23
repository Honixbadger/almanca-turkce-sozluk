#!/usr/bin/env python3
"""
enrich_tatoeba.py
=================
Tatoeba açık veri setinden Almanca-Türkçe cümle çiftlerini sözlüğe ekler.

Her sözlük kelimesi için:
  - Kelimeyi içeren Almanca Tatoeba cümlesi bulunur
  - Türkçe çevirisiyle birlikte ornekler listesine eklenir
  - ornek_turkce alanı da doldurulur (edebi kaynaklarda bu boştu)

Kaynak  : Tatoeba Project — https://tatoeba.org
Lisans  : CC BY 2.0 France — https://creativecommons.org/licenses/by/2.0/fr/
Kredi   : Tatoeba contributors, CC BY 2.0 France
"""

from __future__ import annotations

import bz2
import io
import json
import re
import sys
import tarfile
import time
import unicodedata
import urllib.request as ur
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATH    = PROJECT_ROOT / "output" / "dictionary.json"
DATA_DIR     = PROJECT_ROOT / "data" / "raw" / "downloads"

DEU_URL  = "https://downloads.tatoeba.org/exports/per_language/deu/deu_sentences.tsv.bz2"
TUR_URL  = "https://downloads.tatoeba.org/exports/per_language/tur/tur_sentences.tsv.bz2"
LINKS_URL = "https://downloads.tatoeba.org/exports/links.tar.bz2"

DEU_PATH   = DATA_DIR / "tatoeba_deu.tsv.bz2"
TUR_PATH   = DATA_DIR / "tatoeba_tur.tsv.bz2"
LINKS_PATH = DATA_DIR / "tatoeba_links.tar.bz2"

UA = "AlmancaSozluk/1.0 (educational; contact: github.com/Honixbadger)"

# Kelime başına max kaç Tatoeba cümlesi eklenecek
MAX_TATOEBA_PER_WORD = 2
# ornekler toplam limiti (Gutenberg + Tatoeba birlikte)
MAX_ORNEKLER_TOTAL   = 5
# Cümle uzunluk limitleri
MIN_SENT_LEN = 15
MAX_SENT_LEN = 220


# ---------------------------------------------------------------------------
# Yardımcı
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().casefold()


def strip_article(word: str) -> str:
    parts = word.strip().split(" ", 1)
    if len(parts) == 2 and normalize(parts[0]) in {"der", "die", "das"}:
        return parts[1]
    return word.strip()


def download_file(url: str, dest: Path, label: str) -> bool:
    if dest.exists():
        size_mb = dest.stat().st_size / 1024 / 1024
        print(f"  [{label}] Zaten var ({size_mb:.1f} MB), atlanıyor.")
        return True
    print(f"  [{label}] İndiriliyor: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = ur.Request(url, headers={"User-Agent": UA})
        with ur.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 64 * 1024
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r    {pct:.0f}% ({downloaded//1024//1024}MB/{total//1024//1024}MB)", end="", flush=True)
        print()
        print(f"    Tamamlandı: {dest.stat().st_size//1024//1024} MB")
        return True
    except Exception as e:
        print(f"    HATA: {e}")
        if dest.exists():
            dest.unlink()
        return False


# ---------------------------------------------------------------------------
# Veri yükleme
# ---------------------------------------------------------------------------
def load_sentences(path: Path, label: str) -> dict[int, str]:
    """TSV.BZ2 dosyasından {id: text} sözlüğü oluştur."""
    print(f"  [{label}] Cümleler okunuyor...")
    result: dict[int, str] = {}
    with bz2.open(str(path), "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            try:
                sid = int(parts[0])
                text = parts[2].strip()
                if text:
                    result[sid] = text
            except ValueError:
                continue
    print(f"    {len(result):,} cümle yüklendi.")
    return result


def load_links(path: Path) -> dict[int, list[int]]:
    """
    Links tar.bz2'den Almanca→Türkçe çeviri eşleşmelerini bul.
    links.csv içindeki tüm çiftleri yükleyip döndürür: {deu_id: [tur_id, ...]}
    """
    print("  [LINKS] Çeviri bağlantıları okunuyor (bu ~1-2 dk sürebilir)...")
    links: dict[int, list[int]] = defaultdict(list)
    try:
        with tarfile.open(str(path), "r:bz2") as tar:
            for member in tar.getmembers():
                if "links" in member.name and member.name.endswith(".csv"):
                    f = tar.extractfile(member)
                    if not f:
                        continue
                    for raw_line in io.TextIOWrapper(f, encoding="utf-8", errors="replace"):
                        parts = raw_line.rstrip("\n").split("\t")
                        if len(parts) < 2:
                            continue
                        try:
                            a = int(parts[0])
                            b = int(parts[1])
                            links[a].append(b)
                        except ValueError:
                            continue
    except Exception as e:
        print(f"    HATA: {e}")
    total = sum(len(v) for v in links.values())
    print(f"    {len(links):,} kaynak cümle, {total:,} toplam bağlantı yüklendi.")
    return links


def build_de_tr_pairs(
    deu: dict[int, str],
    tur: dict[int, str],
    links: dict[int, list[int]],
) -> list[tuple[str, str]]:
    """Almanca-Türkçe cümle çiftleri oluştur."""
    pairs: list[tuple[str, str]] = []
    tur_ids = set(tur.keys())
    for deu_id, deu_text in deu.items():
        for linked_id in links.get(deu_id, []):
            if linked_id in tur_ids:
                pairs.append((deu_text, tur[linked_id]))
    print(f"  {len(pairs):,} Almanca-Türkçe cümle çifti bulundu.")
    return pairs


# ---------------------------------------------------------------------------
# Sözlük eşleştirme
# ---------------------------------------------------------------------------
TOKEN_RE = re.compile(r"\b[A-Za-zÄäÖöÜüß]{3,}\b")


def is_good_sentence(text: str) -> bool:
    if not (MIN_SENT_LEN <= len(text) <= MAX_SENT_LEN):
        return False
    if text.count("[") + text.count("{") + text.count("(") > 2:
        return False
    digit_ratio = sum(1 for c in text if c.isdigit()) / max(len(text), 1)
    if digit_ratio > 0.1:
        return False
    if len(TOKEN_RE.findall(text)) < 3:
        return False
    return True


def build_word_to_pairs(
    pairs: list[tuple[str, str]],
    record_index: dict[str, int],
) -> dict[int, list[tuple[str, str]]]:
    """
    Her sözlük kaydı için eşleşen (de, tr) cümle çiftleri listesi döndür.
    {record_idx: [(de_sent, tr_sent), ...]}
    """
    print("  Cümleler sözlük kelimeleriyle eşleştiriliyor...")
    word_pairs: dict[int, list[tuple[str, str]]] = defaultdict(list)

    for de_text, tr_text in pairs:
        if not is_good_sentence(de_text):
            continue
        de_cf = de_text.casefold()
        seen_in_sent: set[int] = set()
        for token in TOKEN_RE.findall(de_text):
            norm = normalize(token)
            idx = record_index.get(norm)
            if idx is None:
                continue
            if idx in seen_in_sent:
                continue
            seen_in_sent.add(idx)
            word_pairs[idx].append((de_text, tr_text))

    # Her kelime için kaliteli çiftleri filtrele (kısa cümleler önce)
    result: dict[int, list[tuple[str, str]]] = {}
    for idx, pair_list in word_pairs.items():
        # Benzersizlik: aynı cümleyi iki kez ekleme
        seen: set[str] = set()
        unique = []
        for de, tr in pair_list:
            if de not in seen:
                seen.add(de)
                unique.append((de, tr))
        unique.sort(key=lambda p: len(p[0]))
        result[idx] = unique

    print(f"  {len(result):,} kelime için Tatoeba cümlesi bulundu.")
    return result


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
def main() -> None:
    start = time.time()

    print("=" * 65)
    print("enrich_tatoeba.py — Tatoeba Almanca-Türkçe Entegrasyonu")
    print("Kaynak : Tatoeba contributors, CC BY 2.0 France")
    print("URL    : https://tatoeba.org")
    print("=" * 65)

    # 1. Dosyaları indir
    print("\n[1/5] Tatoeba dosyaları indiriliyor...")
    ok_deu   = download_file(DEU_URL,   DEU_PATH,   "DE")
    ok_tur   = download_file(TUR_URL,   TUR_PATH,   "TR")
    ok_links = download_file(LINKS_URL, LINKS_PATH, "LINKS")
    if not (ok_deu and ok_tur and ok_links):
        print("İndirme başarısız, çıkılıyor.")
        sys.exit(1)

    # 2. Cümleleri yükle
    print("\n[2/5] Cümleler yükleniyor...")
    deu = load_sentences(DEU_PATH, "DE")
    tur = load_sentences(TUR_PATH, "TR")

    # 3. Bağlantıları yükle
    print("\n[3/5] Çeviri bağlantıları yükleniyor...")
    links = load_links(LINKS_PATH)

    # 4. Almanca-Türkçe çiftleri oluştur
    print("\n[4/5] Çift oluşturuluyor...")
    pairs = build_de_tr_pairs(deu, tur, links)
    if not pairs:
        print("Çift bulunamadı, çıkılıyor.")
        sys.exit(1)

    # 5. Sözlüğe ekle
    print("\n[5/5] Sözlüğe ekleniyor...")
    dictionary = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  Sözlük: {len(dictionary):,} kayıt")

    # record_index: normalize(almanca) → index
    record_index: dict[str, int] = {}
    for i, rec in enumerate(dictionary):
        word = (rec.get("almanca") or "").strip()
        if word:
            record_index[normalize(word)] = i
            record_index[normalize(strip_article(word))] = i

    word_pairs = build_word_to_pairs(pairs, record_index)

    # Ekle
    updated = 0
    added_sentences = 0
    with_turkish = 0

    for idx, pair_list in word_pairs.items():
        rec = dictionary[idx]

        # Mevcut ornekler
        existing = rec.get("ornekler") or []
        if not isinstance(existing, list):
            existing = []
        existing_de = {o.get("almanca", "").strip() for o in existing}
        if rec.get("ornek_almanca", "").strip():
            existing_de.add(rec["ornek_almanca"].strip())

        # Tatoeba çiftlerinden ekle
        added_this = 0
        for de_sent, tr_sent in pair_list:
            if added_this >= MAX_TATOEBA_PER_WORD:
                break
            if len(existing) >= MAX_ORNEKLER_TOTAL:
                break
            if de_sent in existing_de:
                continue
            existing_de.add(de_sent)
            existing.append({
                "almanca": de_sent,
                "turkce": tr_sent,
                "kaynak": "Tatoeba (CC BY 2.0 France)",
            })
            added_this += 1
            added_sentences += 1
            if tr_sent:
                with_turkish += 1

            # İlk cümle yoksa ornek_almanca / ornek_turkce'yi de doldur
            if not rec.get("ornek_almanca", "").strip():
                rec["ornek_almanca"] = de_sent
            if not rec.get("ornek_turkce", "").strip():
                rec["ornek_turkce"] = tr_sent

        if added_this > 0:
            rec["ornekler"] = existing
            # Kaynak güncelle
            src = rec.get("kaynak", "")
            if "Tatoeba" not in src:
                rec["kaynak"] = (src + "; Tatoeba (CC BY 2.0 France)").lstrip("; ")
            updated += 1

    # Kaydet
    DICT_PATH.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    elapsed = time.time() - start

    # İstatistikler
    from collections import Counter
    counts = []
    for rec in dictionary:
        ornekler = [o for o in (rec.get("ornekler") or []) if o.get("almanca", "").strip()]
        n = len(ornekler)
        if n == 0 and (rec.get("ornek_almanca") or "").strip():
            n = 1
        counts.append(n)
    c = Counter(counts)

    print(f"\n{'=' * 65}")
    print("SONUÇ")
    print(f"  Güncellenen kelime      : {updated:,}")
    print(f"  Eklenen cümle çifti     : {added_sentences:,}")
    print(f"  Türkçe çevirili         : {with_turkish:,}")
    print(f"  Toplam kayıt            : {len(dictionary):,}")
    print(f"  Süre                    : {elapsed:.0f}s")
    print(f"\nCümle dağılımı:")
    for k in sorted(c):
        bar = "█" * min(k * 6, 36)
        print(f"  {k} cümle: {c[k]:>6,}  {bar}")
    avg = sum(counts) / max(len(counts), 1)
    print(f"\n  Ortalama : {avg:.2f} cümle/kelime")
    print(f"  3+ cümle : {sum(1 for x in counts if x >= 3):,} (%{sum(1 for x in counts if x >= 3)/len(counts)*100:.1f})")
    print(f"{'=' * 65}")
    print(f"\nKaydedildi: {DICT_PATH}")


if __name__ == "__main__":
    main()
