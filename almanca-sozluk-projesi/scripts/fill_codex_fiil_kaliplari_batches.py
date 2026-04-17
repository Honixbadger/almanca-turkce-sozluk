#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from enrich_verb_usage import (  # noqa: E402
    VERB_POS,
    collect_known_forms,
    compact,
    keep_existing_pattern,
    load_dewiktionary_verbs,
    normalize,
)


BATCH_GLOB = "fiil_kaliplari_batch_*.json"
CODEX_DIR = PROJECT_ROOT / "output" / "codex"
DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
DEWIKT_PATH = PROJECT_ROOT / "data" / "raw" / "downloads" / "dewiktionary.gz"
DWDS_CACHE_DIR = PROJECT_ROOT / "output" / "dwds_wp_cache"
REPORT_PATH = PROJECT_ROOT / "output" / "codex" / "fiil_kaliplari_fill_report.json"

WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß'-]+")
PREP_TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß'-]+|[.,;:!?()]")

PREP_ALIAS = {
    "an": "an",
    "am": "an",
    "ans": "an",
    "auf": "auf",
    "aufs": "auf",
    "aus": "aus",
    "bei": "bei",
    "beim": "bei",
    "für": "für",
    "fur": "für",
    "gegen": "gegen",
    "im": "in",
    "in": "in",
    "ins": "in",
    "mit": "mit",
    "nach": "nach",
    "über": "über",
    "uber": "über",
    "um": "um",
    "ums": "um",
    "unter": "unter",
    "unterm": "unter",
    "von": "von",
    "vom": "von",
    "vor": "vor",
    "vorm": "vor",
    "zu": "zu",
    "zum": "zu",
    "zur": "zu",
}
FIXED_PREP_CASE = {
    "aus": "D",
    "bei": "D",
    "für": "A",
    "gegen": "A",
    "mit": "D",
    "nach": "D",
    "um": "A",
    "von": "D",
    "zu": "D",
}
TWO_WAY_PREPS = {"an", "auf", "in", "über", "unter", "vor"}
CONTRACTION_CASE = {
    "am": ("an", "D"),
    "ans": ("an", "A"),
    "aufs": ("auf", "A"),
    "beim": ("bei", "D"),
    "im": ("in", "D"),
    "ins": ("in", "A"),
    "ums": ("um", "A"),
    "unterm": ("unter", "D"),
    "vom": ("von", "D"),
    "vorm": ("vor", "D"),
    "zum": ("zu", "D"),
    "zur": ("zu", "D"),
}
PERSON_HINTS = {
    "mir",
    "dir",
    "ihm",
    "ihr",
    "ihnen",
    "uns",
    "euch",
    "mich",
    "dich",
    "ihn",
    "sie",
    "einer",
    "einem",
    "seiner",
    "ihrer",
    "meiner",
    "deiner",
    "unserer",
    "eurer",
}
TR_PLACEHOLDERS = {
    "jd.": "biri",
    "jdn.": "birini",
    "jdm.": "birine",
    "etw.(A)": "bir şeyi",
    "etw.(D)": "bir şeye",
    "irgendwo": "bir yerde",
    "irgendwohin": "bir yere",
}
TR_PREP = {
    "an": "bir şeye",
    "auf": "bir şeye",
    "aus": "bir şeyden",
    "bei": "bir yerde",
    "für": "bir şey için",
    "gegen": "bir şeye karşı",
    "in": "bir yerde",
    "mit": "biriyle",
    "nach": "bir şeye",
    "über": "bir şey hakkında",
    "um": "bir şey için",
    "unter": "bir şey altında",
    "von": "bir şeyden",
    "vor": "bir şeyin önünde",
    "zu": "bir şeye",
}
SPECIAL_PREFIX_TR = {
    "an land": "karada",
    "gegen den strom": "akıma karşı",
    "im exil": "sürgünde",
    "im mai": "mayısta",
    "im parkhaus": "otoparkta",
    "im stau": "trafikte",
    "im wald": "ormanda",
    "mit der zeit": "zamanla",
    "mit licht": "ışıkla",
    "nach hause": "eve",
    "per anhalter": "otostopla",
    "zu hause": "evde",
}
ARTICLE_HINTS = {
    "dem": "D",
    "der": "D",
    "einem": "D",
    "einer": "D",
    "den": "A",
    "das": "A",
    "die": "A",
    "einen": "A",
    "eine": "A",
}
LOWER_ALLOWED = {
    "der",
    "die",
    "das",
    "den",
    "dem",
    "des",
    "ein",
    "eine",
    "einen",
    "einem",
    "einer",
    "mein",
    "meine",
    "meinen",
    "meinem",
    "meiner",
    "dein",
    "deine",
    "deinen",
    "deinem",
    "deiner",
    "sein",
    "seine",
    "seinen",
    "seinem",
    "seiner",
    "ihr",
    "ihre",
    "ihren",
    "ihrem",
    "ihrer",
    "unser",
    "unsere",
    "unseren",
    "unserem",
    "unserer",
    "euer",
    "eure",
    "euren",
    "eurem",
    "eurer",
    "hause",
}
LOCATIVE_HINTS = {
    "wohnen",
    "leben",
    "parken",
    "stehen",
    "liegen",
    "sitzen",
    "wachsen",
    "reifen",
    "bleiben",
    "verweilen",
}


