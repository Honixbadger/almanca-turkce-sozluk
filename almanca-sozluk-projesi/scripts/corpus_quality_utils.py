#!/usr/bin/env python3
"""Shared helpers for long-running corpus quality pipelines."""

from __future__ import annotations

import bz2
import gzip
import html
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from grammar_utils import guess_pos, lemmatize_adjective, lemmatize_noun, lemmatize_verb, strip_article


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
CORPUS_OUTPUT_DIR = PROJECT_ROOT / "output" / "corpus_quality"
RAW_DOWNLOADS_DIR = PROJECT_ROOT / "data" / "raw" / "downloads"
RAW_HTML_DIR = PROJECT_ROOT / "data" / "raw" / "html"
TATOEBA_DE_PATH = RAW_DOWNLOADS_DIR / "tatoeba_deu.tsv.bz2"
DEWIKTIONARY_PATH = RAW_DOWNLOADS_DIR / "dewiktionary.gz"

TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+(?:-[A-Za-zÄÖÜäöüß]+)?")
TAG_RE = re.compile(r"<[^>]+>")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9\"„])")
WHITESPACE_RE = re.compile(r"\s+")
STOPWORDS = {
    "aber", "als", "am", "an", "auch", "auf", "aus", "bei", "bin", "bis", "da", "dann",
    "das", "dass", "de", "dem", "den", "der", "des", "die", "doch", "dort", "durch",
    "ein", "eine", "einem", "einen", "einer", "eines", "er", "es", "etwa", "für", "hat",
    "hatte", "hier", "hinter", "ich", "ihm", "ihn", "im", "in", "ist", "ja", "jede",
    "jeder", "jedes", "kann", "kein", "keine", "mit", "nach", "nicht", "noch", "nur",
    "oder", "sein", "seine", "sich", "sie", "sind", "so", "um", "und", "unter", "von",
    "vor", "war", "waren", "warum", "was", "weil", "wenn", "wer", "wie", "wir", "wird",
    "wurde", "zu", "zum", "zur", "über",
}


def ensure_corpus_output_dir() -> Path:
    CORPUS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return CORPUS_OUTPUT_DIR


def compact_space(text: str) -> str:
    return WHITESPACE_RE.sub(" ", str(text or "")).strip()


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return compact_space(value).casefold()


def strip_html_markup(text: str) -> str:
    cleaned = re.sub(r"(?is)<script.*?</script>", " ", str(text or ""))
    cleaned = re.sub(r"(?is)<style.*?</style>", " ", cleaned)
    cleaned = TAG_RE.sub(" ", cleaned)
    return compact_space(html.unescape(cleaned))


def split_sentences(text: str) -> list[str]:
    raw = compact_space(text)
    if not raw:
        return []
    parts = SENTENCE_SPLIT_RE.split(raw)
    result: list[str] = []
    for part in parts:
        sentence = compact_space(part)
        if 18 <= len(sentence) <= 260:
            result.append(sentence)
    return result


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(str(text or "")) if token]


def keyword_tokens(text: str, blocked: set[str] | None = None) -> list[str]:
    blocked = blocked or set()
    result: list[str] = []
    for token in tokenize(text):
        norm = normalize_text(token)
        if len(norm) < 3 or norm in STOPWORDS or norm in blocked:
            continue
        result.append(norm)
    return result


def sentence_score(sentence: str, preferred_source: str = "") -> float:
    text = compact_space(sentence)
    if not text:
        return 0.0
    score = 0.0
    length = len(text)
    if 35 <= length <= 120:
        score += 3.0
    elif 20 <= length <= 170:
        score += 2.0
    else:
        score += 0.5
    if text.endswith((".", "!", "?")):
        score += 0.5
    if text.count(",") <= 2:
        score += 0.5
    digit_ratio = sum(1 for ch in text if ch.isdigit()) / max(length, 1)
    if digit_ratio < 0.05:
        score += 0.5
    source_bonus = {"tatoeba": 2.0, "dewiktionary": 1.4, "html": 1.0}
    score += source_bonus.get(preferred_source, 0.0)
    return round(score, 3)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def build_dictionary_lemma_index(dict_path: Path) -> dict[str, dict]:
    data = load_json(dict_path, [])
    index: dict[str, dict] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        almanca = compact_space(row.get("almanca") or "")
        if not almanca:
            continue
        lemma = compact_space(strip_article(almanca))
        key = normalize_text(lemma)
        if not key:
            continue
        existing = index.get(key)
        payload = {
            "almanca": lemma,
            "tur": compact_space(row.get("tur") or ""),
            "turkce": compact_space(row.get("turkce") or ""),
        }
        if existing is None or (not existing.get("turkce") and payload["turkce"]):
            index[key] = payload
    return index


