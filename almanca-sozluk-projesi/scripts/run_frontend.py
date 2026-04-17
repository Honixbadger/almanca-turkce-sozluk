#!/usr/bin/env python
"""Serve the local frontend and offline definition lookup API."""

from __future__ import annotations

import html
import json
import re
import socket
import threading
import urllib.parse
import unicodedata
import webbrowser
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from build_definition_index import main as build_definition_index
except ModuleNotFoundError:
    from scripts.build_definition_index import main as build_definition_index

try:
    from build_dictionary import annotate_categories, canonicalize_pos_label, polish_turkish_fields
except ModuleNotFoundError:
    from scripts.build_dictionary import annotate_categories, canonicalize_pos_label, polish_turkish_fields


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
MANUAL_DIR = DATA_DIR / "manual"
OUTPUT_DIR = PROJECT_ROOT / "output"
HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFINITION_INDEX_DE_PATH = OUTPUT_DIR / "definition_index_de.json"
DEFINITION_INDEX_TR_PATH = OUTPUT_DIR / "definition_index_tr.json"
DEFINITION_AVAILABILITY_PATH = OUTPUT_DIR / "definition_availability.json"
USER_ENTRIES_PATH = MANUAL_DIR / "user_entries.json"
TDK_GTS_ENDPOINT = "https://sozluk.gov.tr/gts"
TDK_TIMEOUT_SECONDS = 5

_definition_indexes: dict[str, dict[str, dict]] | None = None
_tdk_definition_cache: dict[str, dict] = {}
ALLOWED_ARTICLES = {"", "der", "die", "das"}
ALLOWED_POS = {
    "isim",
    "fiil",
    "sifat",
    "sıfat",
    "zarf",
    "ifade",
    "sayi",
    "sayı",
    "zamir",
    "baglac",
    "bağlaç",
    "edat",
    "unlem",
    "ünlem",
    "kisaltma",
    "kısaltma",
    "karma",
    "belirsiz",
}

ALLOWED_POS = {
    "isim",
    "fiil",
    "sıfat",
    "zarf",
    "ifade",
    "sayı",
    "zamir",
    "bağlaç",
    "edat",
    "ünlem",
    "kısaltma",
    "karma",
    "belirsiz",
}


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = text.replace("ß", "ss")
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return normalize_whitespace(text)


def strip_article(term: str) -> str:
    pieces = normalize_whitespace(term).split(" ", 1)
    if len(pieces) == 2 and pieces[0].casefold() in {"der", "die", "das"}:
        return pieces[1]
    return normalize_whitespace(term)


def send_error_payload(note: str, status: int = 400) -> dict:
    return {"status": "error", "note": note, "http_status": status}


def ensure_user_entries_file() -> None:
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    if USER_ENTRIES_PATH.exists():
        return
    payload = {
        "source_name": "kullanici-ekleme",
        "default_note": "Arayuzden manuel olarak eklendi.",
        "records": [],
    }
    USER_ENTRIES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_user_entries_payload() -> dict:
    ensure_user_entries_file()
    return json.loads(USER_ENTRIES_PATH.read_text(encoding="utf-8-sig"))


def save_user_entries_payload(payload: dict) -> None:
    ensure_user_entries_file()
    USER_ENTRIES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_pos(value: str) -> str:
    return canonicalize_pos_label(normalize_whitespace(value))


def clean_example_items(raw_examples) -> list[dict]:
    items = []
    for raw in raw_examples or []:
        if not isinstance(raw, dict):
            continue
        item = {
            "almanca": normalize_whitespace(raw.get("almanca", "")),
            "turkce": normalize_whitespace(raw.get("turkce", "")),
            "kaynak": normalize_whitespace(raw.get("kaynak", "")),
            "not": normalize_whitespace(raw.get("not", "")),
        }
        if item["almanca"] or item["turkce"] or item["kaynak"] or item["not"]:
            items.append(item)
    return items