def load_prep_db() -> dict[str, list[tuple]]:
    path = SCRIPT_DIR / "enrich_verben_mit_praepositionen.py"
    spec = importlib.util.spec_from_file_location("prepdb", path)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lookup: dict[str, list[tuple]] = {}
    for row in getattr(module, "PATTERNS", []):
        lemma = compact(row[0] if len(row) > 0 else "")
        if not lemma:
            continue
        lookup.setdefault(lemma, []).append(row)
    return lookup


def split_turkish_options(text: str) -> list[str]:
    value = compact(text)
    if not value:
        return []
    parts = re.split(r"[;\n/]|, (?=[a-zçğıöşü])", value)
    cleaned = []
    for part in parts:
        if "->" in part:
            part = compact(part.split("->")[-1])
        part = compact(re.sub(r"\([^)]*\)", "", part))
        if not part:
            continue
        if part not in cleaned:
            cleaned.append(part)
    return cleaned


def looks_verbish_tr(text: str) -> bool:
    value = compact(text).casefold()
    if not value:
        return False
    if any(value.endswith(suffix) for suffix in ("mak", "mek")):
        return True
    if " etmek" in value or " olmak" in value or " kalmak" in value:
        return True
    return False


def choose_base_turkish(record: dict, pattern: str, sense_index: int | None = None) -> str:
    candidates: list[str] = []
    if pattern_starts_with_object(pattern):
        candidates.extend(split_turkish_options(record.get("aciklama_turkce") or ""))
    if sense_index is not None:
        anlamlar = record.get("anlamlar") or []
        if isinstance(anlamlar, list) and sense_index < len(anlamlar) and isinstance(anlamlar[sense_index], dict):
            candidates.extend(split_turkish_options(anlamlar[sense_index].get("turkce") or ""))
            candidates.extend(split_turkish_options(anlamlar[sense_index].get("aciklama_turkce") or ""))
        if isinstance(anlamlar, list):
            for item in anlamlar:
                if isinstance(item, dict):
                    extras = split_turkish_options(item.get("turkce") or "")
                    if extras:
                        candidates.extend(extras)
                        break
    candidates.extend(split_turkish_options(record.get("turkce") or ""))
    if not pattern_starts_with_object(pattern):
        candidates.extend(split_turkish_options(record.get("aciklama_turkce") or ""))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = normalize(item)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    if not deduped:
        return "kullanmak"
    verbish = [item for item in deduped if looks_verbish_tr(item)]
    if pattern_starts_with_prep(pattern) and len(verbish) > 1:
        return verbish[0]
    if pattern_starts_with_object(pattern):
        for item in deduped:
            if looks_verbish_tr(item):
                return item
    return (verbish or deduped)[0]


def normalize_pattern(text: str) -> str:
    value = compact(text)
    if not value:
        return ""
    value = value.replace("etw. (A)", "etw.(A)")
    value = value.replace("etw. (D)", "etw.(D)")
    value = value.replace("etw./jdn. (A)", "etw./jdn.(A)")
    value = value.replace("etw./jdm. (D)", "etw./jdm.(D)")
    value = value.replace("jdn./etw. (A)", "jdn./etw.(A)")
    value = value.replace("jdm./etw. (D)", "jdm./etw.(D)")
    value = re.sub(r"\s+\(A\)", "(A)", value)
    value = re.sub(r"\s+\(D\)", "(D)", value)
    return compact(value)


