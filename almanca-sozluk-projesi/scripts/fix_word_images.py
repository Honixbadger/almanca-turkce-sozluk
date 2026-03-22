"""
fix_word_images.py
------------------
1. Yanlış manifest girişlerini siler ve doğru Wikipedia başlığıyla yeniden indirir.
2. Soyut/uygunsuz kelimeleri "not_found" olarak işaretler.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Windows konsolunda Unicode sorunlarını önle
if sys.stdout.encoding and sys.stdout.encoding.lower() not in {"utf-8", "utf-8-sig"}:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Proje kökünü bulup import yoluna ekle
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from word_image_cache import (
    WORD_IMAGE_CACHE_DIR,
    fetch_commons_file_info,
    fetch_exact_page,
    image_cache_key,
    load_manifest,
    save_image_bytes,
    save_manifest,
    search_page,
    strip_html,
    build_cache_filename,
    prune_cache_for_bytes,
    download_bytes,
)

# ─── 1. Yanlış görsel → doğru Wikipedia başlığı ───────────────────────────────
REFETCH_MAP: dict[str, str] = {
    "fahrer":                "Kraftfahrer",
    "kobalt":                "Kobalt",
    "motordrehmoment":       "Drehmoment",
    "automatgetriebe":       "Automatikgetriebe",
    "abs":                   "Antiblockiersystem",
    "lift":                  "Aufzugsanlage",
    "systemrechner":         "Steuergerät (Kraftfahrzeug)",
    "agenda":                "Tagesordnung",
    "plus":                  "Addition",
    "dauer":                 "Dauer",
    "adas":                  "Fahrerassistenzsystem",
    "antriebsschlupfregelung": "Antriebsschlupfregelung",
    "lenkwinkelsensor":      "Lenkradwinkelsensor",
    "teil":                  "Bauteil (Technik)",
    "wahlbar":               "Wahlrecht",
    "lenkbarkeit":           "Servolenkung",
    "hdi":                   "Common Rail",
    "getriebeubersetzung":   "Übersetzung (Getriebe)",
    "abendland":             "Abendland",
    "anteil":                "Aktie",
    "auslegung":             "Auslegung (Recht)",
}

# ─── 2. Soyut / görseli uygun olmayan kelimeler → not_found ───────────────────
MARK_NOT_FOUND: list[str] = [
    "machen",
    "wieder",
    "aber",
    "sich",
    "ausreichen",
    "ausschlaggebend",
    "absagen",
    "absichtlich",
    "heranreicht",
    "kantigen",
    "verurteilen",
    "streicht",
    "polring",
    "reiche",
    "forderungen",
]


def delete_entry(manifest: dict, key: str) -> None:
    """Manifest girişini ve disk üzerindeki dosyayı sil."""
    entry = manifest["entries"].get(key)
    if entry:
        file_name = entry.get("file_name", "")
        if file_name:
            img_path = WORD_IMAGE_CACHE_DIR / file_name
            if img_path.exists():
                img_path.unlink()
                print(f"  🗑  Silindi: {file_name}")
        manifest["entries"].pop(key, None)


def refetch_with_correct_title(manifest: dict, original_term: str, correct_title: str) -> str:
    """
    Doğru Wikipedia başlığıyla görseli yeniden çek ve manifeste orijinal key altında kaydet.
    Döndürülen değer: "ok" | "not_found" | "error"
    """
    key = image_cache_key(original_term)

    # Doğru sayfayı bul: önce tam başlıkla, sonra arama ile
    page = (
        fetch_exact_page(correct_title, "de")
        or search_page(correct_title, "de")
        or fetch_exact_page(correct_title, "en")
        or search_page(correct_title, "en")
    )

    if not page:
        manifest["entries"][key] = {
            "status": "not_found",
            "note": f"Doğru başlık '{correct_title}' için görsel bulunamadı.",
            "last_accessed": time.time(),
        }
        return "not_found"

    file_name = str(page.get("pageimage", "")).strip()
    file_info = fetch_commons_file_info(file_name)
    if not file_info or not file_info.get("thumburl"):
        manifest["entries"][key] = {
            "status": "not_found",
            "note": "Görsel başlığı bulundu ama küçük önizleme alınamadı.",
            "last_accessed": time.time(),
        }
        return "not_found"

    try:
        image_bytes = download_bytes(file_info["thumburl"])
    except Exception as exc:
        print(f"  ⚠  İndirme hatası: {exc}")
        manifest["entries"][key] = {
            "status": "not_found",
            "note": f"İndirme hatası: {exc}",
            "last_accessed": time.time(),
        }
        return "error"

    if not prune_cache_for_bytes(manifest, max(len(image_bytes), 1)):
        print("  ⚠  Önbellek dolu, görsel kaydedilmedi.")
        return "cache_full"

    file_name_on_disk = build_cache_filename(key)
    target_path = WORD_IMAGE_CACHE_DIR / file_name_on_disk

    try:
        file_size = save_image_bytes(target_path, image_bytes)
    except Exception as exc:
        print(f"  ⚠  Kaydetme hatası: {exc}")
        return "error"

    description = file_info.get("description") or strip_html(page.get("description", "")) or page.get("title", "")
    attribution = " · ".join(p for p in [file_info.get("artist", ""), file_info.get("license", "")] if p)

    manifest["entries"][key] = {
        "status": "ok",
        "file_name": file_name_on_disk,
        "file_size": file_size,
        "source_url": file_info.get("descriptionurl", ""),
        "image_url": file_info.get("image_url", ""),
        "page_title": page.get("title", ""),
        "description": description,
        "artist": file_info.get("artist", ""),
        "credit": file_info.get("credit", ""),
        "license": file_info.get("license", ""),
        "attribution": attribution,
        "last_accessed": time.time(),
    }
    return "ok"


def main() -> None:
    manifest = load_manifest()
    stats = {"ok": 0, "not_found": 0, "error": 0, "marked": 0}

    # ── Aşama 1: Yanlış görselleri sil ve yeniden çek ────────────────────────
    print(f"\n{'─'*60}")
    print(f"Aşama 1: {len(REFETCH_MAP)} yanlış görsel yeniden çekiliyor...")
    print(f"{'─'*60}")

    for term, correct_title in REFETCH_MAP.items():
        key = image_cache_key(term)
        print(f"\n[{term}] → Wikipedia: '{correct_title}' (key={key})")
        delete_entry(manifest, key)
        result = refetch_with_correct_title(manifest, term, correct_title)
        stats[result] = stats.get(result, 0) + 1
        entry = manifest["entries"].get(key, {})
        if result == "ok":
            print(f"  ✅ OK — {entry.get('page_title')} | {entry.get('file_name')}")
        else:
            print(f"  ❌ {result.upper()} — {entry.get('note', '')}")
        save_manifest(manifest)  # Her adımda kaydet
        time.sleep(0.3)  # API'ye saygı

    # ── Aşama 2: Soyut kelimeleri not_found olarak işaretle ──────────────────
    print(f"\n{'─'*60}")
    print(f"Aşama 2: {len(MARK_NOT_FOUND)} soyut kelime işaretleniyor...")
    print(f"{'─'*60}")

    for term in MARK_NOT_FOUND:
        key = image_cache_key(term)
        delete_entry(manifest, key)
        manifest["entries"][key] = {
            "status": "not_found",
            "note": "Soyut kelime — uygun açık kaynak görsel yok.",
            "last_accessed": time.time(),
        }
        stats["marked"] += 1
        print(f"  📌 not_found: {term} (key={key})")

    save_manifest(manifest)

    # ── Özet ──────────────────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print("TAMAMLANDI")
    print(f"  ✅ Başarılı yeniden çekme : {stats.get('ok', 0)}")
    print(f"  ❌ Görsel bulunamadı      : {stats.get('not_found', 0)}")
    print(f"  ⚠  Hata                  : {stats.get('error', 0)}")
    print(f"  📌 Soyut olarak işaretlendi: {stats.get('marked', 0)}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
