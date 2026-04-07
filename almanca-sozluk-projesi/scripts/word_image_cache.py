from __future__ import annotations

import hashlib
import io
import json
import re
import time
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from app_runtime import ensure_user_subdirs, resolve_user_path
except ModuleNotFoundError:
    from scripts.app_runtime import ensure_user_subdirs, resolve_user_path

try:
    from PIL import Image, ImageOps

    PIL_AVAILABLE = True
except ModuleNotFoundError:
    Image = ImageOps = None
    PIL_AVAILABLE = False

OUTPUT_DIR = resolve_user_path("output")
WORD_IMAGE_CACHE_DIR = resolve_user_path("output", "word_images")
WORD_IMAGE_MANIFEST_PATH = resolve_user_path("output", "word_image_manifest.json")
WORD_IMAGE_CACHE_LIMIT_BYTES = 200 * 1024 * 1024
WIKIMEDIA_API_UA = "AlmancaTurkceSozluk/desktop"
OPENVERSE_API_UA = "AlmancaTurkceSozluk/desktop (Openverse integration)"
THUMB_WIDTH = 640
DOWNLOAD_TIMEOUT = 20
KEYWORD_RE = re.compile(r"[A-Za-zÄÖÜäöüßÇĞİÖŞÜçğıöşü]{3,}")
ALLOWED_OPEN_LICENSES = {"cc0", "by", "by-sa", "pdm"}
PREFERRED_OPENVERSE_SOURCES = ("wikimedia", "flickr")
PREFERRED_OPENVERSE_PROVIDERS = {"wikimedia", "flickr", "smithsonian", "metropolitan_museum_of_art"}

NON_VISUAL_POS = {"fiil", "zarf", "edat", "zamir", "bağlaç", "baglac", "ünlem", "unlem"}

# Görsel gösterilmeyecek hassas/müstehcen terimler (küçük harf, normalize edilmiş)
SENSITIVE_TERMS: set[str] = {
    "penis", "vulva", "vagina", "klitoris", "klitoriis", "eichel", "vorhaut",
    "hodensack", "hoden", "schamlippe", "schamlippen", "schambein", "schamhaar",
    "anus", "analöffnung", "rektum", "masturbation", "onanie", "ejakulation",
    "ejakulat", "orgasmus", "erektion", "ständer", "glied", "glans",
    "geschlechtsverkehr", "koitus", "kohabitation", "beischlaf", "coitus",
    "fellatio", "cunnilingus", "oralverkehr", "analverkehr",
    "pornografie", "pornographie", "porno", "erotik", "nacktheit",
    "busen", "brustwarze", "nippel", "scrotum", "phallus", "fallos",
    "gebärmutter", "gebarmutter", "scheide", "uterus", "zervix",
}
ABSTRACT_HINTS = {
    "anlam",
    "durum",
    "süreç",
    "surec",
    "özellik",
    "ozellik",
    "neden",
    "sebep",
    "etki",
    "yöntem",
    "yontem",
    "ilişki",
    "iliski",
    "olasılık",
    "olasilik",
}
BAD_MEDIA_HINTS = {
    "logo",
    "flag",
    "wappen",
    "map",
    "karte",
    "poster",
    "cover",
    "album",
    "comic",
    "advertisement",
    "banner",
    "icon",
    "impression",
    "photographer",
    "street photographer",
}
DOMAIN_HINTS = {
    "automotive": {
        "query": ["Kraftfahrzeug", "Fahrzeug", "Automobiltechnik"],
        "match": {"kraftfahrzeug", "fahrzeug", "automobil", "getriebe", "motor", "reifen", "kupplung", "airbag", "lenkung"},
    },
    "building": {
        "query": ["Gebäude", "Bauwerk"],
        "match": {"gebäude", "gebaude", "bauwerk", "haus", "garage", "carport", "building"},
    },
    "electronics": {
        "query": ["Elektronik", "Technik"],
        "match": {"elektronik", "sensor", "gerät", "geraet", "schaltung", "circuit", "device"},
    },
    "computer": {
        "query": ["Informatik", "Computer"],
        "match": {"computer", "software", "hardware", "rechner", "informatik", "program"},
    },
}


class HTMLTextStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def strip_html(value: str) -> str:
    parser = HTMLTextStripper()
    parser.feed(str(value or ""))
    parser.close()
    return normalize_whitespace(parser.get_text())


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().casefold()


def keyword_tokens(value: str) -> list[str]:
    return [normalize_text(token) for token in KEYWORD_RE.findall(str(value or ""))]


def unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = normalize_whitespace(value)
        if not clean:
            continue
        key = normalize_text(clean)
        if key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result


def strip_known_article(term: str) -> str:
    parts = normalize_whitespace(term).split(" ", 1)
    if len(parts) == 2 and normalize_text(parts[0]) in {"der", "die", "das"}:
        return parts[1]
    return normalize_whitespace(term)


def image_cache_key(term: str) -> str:
    return normalize_text(strip_known_article(term))


def safe_slug(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "kelime"


def safe_json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_manifest() -> dict:
    ensure_user_subdirs()
    manifest = safe_json_load(WORD_IMAGE_MANIFEST_PATH, {})
    if not isinstance(manifest, dict):
        manifest = {}
    entries = manifest.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    manifest["entries"] = entries
    manifest.setdefault("updated_at", 0)
    return manifest


def save_manifest(manifest: dict) -> None:
    manifest["updated_at"] = int(time.time())
    write_json(WORD_IMAGE_MANIFEST_PATH, manifest)


def build_request(url: str, params: dict[str, Any] | None = None) -> Request:
    target = url
    if params:
        target = f"{url}?{urlencode(params)}"
    return Request(target, headers={"User-Agent": WIKIMEDIA_API_UA})


def build_request_with_ua(url: str, user_agent: str, params: dict[str, Any] | None = None) -> Request:
    target = url
    if params:
        target = f"{url}?{urlencode(params)}"
    return Request(target, headers={"User-Agent": user_agent})


def fetch_json(url: str, params: dict[str, Any]) -> dict:
    request = build_request(url, params)
    for attempt in range(2):
        try:
            with urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError):
            if attempt == 1:
                return {}
            time.sleep(0.8)
    return {}


def download_bytes(url: str) -> bytes:
    request = build_request(url)
    for attempt in range(2):
        try:
            with urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                return response.read()
        except (HTTPError, URLError):
            if attempt == 1:
                raise
            time.sleep(0.8)
    raise RuntimeError("download failed")


def fetch_json_with_ua(url: str, params: dict[str, Any], user_agent: str) -> dict:
    request = build_request_with_ua(url, user_agent, params)
    for attempt in range(2):
        try:
            with urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError):
            if attempt == 1:
                return {}
            time.sleep(0.8)
    return {}


def normalize_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    categories = context.get("kategoriler") or []
    if not isinstance(categories, list):
        categories = [categories]
    return {
        "tur": normalize_text(context.get("tur", "")),
        "turkce": normalize_whitespace(context.get("turkce", "")),
        "tanim_almanca": normalize_whitespace(context.get("tanim_almanca", "")),
        "aciklama_turkce": normalize_whitespace(context.get("aciklama_turkce", "")),
        "kategoriler": [normalize_whitespace(item) for item in categories if normalize_whitespace(item)],
        "gorsel_grubu": normalize_whitespace(context.get("gorsel_grubu", "")),
        "gorsel_ipucu": normalize_whitespace(context.get("gorsel_ipucu", "")),
        "gorsel_notu": normalize_whitespace(context.get("gorsel_notu", "")),
    }


def infer_context_domains(context: dict[str, Any]) -> set[str]:
    combined = " ".join(
        [
            context.get("tur", ""),
            context.get("turkce", ""),
            context.get("tanim_almanca", ""),
            context.get("aciklama_turkce", ""),
            context.get("gorsel_grubu", ""),
            context.get("gorsel_ipucu", ""),
            context.get("gorsel_notu", ""),
            " ".join(context.get("kategoriler", [])),
        ]
    )
    tokens = set(keyword_tokens(combined))
    domains: set[str] = set()
    if tokens & {"otomotiv", "araç", "arac", "motor", "getriebe", "kupplung", "fren", "direksiyon", "lastik", "airbag", "fahrzeug"}:
        domains.add("automotive")
    if tokens & {"garaj", "bina", "ev", "yapı", "yapi", "gebäude", "gebaude", "haus", "building"}:
        domains.add("building")
    if tokens & {"elektronik", "elektrik", "sensör", "sensor", "devre", "şalter", "schaltung", "gerät", "geraet"}:
        domains.add("electronics")
    if tokens & {"bilgisayar", "rechner", "software", "hardware", "computer", "informatik"}:
        domains.add("computer")
    return domains