def build_runtime_record(raw: dict) -> dict:
    artikel = normalize_whitespace(raw.get("artikel", ""))
    artikel = artikel if artikel in ALLOWED_ARTICLES else ""
    examples = clean_example_items(raw.get("ornekler", []))
    source_name = normalize_whitespace(raw.get("kaynak", "")) or "kullanici-ekleme"
    translation_status = normalize_whitespace(raw.get("ceviri_durumu", "")) or "kullanici-eklemesi"
    translation_review_note = normalize_whitespace(raw.get("ceviri_inceleme_notu", ""))
    translation_sources = clean_example_items(raw.get("ceviri_kaynaklari", []))
    fallback_example_de = normalize_whitespace(raw.get("ornek_almanca", ""))
    fallback_example_tr = normalize_whitespace(raw.get("ornek_turkce", ""))
    if examples and not fallback_example_de:
        fallback_example_de = examples[0].get("almanca", "")
    if examples and not fallback_example_tr:
        fallback_example_tr = examples[0].get("turkce", "")
    record = {
        "almanca": normalize_whitespace(raw.get("almanca", "")),
        "artikel": artikel,
        "turkce": normalize_whitespace(raw.get("turkce", "")),
        "aciklama_turkce": normalize_whitespace(raw.get("aciklama_turkce", "")),
        "tur": clean_pos(raw.get("tur", "")),
        "ornek_almanca": fallback_example_de,
        "ornek_turkce": fallback_example_tr,
        "ornekler": examples,
        "kaynak": source_name,
        "kaynak_url": normalize_whitespace(raw.get("kaynak_url", "")),
        "not": normalize_whitespace(raw.get("not", "")),
        "source_names": {source_name},
        "source_urls": set(),
        "ceviri_kaynaklari": translation_sources,
        "ceviri_durumu": translation_status,
        "ceviri_inceleme_notu": translation_review_note
        or ("Bu kayıt kullanıcı tarafından eklendi; harici doğrulama kaynağı henüz eklenmedi." if source_name == "kullanici-ekleme" else ""),
        "seed_match": False,
        "autoish": False,
        "wikdict_fallback": False,
        "ilgili_kayitlar": [],
        "kategoriler": ["genel"],
    }
    if record["kaynak_url"]:
        record["source_urls"].add(record["kaynak_url"])
    record = polish_turkish_fields([record])[0]
    record = annotate_categories([record])[0]
    return record


def frontend_payload(record: dict) -> dict:
    return {
        "almanca": record["almanca"],
        "artikel": record["artikel"],
        "turkce": record["turkce"],
        "kategoriler": record.get("kategoriler", []),
        "aciklama_turkce": record.get("aciklama_turkce", ""),
        "ilgili_kayitlar": record.get("ilgili_kayitlar", []),
        "tur": record["tur"],
        "ornek_almanca": record.get("ornek_almanca", ""),
        "ornek_turkce": record.get("ornek_turkce", ""),
        "ornekler": record.get("ornekler", []),
        "kaynak": record.get("kaynak", "kullanici-ekleme"),
        "kaynak_url": record.get("kaynak_url", ""),
        "ceviri_kaynaklari": record.get("ceviri_kaynaklari", []),
        "ceviri_durumu": record.get("ceviri_durumu", "kullanici-eklemesi"),
        "ceviri_inceleme_notu": record.get("ceviri_inceleme_notu", ""),
        "not": record.get("not", ""),
    }


def validate_user_entry(raw: dict) -> dict:
    almanca = normalize_whitespace(raw.get("almanca", ""))
    turkce = normalize_whitespace(raw.get("turkce", ""))
    tur = clean_pos(raw.get("tur", ""))
    artikel = normalize_whitespace(raw.get("artikel", ""))

    if not almanca or not turkce or not tur:
        return send_error_payload("Almanca, Türkçe ve tür alanları zorunlu.", 400)
    if tur not in ALLOWED_POS:
        return send_error_payload("Geçerli bir tür seç.", 400)
    if artikel not in ALLOWED_ARTICLES:
        return send_error_payload("Artikel yalnızca der / die / das olabilir.", 400)
    if tur != "isim" and artikel:
        return send_error_payload("Artikel sadece isimlerde kullanılabilir.", 400)
    return {"status": "ok"}


