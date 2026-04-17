#!/usr/bin/env python3
"""Add German phrase/pattern entries from curated lists and example sentences."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

try:
    from enrich_deep import CURATED_PHRASES
except Exception:
    CURATED_PHRASES = []


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
WIKDICT_PATH = PROJECT_ROOT / "data" / "raw" / "downloads" / "de-tr.sqlite3"
MANUAL_DIR = PROJECT_ROOT / "data" / "manual"
REPORT_PATH = MANUAL_DIR / "auto_phrase_report.json"

MIN_GENERIC_FREQ = 2
MIN_MINED_FREQ = 4
MAX_NEW_PHRASES = 800

EXACT_PHRASES = {
    "wie gesagt",
    "nach wie vor",
    "auf jeden Fall",
    "auf keinen Fall",
    "mit anderen Worten",
    "in der Regel",
    "im Allgemeinen",
    "im Grunde",
    "im Grunde genommen",
    "im Vergleich zu",
    "in diesem Zusammenhang",
    "im Hinblick auf",
    "im Rahmen von",
    "so weit wie möglich",
    "so gut wie möglich",
}

SUPPORT_NOUNS = {
    "rolle", "frage", "ausdruck", "betrieb", "einsatz", "gang", "beweis",
    "aussicht", "verbindung", "bewegung", "sprache", "druck", "anspruch",
    "kauf", "stillstand", "anwendung", "lage", "folge", "betracht",
    "schuss", "umlauf", "panne", "unfall", "eindruck", "auftrag",
    "entscheidung", "vorteil", "nachteil", "verfugung", "verfügung",
}
SUPPORT_VERBS = {
    "kommen", "bringen", "setzen", "stellen", "nehmen", "spielen", "sein",
    "haben", "machen", "finden", "geraten", "treten", "laufen",
}
MINING_END_VERBS = {
    "kommen", "bringen", "setzen", "stellen", "nehmen", "spielen",
    "haben", "machen", "finden", "geraten", "treten", "fuehren", "führen",
}
MINED_SUPPORT_NOUNS = SUPPORT_NOUNS | {
    "vorsitz", "hilfe", "ruecksicht", "rücksicht", "kenntnis", "einfluss",
    "antrag", "rede", "beschreibung", "diskussion", "vergleich", "rahmen",
}
FUNCTION_STARTERS = {
    "wie", "so", "nach", "mit", "in", "im", "am", "an", "auf", "unter", "vor",
    "zu", "zum", "zur", "vom", "beim", "ohne", "ausser", "außer",
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "einer", "eines",
}
LOWERCASE_ALWAYS = FUNCTION_STARTERS | {
    "und", "oder", "aber", "nicht", "noch", "mehr", "weniger", "als",
    "möglich", "moeglich", "gesagt", "vor", "nach", "wie",
}
BOOK_WIKI_MARKERS = ("Wikipedia DE", "Project Gutenberg")

GENERIC_PATTERNS = [
    re.compile(
        r"\b(?:eine|einen|einem|einer|der|die|das)\s+(?:[A-Za-zÄÖÜäöüß-]+\s+){0,2}"
        r"(?:Rolle|Frage|Entscheidung|Ausnahme|Verbindung|Panne|Unfall|Eindruck|Auftrag|Beweis)\s+"
        r"(?:spielen|stellen|treffen|machen|haben|geben|finden|nehmen)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:in|auf|unter|mit|nach|vor|zu|zur|zum|im|am|außer)\s+"
        r"(?:[A-Za-zÄÖÜäöüß-]+\s+){0,3}"
        r"(?:Einsatz|Betrieb|Gang|Frage|Aussicht|Verbindung|Bewegung|Sprache|Druck|"
        r"Kraft|Anspruch|Kauf|Stillstand|Ausdruck|Anwendung|Lage|Folge|Betracht|Schuss|Umlauf)\s+"
        r"(?:kommen|bringen|setzen|stellen|nehmen|sein|haben|treten|geraten)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bso\s+(?:gut|weit)\s+wie\s+möglich\b", re.IGNORECASE),
]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").casefold()
    repl = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
    for src, dst in repl.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return normalize_space(text)


def clean_phrase(text: str) -> str:
    text = normalize_space(text)
    text = text.strip(" .,;:!?\"'()[]{}")
    return normalize_space(text)


def tokenize_german(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß-]*", text)


def canonicalize_phrase_tokens(tokens: list[str]) -> str:
    cleaned = []
    for token in tokens:
        key = normalize_key(token)
        if key in LOWERCASE_ALWAYS:
            cleaned.append(token.lower())
        else:
            cleaned.append(token)
    return clean_phrase(" ".join(cleaned))


def is_clean_mining_sentence(sentence: str) -> bool:
    if not sentence:
        return False
    if len(sentence) < 12 or len(sentence) > 220:
        return False
    if any(ch.isdigit() for ch in sentence):
        return False
    if any(mark in sentence for mark in ("http", "www.", "[", "]", "{", "}", "|", "=", "/", "\\", "PHP")):
        return False
    if sentence.count(",") > 3 or sentence.count("(") > 1:
        return False
    return True


def source_allows_bulk_mining(source_names: list[str]) -> bool:
    joined = "; ".join(source_names)
    return any(marker in joined for marker in BOOK_WIKI_MARKERS)


def is_bulk_phrase_candidate(tokens: list[str]) -> bool:
    if not (2 <= len(tokens) <= 5):
        return False
    norm_tokens = [normalize_key(token) for token in tokens]
    if not norm_tokens or norm_tokens[0] not in FUNCTION_STARTERS:
        return False
    if norm_tokens[-1] not in MINING_END_VERBS:
        return False
    if any(not tok for tok in norm_tokens):
        return False
    if any(len(tok) == 1 for tok in norm_tokens if tok not in {"a", "o"}):
        return False
    if not any(normalize_key(token) in MINED_SUPPORT_NOUNS for token in tokens[:-1]):
        return False
    return True


def mine_bulk_candidates(sentence: str) -> list[tuple[str, str, str]]:
    if not is_clean_mining_sentence(sentence):
        return []

    tokens = tokenize_german(sentence)
    if len(tokens) < 2:
        return []

    results: list[tuple[str, str, str]] = []
    norm_tokens = [normalize_key(token) for token in tokens]
    for end_idx, end_norm in enumerate(norm_tokens):
        if end_norm not in MINING_END_VERBS:
            continue
        noun_positions = [
            idx for idx in range(max(0, end_idx - 3), end_idx)
            if norm_tokens[idx] in MINED_SUPPORT_NOUNS
        ]
        for noun_idx in noun_positions:
            start_idx = noun_idx
            while start_idx > 0 and (noun_idx - start_idx) < 2 and norm_tokens[start_idx - 1] in FUNCTION_STARTERS:
                start_idx -= 1
            candidate_tokens = tokens[start_idx:end_idx + 1]
            if not is_bulk_phrase_candidate(candidate_tokens):
                continue
            phrase = canonicalize_phrase_tokens(candidate_tokens)
            if phrase:
                results.append((phrase, "kalıp", "bulk-mined"))

    deduped: list[tuple[str, str, str]] = []
    seen = set()
    for phrase, pos, source_kind in results:
        key = normalize_key(phrase)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((phrase, pos, source_kind))
    return deduped


def shorten_translation(text: str) -> str:
    text = normalize_space(text)
    text = re.sub(r"^\([^)]*\)\s*", "", text)
    parts = [p.strip() for p in re.split(r"\s*\|\s*|\s*;\s*", text) if p.strip()]
    text = parts[0] if parts else text
    pieces = [p.strip() for p in text.split(",") if p.strip()]
    if len(pieces) > 3:
        text = ", ".join(pieces[:3])
    return text[:140].strip(" ,;")


def build_reference_links(phrase: str) -> dict[str, str]:
    q = urllib.parse.quote(phrase)
    return {
        "duden": f"https://www.duden.de/suchen/dudenonline/{q}",
        "dwds": f"https://www.dwds.de/wb/{q}",
        "wiktionary_de": f"https://de.wiktionary.org/wiki/{q}",
    }


def load_manual_phrase_records() -> list[dict]:
    records: list[dict] = []
    for path in sorted(MANUAL_DIR.glob("*phrases*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for record in payload.get("records") or []:
            if isinstance(record, dict) and record.get("almanca"):
                records.append(record)
    return records


def load_wikdict_index() -> dict[str, str]:
    if not WIKDICT_PATH.exists():
        return {}
    conn = sqlite3.connect(WIKDICT_PATH)
    cur = conn.cursor()
    index: dict[str, tuple[str, float]] = {}
    for written_rep, trans_list, max_score, rel_importance in cur.execute(
        "select written_rep, trans_list, max_score, rel_importance from simple_translation"
    ):
        if not written_rep or not trans_list:
            continue
        key = normalize_key(str(written_rep))
        score = float(max_score or 0) + float(rel_importance or 0)
        current = index.get(key)
        value = shorten_translation(str(trans_list))
        if not value:
            continue
        if current is None or score > current[1]:
            index[key] = (value, score)
    conn.close()
    return {key: value for key, (value, _score) in index.items()}


def split_semicolon_urls(text: str) -> list[str]:
    return [part.strip() for part in str(text or "").split(";") if part.strip()]


def split_semicolon_sources(text: str) -> list[str]:
    return [part.strip() for part in str(text or "").split(";") if part.strip()]


def extract_candidates(sentence: str, curated_map: dict[str, tuple[str, str]]) -> list[tuple[str, str, str]]:
    sentence = normalize_space(sentence)
    if not sentence:
        return []

    results: list[tuple[str, str, str]] = []
    lowered = sentence.casefold()

    for phrase in EXACT_PHRASES:
        if phrase in lowered:
            results.append((phrase, "kalıp", "exact"))

    for curated_key, (phrase, pos) in curated_map.items():
        if curated_key and curated_key in lowered:
            results.append((phrase, pos, "curated-match"))

    for pattern in GENERIC_PATTERNS:
        for match in pattern.finditer(sentence):
            phrase = clean_phrase(match.group(0))
            tokens = phrase.split()
            if not (2 <= len(tokens) <= 7):
                continue
            results.append((phrase, "kalıp", "generic"))

    deduped: list[tuple[str, str, str]] = []
    seen = set()
    for phrase, pos, source_kind in results:
        key = normalize_key(phrase)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append((phrase, pos, source_kind))
    return deduped


def seed_phrase_meta(curated_map: dict[str, tuple[str, str]], manual_records: list[dict]) -> dict[str, dict]:
    phrase_meta: dict[str, dict] = {}

    def ensure(phrase: str, pos: str, source_kind: str) -> dict:
        key = normalize_key(phrase)
        meta = phrase_meta.get(key)
        if meta is None:
            meta = {
                "almanca": phrase,
                "tur": pos,
                "translation": "",
                "freq": 0,
                "seeded": False,
                "generic_hits": 0,
                "mined_hits": 0,
                "categories": Counter(),
                "sources": set(),
                "source_urls": set(),
                "examples": [],
                "source_kinds": set(),
            }
            phrase_meta[key] = meta
        meta["source_kinds"].add(source_kind)
        return meta

    for phrase, translation, pos in CURATED_PHRASES:
        meta = ensure(phrase, pos, "curated")
        meta["seeded"] = True
        meta["translation"] = translation or meta["translation"]
        meta["sources"].add("curated-phrases")

    for phrase in EXACT_PHRASES:
        meta = ensure(phrase, "kalıp", "exact-seed")
        meta["seeded"] = True
        meta["sources"].add("exact-phrase-seed")

    for record in manual_records:
        phrase = clean_phrase(str(record.get("almanca") or ""))
        if not phrase:
            continue
        pos = str(record.get("tur") or "ifade").strip() or "ifade"
        meta = ensure(phrase, pos, "manual")
        meta["seeded"] = True
        if record.get("turkce"):
            meta["translation"] = str(record["turkce"]).strip()
        if record.get("kaynak_url"):
            meta["source_urls"].add(str(record["kaynak_url"]).strip())
        meta["sources"].add("manual-phrases")

    return phrase_meta


def build_translation_index(data: list[dict], manual_records: list[dict], wikdict_index: dict[str, str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for record in data:
        phrase = clean_phrase(str(record.get("almanca") or ""))
        translation = str(record.get("turkce") or "").strip()
        if phrase and translation:
            index[normalize_key(phrase)] = translation
    for record in manual_records:
        phrase = clean_phrase(str(record.get("almanca") or ""))
        translation = str(record.get("turkce") or "").strip()
        if phrase and translation:
            index[normalize_key(phrase)] = translation
    for phrase, translation, _pos in CURATED_PHRASES:
        if phrase and translation:
            index[normalize_key(phrase)] = translation
    for key, value in wikdict_index.items():
        if value:
            index.setdefault(key, value)
    return index


def build_entry(meta: dict, translation_index: dict[str, str]) -> dict:
    phrase = meta["almanca"]
    key = normalize_key(phrase)
    translation = meta["translation"] or translation_index.get(key, "")
    example = meta["examples"][0] if meta["examples"] else {}
    example_de = example.get("almanca", "")
    example_tr = example.get("turkce", "")
    source_names = sorted(meta["sources"]) or ["kalip-cikarim"]
    source_urls = sorted(meta["source_urls"])
    note_parts = ["Örnek cümlelerden ve mevcut kalıp listelerinden otomatik çıkarılan Almanca söz öbeği."]
    if not translation:
        note_parts.append("Açık kaynakta güvenilir Türkçe karşılık bulunamadı; alan bilinçli olarak boş bırakıldı.")

    entry = {
        "aciklama_turkce": "",
        "almanca": phrase,
        "artikel": "",
        "bilesen_kelimeler": [],
        "ceviri_durumu": "kaynak-izli" if translation else "eksik",
        "ceviri_inceleme_notu": "",
        "ceviri_kaynaklari": [],
        "cogul": "",
        "esanlamlilar": [],
        "genitiv_endung": "",
        "ilgili_kayitlar": [],
        "kategoriler": [name for name, _count in meta["categories"].most_common(3)],
        "kaynak": "; ".join(source_names),
        "kaynak_url": "; ".join(source_urls),
        "kelime_ailesi": [],
        "not": " ".join(note_parts),
        "ornek_almanca": example_de,
        "ornek_turkce": example_tr if example_de else "",
        "ornekler": [{"almanca": example_de, "turkce": example_tr}] if example_de else [],
        "referans_linkler": build_reference_links(phrase),
        "seviye": "",
        "sinonim": [],
        "tanim_almanca": "",
        "telaffuz": "",
        "tur": meta["tur"],
        "turkce": translation,
        "verb_typ": "",
        "zipf_skoru": 0.0,
        "zit_anlamlilar": [],
    }
    return entry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dict-path", type=Path, default=DICT_PATH)
    parser.add_argument("--report-path", type=Path, default=REPORT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dict_path = args.dict_path
    report_path = args.report_path
    data = json.loads(dict_path.read_text(encoding="utf-8"))
    existing_keys = {normalize_key(str(record.get("almanca") or "")) for record in data if record.get("almanca")}

    manual_records = load_manual_phrase_records()
    wikdict_index = load_wikdict_index()
    translation_index = build_translation_index(data, manual_records, wikdict_index)
    curated_map = {
        phrase.casefold(): (phrase, pos)
        for phrase, _translation, pos in CURATED_PHRASES
    }
    phrase_meta = seed_phrase_meta(curated_map, manual_records)

    for record in data:
        categories = record.get("kategoriler") or []
        source_names = split_semicolon_sources(record.get("kaynak") or "")
        source_urls = split_semicolon_urls(record.get("kaynak_url") or "")
        sentence_pairs = []

        if (record.get("ornek_almanca") or "").strip():
            sentence_pairs.append(
                {
                    "almanca": str(record.get("ornek_almanca") or "").strip(),
                    "turkce": str(record.get("ornek_turkce") or "").strip(),
                }
            )
        for example in record.get("ornekler") or []:
            if not isinstance(example, dict):
                continue
            de = str(example.get("almanca") or "").strip()
            tr = str(example.get("turkce") or "").strip()
            if de:
                sentence_pairs.append({"almanca": de, "turkce": tr})

        for pair in sentence_pairs:
            for phrase, pos, source_kind in extract_candidates(pair["almanca"], curated_map):
                key = normalize_key(phrase)
                meta = phrase_meta.setdefault(
                    key,
                    {
                        "almanca": phrase,
                        "tur": pos,
                        "translation": translation_index.get(key, ""),
                        "freq": 0,
                        "seeded": False,
                        "generic_hits": 0,
                        "mined_hits": 0,
                        "categories": Counter(),
                        "sources": set(),
                        "source_urls": set(),
                        "examples": [],
                        "source_kinds": set(),
                    },
                )
                meta["freq"] += 1
                meta["tur"] = meta["tur"] or pos
                meta["categories"].update([str(cat) for cat in categories if cat])
                meta["sources"].update(source_names or ["kalip-cikarim"])
                meta["source_urls"].update(source_urls)
                meta["source_kinds"].add(source_kind)
                if source_kind == "generic":
                    meta["generic_hits"] += 1
                if source_kind == "bulk-mined":
                    meta["mined_hits"] += 1
                if pair["almanca"] and len(meta["examples"]) < 3:
                    meta["examples"].append(pair)

            if source_allows_bulk_mining(source_names):
                for phrase, pos, source_kind in mine_bulk_candidates(pair["almanca"]):
                    key = normalize_key(phrase)
                    meta = phrase_meta.setdefault(
                        key,
                        {
                            "almanca": phrase,
                            "tur": pos,
                            "translation": translation_index.get(key, ""),
                            "freq": 0,
                            "seeded": False,
                            "generic_hits": 0,
                            "mined_hits": 0,
                            "categories": Counter(),
                            "sources": set(),
                            "source_urls": set(),
                            "examples": [],
                            "source_kinds": set(),
                        },
                    )
                    meta["freq"] += 1
                    meta["mined_hits"] += 1
                    meta["tur"] = meta["tur"] or pos
                    meta["categories"].update([str(cat) for cat in categories if cat])
                    meta["sources"].update(source_names or ["kalip-cikarim"])
                    meta["source_urls"].update(source_urls)
                    meta["source_kinds"].add(source_kind)
                    if pair["almanca"] and len(meta["examples"]) < 3:
                        meta["examples"].append(pair)

    new_entries = []
    for key, meta in phrase_meta.items():
        if key in existing_keys:
            continue
        include = (
            meta["seeded"]
            or meta["generic_hits"] >= MIN_GENERIC_FREQ
            or meta["mined_hits"] >= MIN_MINED_FREQ
            or "exact" in meta["source_kinds"]
        )
        if not include:
            continue
        new_entries.append(build_entry(meta, translation_index))

    new_entries.sort(key=lambda item: (item["tur"], normalize_key(item["almanca"])))
    if len(new_entries) > MAX_NEW_PHRASES:
        new_entries = new_entries[:MAX_NEW_PHRASES]

    data.extend(new_entries)
    dict_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    report = {
        "new_entries": len(new_entries),
        "seeded_entries": sum(1 for meta in phrase_meta.values() if meta["seeded"]),
        "bulk_mined_entries": sum(1 for entry in new_entries if "Project Gutenberg" in entry["kaynak"] or "Wikipedia DE" in entry["kaynak"]),
        "blank_translations": sum(1 for entry in new_entries if not (entry.get("turkce") or "").strip()),
        "with_translations": sum(1 for entry in new_entries if (entry.get("turkce") or "").strip()),
        "sample": [
            {
                "almanca": entry["almanca"],
                "turkce": entry["turkce"],
                "tur": entry["tur"],
            }
            for entry in new_entries[:30]
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