def extract_context_keywords(context: dict[str, Any]) -> list[str]:
    keywords: list[str] = []
    for value in [
        context.get("turkce", ""),
        context.get("tanim_almanca", ""),
        context.get("aciklama_turkce", ""),
        context.get("gorsel_grubu", ""),
        context.get("gorsel_ipucu", ""),
        context.get("gorsel_notu", ""),
        " ".join(context.get("kategoriler", [])),
    ]:
        for token in keyword_tokens(value):
            if token in ABSTRACT_HINTS or len(token) < 4:
                continue
            keywords.append(token)
    return unique_texts(keywords)[:8]


def is_visualizable_context(context: dict[str, Any]) -> bool:
    if not context:
        return True
    pos = context.get("tur", "")
    domains = infer_context_domains(context)
    if pos in NON_VISUAL_POS:
        return False
    if pos in {"fiil", "zarf", "sıfat", "sifat"} and not domains:
        return False
    if not domains and (set(keyword_tokens(context.get("turkce", ""))) & ABSTRACT_HINTS):
        return False
    return True


def build_query_variants(term: str, context: dict[str, Any]) -> list[str]:
    clean = normalize_whitespace(strip_known_article(term))
    variants = [clean]
    for domain in infer_context_domains(context):
        for hint in DOMAIN_HINTS.get(domain, {}).get("query", []):
            variants.append(f"{clean} {hint}")
    for keyword in extract_context_keywords(context)[:2]:
        variants.append(f"{clean} {keyword}")
    return unique_texts(variants)[:6]


def page_is_disambiguation(page: dict) -> bool:
    props = page.get("pageprops", {}) or {}
    description = normalize_text(page.get("description", ""))
    return "disambiguation" in props or "begriffsklarungsseite" in description


def score_page(page: dict, term: str) -> tuple[int, int]:
    title = normalize_text(page.get("title", ""))
    target = normalize_text(strip_known_article(term))
    exact = int(title == target)
    starts = int(title.startswith(target))
    return exact, starts


def choose_page(term: str, pages: list[dict]) -> dict | None:
    candidates = [page for page in pages if page.get("pageimage") and not page.get("missing") and not page_is_disambiguation(page)]
    if not candidates:
        return None
    candidates.sort(key=lambda page: (*score_page(page, term), -int(page.get("index", 9999))), reverse=True)
    return candidates[0]


def fetch_exact_page(term: str, lang: str = "de") -> dict | None:
    clean = normalize_whitespace(strip_known_article(term))
    if not clean:
        return None
    variants = [clean]
    if clean[:1].islower():
        variants.append(clean[:1].upper() + clean[1:])
    params = {
        "action": "query",
        "titles": "|".join(dict.fromkeys(variants)),
        "prop": "pageimages|description|pageprops",
        "piprop": "name|original",
        "format": "json",
        "formatversion": 2,
    }
    pages = fetch_json(f"https://{lang}.wikipedia.org/w/api.php", params).get("query", {}).get("pages", [])
    return choose_page(clean, pages)


def search_page(term: str, lang: str = "de") -> dict | None:
    clean = normalize_whitespace(strip_known_article(term))
    if not clean:
        return None
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": clean,
        "gsrnamespace": 0,
        "gsrlimit": 8,
        "prop": "pageimages|description|pageprops",
        "piprop": "name|original",
        "format": "json",
        "formatversion": 2,
    }
    pages = fetch_json(f"https://{lang}.wikipedia.org/w/api.php", params).get("query", {}).get("pages", [])
    return choose_page(clean, pages)


