from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from word_image_cache import prefetch_terms
except ModuleNotFoundError:
    from scripts.word_image_cache import prefetch_terms


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICTIONARY_PATH = PROJECT_ROOT / "output" / "dictionary.json"


def load_terms() -> list[str]:
    items = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
    return [str(item.get("almanca", "")).strip() for item in items if str(item.get("almanca", "")).strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sözlük kelimeleri için Wikimedia tabanlı offline görsel cache hazırlar.")
    parser.add_argument("--max-terms", type=int, default=0, help="İlk N kelimeyi işle. 0 ise hepsi.")
    args = parser.parse_args()

    terms = load_terms()
    if args.max_terms and args.max_terms > 0:
        terms = terms[: args.max_terms]

    stats = prefetch_terms(terms)
    print(
        "İşlenen: {processed} | Başarılı: {ok} | Bulunamadı: {not_found} | Hata: {error} | Limit: {cache_full} | Kullanım: {usage_bytes} bayt".format(
            **stats
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