def pattern_starts_with_object(pattern: str) -> bool:
    return pattern.startswith(("jdn. ", "jdm. ", "etw.(A) ", "jd. "))


def pattern_starts_with_prep(pattern: str) -> bool:
    first = compact(pattern).split(" ", 1)[0]
    return normalize(first) in PREP_ALIAS or first in {"irgendwo", "irgendwohin"} or pattern.startswith("sich ")


def word_tokens(text: str) -> list[str]:
    return [token for token in WORD_RE.findall(str(text or "")) if compact(token)]


def add_candidate(store: dict[str, dict], phrase: str, score: int, source: str, record: dict, *, translation: str = "", sense_index: int | None = None) -> None:
    phrase = normalize_pattern(phrase)
    if not phrase or "," in phrase or len(phrase) > 96:
        return
    key = normalize(phrase)
    if not key:
        return
    existing = store.get(key)
    payload = {
        "kalip": phrase,
        "score": score,
        "source": source,
        "sense_index": sense_index,
        "turkce": compact(translation) if compact(translation) else "",
    }
    if existing is None or score > existing["score"] or (score == existing["score"] and compact(translation) and not existing["turkce"]):
        store[key] = payload


def extract_start_slots(text: str) -> dict[str, bool]:
    tokens = [normalize(token) for token in word_tokens(text)]
    flags = {"reflexive": False, "jdm": False, "jdn": False, "etw": False}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "sich":
            flags["reflexive"] = True
            index += 1
            continue
        if token == "jemandem":
            flags["jdm"] = True
            index += 1
            continue
        if token == "jemanden":
            flags["jdn"] = True
            index += 1
            continue
        if token == "etwas":
            next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
            if flags["jdm"] or flags["jdn"] or next_token in PREP_ALIAS or next_token in {"als", "zu"}:
                flags["etw"] = True
            index += 1
            continue
        break
    return flags


def extract_flags_from_texts(texts: list[str], tags: list[str]) -> dict[str, bool]:
    norm_text = " ".join(normalize(text) for text in texts if compact(text))
    tag_set = {normalize(tag) for tag in tags if compact(tag)}
    start_flags = {"reflexive": False, "jdm": False, "jdn": False, "etw": False}
    for text in texts:
        row = extract_start_slots(text)
        for key, value in row.items():
            start_flags[key] = start_flags[key] or value
    return {
        "transitive": "transitive" in tag_set or "transitiv" in norm_text,
        "intransitive": "intransitive" in tag_set or "intransitiv" in norm_text,
        "reflexive": "reflexive" in tag_set or "reflexiv" in tag_set,
        "jdm": start_flags["jdm"],
        "jdn": start_flags["jdn"],
        "etw": start_flags["etw"],
    }


def fixed_prep_from_tokens(tokens: list[str]) -> list[str]:
    found: list[str] = []
    for index, token in enumerate(tokens[:-1]):
        if index >= 4:
            break
        prep = PREP_ALIAS.get(token)
        if prep not in FIXED_PREP_CASE:
            continue
        probe = tokens[index + 1:index + 3]
        if not probe:
            continue
        if len(probe) > 1 and probe[0] == "jemandem" and probe[1] == "etwas":
            found.append(f"{prep} etw.({FIXED_PREP_CASE[prep]})")
        elif probe[0] == "jemandem":
            found.append(f"{prep} jdm.")
        elif probe[0] == "jemanden":
            found.append(f"{prep} jdn.")
        elif probe[0] == "jemand":
            found.append(f"{prep} {'jdm.' if FIXED_PREP_CASE[prep] == 'D' else 'jdn.'}")
        elif probe[0] == "etwas":
            found.append(f"{prep} etw.({FIXED_PREP_CASE[prep]})")
    return found


