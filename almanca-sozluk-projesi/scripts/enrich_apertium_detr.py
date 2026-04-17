#!/usr/bin/env python3
"""
enrich_apertium_detr.py
========================
Apertium Almanca-Türkçe açık kaynak ikidilli sözlüğünden
ek çeviriler çıkarıp sözlüğe ekler.

Doldurduğu alanlar:
  turkce      — boşsa Apertium çevirisini ekler
  anlamlar    — mevcut anlam listesini Apertium ile zenginleştirir

Kaynak:
  Apertium deu-tur (GPL-3.0)
  https://github.com/apertium/apertium-deu-tur
"""

from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
import urllib.request as ur
import xml.etree.ElementTree as ET
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATH    = PROJECT_ROOT / "output" / "dictionary.json"
DATA_DIR     = PROJECT_ROOT / "data" / "raw" / "downloads"
DIX_PATH     = DATA_DIR / "apertium_deu_tur.dix"

DIX_URL = (
    "https://raw.githubusercontent.com/apertium/apertium-deu-tur"
    "/master/apertium-deu-tur.deu-tur.dix"
)
UA = "AlmancaSozluk/1.0 (educational; contact: github.com/Honixbadger)"

# POS etiket eşleştirme (Apertium → sözlük tur değeri)
POS_MAP = {
    "vblex": "fiil", "vaux": "fiil", "vbmod": "fiil", "vbser": "fiil",
    "n": "isim", "np": "isim",
    "adj": "sıfat",
    "adv": "zarf",
    "pr": "edat", "prn": "zamir",
    "cnjcoo": "bağlaç", "cnjsub": "bağlaç", "cnjadv": "bağlaç",
    "ij": "ünlem",
    "num": "sayı",
}


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().casefold()


def strip_article(word: str) -> str:
    parts = word.strip().split(" ", 1)
    if len(parts) == 2 and normalize(parts[0]) in {"der", "die", "das"}:
        return parts[1]
    return word.strip()


