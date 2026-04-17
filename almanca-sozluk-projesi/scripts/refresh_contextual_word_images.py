from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from word_image_cache import ensure_word_image_cached, image_cache_key, load_manifest, manifest_entry_is_relevant, save_manifest
except ModuleNotFoundError:
    from scripts.word_image_cache import ensure_word_image_cached, image_cache_key, load_manifest, manifest_entry_is_relevant, save_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICTIONARY_PATH = PROJECT_ROOT / "output" / "dictionary.json"


def load_dictionary() -> list[dict]:
    return json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))


def build_record_index(records: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for record in records:
        term = str(record.get("almanca", "") or "").strip()
        if not term:
            continue
        key = image_cache_key(term)
        if key in index:
            continue
        index[key] = {
            "tur": record.get("tur", ""),
            "turkce": record.get("turkce", ""),
            "tanim_almanca": record.get("tanim_almanca", ""),
            "aciklama_turkce": record.get("aciklama_turkce", ""),
            "kategoriler": record.get("kategoriler") or [],
            "gorsel_grubu": record.get("gorsel_grubu", ""),
            "gorsel_ipucu": record.get("gorsel_ipucu", ""),
            "gorsel_notu": record.get("gorsel_notu", ""),
            "term": term,
        }
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description="Bağlama göre düşük güvenli kelime görsellerini yeniler.")
    parser.add_argument("--limit", type=int, default=0, help="İlk N şüpheli kaydı işle. 0 ise hepsi.")
    parser.add_argument("--refresh-all", action="store_true", help="Sadece şüphelileri değil tüm mevcut görselleri yeniden dene.")
    args = parser.parse_args()

    records = load_dictionary()
    record_index = build_record_index(records)
    manifest = load_manifest()
    entries = manifest.get("entries", {})

    suspicious: list[tuple[str, dict, dict]] = []
    for key, entry in entries.items():
        if entry.get("status") != "ok":
            continue
        context = record_index.get(key)
        if not context:
            continue
        if args.refresh_all or not manifest_entry_is_relevant(context["term"], entry, context):
            suspicious.append((key, entry, context))

    if args.limit and args.limit > 0:
        suspicious = suspicious[: args.limit]

    stats = {"processed": 0, "refreshed": 0, "not_found": 0, "error": 0}
    for key, _entry, context in suspicious:
        try:
            payload = ensure_word_image_cached(context["term"], context=context, force_refresh=True)
        except Exception:
            stats["error"] += 1
            stats["processed"] += 1
            continue
        stats["processed"] += 1
        if payload.get("status") == "ok":
            stats["refreshed"] += 1
        elif payload.get("status") == "not_found":
            stats["not_found"] += 1
        manifest = load_manifest()
        save_manifest(manifest)

    print(
        "Supheli: {processed} | Yenilenen: {refreshed} | Not found: {not_found} | Hata: {error}".format(
            **stats
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