def generic_from_phrase(phrase: str) -> str:
    words = word_tokens(phrase)
    if len(words) < 2:
        return ""
    first_norm = normalize(words[0])
    if first_norm in CONTRACTION_CASE:
        prep, case_name = CONTRACTION_CASE[first_norm]
        slot = "jdm." if any(normalize(word) in PERSON_HINTS for word in words[1:]) else f"etw.({case_name})"
        return f"{prep} {slot}"
    prep = PREP_ALIAS.get(first_norm)
    if prep in FIXED_PREP_CASE:
        case_name = FIXED_PREP_CASE[prep]
        slot = "jdm." if any(normalize(word) in PERSON_HINTS for word in words[1:]) else f"etw.({case_name})"
        return f"{prep} {slot}"
    if prep in TWO_WAY_PREPS:
        case_name = ""
        for word in words[1:3]:
            case_name = ARTICLE_HINTS.get(normalize(word), "")
            if case_name:
                break
        if case_name:
            return f"{prep} etw.({case_name})"
    return ""


def clean_exact_phrase(phrase: str) -> str:
    words = word_tokens(phrase)
    if len(words) < 2:
        return ""
    kept = [words[0]]
    has_content = False
    for word in words[1:]:
        norm_word = normalize(word)
        if norm_word in LOWER_ALLOWED or word[:1].isupper():
            kept.append(word)
            if word[:1].isupper():
                has_content = True
            continue
        break
    if len(kept) < 2 or not has_content:
        return ""
    return compact(" ".join(kept))


def exact_phrase_candidates(example: str, forms: set[str]) -> list[str]:
    plain_words = [token for token in word_tokens(example) if compact(token)]
    lowered = [normalize(token) for token in plain_words]
    positions = [idx for idx, token in enumerate(lowered) if token in forms]
    if not positions:
        return []
    phrases: list[str] = []
    for pos in positions:
        left_start = max(0, pos - 4)
        for idx in range(left_start, pos):
            norm = lowered[idx]
            if norm not in PREP_ALIAS:
                continue
            phrase_words = plain_words[idx:pos]
            if 1 < len(phrase_words) <= 4:
                phrases.append(" ".join(phrase_words))
        right_end = min(len(plain_words), pos + 5)
        for idx in range(pos + 1, right_end):
            norm = lowered[idx]
            if norm not in PREP_ALIAS:
                continue
            phrase_words = plain_words[idx:min(len(plain_words), idx + 3)]
            if 1 < len(phrase_words) <= 4:
                phrases.append(" ".join(phrase_words))
    ordered: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        key = normalize(phrase)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(phrase)
    return ordered


def looks_locative_phrase(phrase: str) -> bool:
    first = normalize(compact(phrase).split(" ", 1)[0])
    return PREP_ALIAS.get(first) in {"an", "auf", "bei", "in", "unter", "vor"}


def extract_exact_and_generic_patterns(lemma: str, examples: list[str], forms: set[str], store: dict[str, dict], record: dict, sense_index: int | None = None) -> None:
    locative_hits = 0
    for example in examples:
        for phrase in exact_phrase_candidates(example, forms):
            phrase = clean_exact_phrase(phrase)
            if not phrase:
                continue
            add_candidate(store, f"{phrase} {lemma}", 76, "example-exact", record, sense_index=sense_index)
            if looks_locative_phrase(phrase):
                locative_hits += 1
    if locative_hits >= 1 and normalize(lemma) in {normalize(item) for item in LOCATIVE_HINTS}:
        add_candidate(store, f"irgendwo {lemma}", 80, "locative-fallback", record, sense_index=sense_index)


def add_core_patterns(lemma: str, record: dict, texts: list[str], tags: list[str], store: dict[str, dict], sense_index: int | None = None) -> None:
    flags = extract_flags_from_texts(texts, tags)
    token_stream = []
    for text in texts:
        token_stream.extend(normalize(token) for token in word_tokens(text))
    prep_slots = fixed_prep_from_tokens(token_stream)
    if flags["reflexive"]:
        add_candidate(store, f"sich {lemma}", 88, "reflexive", record, sense_index=sense_index)
    if flags["jdm"] and flags["etw"]:
        add_candidate(store, f"jdm. etw.(A) {lemma}", 92, "gloss-core", record, sense_index=sense_index)
    if flags["jdm"]:
        add_candidate(store, f"jdm. {lemma}", 86, "gloss-core", record, sense_index=sense_index)
    if flags["jdn"]:
        add_candidate(store, f"jdn. {lemma}", 86, "gloss-core", record, sense_index=sense_index)
    if flags["etw"] or flags["transitive"]:
        add_candidate(store, f"etw.(A) {lemma}", 82, "gloss-core", record, sense_index=sense_index)
    if flags["intransitive"] and normalize(lemma) not in {normalize(item) for item in LOCATIVE_HINTS}:
        add_candidate(store, lemma, 55, "intransitive-fallback", record, sense_index=sense_index)
    for slot in prep_slots:
        add_candidate(store, f"{slot} {lemma}", 90, "gloss-prep", record, sense_index=sense_index)
        if flags["jdn"] and not slot.startswith(("jdn.", "jdm.", "etw.")):
            add_candidate(store, f"jdn. {slot} {lemma}", 91, "gloss-prep", record, sense_index=sense_index)
        if flags["jdm"] and not flags["jdn"] and not slot.startswith(("jdn.", "jdm.", "etw.")):
            add_candidate(store, f"jdm. {slot} {lemma}", 91, "gloss-prep", record, sense_index=sense_index)


