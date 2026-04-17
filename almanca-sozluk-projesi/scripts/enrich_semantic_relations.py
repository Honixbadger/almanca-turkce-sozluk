#!/usr/bin/env python3
"""
enrich_semantic_relations.py
=============================
dewiktionary.gz dump'ından semantik ilişkileri çıkarıp sözlüğe ekler.

Doldurduğu alanlar:
  ilgili_kayitlar  — sözlükte var olan hipernim, hiponim, koordinat ve
                     türetilmiş kelimelere çapraz referans listesi
  sinonim          — ek eş anlamlılar (mevcut listeye ekler, silmez)
  antonim          — ek zıt anlamlılar (mevcut listeye ekler, silmez)
  kelime_ailesi    — türetilmiş ve bileşik formlar

Veri kaynağı:
  data/raw/downloads/dewiktionary.gz  (Kaikki/Wiktionary, CC BY-SA 3.0)
  Ekstra indirme gerektirmez — zaten projede mevcut.

Lisans: Wiktionary CC BY-SA 3.0
"""

from __future__ import annotations

import gzip
import json
import re
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Yollar ve limitler
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATH    = PROJECT_ROOT / "output" / "dictionary.json"
DUMP_PATH    = PROJECT_ROOT / "data" / "raw" / "downloads" / "dewiktionary.gz"

# ilgili_kayitlar başına max ilişki sayısı (türe göre)
MAX_HYPERNYM  = 3   # üst kavram
MAX_HYPONYM   = 8   # alt kavram
MAX_COORD     = 6   # koordinat (kardeş) terimler
MAX_DERIVED   = 10  # türetilmiş
MAX_SYN       = 20  # eş anlamlı
MAX_ANT       = 10  # zıt anlamlı
MAX_FAMILY    = 20  # kelime ailesi

# ilgili_kayitlar girdisi için tip etiketleri (Türkçe)
REL_LABELS = {
    "hypernym":   "üst kavram",
    "hyponym":    "alt kavram",
    "coordinate": "koordinat terim",
    "derived":    "türetilmiş",
    "holonym":    "bütün",
    "meronym":    "parça",
}


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


def collect_words(raw_list: list | None) -> list[str]:
    """Kaikki formatındaki terim listesinden temiz kelime listesi çıkar."""
    result = []
    for item in (raw_list or []):
        if isinstance(item, str):
            word = item.strip()
        elif isinstance(item, dict):
            word = (item.get("word") or "").strip()
        else:
            continue
        if word and len(word) <= 80 and not word.startswith("*"):
            result.append(word)
    return result