def download_dix(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  Zaten var ({dest.stat().st_size//1024} KB), atlanıyor.")
        return True
    print(f"  İndiriliyor: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = ur.Request(url, headers={"User-Agent": UA})
        with ur.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
            f.write(resp.read())
        print(f"  Tamamlandı: {dest.stat().st_size//1024} KB")
        return True
    except Exception as e:
        print(f"  HATA: {e}")
        return False


def parse_dix(dix_path: Path) -> dict[str, list[dict]]:
    """
    .dix XML dosyasını parse et.
    Döndürür: {normalize(de_lemma): [{tr, pos}, ...]}
    """
    print(f"  Parsing: {dix_path}")
    result: dict[str, list[dict]] = {}

    tree = ET.parse(str(dix_path))
    root = tree.getroot()

    # Apertium .dix formatı:
    # <e><p><l>GERMAN<s n="POS"/></l><r>TURKISH<s n="POS"/></r></p></e>
    for section in root.findall(".//section"):
        for entry in section.findall("e"):
            pair = entry.find("p")
            if pair is None:
                continue
            l_elem = pair.find("l")
            r_elem = pair.find("r")
            if l_elem is None or r_elem is None:
                continue

            # Almanca lemma ve POS
            de_parts = [l_elem.text or ""]
            de_pos = ""
            for s in l_elem.findall("s"):
                n = s.get("n", "")
                if n in POS_MAP:
                    de_pos = n
                de_parts.append("")  # <s> etiketleri metni bölebilir

            # r elementinin tam metnini al (alt elementleri dahil)
            tr_text = (r_elem.text or "")
            for child in r_elem:
                if child.tag == "s":
                    pass  # POS etiketi
                else:
                    tr_text += (child.text or "") + (child.tail or "")
            tr_text = tr_text.strip()

            # l elementinin tam metnini al
            de_text = (l_elem.text or "")
            for child in l_elem:
                if child.tag != "s":
                    de_text += (child.text or "") + (child.tail or "")
                else:
                    de_text += (child.tail or "")
            de_text = de_text.strip()

            if not de_text or not tr_text:
                continue
            if len(de_text) > 60 or len(tr_text) > 80:
                continue

            key = normalize(de_text)
            pos_label = POS_MAP.get(de_pos, "")
            entry_dict = {"tr": tr_text, "pos": pos_label}
            result.setdefault(key, [])
            # Tekrar önleme
            if not any(normalize(x["tr"]) == normalize(tr_text) for x in result[key]):
                result[key].append(entry_dict)

    print(f"  {len(result):,} Almanca lemma yüklendi.")
    return result


def apply_apertium(
    dictionary: list[dict],
    apertium: dict[str, list[dict]],
) -> dict[str, int]:
    counters = {
        "turkce_filled": 0,
        "anlamlar_added": 0,
        "entries_updated": 0,
    }

    for rec in dictionary:
        word = (rec.get("almanca") or "").strip()
        key = normalize(strip_article(word))
        if not key:
            continue

        matches = apertium.get(key, [])
        if not matches:
            continue

        changed = False
        tr_current = (rec.get("turkce") or "").strip()

        # turkce alanı boşsa doldur
        if not tr_current and matches:
            new_tr = "; ".join(m["tr"] for m in matches[:3])
            rec["turkce"] = new_tr
            counters["turkce_filled"] += 1
            changed = True

        # anlamlar listesine ekle (zaten yoksa)
        existing_anlamlar: list[dict] = list(rec.get("anlamlar") or [])
        existing_tr_norms = {normalize(a.get("turkce", "")) for a in existing_anlamlar}
        existing_tr_norms.add(normalize(tr_current))

        for m in matches:
            tr_norm = normalize(m["tr"])
            if not tr_norm or tr_norm in existing_tr_norms:
                continue
            existing_anlamlar.append({
                "sira": len(existing_anlamlar) + 1,
                "turkce": m["tr"],
                "tanim_almanca": "",
                "kaynak": "Apertium deu-tur (GPL-3.0)",
                "guven": 0.55,
            })
            existing_tr_norms.add(tr_norm)
            counters["anlamlar_added"] += 1
            changed = True

        if existing_anlamlar and existing_anlamlar != (rec.get("anlamlar") or []):
            rec["anlamlar"] = existing_anlamlar

        if changed:
            # Kaynak güncelle
            src = rec.get("kaynak") or ""
            if "Apertium" not in src:
                rec["kaynak"] = (src + "; Apertium deu-tur (GPL-3.0)").lstrip("; ")
            counters["entries_updated"] += 1

    return counters


def main() -> None:
    start = time.time()

    print("=" * 65)
    print("enrich_apertium_detr.py — Apertium DE-TR Entegrasyonu")
    print("Kaynak: Apertium deu-tur (GPL-3.0)")
    print("URL: https://github.com/apertium/apertium-deu-tur")
    print("=" * 65)

    print("\n[1/4] Apertium sözlüğü indiriliyor...")
    if not download_dix(DIX_URL, DIX_PATH):
        print("İndirme başarısız.")
        sys.exit(1)

    print("\n[2/4] Sözlük parse ediliyor...")
    apertium = parse_dix(DIX_PATH)
    if not apertium:
        print("Veri okunamadı.")
        sys.exit(1)

    print("\n[3/4] Ana sözlük yükleniyor...")
    dictionary: list[dict] = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(dictionary):,} kayıt")

    print("\n[4/4] Apertium verileri uygulanıyor...")
    counters = apply_apertium(dictionary, apertium)

    DICT_PATH.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    elapsed = time.time() - start

    print(f"\n{'=' * 65}")
    print("SONUÇ")
    print(f"  Güncellenen kayıt     : {counters['entries_updated']:,}")
    print(f"  Doldurulan turkce     : {counters['turkce_filled']:,}")
    print(f"  Eklenen anlamlar      : {counters['anlamlar_added']:,}")
    print(f"  Süre                  : {elapsed:.0f}s")
    print(f"{'=' * 65}")
    print(f"\nKaydedildi: {DICT_PATH}")


if __name__ == "__main__":
    main()