def list_user_entries() -> list[dict]:
    payload = load_user_entries_payload()
    items = []
    for item in payload.get("records", []):
        runtime = build_runtime_record(item)
        items.append(frontend_payload(runtime))
    return items


def save_user_entry(raw: dict) -> dict:
    payload = load_user_entries_payload()
    records = payload.setdefault("records", [])

    key = (
        normalize_key(raw.get("almanca", "")),
        clean_pos(raw.get("tur", "")),
        normalize_key(raw.get("turkce", "")),
    )
    stored = {
        "almanca": normalize_whitespace(raw.get("almanca", "")),
        "artikel": normalize_whitespace(raw.get("artikel", "")),
        "turkce": normalize_whitespace(raw.get("turkce", "")),
        "aciklama_turkce": normalize_whitespace(raw.get("aciklama_turkce", "")),
        "tur": clean_pos(raw.get("tur", "")),
        "ornek_almanca": normalize_whitespace(raw.get("ornek_almanca", "")),
        "ornek_turkce": normalize_whitespace(raw.get("ornek_turkce", "")),
        "ornekler": clean_example_items(raw.get("ornekler", [])),
        "kaynak": normalize_whitespace(raw.get("kaynak", "")) or "kullanici-ekleme",
        "not": normalize_whitespace(raw.get("not", "")),
        "kaynak_url": normalize_whitespace(raw.get("kaynak_url", "")),
        "ceviri_kaynaklari": clean_example_items(raw.get("ceviri_kaynaklari", [])),
        "ceviri_durumu": normalize_whitespace(raw.get("ceviri_durumu", "")) or "kullanici-eklemesi",
        "ceviri_inceleme_notu": normalize_whitespace(raw.get("ceviri_inceleme_notu", "")),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    replaced = False
    for index, current in enumerate(records):
        current_key = (
            normalize_key(current.get("almanca", "")),
            clean_pos(current.get("tur", "")),
            normalize_key(current.get("turkce", "")),
        )
        if current_key == key:
            records[index] = stored
            replaced = True
            break
    if not replaced:
        records.append(stored)

    save_user_entries_payload(payload)
    return frontend_payload(build_runtime_record(stored))


def turkish_candidates(term: str) -> list[str]:
    normalized = normalize_whitespace(term)
    candidates = [normalized]
    parts = [part for part in normalized.split(" ") if part]
    if len(parts) > 1:
        candidates.append(" ".join(parts[-2:]))
        candidates.append(parts[-1])

    seen = set()
    results = []
    for item in candidates:
        key = normalize_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


def filter_suspicious_turkish_definitions(term: str, definitions: list[str]) -> list[str]:
    normalized_term = normalize_whitespace(term)
    if not normalized_term:
        return definitions
    lower_term = normalized_term.casefold()
    suspicious_markers = [
        "erkek adı",
        "kadın adı",
        "soyadı",
        "iline bağlı köy",
        "ilçesine bağlı köy",
        "beldesi",
        "mahallesi",
        "yerleşim yeri",
    ]
    filtered = []
    for definition in definitions:
        normalized_definition = normalize_whitespace(definition).casefold()
        if lower_term == normalized_term and any(marker in normalized_definition for marker in suspicious_markers):
            continue
        filtered.append(definition)
    return filtered


def ensure_definition_files() -> None:
    if (
        DEFINITION_INDEX_DE_PATH.exists()
        and DEFINITION_INDEX_TR_PATH.exists()
        and DEFINITION_AVAILABILITY_PATH.exists()
    ):
        return
    build_definition_index()


def load_definition_indexes() -> dict[str, dict[str, dict]]:
    global _definition_indexes

    if _definition_indexes is not None:
        return _definition_indexes

    ensure_definition_files()
    _definition_indexes = {
        "de": json.loads(DEFINITION_INDEX_DE_PATH.read_text(encoding="utf-8"))
        if DEFINITION_INDEX_DE_PATH.exists()
        else {},
        "tr": json.loads(DEFINITION_INDEX_TR_PATH.read_text(encoding="utf-8"))
        if DEFINITION_INDEX_TR_PATH.exists()
        else {},
    }
    return _definition_indexes


def strip_html_markup(text: str) -> str:
    clean = re.sub(r"<[^>]+>", "", str(text or ""))
    return normalize_whitespace(html.unescape(clean))


def fetch_tdk_definition(term: str) -> dict:
    normalized_term = normalize_whitespace(term)
    cache_key = normalize_key(normalized_term)
    if not cache_key:
        return {
            "status": "empty",
            "term": term,
            "source": "",
            "definitions": [],
            "note": "Bos terim icin TDK sorgusu yapilamadi.",
            "url": "",
        }
    if cache_key in _tdk_definition_cache:
        return _tdk_definition_cache[cache_key]

    url = f"{TDK_GTS_ENDPOINT}?{urllib.parse.urlencode({'ara': normalized_term})}"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://sozluk.gov.tr/",
            "Accept": "application/json, text/plain, */*",
        },
    )
    try:
        response_text = urlopen(request, timeout=TDK_TIMEOUT_SECONDS).read().decode("utf-8", errors="replace")
        payload = json.loads(response_text)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        result = {
            "status": "error",
            "term": term,
            "source": "TDK",
            "definitions": [],
            "note": f"TDK cevirmici sozluk su an okunamadi: {exc}",
            "url": "https://sozluk.gov.tr/",
        }
        _tdk_definition_cache[cache_key] = result
        return result

    if isinstance(payload, dict) and payload.get("error"):
        result = {
            "status": "empty",
            "term": term,
            "source": "TDK",
            "definitions": [],
            "note": payload.get("error", "TDK sonuc bulamadi."),
            "url": "https://sozluk.gov.tr/",
        }
        _tdk_definition_cache[cache_key] = result
        return result

    definitions: list[str] = []
    matched_term = normalized_term
    if isinstance(payload, list):
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            matched_term = normalize_whitespace(entry.get("madde", matched_term)) or matched_term
            for meaning in entry.get("anlamlarListe", []) or []:
                if not isinstance(meaning, dict):
                    continue
                text = strip_html_markup(meaning.get("anlam", ""))
                if text:
                    definitions.append(text)
            definitions = filter_suspicious_turkish_definitions(normalized_term, definitions)
            if definitions:
                break

    if definitions:
        result = {
            "status": "ok",
            "term": term,
            "matched_term": matched_term,
            "source": "TDK",
            "definitions": definitions,
            "note": "Turkce tanim TDK cevrimici sozlugunden getirildi.",
            "url": "https://sozluk.gov.tr/",
        }
        _tdk_definition_cache[cache_key] = result
        return result

    result = {
        "status": "empty",
        "term": term,
        "source": "TDK",
        "definitions": [],
        "note": "TDK cevabinda kullanilabilir tanim bulunamadi.",
        "url": "https://sozluk.gov.tr/",
    }
    _tdk_definition_cache[cache_key] = result
    return result