def fetch_commons_file_info(file_name: str) -> dict | None:
    if not file_name:
        return None
    title = file_name if file_name.startswith("File:") else f"File:{file_name}"
    params = {
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": THUMB_WIDTH,
        "format": "json",
        "formatversion": 2,
    }
    pages = fetch_json("https://commons.wikimedia.org/w/api.php", params).get("query", {}).get("pages", [])
    if not pages:
        return None
    imageinfo = (pages[0].get("imageinfo") or [None])[0]
    if not imageinfo:
        return None
    ext = imageinfo.get("extmetadata", {}) or {}
    return {
        "thumburl": imageinfo.get("thumburl") or imageinfo.get("url"),
        "descriptionurl": imageinfo.get("descriptionurl", ""),
        "image_url": imageinfo.get("url", ""),
        "title": pages[0].get("title", title),
        "description": strip_html((ext.get("ImageDescription") or {}).get("value", "")),
        "artist": strip_html((ext.get("Artist") or {}).get("value", "")),
        "creator_url": "",
        "credit": strip_html((ext.get("Credit") or {}).get("value", "")),
        "license": strip_html((ext.get("LicenseShortName") or {}).get("value", "")),
        "license_code": strip_html((ext.get("LicenseShortName") or {}).get("value", "")),
        "license_url": strip_html((ext.get("LicenseUrl") or {}).get("value", "")),
        "usage_terms": strip_html((ext.get("UsageTerms") or {}).get("value", "")),
        "object_name": strip_html((ext.get("ObjectName") or {}).get("value", "")),
        "provider": "wikimedia",
        "source_name": "Wikimedia Commons",
        "attribution": "",
    }


def search_commons_files(query: str, limit: int = 6) -> list[dict[str, Any]]:
    clean = normalize_whitespace(query)
    if not clean:
        return []
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": clean,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": THUMB_WIDTH,
        "format": "json",
        "formatversion": 2,
    }
    pages = fetch_json("https://commons.wikimedia.org/w/api.php", params).get("query", {}).get("pages", [])
    results: list[dict[str, Any]] = []
    for page in pages:
        imageinfo = (page.get("imageinfo") or [None])[0]
        if not imageinfo:
            continue
        ext = imageinfo.get("extmetadata", {}) or {}
        results.append(
            {
                "kind": "commons",
                "page_title": page.get("title", ""),
                "page_description": "",
                "query": clean,
                "file_info": {
                    "thumburl": imageinfo.get("thumburl") or imageinfo.get("url"),
                    "descriptionurl": imageinfo.get("descriptionurl", ""),
                    "image_url": imageinfo.get("url", ""),
                    "title": page.get("title", ""),
                    "description": strip_html((ext.get("ImageDescription") or {}).get("value", "")),
                    "artist": strip_html((ext.get("Artist") or {}).get("value", "")),
                    "creator_url": "",
                    "credit": strip_html((ext.get("Credit") or {}).get("value", "")),
                    "license": strip_html((ext.get("LicenseShortName") or {}).get("value", "")),
                    "license_code": strip_html((ext.get("LicenseShortName") or {}).get("value", "")),
                    "license_url": strip_html((ext.get("LicenseUrl") or {}).get("value", "")),
                    "usage_terms": strip_html((ext.get("UsageTerms") or {}).get("value", "")),
                    "object_name": strip_html((ext.get("ObjectName") or {}).get("value", "")),
                    "provider": "wikimedia",
                    "source_name": "Wikimedia Commons",
                    "attribution": "",
                    "category": "",
                },
            }
        )
    return results


def normalize_license_code(value: str) -> str:
    text = normalize_text(value)
    if text in {"cc by", "by"}:
        return "by"
    if text in {"cc by-sa", "by-sa"}:
        return "by-sa"
    if text in {"cc0", "cc 0"}:
        return "cc0"
    if text in {"public domain mark", "pdm"}:
        return "pdm"
    return text


def has_allowed_open_license(file_info: dict[str, Any]) -> bool:
    license_code = normalize_license_code(file_info.get("license_code") or file_info.get("license") or "")
    if license_code in ALLOWED_OPEN_LICENSES:
        return True
    license_url = normalize_text(file_info.get("license_url", ""))
    return any(marker in license_url for marker in ("/by/", "/by-sa/", "/zero/1.0/", "/publicdomain/mark/1.0/"))


