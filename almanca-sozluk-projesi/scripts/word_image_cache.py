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
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from PIL import Image, ImageOps

    PIL_AVAILABLE = True
except ModuleNotFoundError:
    Image = ImageOps = None
    PIL_AVAILABLE = False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"
WORD_IMAGE_CACHE_DIR = OUTPUT_DIR / "word_images"
WORD_IMAGE_MANIFEST_PATH = OUTPUT_DIR / "word_image_manifest.json"
WORD_IMAGE_CACHE_LIMIT_BYTES = 200 * 1024 * 1024
WIKIMEDIA_API_UA = "AlmancaTurkceSozluk/desktop"
THUMB_WIDTH = 640
DOWNLOAD_TIMEOUT = 20


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
    manifest = safe_json_load(WORD_IMAGE_MANIFEST_PATH, {})
    entries = manifest.get("entries")
    if not isinstance(entries, dict):
        manifest = {"entries": {}}
    manifest.setdefault("entries", {})
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


def fetch_json(url: str, params: dict[str, Any]) -> dict:
    with urlopen(build_request(url, params), timeout=DOWNLOAD_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def download_bytes(url: str) -> bytes:
    with urlopen(build_request(url), timeout=DOWNLOAD_TIMEOUT) as response:
        return response.read()


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
    candidates = [
        page
        for page in pages
        if page.get("pageimage") and not page.get("missing") and not page_is_disambiguation(page)
    ]
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
        "credit": strip_html((ext.get("Credit") or {}).get("value", "")),
        "license": strip_html((ext.get("LicenseShortName") or {}).get("value", "")),
        "usage_terms": strip_html((ext.get("UsageTerms") or {}).get("value", "")),
        "object_name": strip_html((ext.get("ObjectName") or {}).get("value", "")),
    }


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
    removable = sorted(
        list_existing_entries(manifest),
        key=lambda item: float(item[1].get("last_accessed", 0) or 0),
    )
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


def load_cached_word_image(term: str) -> dict:
    key = image_cache_key(term)
    if not key:
        return {"status": "idle", "note": "Kelime boş."}
    manifest = load_manifest()
    entry = manifest.get("entries", {}).get(key)
    if not entry:
        return {"status": "missing"}
    if entry.get("status") == "not_found":
        return {
            "status": "not_found",
            "note": entry.get("note", "Bu kelime için uygun açık kaynak görsel bulunamadı."),
        }
    path = WORD_IMAGE_CACHE_DIR / str(entry.get("file_name", ""))
    if not path.exists():
        manifest.get("entries", {}).pop(key, None)
        save_manifest(manifest)
        return {"status": "missing"}
    entry["last_accessed"] = time.time()
    save_manifest(manifest)
    return {
        "status": "ok",
        "path": str(path),
        "source_url": entry.get("source_url", ""),
        "page_title": entry.get("page_title", ""),
        "description": entry.get("description", ""),
        "artist": entry.get("artist", ""),
        "license": entry.get("license", ""),
        "credit": entry.get("credit", ""),
        "attribution": entry.get("attribution", ""),
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


def ensure_word_image_cached(term: str) -> dict:
    key = image_cache_key(term)
    if not key:
        return {"status": "idle", "note": "Kelime boş."}

    cached = load_cached_word_image(term)
    if cached.get("status") in {"ok", "not_found"}:
        return cached

    manifest = load_manifest()
    # Önce Almanca Wikipedia, bulamazsa İngilizce'ye fallback
    page = (
        fetch_exact_page(term, "de")
        or search_page(term, "de")
        or fetch_exact_page(term, "en")
        or search_page(term, "en")
    )
    if not page:
        manifest["entries"][key] = {
            "status": "not_found",
            "note": "Bu kelime için uygun açık kaynak görsel bulunamadı.",
            "last_accessed": time.time(),
        }
        save_manifest(manifest)
        return {"status": "not_found", "note": "Bu kelime için uygun açık kaynak görsel bulunamadı."}

    file_name = str(page.get("pageimage", "")).strip()
    file_info = fetch_commons_file_info(file_name)
    if not file_info or not file_info.get("thumburl"):
        manifest["entries"][key] = {
            "status": "not_found",
            "note": "Görsel bulundu ama indirilebilir küçük önizleme alınamadı.",
            "last_accessed": time.time(),
        }
        save_manifest(manifest)
        return {"status": "not_found", "note": "Görsel bulundu ama indirilebilir küçük önizleme alınamadı."}

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

    description = file_info.get("description") or strip_html(page.get("description", "")) or page.get("title", "")
    attribution = " · ".join(part for part in [file_info.get("artist", ""), file_info.get("license", "")] if part)
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
    save_manifest(manifest)
    return {
        "status": "ok",
        "path": str(target_path),
        "source_url": file_info.get("descriptionurl", ""),
        "page_title": page.get("title", ""),
        "description": description,
        "artist": file_info.get("artist", ""),
        "license": file_info.get("license", ""),
        "credit": file_info.get("credit", ""),
        "attribution": attribution,
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