def fetch_dwds_definition(term: str) -> dict:
    normalized_term = strip_article(normalize_whitespace(term))
    cache_key = normalize_key(normalized_term)
    if not cache_key:
        return {
            "status": "empty",
            "term": term,
            "source": "",
            "definitions": [],
            "note": "Bos terim icin DWDS sorgusu yapilamadi.",
            "url": "",
        }
    cached = _tdk_definition_cache.get(f"dwds::{cache_key}")
    if cached is not None:
        return cached

    url = f"https://www.dwds.de/wb/{urllib.parse.quote(normalized_term, safe='')}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        response_text = urlopen(request, timeout=TDK_TIMEOUT_SECONDS).read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        result = {
            "status": "error",
            "term": term,
            "source": "DWDS",
            "definitions": [],
            "note": f"DWDS su an okunamadi: {exc}",
            "url": url,
        }
        _tdk_definition_cache[f"dwds::{cache_key}"] = result
        return result

    matched_term = normalized_term
    lemma_match = re.search(r'<h1 class="dwdswb-ft-lemmaansatz"><b>(.*?)</b>', response_text)
    if lemma_match:
        matched_term = strip_html_markup(lemma_match.group(1)) or normalized_term

    definitions = []
    for raw_definition in re.findall(r'<span class="dwdswb-definition">(.*?)</span>', response_text, flags=re.DOTALL):
        definition = strip_html_markup(raw_definition)
        if definition and definition not in definitions:
            definitions.append(definition)
        if len(definitions) >= 3:
            break

    if definitions:
        result = {
            "status": "ok",
            "term": term,
            "matched_term": matched_term,
            "source": "DWDS",
            "definitions": definitions,
            "note": "Almanca tanim DWDS cevrimici sozlugunden getirildi.",
            "url": url,
        }
        _tdk_definition_cache[f"dwds::{cache_key}"] = result
        return result

    result = {
        "status": "empty",
        "term": term,
        "source": "DWDS",
        "definitions": [],
        "note": "DWDS sayfasinda kullanilabilir tanim bulunamadi.",
        "url": url,
    }
    _tdk_definition_cache[f"dwds::{cache_key}"] = result
    return result