def search_openverse_images(query: str, limit: int = 6) -> list[dict[str, Any]]:
    clean = normalize_whitespace(query)
    if not clean:
        return []
    params = {
        "q": clean,
        "page_size": limit,
        "license": ",".join(sorted(ALLOWED_OPEN_LICENSES)),
        "source": ",".join(PREFERRED_OPENVERSE_SOURCES),
    }
    payload = fetch_json_with_ua("https://api.openverse.org/v1/images/", params, OPENVERSE_API_UA)
    results: list[dict[str, Any]] = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        provider = normalize_whitespace(item.get("provider", ""))
        if provider and normalize_text(provider) not in PREFERRED_OPENVERSE_PROVIDERS:
            continue
        file_info = {
            "thumburl": item.get("thumbnail") or item.get("url") or "",
            "descriptionurl": item.get("foreign_landing_url") or item.get("detail_url") or "",
            "image_url": item.get("url") or "",
            "title": normalize_whitespace(item.get("title", "")),
            "description": "",
            "artist": normalize_whitespace(item.get("creator", "")),
            "creator_url": normalize_whitespace(item.get("creator_url", "")),
            "credit": normalize_whitespace(item.get("attribution", "")),
            "license": normalize_whitespace(item.get("license", "")),
            "license_code": normalize_whitespace(item.get("license", "")),
            "license_url": normalize_whitespace(item.get("license_url", "")),
            "usage_terms": normalize_whitespace(item.get("license_url", "")),
            "object_name": normalize_whitespace(item.get("title", "")),
            "provider": provider,
            "source_name": normalize_whitespace(item.get("source", "")) or provider,
            "attribution": normalize_whitespace(item.get("attribution", "")),
            "category": normalize_whitespace(item.get("category", "")),
        }
        if not file_info["thumburl"] or not has_allowed_open_license(file_info):
            continue
        tags = [normalize_whitespace(tag.get("name", "")) for tag in (item.get("tags") or []) if isinstance(tag, dict)]
        results.append(
            {
                "kind": "openverse",
                "page_title": normalize_whitespace(item.get("title", "")) or clean,
                "page_description": " ".join(tag for tag in tags[:8] if tag),
                "query": clean,
                "file_info": file_info,
            }
        )
    return results


def build_candidate_from_page(page: dict, query: str, lang: str) -> dict[str, Any] | None:
    file_name = str(page.get("pageimage", "")).strip()
    if not file_name:
        return None
    file_info = fetch_commons_file_info(file_name)
    if not file_info or not file_info.get("thumburl"):
        return None
    return {
        "kind": f"wiki:{lang}",
        "page_title": page.get("title", ""),
        "page_description": page.get("description", ""),
        "query": query,
        "file_info": file_info,
    }