def build_sense_rows(record: dict, dewikt_entry: dict | None) -> list[dict]:
    rows: list[dict] = []
    if dewikt_entry:
        for index, sense in enumerate(dewikt_entry.get("senses") or []):
            rows.append(
                {
                    "sense_index": index,
                    "texts": [compact(text) for text in (sense.get("glosses") or []) + (sense.get("raw_glosses") or []) if compact(text)],
                    "examples": [compact(item.get("text") or "") for item in (sense.get("examples") or []) if isinstance(item, dict) and compact(item.get("text") or "")],
                    "tags": [str(tag) for tag in (sense.get("tags") or [])],
                }
            )
        return rows
    for index, sense in enumerate(record.get("anlamlar") or []):
        if not isinstance(sense, dict):
            continue
        texts = [compact(sense.get("tanim_almanca") or ""), compact(sense.get("aciklama_turkce") or "")]
        examples = []
        for item in sense.get("ornekler") or []:
            if isinstance(item, dict) and compact(item.get("almanca") or ""):
                examples.append(compact(item.get("almanca") or ""))
        rows.append(
            {
                "sense_index": index,
                "texts": [text for text in texts if text],
                "examples": examples,
                "tags": [str(tag) for tag in (sense.get("etiketler") or [])],
            }
        )
    return rows


def fetch_dwds_wp_html(lemma: str, *, refresh: bool = False, delay: float = 0.0) -> str:
    DWDS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = DWDS_CACHE_DIR / f"{urllib.parse.quote(lemma, safe='')}.html"
    if cache_path.exists() and not refresh:
        return cache_path.read_text(encoding="utf-8", errors="replace")
    url = f"https://www.dwds.de/wp/{urllib.parse.quote(lemma, safe='')}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8", errors="replace")
    cache_path.write_text(payload, encoding="utf-8")
    if delay > 0:
        time.sleep(delay)
    return payload


def parse_dwds_wp(html_text: str) -> dict[str, list[str]]:
    tables: dict[str, list[str]] = {}
    for code, body in re.findall(r'<table[^>]+id="wp-rel-[^"]+-Verb-(OBJ|OBJO|PP)"[^>]*>.*?<tbody>(.*?)</tbody>', html_text, re.S):
        items: list[str] = []
        for lemma in re.findall(r'title="Lemma: ([^;"]+);', body):
            value = compact(html.unescape(lemma))
            if value:
                items.append(value)
        tables[code] = items
    return tables


def add_dwds_fallbacks(lemma: str, record: dict, store: dict[str, dict], *, refresh: bool = False) -> None:
    try:
        html_text = fetch_dwds_wp_html(lemma, refresh=refresh)
    except Exception:
        return
    tables = parse_dwds_wp(html_text)
    existing = [item["kalip"] for item in store.values()]
    if tables.get("OBJ") and not any(pattern_starts_with_object(item) for item in existing):
        add_candidate(store, f"etw.(A) {lemma}", 72, "dwds-obj", record)
    if tables.get("OBJO") and not any(item.startswith(("jdm. ", "jdm. etw.(A)")) for item in existing):
        add_candidate(store, f"jdm. {lemma}", 70, "dwds-objo", record)
    for phrase in (tables.get("PP") or [])[:3]:
        add_candidate(store, f"{phrase} {lemma}", 68, "dwds-pp-exact", record)