# ---------------------------------------------------------------------------
# Dump okuma
# ---------------------------------------------------------------------------
def load_dump(dump_path: Path) -> dict[str, dict]:
    """
    dewiktionary.gz'den Almanca kelimelerin semantik ilişkilerini çıkar.
    Döndürür: {normalize(word): {hypernyms, hyponyms, synonyms, antonyms,
                                  coordinate_terms, derived, related}}
    """
    print(f"  Dump okunuyor: {dump_path}")
    data: dict[str, dict] = {}
    count = 0

    with gzip.open(str(dump_path), "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("lang_code") != "de":
                continue
            word = (d.get("word") or "").strip()
            if not word:
                continue

            key = normalize(word)
            entry = data.setdefault(key, {
                "word": word,
                "hypernyms": [],
                "hyponyms": [],
                "synonyms": [],
                "antonyms": [],
                "coordinate_terms": [],
                "derived": [],
                "related": [],
                "holonyms": [],
                "meronyms": [],
            })

            def merge(field_key: str, raw_field: str) -> None:
                existing_norms = {normalize(x) for x in entry[field_key]}
                for w in collect_words(d.get(raw_field)):
                    nw = normalize(w)
                    if nw and nw != key and nw not in existing_norms:
                        entry[field_key].append(w)
                        existing_norms.add(nw)

            merge("hypernyms",        "hypernyms")
            merge("hyponyms",         "hyponyms")
            merge("synonyms",         "synonyms")
            merge("antonyms",         "antonyms")
            merge("coordinate_terms", "coordinate_terms")
            merge("derived",          "derived")
            merge("related",          "related")
            merge("holonyms",         "holonyms")
            merge("meronyms",         "meronyms")
            count += 1

    nonempty = sum(
        1 for e in data.values()
        if any(e[k] for k in ("hypernyms", "hyponyms", "synonyms", "antonyms",
                               "coordinate_terms", "derived"))
    )
    print(f"  {count:,} Almanca kelime okundu, {nonempty:,} tanesinde semantik ilişki var.")
    return data


# ---------------------------------------------------------------------------
# Sözlüğe uygulama
# ---------------------------------------------------------------------------
def apply_relations(dictionary: list[dict], dump: dict[str, dict]) -> dict[str, int]:
    """
    Her sözlük kaydına ilgili semantik ilişkileri ekle.
    Döndürür: güncelleme sayaçları.
    """
    # Sözlükte var olan kelimeleri indeksle (ilgili_kayitlar sadece bunlara referans vermeli)
    dict_words: set[str] = set()
    for rec in dictionary:
        word = (rec.get("almanca") or "").strip()
        if word:
            dict_words.add(normalize(word))
            dict_words.add(normalize(strip_article(word)))

    counters = {
        "ilgili_updated": 0,
        "ilgili_items": 0,
        "syn_updated": 0,
        "syn_items": 0,
        "ant_updated": 0,
        "ant_items": 0,
        "family_updated": 0,
        "family_items": 0,
    }

    for rec in dictionary:
        word = (rec.get("almanca") or "").strip()
        key = normalize(strip_article(word))
        if not key:
            continue

        dump_entry = dump.get(key)
        if not dump_entry:
            # Makaleliyse makalesiz formda dene
            bare = normalize(strip_article(word))
            dump_entry = dump.get(bare)
        if not dump_entry:
            continue

        # ── ilgili_kayitlar ──────────────────────────────────────────────
        raw_related = rec.get("ilgili_kayitlar") or []
        # Eski format: string listesi → dict listesine dönüştür
        existing_related: list[dict] = []
        for r in raw_related:
            if isinstance(r, dict):
                existing_related.append(r)
            elif isinstance(r, str) and r.strip():
                existing_related.append({"almanca": r.strip(), "iliski": "ilgili", "kaynak": "eski-veri"})
        existing_rel_norms = {normalize(r.get("almanca", "")) for r in existing_related}
        rel_added = 0

        def add_relation(words: list[str], rel_type: str, limit: int) -> None:
            nonlocal rel_added
            label = REL_LABELS.get(rel_type, rel_type)
            for w in words[:limit]:
                nw = normalize(w)
                if not nw or nw in existing_rel_norms:
                    continue
                # Sadece sözlükte var olan kelimeleri bağla
                if nw not in dict_words:
                    continue
                existing_related.append({
                    "almanca": w,
                    "iliski": label,
                    "kaynak": "Wiktionary DE (CC BY-SA 3.0)",
                })
                existing_rel_norms.add(nw)
                rel_added += 1

        add_relation(dump_entry["hypernyms"],        "hypernym",   MAX_HYPERNYM)
        add_relation(dump_entry["hyponyms"],         "hyponym",    MAX_HYPONYM)
        add_relation(dump_entry["coordinate_terms"], "coordinate", MAX_COORD)
        add_relation(dump_entry["derived"],          "derived",    MAX_DERIVED)
        add_relation(dump_entry["holonyms"],         "holonym",    MAX_HYPERNYM)
        add_relation(dump_entry["meronyms"],         "meronym",    MAX_COORD)

        if rel_added > 0:
            rec["ilgili_kayitlar"] = existing_related
            counters["ilgili_updated"] += 1
            counters["ilgili_items"] += rel_added

        # ── sinonim ──────────────────────────────────────────────────────
        new_syns = dump_entry["synonyms"]
        if new_syns:
            existing_syn: list[str] = list(rec.get("sinonim") or [])
            existing_syn_norms = {normalize(x) for x in existing_syn}
            syn_added = 0
            for s in new_syns:
                ns = normalize(s)
                if ns and ns != key and ns not in existing_syn_norms and len(existing_syn) < MAX_SYN:
                    existing_syn.append(s)
                    existing_syn_norms.add(ns)
                    syn_added += 1
            if syn_added:
                rec["sinonim"] = existing_syn
                counters["syn_updated"] += 1
                counters["syn_items"] += syn_added

        # ── antonim ──────────────────────────────────────────────────────
        new_ants = dump_entry["antonyms"]
        if new_ants:
            existing_ant: list[str] = list(rec.get("antonim") or [])
            existing_ant_norms = {normalize(x) for x in existing_ant}
            ant_added = 0
            for a in new_ants:
                na = normalize(a)
                if na and na != key and na not in existing_ant_norms and len(existing_ant) < MAX_ANT:
                    existing_ant.append(a)
                    existing_ant_norms.add(na)
                    ant_added += 1
            if ant_added:
                rec["antonim"] = existing_ant
                counters["ant_updated"] += 1
                counters["ant_items"] += ant_added

        # ── kelime_ailesi ─────────────────────────────────────────────────
        family_sources = dump_entry["derived"] + dump_entry["related"]
        if family_sources:
            existing_fam: list[str] = list(rec.get("kelime_ailesi") or [])
            existing_fam_norms = {normalize(x) for x in existing_fam}
            fam_added = 0
            for w in family_sources:
                nw = normalize(w)
                if nw and nw != key and nw not in existing_fam_norms and len(existing_fam) < MAX_FAMILY:
                    existing_fam.append(w)
                    existing_fam_norms.add(nw)
                    fam_added += 1
            if fam_added:
                rec["kelime_ailesi"] = existing_fam
                counters["family_updated"] += 1
                counters["family_items"] += fam_added

    return counters


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
def main() -> None:
    start = time.time()

    print("=" * 65)
    print("enrich_semantic_relations.py — Wiktionary Semantik Ağ Entegrasyonu")
    print("Kaynak: dewiktionary.gz (Kaikki, CC BY-SA 3.0)")
    print("=" * 65)

    if not DUMP_PATH.exists():
        print(f"\nHATA: Dump bulunamadı: {DUMP_PATH}")
        print("Önce fetch_sources.py çalıştırarak dewiktionary.gz'yi indirin.")
        sys.exit(1)

    # 1. Dump yükle
    print("\n[1/3] Wiktionary dump'ı okunuyor...")
    dump = load_dump(DUMP_PATH)

    # 2. Sözlük yükle
    print("\n[2/3] Sözlük yükleniyor...")
    dictionary: list[dict] = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(dictionary):,} kayıt")

    # 3. Uygula
    print("\n[3/3] Semantik ilişkiler uygulanıyor...")
    counters = apply_relations(dictionary, dump)

    # Kaydet
    DICT_PATH.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    elapsed = time.time() - start

    # İstatistikler
    total_with_related = sum(1 for r in dictionary if r.get("ilgili_kayitlar"))
    total_with_syn     = sum(1 for r in dictionary if r.get("sinonim"))
    total_with_ant     = sum(1 for r in dictionary if r.get("antonim"))
    total_with_family  = sum(1 for r in dictionary if r.get("kelime_ailesi"))
    total              = len(dictionary)

    print(f"\n{'=' * 65}")
    print("SONUÇ")
    print(f"  ilgili_kayitlar  : {counters['ilgili_updated']:>6,} kayıt güncellendi  "
          f"({counters['ilgili_items']:,} ilişki eklendi)")
    print(f"  sinonim          : {counters['syn_updated']:>6,} kayıt güncellendi  "
          f"({counters['syn_items']:,} kelime eklendi)")
    print(f"  antonim          : {counters['ant_updated']:>6,} kayıt güncellendi  "
          f"({counters['ant_items']:,} kelime eklendi)")
    print(f"  kelime_ailesi    : {counters['family_updated']:>6,} kayıt güncellendi  "
          f"({counters['family_items']:,} kelime eklendi)")
    print()
    print(f"  ilgili_kayitlar dolu : {total_with_related:,}/{total:,}  "
          f"(%{100*total_with_related//total})")
    print(f"  sinonim dolu         : {total_with_syn:,}/{total:,}  "
          f"(%{100*total_with_syn//total})")
    print(f"  antonim dolu         : {total_with_ant:,}/{total:,}  "
          f"(%{100*total_with_ant//total})")
    print(f"  kelime_ailesi dolu   : {total_with_family:,}/{total:,}  "
          f"(%{100*total_with_family//total})")
    print(f"\n  Süre : {elapsed:.0f}s")
    print(f"{'=' * 65}")
    print(f"\nKaydedildi: {DICT_PATH}")


if __name__ == "__main__":
    main()