def lookup_turkish_definition_online(term: str) -> dict:
    errors: list[str] = []
    for position, candidate in enumerate(turkish_candidates(term)):
        payload = fetch_tdk_definition(candidate)
        if payload.get("status") == "ok":
            result = dict(payload)
            result["term"] = term
            if position > 0:
                result["note"] = f"Tam ifade yerine `{candidate}` icin TDK tanimi gosteriliyor."
            return result
        if payload.get("status") == "error" and payload.get("note"):
            errors.append(str(payload["note"]))
    if errors:
        return {
            "status": "error",
            "term": term,
            "source": "TDK",
            "definitions": [],
            "note": errors[0],
            "url": "https://sozluk.gov.tr/",
        }
    return {
        "status": "empty",
        "term": term,
        "source": "TDK",
        "definitions": [],
        "note": "TDK'da uygun Turkce tanim bulunamadi.",
        "url": "https://sozluk.gov.tr/",
    }


def lookup_german_definition(term: str) -> dict:
    index = load_definition_indexes().get("de", {})
    candidates = [
        normalize_key(term),
        normalize_key(strip_article(term)),
        normalize_key(term.replace("-", " ")),
    ]
    seen = set()
    for key in candidates:
        if not key or key in seen:
            continue
        seen.add(key)
        if key in index:
            entry = index[key]
            return {
                "status": "ok",
                "term": term,
                "matched_term": entry.get("term", term),
                "source": entry.get("source", "dewiktionary"),
                "definitions": entry.get("definitions", []),
                "note": "Tamamen offline acik veri tanimi gosteriliyor.",
                "url": entry.get("url", ""),
            }

    return {
        "status": "empty",
        "term": term,
        "source": "",
        "definitions": [],
        "note": "Bu Almanca terim icin offline tanim bulunamadi.",
        "url": "",
    }


def lookup_turkish_definition(term: str) -> dict:
    index = load_definition_indexes().get("tr", {})
    for position, candidate in enumerate(turkish_candidates(term)):
        key = normalize_key(candidate)
        if key not in index:
            continue

        entry = index[key]
        filtered_definitions = filter_suspicious_turkish_definitions(candidate, entry.get("definitions", []))
        if not filtered_definitions:
            continue
        note = "Tamamen offline acik veri tanimi gosteriliyor."
        if position > 0:
            note = (
                f"Tam ifade yerine `{candidate}` icin offline tanim gosteriliyor."
            )
        return {
            "status": "ok",
            "term": term,
            "matched_term": entry.get("term", candidate),
            "source": entry.get("source", "trwiktionary"),
            "definitions": filtered_definitions,
            "note": note,
            "url": entry.get("url", ""),
        }

    return {
        "status": "empty",
        "term": term,
        "source": "",
        "definitions": [],
        "note": "Bu Turkce ifade icin offline tanim bulunamadi.",
        "url": "",
    }