def diversity_key(pattern: str) -> str:
    if pattern.startswith("sich "):
        tokens = pattern.split()
        if len(tokens) >= 3 and normalize(tokens[1]) in PREP_ALIAS:
            return f"refl:{PREP_ALIAS[normalize(tokens[1])]}"
        return "refl"
    if pattern.startswith("jdm. etw.(A) "):
        return "ditransitive"
    if pattern.startswith(("jdn. ", "jdm. ", "etw.(A) ", "jd. ")):
        bits = pattern.split()
        if len(bits) >= 2 and normalize(bits[1]) in PREP_ALIAS:
            return f"obj+prep:{PREP_ALIAS[normalize(bits[1])]}"
        return bits[0]
    first = normalize(pattern.split(" ", 1)[0])
    if first in PREP_ALIAS:
        return f"prep:{PREP_ALIAS[first]}"
    if first in {"irgendwo", "irgendwohin"}:
        return first
    return "bare"


def get_translator():
    try:
        import argostranslate.translate  # type: ignore
    except Exception:
        return None
    try:
        langs = argostranslate.translate.get_installed_languages()
        src = next(item for item in langs if item.code == "de")
        dst = next(item for item in langs if item.code == "tr")
        return src.get_translation(dst)
    except Exception:
        return None


def translate_prefix(prefix: str, translator, cache: dict[str, str]) -> str:
    clean = compact(prefix)
    if not clean:
        return ""
    key = normalize(clean)
    if key in cache:
        return cache[key]
    if translator is None:
        cache[key] = ""
        return ""
    try:
        value = compact(translator.translate(clean))
    except Exception:
        value = ""
    cache[key] = value
    return value


def translation_looks_bad(text: str) -> bool:
    value = compact(text)
    if not value:
        return True
    if "?" in value:
        return True
    tokens = [token.casefold() for token in value.split()]
    if not tokens:
        return True
    most_common = Counter(tokens).most_common(1)[0][1]
    if most_common >= 3:
        return True
    if any(token in {"home", "from"} for token in tokens):
        return True
    return False


def fallback_exact_prefix(prefix: str) -> str:
    norm_prefix = normalize(prefix)
    if norm_prefix in SPECIAL_PREFIX_TR:
        return SPECIAL_PREFIX_TR[norm_prefix]
    words = word_tokens(prefix)
    if len(words) < 1:
        return ""
    first_norm = normalize(words[0])
    prep = ""
    case_name = ""
    if first_norm in CONTRACTION_CASE:
        prep, case_name = CONTRACTION_CASE[first_norm]
    else:
        prep = PREP_ALIAS.get(first_norm, "")
        if prep in FIXED_PREP_CASE:
            case_name = FIXED_PREP_CASE[prep]
        elif prep in TWO_WAY_PREPS:
            for word in words[1:3]:
                case_name = ARTICLE_HINTS.get(normalize(word), "")
                if case_name:
                    break
    if prep == "nach":
        return "bir yere"
    if prep == "zu":
        return "bir yere"
    if prep in {"an", "auf", "bei", "in", "unter", "vor"}:
        return "bir yere" if case_name == "A" else "bir yerde"
    if prep == "von":
        return "bir şeyden"
    if prep == "mit":
        return "bir şeyle"
    if prep == "für":
        return "bir şey için"
    if prep == "gegen":
        return "bir şeye karşı"
    if prep == "über":
        return "bir şey hakkında"
    if prep == "um":
        return "bir şey için"
    if prep == "aus":
        return "bir şeyden"
    return ""