def collect_image_candidates(term: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for query in build_query_variants(term, context):
        for lang in ("de", "en"):
            for fetcher in (fetch_exact_page, search_page):
                page = fetcher(query, lang)
                if not page:
                    continue
                candidate = build_candidate_from_page(page, query, lang)
                if not candidate:
                    continue
                key = (normalize_text(candidate.get("page_title", "")), normalize_text(candidate.get("file_info", {}).get("title", "")))
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
        for candidate in search_commons_files(query):
            key = (normalize_text(candidate.get("page_title", "")), normalize_text(candidate.get("file_info", {}).get("title", "")))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
        for candidate in search_openverse_images(query):
            key = (normalize_text(candidate.get("page_title", "")), normalize_text(candidate.get("file_info", {}).get("title", "")))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    return candidates


def candidate_text(candidate: dict[str, Any]) -> str:
    file_info = candidate.get("file_info", {}) or {}
    return normalize_text(
        " ".join(
            [
                candidate.get("page_title", ""),
                candidate.get("page_description", ""),
                file_info.get("title", ""),
                file_info.get("description", ""),
                file_info.get("object_name", ""),
                candidate.get("query", ""),
            ]
        )
    )


def score_candidate(candidate: dict[str, Any], term: str, context: dict[str, Any]) -> tuple[int, int]:
    text = candidate_text(candidate)
    base = normalize_text(strip_known_article(term))
    page_title = normalize_text(candidate.get("page_title", ""))
    file_title = normalize_text((candidate.get("file_info", {}) or {}).get("title", ""))
    file_description = normalize_text(
        " ".join(
            [
                (candidate.get("file_info", {}) or {}).get("description", ""),
                (candidate.get("file_info", {}) or {}).get("object_name", ""),
            ]
        )
    )
    score = 0
    context_hits = 0

    if page_title == base or file_title == base:
        score += 14
    elif page_title.startswith(base) or file_title.startswith(base):
        score += 9
    elif base and base in text:
        score += 4

    if base and (base in file_title or base in file_description):
        score += 5
    elif page_title == base:
        score -= 6

    for keyword in extract_context_keywords(context):
        if keyword and keyword in text:
            score += 2
            context_hits += 1

    for domain in infer_context_domains(context):
        if any(hint in text for hint in DOMAIN_HINTS.get(domain, {}).get("match", set())):
            score += 5
            context_hits += 2

    if any(hint in text for hint in BAD_MEDIA_HINTS):
        score -= 8
        if infer_context_domains(context):
            score -= 6
    if candidate.get("kind") == "commons" and normalize_text(candidate.get("query", "")) != base:
        score += 2
    if candidate.get("kind") in {"commons", "wiki:de", "wiki:en"}:
        score += 2
    if candidate.get("kind") == "openverse":
        provider = normalize_text((candidate.get("file_info", {}) or {}).get("provider", ""))
        if provider == "wikimedia":
            score += 2
        elif provider == "flickr":
            score += 1
        if normalize_text((candidate.get("file_info", {}) or {}).get("category", "")) == "illustration":
            score -= 1

    return score, context_hits


def manifest_entry_is_relevant(term: str, entry: dict[str, Any], context: dict[str, Any] | None = None) -> bool:
    normalized_context = normalize_context(context)
    if not normalized_context:
        return True
    if not is_visualizable_context(normalized_context):
        return False
    candidate = {
        "kind": "manifest",
        "page_title": entry.get("page_title", ""),
        "page_description": "",
        "query": strip_known_article(term),
        "file_info": {
            "title": entry.get("page_title", ""),
            "description": entry.get("description", ""),
            "object_name": entry.get("description", ""),
        },
    }
    score, context_hits = score_candidate(candidate, term, normalized_context)
    has_domain = bool(infer_context_domains(normalized_context))
    return score >= (9 if has_domain else 4) and (context_hits > 0 or not has_domain)


def build_cache_filename(cache_key: str) -> str:
    slug = safe_slug(cache_key)[:48]
    digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{digest}.jpg"


def list_existing_entries(manifest: dict) -> list[tuple[str, dict]]:
    entries = manifest.get("entries", {})
    result: list[tuple[str, dict]] = []
    for key, entry in entries.items():
        path = WORD_IMAGE_CACHE_DIR / str(entry.get("file_name", ""))
        if path.exists():
            result.append((key, entry))
    return result


def get_cache_usage_bytes(manifest: dict) -> int:
    total = 0
    for _key, entry in list_existing_entries(manifest):
        total += int(entry.get("file_size", 0) or 0)
    return total


def prune_cache_for_bytes(manifest: dict, required_bytes: int) -> bool:
    current = get_cache_usage_bytes(manifest)
    if current + required_bytes <= WORD_IMAGE_CACHE_LIMIT_BYTES:
        return True
    removable = sorted(list_existing_entries(manifest), key=lambda item: float(item[1].get("last_accessed", 0) or 0))
    for key, entry in removable:
        path = WORD_IMAGE_CACHE_DIR / str(entry.get("file_name", ""))
        try:
            if path.exists():
                path.unlink()
        except OSError:
            continue
        manifest.get("entries", {}).pop(key, None)
        current = get_cache_usage_bytes(manifest)
        if current + required_bytes <= WORD_IMAGE_CACHE_LIMIT_BYTES:
            return True
    return current + required_bytes <= WORD_IMAGE_CACHE_LIMIT_BYTES


def load_cached_word_image(term: str, context: dict[str, Any] | None = None) -> dict:
    key = image_cache_key(term)
    if not key:
        return {"status": "idle", "note": "Kelime boş."}
    manifest = load_manifest()
    entry = manifest.get("entries", {}).get(key)
    if not entry:
        return {"status": "missing"}
    if entry.get("status") == "not_found":
        return {"status": "not_found", "note": entry.get("note", "Bu kelime için uygun açık kaynak görsel bulunamadı.")}
    path = WORD_IMAGE_CACHE_DIR / str(entry.get("file_name", ""))
    if not path.exists():
        manifest.get("entries", {}).pop(key, None)
        save_manifest(manifest)
        return {"status": "missing"}
    if not manifest_entry_is_relevant(term, entry, context):
        return {"status": "missing"}
    entry["last_accessed"] = time.time()
    save_manifest(manifest)
    return {
        "status": "ok",
        "path": str(path),
        "source_url": entry.get("source_url", ""),
        "source_name": entry.get("source_name", ""),
        "page_title": entry.get("page_title", ""),
        "description": entry.get("description", ""),
        "artist": entry.get("artist", ""),
        "creator_url": entry.get("creator_url", ""),
        "license": entry.get("license", ""),
        "license_url": entry.get("license_url", ""),
        "credit": entry.get("credit", ""),
        "attribution": entry.get("attribution", ""),
        "provider": entry.get("provider", ""),
        "review_state": entry.get("review_state", ""),
        "match_score": entry.get("match_score", 0),
        "from_cache": True,
    }


def save_image_bytes(path: Path, payload: bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if PIL_AVAILABLE:
        with Image.open(io.BytesIO(payload)) as source_image:
            image = ImageOps.exif_transpose(source_image)
            if image.mode not in {"RGB", "L"}:
                flattened = Image.new("RGB", image.size, "#ffffff")
                flattened.paste(image, mask=image.getchannel("A") if "A" in image.getbands() else None)
                image = flattened
            elif image.mode != "RGB":
                image = image.convert("RGB")
            image.thumbnail((900, 900), Image.Resampling.LANCZOS)
            image.save(path, format="JPEG", quality=82, optimize=True, progressive=True)
    else:
        path.write_bytes(payload)
    return path.stat().st_size


def ensure_word_image_cached(term: str, context: dict[str, Any] | None = None, force_refresh: bool = False) -> dict:
    key = image_cache_key(term)
    if not key:
        return {"status": "idle", "note": "Kelime boş."}

    # Hassas/müstehcen terimler için görsel gösterilmez
    term_lower = unicodedata.normalize("NFC", term.lower().strip())
    if term_lower in SENSITIVE_TERMS:
        manifest = load_manifest()
        manifest["entries"][key] = {
            "status": "not_found",
            "note": "Bu terim için görsel gösterilmiyor.",
            "last_accessed": time.time(),
        }
        save_manifest(manifest)
        return {"status": "not_found", "note": "Bu terim için görsel gösterilmiyor."}

    normalized_context = normalize_context(context)
    if normalized_context and not is_visualizable_context(normalized_context):
        manifest = load_manifest()
        manifest["entries"][key] = {
            "status": "not_found",
            "note": "Bu kayıt için güvenilir ve somut bir açık kaynak görsel önerilmedi.",
            "last_accessed": time.time(),
        }
        save_manifest(manifest)
        return {"status": "not_found", "note": "Bu kayıt için güvenilir ve somut bir açık kaynak görsel önerilmedi."}

    cached = load_cached_word_image(term, normalized_context)
    if not force_refresh and cached.get("status") in {"ok", "not_found"}:
        return cached

    manifest = load_manifest()
    candidates = collect_image_candidates(term, normalized_context)
    scored_candidates: list[tuple[int, int, dict[str, Any]]] = []
    for candidate in candidates:
        score, context_hits = score_candidate(candidate, term, normalized_context)
        scored_candidates.append((score, context_hits, candidate))
    scored_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)

    best_score, best_context_hits, best_candidate = scored_candidates[0] if scored_candidates else (-999, 0, None)
    min_score = 9 if infer_context_domains(normalized_context) else 4
    if not best_candidate or best_score < min_score or (infer_context_domains(normalized_context) and best_context_hits <= 0):
        manifest["entries"][key] = {
            "status": "not_found",
            "note": "Bu kelime için bağlama uygun güvenilir açık kaynak görsel bulunamadı.",
            "last_accessed": time.time(),
        }
        save_manifest(manifest)
        return {"status": "not_found", "note": "Bu kelime için bağlama uygun güvenilir açık kaynak görsel bulunamadı."}

    file_info = best_candidate.get("file_info", {}) or {}
    if not file_info.get("thumburl"):
        manifest["entries"][key] = {
            "status": "not_found",
            "note": "Görsel adayı bulundu ama indirilebilir küçük önizleme alınamadı.",
            "last_accessed": time.time(),
        }
        save_manifest(manifest)
        return {"status": "not_found", "note": "Görsel adayı bulundu ama indirilebilir küçük önizleme alınamadı."}

    image_bytes = download_bytes(file_info["thumburl"])
    file_name_on_disk = build_cache_filename(key)
    target_path = WORD_IMAGE_CACHE_DIR / file_name_on_disk

    if not prune_cache_for_bytes(manifest, max(len(image_bytes), 1)):
        return {"status": "cache_full", "note": "200 MB görsel sınırı dolu. Yeni görsel indirilmedi."}

    file_size = save_image_bytes(target_path, image_bytes)
    if not prune_cache_for_bytes(manifest, file_size):
        try:
            target_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {"status": "cache_full", "note": "200 MB görsel sınırı dolu. Yeni görsel indirilmedi."}

    description = (
        file_info.get("object_name")
        or file_info.get("description")
        or best_candidate.get("page_description", "")
        or best_candidate.get("page_title", "")
    )
    attribution = normalize_whitespace(
        file_info.get("attribution")
        or " | ".join(part for part in [file_info.get("artist", ""), file_info.get("license", "")] if part)
    )
    manifest["entries"][key] = {
        "status": "ok",
        "file_name": file_name_on_disk,
        "file_size": file_size,
        "source_url": file_info.get("descriptionurl", ""),
        "source_name": file_info.get("source_name", "") or file_info.get("provider", "") or best_candidate.get("kind", ""),
        "image_url": file_info.get("image_url", ""),
        "page_title": best_candidate.get("page_title", ""),
        "description": description,
        "artist": file_info.get("artist", ""),
        "creator_url": file_info.get("creator_url", ""),
        "credit": file_info.get("credit", ""),
        "license": file_info.get("license", ""),
        "license_url": file_info.get("license_url", ""),
        "attribution": attribution,
        "provider": file_info.get("provider", "") or best_candidate.get("kind", ""),
        "review_state": "auto",
        "match_score": best_score,
        "last_accessed": time.time(),
    }
    save_manifest(manifest)
    return {
        "status": "ok",
        "path": str(target_path),
        "source_url": file_info.get("descriptionurl", ""),
        "source_name": file_info.get("source_name", "") or file_info.get("provider", "") or best_candidate.get("kind", ""),
        "page_title": best_candidate.get("page_title", ""),
        "description": description,
        "artist": file_info.get("artist", ""),
        "creator_url": file_info.get("creator_url", ""),
        "license": file_info.get("license", ""),
        "license_url": file_info.get("license_url", ""),
        "credit": file_info.get("credit", ""),
        "attribution": attribution,
        "provider": file_info.get("provider", "") or best_candidate.get("kind", ""),
        "review_state": "auto",
        "match_score": best_score,
        "from_cache": False,
    }


def prefetch_terms(terms: list[str], stop_when_full: bool = True) -> dict:
    stats = {"ok": 0, "not_found": 0, "cache_full": 0, "error": 0, "processed": 0}
    for term in terms:
        clean = normalize_whitespace(term)
        if not clean:
            continue
        try:
            payload = ensure_word_image_cached(clean)
        except Exception:
            stats["error"] += 1
            stats["processed"] += 1
            continue
        status = payload.get("status", "error")
        stats[status] = stats.get(status, 0) + 1
        stats["processed"] += 1
        if stop_when_full and status == "cache_full":
            break
    stats["usage_bytes"] = get_cache_usage_bytes(load_manifest())
    return stats