def candidate_lemmas_for_token(token: str) -> list[str]:
    raw = compact_space(token)
    if not raw:
        return []
    candidates: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        key = normalize_text(value)
        if not key or key in seen:
            return
        seen.add(key)
        candidates.append(key)

    add(strip_article(raw))
    pos_guess = guess_pos(raw)
    if pos_guess == "fiil" or raw[:1].islower():
        add(lemmatize_verb(raw))
        add(lemmatize_adjective(raw))
    if pos_guess == "isim" or raw[:1].isupper():
        add(lemmatize_noun(raw))
    if pos_guess == "sıfat":
        add(lemmatize_adjective(raw))
    return candidates


def update_usage_entry(entry: dict, sentence: str, source: str, match_lemma: str) -> None:
    entry["hits_total"] = int(entry.get("hits_total", 0)) + 1
    source_counts = entry.setdefault("source_counts", {})
    source_counts[source] = int(source_counts.get(source, 0)) + 1

    blocked = {normalize_text(match_lemma)}
    context_counter = Counter(entry.get("context_counts") or {})
    for token in keyword_tokens(sentence, blocked=blocked):
        context_counter[token] += 1
    entry["context_counts"] = dict(context_counter.most_common(40))

    sentence_key = normalize_text(sentence)
    samples = entry.setdefault("samples", [])
    if any(
        item.get("key") == sentence_key or normalize_text(item.get("sentence", "")) == sentence_key
        for item in samples
    ):
        return
    score = sentence_score(sentence, preferred_source=source)
    samples.append(
        {
            "key": sentence_key,
            "sentence": compact_space(sentence),
            "source": source,
            "score": score,
        }
    )
    samples.sort(key=lambda item: (-float(item.get("score", 0.0)), len(item.get("sentence", ""))))
    del samples[10:]


def html_files_sorted() -> list[Path]:
    if not RAW_HTML_DIR.exists():
        return []
    return sorted(path for path in RAW_HTML_DIR.rglob("*.html") if path.is_file())


def iter_html_sentences(files: list[Path], start_index: int, max_files: int) -> tuple[int, list[dict]]:
    payloads: list[dict] = []
    current = start_index
    subset = files[start_index:start_index + max_files]
    for path in subset:
        current += 1
        try:
            text = strip_html_markup(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for sentence in split_sentences(text):
            payloads.append({"source": "html", "sentence": sentence, "path": str(path)})
    return current, payloads


def iter_tatoeba_sentences(start_line: int, max_lines: int) -> tuple[int, list[dict]]:
    payloads: list[dict] = []
    current = 0
    if not TATOEBA_DE_PATH.exists():
        return current, payloads
    with bz2.open(TATOEBA_DE_PATH, "rt", encoding="utf-8", errors="replace") as handle:
        for _ in range(start_line):
            if not handle.readline():
                return current, payloads
            current += 1
        while len(payloads) < max_lines:
            line = handle.readline()
            if not line:
                break
            current += 1
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            sentence = compact_space(parts[2])
            if 18 <= len(sentence) <= 260:
                payloads.append({"source": "tatoeba", "sentence": sentence, "sid": parts[0]})
    return current, payloads


def iter_dewiktionary_example_sentences(start_line: int, max_lines: int) -> tuple[int, list[dict]]:
    payloads: list[dict] = []
    current = 0
    if not DEWIKTIONARY_PATH.exists():
        return current, payloads
    with gzip.open(DEWIKTIONARY_PATH, "rt", encoding="utf-8", errors="replace") as handle:
        for _ in range(start_line):
            if not handle.readline():
                return current, payloads
            current += 1
        while current - start_line < max_lines:
            line = handle.readline()
            if not line:
                break
            current += 1
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("lang_code") != "de":
                continue
            lemma = compact_space(obj.get("word") or "")
            for sense in obj.get("senses") or []:
                if not isinstance(sense, dict):
                    continue
                for example in sense.get("examples") or []:
                    if isinstance(example, dict):
                        sentence = compact_space(example.get("text") or example.get("example") or "")
                    else:
                        sentence = compact_space(example)
                    if 18 <= len(sentence) <= 260:
                        payloads.append({"source": "dewiktionary", "sentence": sentence, "lemma": lemma})
    return current, payloads