class DictionaryRequestHandler(SimpleHTTPRequestHandler):
    def guess_type(self, path: str) -> str:
        guessed = super().guess_type(path)
        if guessed in {
            "text/html",
            "text/css",
            "application/javascript",
            "text/javascript",
            "application/json",
        }:
            return f"{guessed}; charset=utf-8"
        return guessed

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/define":
            self.handle_define(parsed.query)
            return
        if parsed.path == "/api/user-entries":
            self.send_json(200, {"status": "ok", "entries": list_user_entries()})
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/categorize-preview":
            self.handle_categorize_preview()
            return
        if parsed.path == "/api/add-entry":
            self.handle_add_entry()
            return
        if parsed.path == "/api/ai-import/scan":
            self.handle_ai_import_scan()
            return
        if parsed.path == "/api/ai-import/save":
            self.handle_ai_import_save()
            return
        self.send_json(404, {"status": "error", "note": "Bilinmeyen API yolu."})

    def handle_define(self, query_string: str) -> None:
        params = urllib.parse.parse_qs(query_string)
        lang = (params.get("lang") or [""])[0].strip().lower()
        term = normalize_whitespace((params.get("q") or [""])[0])

        if lang not in {"de", "tr"} or not term:
            self.send_json(
                400,
                {
                    "status": "error",
                    "note": "Gecerli `lang` ve `q` parametreleri gerekli.",
                },
            )
            return

        payload = lookup_german_definition(term) if lang == "de" else lookup_turkish_definition(term)
        self.send_json(200, payload)

    def read_json_body(self) -> dict:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def handle_categorize_preview(self) -> None:
        payload = self.read_json_body()
        validation = validate_user_entry(
            {
                "almanca": payload.get("almanca", ""),
                "turkce": payload.get("turkce", ""),
                "tur": payload.get("tur", ""),
                "artikel": payload.get("artikel", ""),
            }
        )
        if validation.get("status") == "error":
            self.send_json(validation.pop("http_status", 400), validation)
            return

        record = build_runtime_record(payload)
        self.send_json(
            200,
            {
                "status": "ok",
                "categories": record.get("kategoriler", ["genel"]),
                "normalized_pos": record.get("tur", ""),
            },
        )

    def handle_add_entry(self) -> None:
        payload = self.read_json_body()
        validation = validate_user_entry(payload)
        if validation.get("status") == "error":
            self.send_json(validation.pop("http_status", 400), validation)
            return

        saved = save_user_entry(payload)
        self.send_json(200, {"status": "ok", "entry": saved})

    def handle_ai_import_scan(self) -> None:
        """Fetch a URL and use Gemini AI to extract German vocabulary."""
        payload = self.read_json_body()
        url = (payload.get("url") or "").strip()
        api_key = (payload.get("api_key") or "").strip()

        if not url:
            self.send_json(400, {"status": "error", "note": "URL gerekli."})
            return
        if not api_key:
            self.send_json(400, {"status": "error", "note": "Gemini API key gerekli."})
            return

        # Fetch the URL content
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AlmancaSozluk/1.0)"})
            with urlopen(req, timeout=15) as resp:
                raw_bytes = resp.read(300_000)  # max 300KB
            # Try to detect encoding from headers
            content_type = resp.headers.get("Content-Type", "")
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()
            try:
                page_text = raw_bytes.decode(charset, errors="replace")
            except Exception:
                page_text = raw_bytes.decode("utf-8", errors="replace")
        except (HTTPError, URLError, Exception) as exc:
            self.send_json(502, {"status": "error", "note": f"URL alınamadı: {exc}"})
            return

        # Strip HTML tags
        clean_text = re.sub(r"<[^>]+>", " ", page_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        clean_text = html.unescape(clean_text)
        # Limit to ~6000 chars for Gemini
        clean_text = clean_text[:6000]

        # Call Gemini API
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
        prompt = (
            "Aşağıdaki Almanca metin içindeki önemli Almanca kelimeleri listele. "
            "Yalnızca eğitim değeri olan kelimeler: isimler, fiiller, sıfatlar, zarflar. "
            "Her kelime için şu JSON formatını kullan:\n"
            '[{"almanca":"Wort","turkce":"kelime","tur":"isim","artikel":"der/die/das veya bos"}]\n'
            "Sadece JSON dizisi döndür, başka açıklama ekleme. En fazla 40 kelime.\n\n"
            f"METİN:\n{clean_text}"
        )
        gemini_body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048}
        }).encode("utf-8")

        try:
            greq = Request(
                gemini_url,
                data=gemini_body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urlopen(greq, timeout=30) as gresp:
                gemini_raw = gresp.read()
            gemini_data = json.loads(gemini_raw.decode("utf-8"))
            text_out = gemini_data["candidates"][0]["content"]["parts"][0]["text"]
        except (HTTPError, URLError) as exc:
            self.send_json(502, {"status": "error", "note": f"Gemini API hatası: {exc}"})
            return
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            self.send_json(502, {"status": "error", "note": f"Gemini yanıtı ayrıştırılamadı: {exc}"})
            return

        # Parse JSON from Gemini output (it may include markdown fences)
        json_match = re.search(r"\[.*\]", text_out, re.DOTALL)
        if not json_match:
            self.send_json(200, {"status": "ok", "candidates": [], "note": "Gemini çıktısında kelime bulunamadı."})
            return
        try:
            candidates = json.loads(json_match.group())
        except json.JSONDecodeError:
            self.send_json(200, {"status": "ok", "candidates": [], "note": "Gemini JSON ayrıştırma hatası."})
            return

        # Normalize candidates
        normalized = []
        for c in candidates:
            if not isinstance(c, dict):
                continue
            almanca = str(c.get("almanca") or "").strip()
            if not almanca:
                continue
            normalized.append({
                "almanca": almanca,
                "turkce": str(c.get("turkce") or "").strip(),
                "tur": canonicalize_pos_label(str(c.get("tur") or "isim")),
                "artikel": str(c.get("artikel") or "").strip().lower() if str(c.get("artikel") or "").strip().lower() in {"der", "die", "das"} else "",
            })

        self.send_json(200, {
            "status": "ok",
            "candidates": normalized,
            "note": f"{len(normalized)} kelime bulundu.",
        })

    def handle_ai_import_save(self) -> None:
        """Save multiple AI-imported entries."""
        payload = self.read_json_body()
        entries = payload.get("entries", [])
        if not isinstance(entries, list):
            self.send_json(400, {"status": "error", "note": "entries listesi gerekli."})
            return

        saved_count = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            try:
                save_user_entry(entry)
                saved_count += 1
            except Exception:
                pass

        self.send_json(200, {
            "status": "ok",
            "note": f"{saved_count} kelime kaydedildi.",
            "saved_count": saved_count,
        })

    def send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def find_open_port(start: int) -> int:
    port = start
    while port < start + 50:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex((HOST, port)) != 0:
                return port
        port += 1
    raise RuntimeError("Uygun bir port bulunamadi.")


def main() -> None:
    port = find_open_port(DEFAULT_PORT)
    handler = partial(DictionaryRequestHandler, directory=str(PROJECT_ROOT))
    server = ThreadingHTTPServer((HOST, port), handler)
    url = f"http://{HOST}:{port}/frontend/index.html"

    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Arayuz hazir: {url}")
    print("Durdurmak icin Ctrl+C")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSunucu durduruldu.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
