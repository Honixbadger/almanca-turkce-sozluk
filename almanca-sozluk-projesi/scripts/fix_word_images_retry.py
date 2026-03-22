"""
fix_word_images_retry.py
------------------------
Rate-limit nedeniyle başarısız olan görselleri 3 saniyelik aralıklarla yeniden dener.
Kobalt için İngilizce Wikipedia'ya fallback yapar.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in {"utf-8", "utf-8-sig"}:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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

# Yeniden denenecek kelimeler: (orijinal_kelime, doğru_wikipedia_başlığı, lang)
# lang: "de" veya "en" (kobalt için "en" kullan — Almanca sayfa pageimage'sız)
RETRY_MAP: list[tuple[str, str, str]] = [
    ("kobalt",            "Cobalt",                    "en"),
    ("motordrehmoment",   "Drehmoment",                "de"),
    ("lift",              "Aufzugsanlage",              "de"),
    ("systemrechner",     "Steuergerät (Kraftfahrzeug)", "de"),
    ("agenda",            "Tagesordnung",              "de"),
    ("dauer",             "Dauer",                     "de"),
    ("teil",              "Bauteil (Technik)",          "de"),
    ("wahlbar",           "Wahlrecht",                 "de"),
    ("lenkbarkeit",       "Servolenkung",              "de"),
    ("hdi",               "Common Rail",               "de"),
    ("abendland",         "Abendland",                 "de"),
    ("anteil",            "Aktie",                     "de"),
]

SLEEP_BETWEEN = 3.0  # saniye


def delete_entry(manifest: dict, key: str) -> None:
    entry = manifest["entries"].get(key)
    if entry and entry.get("status") != "not_found":
        file_name = entry.get("file_name", "")
        if file_name:
            img_path = WORD_IMAGE_CACHE_DIR / file_name
            if img_path.exists():
                img_path.unlink()
                print(f"  🗑  Silindi: {file_name}")
        manifest["entries"].pop(key, None)


def refetch(manifest: dict, term: str, correct_title: str, lang: str) -> str:
    key = image_cache_key(term)
    page = (
        fetch_exact_page(correct_title, lang)
        or search_page(correct_title, lang)
        or fetch_exact_page(correct_title, "en" if lang == "de" else "de")
        or search_page(correct_title, "en" if lang == "de" else "de")
    )
    if not page:
        manifest["entries"][key] = {
            "status": "not_found",
            "note": f"'{correct_title}' için Wikipedia görseli bulunamadı.",
            "last_accessed": time.time(),
        }
        return "not_found"

    file_name = str(page.get("pageimage", "")).strip()
    file_info = fetch_commons_file_info(file_name)
    if not file_info or not file_info.get("thumburl"):
        manifest["entries"][key] = {
            "status": "not_found",
            "note": "Sayfa bulundu ama önizleme URL'si alınamadı.",
            "last_accessed": time.time(),
        }
        return "not_found"

    time.sleep(1.0)  # Commons API çağrısından sonra da bekle
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
    stats = {"ok": 0, "not_found": 0, "error": 0}

    print(f"\n{'─'*60}")
    print(f"Yeniden deneme: {len(RETRY_MAP)} kelime ({SLEEP_BETWEEN}s aralıkla)")
    print(f"{'─'*60}\n")

    for i, (term, correct_title, lang) in enumerate(RETRY_MAP):
        key = image_cache_key(term)
        print(f"[{i+1}/{len(RETRY_MAP)}] {term} → '{correct_title}' ({lang}.wikipedia)")

        # Önceki hatalı kaydı temizle
        delete_entry(manifest, key)

        result = refetch(manifest, term, correct_title, lang)
        stats[result] = stats.get(result, 0) + 1

        entry = manifest["entries"].get(key, {})
        if result == "ok":
            print(f"  ✅ OK — sayfa: {entry.get('page_title')} | dosya: {entry.get('file_name')}")
        else:
            print(f"  ❌ {result.upper()} — {entry.get('note', '')}")

        save_manifest(manifest)

        if i < len(RETRY_MAP) - 1:
            print(f"  ⏱  {SLEEP_BETWEEN}s bekleniyor...")
            time.sleep(SLEEP_BETWEEN)

    print(f"\n{'═'*60}")
    print("RETRY TAMAMLANDI")
    print(f"  ✅ Başarılı : {stats.get('ok', 0)}")
    print(f"  ❌ Bulunamadı: {stats.get('not_found', 0)}")
    print(f"  ⚠  Hata    : {stats.get('error', 0)}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