def render_turkish(pattern: str, record: dict, translator, cache: dict[str, str], sense_index: int | None = None) -> str:
    base = choose_base_turkish(record, pattern, sense_index=sense_index)
    if not compact(base):
        base = "kullanmak"
    if pattern.startswith("sich "):
        tail = compact(pattern[5:])
        if tail and tail != compact(record.get("almanca") or ""):
            pattern = tail
        else:
            return base
    lemma = compact(record.get("almanca") or "")
    if compact(pattern) == lemma:
        return base
    if pattern.startswith("irgendwohin "):
        return f"bir yere {base}"
    if pattern.startswith("irgendwo "):
        return f"bir yerde {base}"
    if pattern.endswith(f" {lemma}"):
        prefix = compact(pattern[: -len(lemma)]).strip()
    else:
        prefix = pattern
    if not prefix:
        return base
    tokens = prefix.split()
    pieces: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in TR_PLACEHOLDERS:
            pieces.append(TR_PLACEHOLDERS[token])
            index += 1
            continue
        token_norm = normalize(token)
        prep = PREP_ALIAS.get(token_norm)
        if prep and index + 1 < len(tokens) and tokens[index + 1] in TR_PLACEHOLDERS:
            target = tokens[index + 1]
            if target == "jdm." and prep == "mit":
                pieces.append("biriyle")
            elif target == "jdm." and prep == "bei":
                pieces.append("birinin yanında")
            elif target == "jdm.":
                pieces.append(TR_PREP.get(prep, "birine"))
            elif target == "jdn.":
                pieces.append("birini")
            elif target in {"etw.(A)", "etw.(D)"}:
                if prep == "über":
                    pieces.append("bir şey hakkında")
                elif prep == "für":
                    pieces.append("bir şey için")
                elif prep == "gegen":
                    pieces.append("bir şeye karşı")
                elif prep == "mit":
                    pieces.append("bir şeyle")
                elif prep == "von":
                    pieces.append("bir şeyden")
                elif prep in {"zu", "nach", "an"}:
                    pieces.append("bir şeye")
                elif prep == "auf":
                    pieces.append("bir şeye")
                elif prep == "in":
                    pieces.append("bir yerde" if target == "etw.(D)" else "bir şeye")
                elif prep == "um":
                    pieces.append("bir şey için")
                elif prep == "aus":
                    pieces.append("bir şeyden")
                elif prep == "unter":
                    pieces.append("bir şey altında")
                elif prep == "vor":
                    pieces.append("bir şeyin önünde")
                elif prep == "bei":
                    pieces.append("bir yerde")
                else:
                    pieces.append(TR_PREP.get(prep, "bir şeye"))
            index += 2
            continue
        break
    if index >= len(tokens):
        return compact(" ".join(pieces + [base]))
    exact_prefix = compact(" ".join(tokens[index:]))
    fallback_exact = fallback_exact_prefix(exact_prefix)
    if fallback_exact:
        return compact(" ".join(pieces + [fallback_exact, base]))
    translated_prefix = translate_prefix(exact_prefix, translator, cache)
    if compact(translated_prefix) and not translation_looks_bad(translated_prefix):
        return compact(" ".join(pieces + [translated_prefix, base]))
    fallback_prep = PREP_ALIAS.get(normalize(tokens[index]))
    if fallback_prep:
        pieces.append(TR_PREP.get(fallback_prep, "bir şeye"))
        return compact(" ".join(pieces + [base]))
    return compact(" ".join(pieces + [base]))


def select_patterns(record: dict, candidates: dict[str, dict], translator, cache: dict[str, str]) -> list[dict]:
    ordered = sorted(candidates.values(), key=lambda item: (-item["score"], len(item["kalip"]), item["kalip"]))
    selected: list[dict] = []
    used_diversity: set[str] = set()
    for item in ordered:
        key = diversity_key(item["kalip"])
        if key in used_diversity and item["score"] < 85:
            continue
        selected.append(item)
        used_diversity.add(key)
        if len(selected) == 3:
            break
    if len(selected) < 2:
        for item in ordered:
            if item in selected:
                continue
            selected.append(item)
            if len(selected) == 2:
                break
    rendered: list[dict] = []
    for item in selected:
        rendered.append(
            {
                "kalip": item["kalip"],
                "turkce": item["turkce"] or render_turkish(item["kalip"], record, translator, cache, sense_index=item["sense_index"]),
            }
        )
    return rendered


