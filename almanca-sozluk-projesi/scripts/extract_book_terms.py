#!/usr/bin/env python
"""Extract outline titles from the truck-technology book PDF string dump."""

from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
STRINGS_PATH = INTERIM_DIR / "nutzfahrzeugtechnik_pdf_strings.txt"
OUTPUT_PATH = INTERIM_DIR / "nutzfahrzeugtechnik_book_titles.json"


def clean_title(text: str) -> str:
    text = text.replace("\\(", "(").replace("\\)", ")")
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace("  ", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^Title\(", "", text)
    text = re.sub(r"^\d+(?:\.\d+)*\s+", "", text)
    return text.strip(" >")


def main() -> None:
    text = STRINGS_PATH.read_text(encoding="utf-8", errors="ignore")
    titles = re.findall(r"Title\((.*?)\)>>", text, flags=re.S)

    cleaned_titles: list[str] = []
    seen = set()
    for title in titles:
        title = clean_title(title)
        if not title:
            continue
        if "endobj" in title:
            title = title.split("endobj", 1)[0].strip()
        if not title or title in seen:
            continue
        seen.add(title)
        cleaned_titles.append(title)

    payload = {
        "source_file": str(STRINGS_PATH),
        "title_count": len(cleaned_titles),
        "titles": cleaned_titles,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"title_count": len(cleaned_titles), "output": str(OUTPUT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
