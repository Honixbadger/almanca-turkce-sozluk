#!/usr/bin/env python3
"""
enrich_opus_detr.py
===================
OPUS açık paralel korpusundan Almanca-Türkçe cümle çiftlerini sözlüğe ekler.

Kullanılan alt-korpuslar (öncelik sırasıyla):
  1. OpenSubtitles  — doğal, konuşma dili   (~3M çift)
  2. WikiMatrix     — ansiklopedik, bilgi    (~300K çift)
  3. CCAligned      — web metni, karma       (~200K çift)
  4. TED2020        — konuşmalar, yarı-resmi (~200K çift)

Her sözlük kaydı için:
  - Kelimeyi içeren Almanca cümlesi bulunur
  - Türkçe karşılığıyla ornekler listesine eklenir
  - ornek_turkce alanı doluysa dokunulmaz

Kaynaklar / Lisanslar:
  OpenSubtitles  : Lison & Tiedemann, CC BY 4.0
  WikiMatrix     : Facebook AI, MIT Lisansı
  CCAligned      : El-Kishky et al., CC0
  TED2020        : TED, araştırma kullanımı (kısıtlı ticari)

OPUS : https://opus.nlpl.eu
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import unicodedata
import urllib.request as ur
import zipfile
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Yollar ve sabitler
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DATA_DIR = PROJECT_ROOT / "data" / "raw" / "downloads" / "opus"
CHECKPOINT_PATH = PROJECT_ROOT / "output" / "opus_detr_checkpoint.json"

UA = "AlmancaSozluk/1.0 (educational; contact: github.com/Honixbadger)"

# Kelime başına max kaç OPUS cümlesi eklenecek
MAX_OPUS_PER_WORD = 3
# ornekler toplam limiti (tüm kaynaklar dahil)
MAX_ORNEKLER_TOTAL = 7
# Cümle uzunluk limitleri (karakter)
MIN_SENT_LEN = 18
MAX_SENT_LEN = 200
# Bellek tasarrufu: korpus başına max işlenecek çift sayısı (0 = sınırsız)
MAX_PAIRS_PER_CORPUS = 5_000_000

# Almanca token regex (≥3 harf)
TOKEN_RE = re.compile(r"\b[A-Za-zÄäÖöÜüß]{3,}\b")

# ---------------------------------------------------------------------------
# Alt-korpus tanımları
# (OPUS Moses formatı: zip içinde iki hizalı düz metin dosyası)
# ---------------------------------------------------------------------------
CORPORA: list[dict] = [
    {
        "name": "OpenSubtitles",
        "url": "https://object.pouta.csc.fi/OPUS-OpenSubtitles/v2016/moses/de-tr.txt.zip",
        "filename": "opus_opensubtitles_de-tr.zip",
        "de_file": "OpenSubtitles.de-tr.de",
        "tr_file": "OpenSubtitles.de-tr.tr",
        "license": "CC BY 4.0",
        "citation": "Lison & Tiedemann (2016), LREC",
    },
    {
        "name": "WikiMatrix",
        "url": "https://object.pouta.csc.fi/OPUS-WikiMatrix/v1/moses/de-tr.txt.zip",
        "filename": "opus_wikimatrix_de-tr.zip",
        "de_file": "WikiMatrix.de-tr.de",
        "tr_file": "WikiMatrix.de-tr.tr",
        "license": "MIT (Facebook AI Research)",
        "citation": "Schwartz et al. (2021), EACL",
    },
    {
        "name": "CCAligned",
        "url": "https://object.pouta.csc.fi/OPUS-CCAligned/v1/moses/de-tr.txt.zip",
        "filename": "opus_ccaligned_de-tr.zip",
        "de_file": "CCAligned.de-tr.de",
        "tr_file": "CCAligned.de-tr.tr",
        "license": "CC0",
        "citation": "El-Kishky et al. (2020), EMNLP",
    },
    {
        "name": "TED2020",
        "url": "https://object.pouta.csc.fi/OPUS-TED2020/v1/moses/de-tr.txt.zip",
        "filename": "opus_ted2020_de-tr.zip",
        "de_file": "TED2020.de-tr.de",
        "tr_file": "TED2020.de-tr.tr",
        "license": "TED (araştırma kullanımı)",
        "citation": "Reimers & Gurevych (2020)",
    },
]


# ---------------------------------------------------------------------------
# Yardımcı fonksiyonlar
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


def is_good_sentence(text: str) -> bool:
    """Cümle kalite filtresi."""
    if not (MIN_SENT_LEN <= len(text) <= MAX_SENT_LEN):
        return False
    # Çok fazla parantez/köşeli parantez → altyazı efekti, sözlük notu vs.
    if text.count("[") + text.count("{") + text.count("(") > 2:
        return False
    # Aşırı rakam içeriği → kod, tarih dizisi vs.
    digit_ratio = sum(1 for c in text if c.isdigit()) / max(len(text), 1)
    if digit_ratio > 0.12:
        return False
    # Yeterli kelime yok
    if len(TOKEN_RE.findall(text)) < 3:
        return False
    # Yalnızca büyük harf → başlık/altyazı formatı
    if text.isupper():
        return False
    return True


def download_file(url: str, dest: Path, label: str) -> bool:
    """Dosyayı indir, varsa atla."""
    if dest.exists() and dest.stat().st_size > 0:
        size_mb = dest.stat().st_size / 1024 / 1024
        print(f"  [{label}] Zaten var ({size_mb:.1f} MB), atlanıyor.")
        return True
    print(f"  [{label}] İndiriliyor: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = ur.Request(url, headers={"User-Agent": UA})
        with ur.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk = 128 * 1024
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                downloaded += len(buf)
                if total:
                    pct = downloaded / total * 100
                    mb_done = downloaded / 1024 / 1024
                    mb_total = total / 1024 / 1024
                    print(f"\r    %{pct:.0f}  ({mb_done:.0f}/{mb_total:.0f} MB)", end="", flush=True)
        print()
        tmp.rename(dest)
        print(f"    Tamamlandı: {dest.stat().st_size // 1024 // 1024} MB")
        return True
    except Exception as e:
        print(f"    HATA [{label}]: {e}")
        if tmp.exists():
            tmp.unlink()
        return False


# ---------------------------------------------------------------------------
# Korpus okuma
# ---------------------------------------------------------------------------
def load_pairs_from_zip(
    zip_path: Path,
    de_filename: str,
    tr_filename: str,
    corpus_name: str,
    max_pairs: int = MAX_PAIRS_PER_CORPUS,
) -> list[tuple[str, str]]:
    """
    OPUS Moses zip'inden hizalı (de, tr) çiftlerini oku.
    Zip içindeki iki dosya satır bazında hizalıdır.
    """
    pairs: list[tuple[str, str]] = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            # Tam ad ya da suffix eşleşmesi
            de_match = next((n for n in names if n == de_filename or n.endswith("/" + de_filename)), None)
            tr_match = next((n for n in names if n == tr_filename or n.endswith("/" + tr_filename)), None)
            if not de_match or not tr_match:
                # Fallback: .de / .tr uzantılarına göre bul
                de_match = next((n for n in names if n.endswith(".de")), None)
                tr_match = next((n for n in names if n.endswith(".tr")), None)
            if not de_match or not tr_match:
                print(f"  [{corpus_name}] ZIP içinde DE/TR dosyaları bulunamadı. Mevcut: {names[:10]}")
                return pairs

            with zf.open(de_match) as de_raw, zf.open(tr_match) as tr_raw:
                de_stream = io.TextIOWrapper(de_raw, encoding="utf-8", errors="replace")
                tr_stream = io.TextIOWrapper(tr_raw, encoding="utf-8", errors="replace")
                count = 0
                for de_line, tr_line in zip(de_stream, tr_stream):
                    de = de_line.rstrip("\n").strip()
                    tr = tr_line.rstrip("\n").strip()
                    if de and tr:
                        pairs.append((de, tr))
                        count += 1
                        if max_pairs and count >= max_pairs:
                            print(f"  [{corpus_name}] {max_pairs:,} çift limiti doldu, duruldu.")
                            break

    except zipfile.BadZipFile as e:
        print(f"  [{corpus_name}] Bozuk ZIP: {e}")
    except Exception as e:
        print(f"  [{corpus_name}] Okuma hatası: {e}")

    print(f"  [{corpus_name}] {len(pairs):,} ham çift okundu.")
    return pairs


# ---------------------------------------------------------------------------
# Sözlük eşleştirme
# ---------------------------------------------------------------------------
def build_record_index(dictionary: list[dict]) -> dict[str, int]:
    """normalize(almanca) → kayıt indeksi."""
    idx: dict[str, int] = {}
    for i, rec in enumerate(dictionary):
        word = (rec.get("almanca") or "").strip()
        if not word:
            continue
        idx[normalize(word)] = i
        bare = normalize(strip_article(word))
        if bare:
            idx[bare] = i
    return idx


def match_pairs_to_words(
    pairs: list[tuple[str, str]],
    record_index: dict[str, int],
    corpus_name: str,
) -> dict[int, list[tuple[str, str]]]:
    """
    Her cümle çiftini sözlük kelimeleriyle eşleştir.
    Döndürür: {record_idx: [(de_sent, tr_sent), ...]}
    """
    word_pairs: dict[int, list[tuple[str, str]]] = defaultdict(list)
    good = 0

    for de_text, tr_text in pairs:
        if not is_good_sentence(de_text):
            continue
        good += 1
        seen_in_sent: set[int] = set()
        for token in TOKEN_RE.findall(de_text):
            norm = normalize(token)
            record_idx = record_index.get(norm)
            if record_idx is None:
                continue
            if record_idx in seen_in_sent:
                continue
            seen_in_sent.add(record_idx)
            word_pairs[record_idx].append((de_text, tr_text))

    # Her kelime için: tekrarsız, kısa cümleler önce
    result: dict[int, list[tuple[str, str]]] = {}
    for idx, pair_list in word_pairs.items():
        seen_de: set[str] = set()
        unique = []
        for de, tr in pair_list:
            if de not in seen_de:
                seen_de.add(de)
                unique.append((de, tr))
        unique.sort(key=lambda p: len(p[0]))
        result[idx] = unique

    print(f"  [{corpus_name}] {good:,} kaliteli cümle, {len(result):,} kelime eşleşti.")
    return result


def merge_into_dictionary(
    dictionary: list[dict],
    word_pairs: dict[int, list[tuple[str, str]]],
    corpus_name: str,
    license_str: str,
    citation: str,
    checkpoint_done: set[str],
) -> tuple[int, int]:
    """
    Eşleşen çiftleri sözlüğe ekle.
    Döndürür: (güncellenen kelime sayısı, eklenen cümle sayısı)
    """
    source_tag = f"OPUS-{corpus_name} ({license_str})"
    updated = 0
    added = 0

    for idx, pair_list in word_pairs.items():
        rec = dictionary[idx]
        word_key = (rec.get("almanca") or "").strip()

        # Bu kelime bu korpus için zaten işlendiyse atla
        ck = f"{corpus_name}::{normalize(word_key)}"
        if ck in checkpoint_done:
            continue

        existing = rec.get("ornekler") or []
        if not isinstance(existing, list):
            existing = []

        # Mevcut Almanca cümleler (tekrar önleme)
        existing_de: set[str] = {o.get("almanca", "").strip() for o in existing}
        if rec.get("ornek_almanca", "").strip():
            existing_de.add(rec["ornek_almanca"].strip())

        added_this = 0
        for de_sent, tr_sent in pair_list:
            if added_this >= MAX_OPUS_PER_WORD:
                break
            if len(existing) >= MAX_ORNEKLER_TOTAL:
                break
            if de_sent in existing_de:
                continue
            existing_de.add(de_sent)
            existing.append({
                "almanca": de_sent,
                "turkce": tr_sent,
                "kaynak": source_tag,
            })
            added_this += 1
            added += 1

            # Üst düzey alanları doldur (boşsa)
            if not rec.get("ornek_almanca", "").strip():
                rec["ornek_almanca"] = de_sent
            if not rec.get("ornek_turkce", "").strip() and tr_sent:
                rec["ornek_turkce"] = tr_sent

        if added_this > 0:
            rec["ornekler"] = existing
            src = rec.get("kaynak", "") or ""
            if corpus_name not in src:
                rec["kaynak"] = (src + f"; {source_tag}").lstrip("; ")
            updated += 1

        checkpoint_done.add(ck)

    return updated, added


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OPUS DE-TR korpusunu sözlüğe entegre et.")
    p.add_argument("--input-path", default=str(DEFAULT_DICT_PATH))
    p.add_argument("--output-path", default="")
    p.add_argument(
        "--corpus",
        nargs="+",
        choices=[c["name"] for c in CORPORA],
        default=None,
        help="Kullanılacak korpuslar (boş = hepsi)",
    )
    p.add_argument(
        "--max-pairs",
        type=int,
        default=MAX_PAIRS_PER_CORPUS,
        help="Korpus başına max cümle çifti (0 = sınırsız)",
    )
    p.add_argument(
        "--skip-download",
        action="store_true",
        help="İndirmeyi atla (dosyalar zaten mevcut olmalı)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    start = time.time()

    dict_input = Path(args.input_path)
    dict_output = Path(args.output_path) if args.output_path else dict_input
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    selected_corpora = [
        c for c in CORPORA
        if args.corpus is None or c["name"] in args.corpus
    ]

    print("=" * 65)
    print("enrich_opus_detr.py — OPUS Almanca-Türkçe Entegrasyonu")
    print("URL: https://opus.nlpl.eu")
    print(f"Seçili korpus: {', '.join(c['name'] for c in selected_corpora)}")
    print("=" * 65)

    # Checkpoint yükle
    checkpoint_done: set[str] = set()
    if CHECKPOINT_PATH.exists():
        try:
            checkpoint_done = set(json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8")))
            print(f"\nCheckpoint: {len(checkpoint_done):,} işlem yüklendi.")
        except Exception:
            pass

    # Sözlüğü yükle
    print(f"\nSözlük yükleniyor: {dict_input}")
    dictionary: list[dict] = json.loads(dict_input.read_text(encoding="utf-8"))
    print(f"  {len(dictionary):,} kayıt.")

    record_index = build_record_index(dictionary)
    print(f"  {len(record_index):,} arama indeksi oluşturuldu.")

    total_updated = 0
    total_added = 0

    for corpus in selected_corpora:
        name = corpus["name"]
        zip_path = DATA_DIR / corpus["filename"]

        print(f"\n{'─' * 55}")
        print(f"[{name}]  {corpus['license']}")

        # İndir
        if not args.skip_download:
            ok = download_file(corpus["url"], zip_path, name)
            if not ok:
                print(f"  [{name}] İndirilemedi, atlanıyor.")
                continue
        elif not zip_path.exists():
            print(f"  [{name}] Dosya yok ve --skip-download aktif, atlanıyor.")
            continue

        # Çiftleri oku
        pairs = load_pairs_from_zip(
            zip_path,
            corpus["de_file"],
            corpus["tr_file"],
            name,
            max_pairs=args.max_pairs,
        )
        if not pairs:
            print(f"  [{name}] Çift bulunamadı.")
            continue

        # Eşleştir
        word_pairs = match_pairs_to_words(pairs, record_index, name)
        del pairs  # bellek serbest bırak

        # Sözlüğe ekle
        updated, added = merge_into_dictionary(
            dictionary,
            word_pairs,
            name,
            corpus["license"],
            corpus["citation"],
            checkpoint_done,
        )
        total_updated += updated
        total_added += added
        print(f"  [{name}] {updated:,} kelime güncellendi, {added:,} cümle eklendi.")

        # Her korpus sonrası ara kaydet
        dict_output.write_text(
            json.dumps(dictionary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        CHECKPOINT_PATH.write_text(
            json.dumps(sorted(checkpoint_done), ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  [{name}] Ara kayıt tamamlandı.")

    # Son istatistikler
    elapsed = time.time() - start
    total_with_tr = sum(
        1 for rec in dictionary
        if any(
            (o.get("turkce") or "").strip()
            for o in (rec.get("ornekler") or [])
        )
    )
    total_without_tr = sum(
        1 for rec in dictionary
        if all(
            not (o.get("turkce") or "").strip()
            for o in (rec.get("ornekler") or [])
        ) and any(
            (o.get("almanca") or "").strip()
            for o in (rec.get("ornekler") or [])
        )
    )

    print(f"\n{'=' * 65}")
    print("ÖZET")
    print(f"  Güncellenen kelime        : {total_updated:,}")
    print(f"  Eklenen cümle çifti       : {total_added:,}")
    print(f"  Türkçe çevirili örnek var : {total_with_tr:,} kelime")
    print(f"  Türkçe örnek eksik        : {total_without_tr:,} kelime")
    print(f"  Toplam kayıt              : {len(dictionary):,}")
    print(f"  Süre                      : {elapsed:.0f}s")
    print(f"{'=' * 65}")
    print(f"\nKaydedildi : {dict_output}")
    print(f"Checkpoint : {CHECKPOINT_PATH}")


if __name__ == "__main__":
    main()