def build_patterns_for_record(lemma: str, record: dict, dewikt_entry: dict | None, prep_db: dict[str, list[tuple]], translator, cache: dict[str, str], *, refresh_dwds: bool = False) -> list[dict]:
    candidates: dict[str, dict] = {}
    for row in record.get("fiil_kaliplari") or []:
        if not isinstance(row, dict):
            continue
        if not keep_existing_pattern(record, row):
            continue
        add_candidate(candidates, row.get("kalip") or "", 94, "dictionary-existing", record, translation=row.get("turkce") or "")
    for row in prep_db.get(lemma, []):
        add_candidate(candidates, row[4] if len(row) > 4 else "", 97, "prep-db", record, translation=row[5] if len(row) > 5 else "")

    forms = collect_known_forms(record)
    forms.add(normalize(lemma))
    if dewikt_entry:
        for form_row in dewikt_entry.get("forms") or []:
            value = compact(form_row.get("form") or "")
            if not value:
                continue
            tokens = [normalize(token) for token in word_tokens(value)]
            if len(tokens) == 1:
                forms.add(tokens[0])

    for sense in build_sense_rows(record, dewikt_entry):
        texts = list(sense["texts"])
        examples = list(sense["examples"])
        tags = list(sense["tags"])
        add_core_patterns(lemma, record, texts, tags, candidates, sense_index=sense["sense_index"])
        extract_exact_and_generic_patterns(lemma, examples, forms, candidates, record, sense_index=sense["sense_index"])

    if len(candidates) < 2:
        add_dwds_fallbacks(lemma, record, candidates, refresh=refresh_dwds)

    if len(candidates) < 2 and normalize(lemma) in {normalize(item) for item in LOCATIVE_HINTS}:
        add_candidate(candidates, f"irgendwo {lemma}", 60, "late-locative", record)
    if len(candidates) < 2:
        add_candidate(candidates, f"etw.(A) {lemma}", 58, "late-object", record)
    if len(candidates) < 2:
        add_candidate(candidates, lemma, 50, "late-bare", record)
    return select_patterns(record, candidates, translator, cache)


def load_dictionary_lookup() -> dict[str, dict]:
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("verbs") or data.get("fiiller") or []
    lookup: dict[str, dict] = {}
    for row in rows:
        if compact(row.get("tur") or "").casefold() != VERB_POS:
            continue
        lemma = compact(row.get("almanca") or "")
        if lemma and lemma not in lookup:
            lookup[lemma] = row
    return lookup


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill fiil_kaliplari batch files in output/codex.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--refresh-dwds", action="store_true")
    parser.add_argument("--report-path", type=Path, default=REPORT_PATH)
    args = parser.parse_args()

    batch_paths = sorted(CODEX_DIR.glob(BATCH_GLOB))
    if not batch_paths:
        print("No batch files found.")
        return 1

    dictionary = load_dictionary_lookup()
    prep_db = load_prep_db()

    targets: list[str] = []
    batch_data: list[tuple[Path, dict]] = []
    for path in batch_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        batch_data.append((path, payload))
        for row in payload.get("fiiller", []):
            lemma = compact(row.get("almanca") or "")
            if lemma:
                targets.append(lemma)
    if args.limit > 0:
        targets = targets[: args.limit]
    target_set = {normalize(item) for item in targets}

    dewikt_lookup = load_dewiktionary_verbs(target_set) if DEWIKT_PATH.exists() else {}
    translator = get_translator()
    translation_cache: dict[str, str] = {}

    counters = Counter()
    sample: list[dict] = []

    for path, payload in batch_data:
        changed = False
        for row in payload.get("fiiller", []):
            lemma = compact(row.get("almanca") or "")
            if not lemma:
                continue
            if args.limit > 0 and counters["verbs_seen"] >= args.limit:
                break
            counters["verbs_seen"] += 1
            record = dictionary.get(lemma)
            if record is None:
                counters["missing_in_dictionary"] += 1
                continue
            patterns = build_patterns_for_record(
                lemma,
                record,
                dewikt_lookup.get(normalize(lemma)),
                prep_db,
                translator,
                translation_cache,
                refresh_dwds=args.refresh_dwds,
            )
            if len(patterns) >= 2:
                counters["verbs_with_2plus"] += 1
            else:
                counters["verbs_with_lt2"] += 1
            row["fiil_kaliplari"] = patterns
            changed = True
            counters["patterns_total"] += len(patterns)
            if len(sample) < 40:
                sample.append({"almanca": lemma, "fiil_kaliplari": patterns})
        if changed and not args.dry_run:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.limit > 0 and counters["verbs_seen"] >= args.limit:
            break

    report = {
        "batch_count": len(batch_paths),
        "counters": dict(counters),
        "dewiktionary_hits": len(dewikt_lookup),
        "translator_available": bool(translator),
        "sample": sample,
    }
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
