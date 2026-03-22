#!/usr/bin/env python
"""Download public datasets and glossary seed pages for the dictionary project."""

from __future__ import annotations

import json
import re
import string
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
USER_AGENT = "CodexDictionaryBuilder/1.0 (+public research; contact: local-run)"
REQUEST_DELAY_SECONDS = 1.0
TIMEOUT_SECONDS = 60


class LinkParser(HTMLParser):
    """Collect anchors with their visible text."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = dict(attrs)
        self._current_href = attr_map.get("href")
        self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current_href is None:
            return
        text = " ".join(chunk.strip() for chunk in self._chunks if chunk.strip()).strip()
        self.links.append({"href": self._current_href, "text": text})
        self._current_href = None
        self._chunks = []


@dataclass
class Session:
    last_fetch_by_host: dict[str, float]
    robots_by_host: dict[str, urllib.robotparser.RobotFileParser]

    def wait_for_host(self, host: str) -> None:
        previous = self.last_fetch_by_host.get(host)
        if previous is None:
            return
        elapsed = time.monotonic() - previous
        if elapsed < REQUEST_DELAY_SECONDS:
            time.sleep(REQUEST_DELAY_SECONDS - elapsed)

    def mark_fetch(self, host: str) -> None:
        self.last_fetch_by_host[host] = time.monotonic()


def ensure_dirs() -> None:
    for path in (
        RAW_DIR,
        RAW_DIR / "downloads",
        RAW_DIR / "html" / "autolexikon",
        RAW_DIR / "html" / "kfztech",
        RAW_DIR / "html" / "wirkaufendeinauto",
        RAW_DIR / "html" / "t4-wiki",
        INTERIM_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "page"


def request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )


def get_robot_parser(session: Session, url: str) -> urllib.robotparser.RobotFileParser:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc
    if host in session.robots_by_host:
        return session.robots_by_host[host]

    robots_url = f"{parsed.scheme}://{host}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    try:
        session.wait_for_host(host)
        with urllib.request.urlopen(request(robots_url), timeout=TIMEOUT_SECONDS) as response:
            parser.parse(response.read().decode("utf-8", errors="ignore").splitlines())
        session.mark_fetch(host)
    except Exception:
        parser = urllib.robotparser.RobotFileParser()
        parser.parse([])
    session.robots_by_host[host] = parser
    return parser


def fetch_text(session: Session, url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc
    robots = get_robot_parser(session, url)
    if not robots.can_fetch(USER_AGENT, url):
        raise RuntimeError(f"robots.txt blocked: {url}")

    session.wait_for_host(host)
    with urllib.request.urlopen(request(url), timeout=TIMEOUT_SECONDS) as response:
        body = response.read()
    session.mark_fetch(host)
    return body.decode("utf-8", errors="ignore")


def download_file(session: Session, url: str, destination: Path) -> Path:
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc
    robots = get_robot_parser(session, url)
    if not robots.can_fetch(USER_AGENT, url):
        raise RuntimeError(f"robots.txt blocked: {url}")

    session.wait_for_host(host)
    with urllib.request.urlopen(request(url), timeout=TIMEOUT_SECONDS) as response:
        destination.write_bytes(response.read())
    session.mark_fetch(host)
    return destination


def extract_links(base_url: str, html: str) -> list[dict[str, str]]:
    parser = LinkParser()
    parser.feed(html)
    links: list[dict[str, str]] = []
    for item in parser.links:
        href = item["href"].strip()
        if not href:
            continue
        full_url = urllib.parse.urljoin(base_url, href)
        links.append({"url": full_url, "text": item["text"].strip()})
    return links


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_term_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip("·|/-")
    return text


def filter_candidate_terms(links: Iterable[dict[str, str]], allowed_host: str) -> list[dict[str, str]]:
    blocked_texts = {
        "",
        "home",
        "impressum",
        "datenschutz",
        "kontakt",
        "suche",
        "weiterlesen",
        "menu",
        "menü",
        "startseite",
        "zurück",
        "zurueck",
    }
    results: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for link in links:
        parsed = urllib.parse.urlparse(link["url"])
        if parsed.netloc != allowed_host:
            continue
        text = clean_term_text(link["text"])
        if not text or text.lower() in blocked_texts:
            continue
        if len(text) > 80 or len(text) < 2:
            continue
        if not re.search(r"[A-Za-zÄÖÜäöüß]", text):
            continue
        if text.lower() in list(string.ascii_lowercase):
            continue
        key = (text.lower(), link["url"])
        if key in seen:
            continue
        seen.add(key)
        results.append({"term": text, "url": link["url"]})
    return results


def dedupe_records(records: Iterable[dict[str, str]], key_fields: tuple[str, ...]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    deduped: list[dict[str, str]] = []
    for record in records:
        key = tuple(record.get(field, "").strip().lower() for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def discover_latest_kaikki_dump(session: Session) -> str:
    rawdata_url = "https://kaikki.org/trwiktionary/rawdata.html"
    html = fetch_text(session, rawdata_url)
    candidates = []
    for link in extract_links(rawdata_url, html):
        if re.search(r"raw-wiktextract-data\.jsonl(\.gz)?$", link["url"]):
            candidates.append(link["url"])
    if not candidates:
        raise RuntimeError("Could not find trwiktionary raw dump link on Kaikki rawdata page.")
    return sorted(candidates, key=len)[-1]


def fetch_autolexikon(session: Session) -> dict[str, object]:
    base_url = "https://www.autolexikon.net/"
    root_html = fetch_text(session, base_url)
    (RAW_DIR / "html" / "autolexikon" / "page.html").write_text(root_html, encoding="utf-8")

    index_urls = [base_url]
    for link in extract_links(base_url, root_html):
        if re.search(r"/autolexikon/buchstabe-[a-z]\.html$", link["url"]):
            index_urls.append(link["url"])
    index_urls = sorted(set(index_urls))
    pages: list[dict[str, object]] = []
    seeds: list[dict[str, str]] = []

    for url in index_urls:
        if url == base_url:
            html = root_html
            file_name = "page.html"
            pages.append({"url": url, "status": "ok", "saved_as": file_name})
            continue

        try:
            html = fetch_text(session, url)
        except Exception as exc:
            pages.append({"url": url, "status": "error", "error": str(exc)})
            continue
        file_name = slugify(urllib.parse.urlparse(url).path or "index") + ".html"
        (RAW_DIR / "html" / "autolexikon" / file_name).write_text(html, encoding="utf-8")
        pages.append({"url": url, "status": "ok", "saved_as": file_name})
        for link in extract_links(url, html):
            if re.search(r"/autolexikon/buchstabe-[a-z]/\d+-[^/]+\.html$", link["url"]):
                seeds.append({"term": clean_term_text(link["text"]), "url": link["url"]})

    payload = {
        "source": "autolexikon",
        "pages": pages,
        "seeds": dedupe_records(seeds, ("term", "url")),
    }
    write_json(INTERIM_DIR / "autolexikon_terms.json", payload)
    return payload


def fetch_mein_autolexikon(session: Session) -> dict[str, object]:
    root_url = "https://www.mein-autolexikon.de/lexikon"
    pages: list[dict[str, object]] = []
    categories: list[str] = []
    seeds: list[dict[str, str]] = []

    try:
        root_html = fetch_text(session, root_url)
        (RAW_DIR / "html" / "mein-autolexikon-root.html").write_text(root_html, encoding="utf-8")
        pages.append({"url": root_url, "status": "ok", "saved_as": "mein-autolexikon-root.html"})
        for link in extract_links(root_url, root_html):
            parsed = urllib.parse.urlparse(link["url"])
            if parsed.netloc != "www.mein-autolexikon.de":
                continue
            if re.search(r"^/lexikon/[^/]+$", parsed.path):
                categories.append(link["url"])
    except Exception as exc:
        pages.append({"url": root_url, "status": "error", "error": str(exc)})

    for url in sorted(set(categories)):
        try:
            html = fetch_text(session, url)
        except Exception as exc:
            pages.append({"url": url, "status": "error", "error": str(exc)})
            continue
        file_name = "mein-autolexikon-" + slugify(urllib.parse.urlparse(url).path) + ".html"
        (RAW_DIR / "html" / file_name).write_text(html, encoding="utf-8")
        pages.append({"url": url, "status": "ok", "saved_as": file_name})
        for link in extract_links(url, html):
            parsed = urllib.parse.urlparse(link["url"])
            if parsed.netloc != "www.mein-autolexikon.de":
                continue
            if re.search(r"^/lexikon/[^/]+/[^/]+$", parsed.path):
                seeds.append(
                    {
                        "term": clean_term_text(link["text"]),
                        "url": link["url"],
                        "slug": Path(parsed.path).name,
                    }
                )

    payload = {
        "source": "mein-autolexikon",
        "pages": pages,
        "seeds": dedupe_records(seeds, ("url",)),
    }
    write_json(INTERIM_DIR / "mein_autolexikon_terms.json", payload)
    return payload


def fetch_wirkaufendeinauto(session: Session) -> dict[str, object]:
    glossary_url = "https://www.wirkaufendeinauto.de/auto-glossar/"
    pages: list[dict[str, object]] = []
    seeds: list[dict[str, str]] = []

    try:
        html = fetch_text(session, glossary_url)
        file_name = "auto-glossar.html"
        (RAW_DIR / "html" / "wirkaufendeinauto" / file_name).write_text(html, encoding="utf-8")
        pages.append({"url": glossary_url, "status": "ok", "saved_as": file_name})
        links = extract_links(glossary_url, html)
        seeds = filter_candidate_terms(links, "www.wirkaufendeinauto.de")
    except Exception as exc:
        pages.append({"url": glossary_url, "status": "error", "error": str(exc)})

    payload = {
        "source": "wirkaufendeinauto",
        "pages": pages,
        "seeds": seeds,
    }
    write_json(INTERIM_DIR / "wirkaufendeinauto_terms.json", payload)
    return payload


def fetch_t4_wiki(session: Session) -> dict[str, object]:
    page_url = "https://www.t4-wiki.de/wiki/Abk%C3%BCrzungen"
    pages: list[dict[str, object]] = []
    content = ""
    try:
        content = fetch_text(session, page_url)
        file_name = "abkuerzungen.html"
        (RAW_DIR / "html" / "t4-wiki" / file_name).write_text(content, encoding="utf-8")
        pages.append({"url": page_url, "status": "ok", "saved_as": file_name})
    except Exception as exc:
        pages.append({"url": page_url, "status": "error", "error": str(exc)})

    payload = {
        "source": "t4-wiki",
        "pages": pages,
        "html_saved": bool(content),
    }
    write_json(INTERIM_DIR / "t4_wiki_fetch.json", payload)
    return payload


def fetch_kfztech(session: Session) -> dict[str, object]:
    urls = [
        "https://www.kfztech.de/kfztechnik/sicherheit/ESP.htm",
        "https://www.kfztech.de/kfztechnik/fahrwerk/bremsen/abs.htm",
        "https://www.kfztech.de/kfztechnik/elo/sensoren/drehzahlsensor.htm",
        "https://www.kfztech.de/kfztechnik/elo/can/can_grundlagen_1.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-A-AC.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-D-DI.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-DK-DZ.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-E-EL.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-EM-EZ.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-F.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-H.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-I.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-L.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-M.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-PK-Q.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-R.htm",
        "https://www.kfztech.de/abc/Abkuerzungs-ABC-V.htm",
    ]
    pages: list[dict[str, object]] = []
    for url in urls:
        try:
            html = fetch_text(session, url)
        except Exception as exc:
            pages.append({"url": url, "status": "error", "error": str(exc)})
            continue
        file_name = slugify(urllib.parse.urlparse(url).path or "index") + ".html"
        (RAW_DIR / "html" / "kfztech" / file_name).write_text(html, encoding="utf-8")
        pages.append({"url": url, "status": "ok", "saved_as": file_name})

    payload = {
        "source": "kfztech",
        "pages": pages,
    }
    write_json(INTERIM_DIR / "kfztech_fetch.json", payload)
    return payload


def download_primary_datasets(session: Session) -> dict[str, object]:
    dump_url = discover_latest_kaikki_dump(session)
    suffix = ".gz" if dump_url.endswith(".gz") else ".jsonl"
    dump_destination = RAW_DIR / "downloads" / f"trwiktionary{suffix}"
    download_file(session, dump_url, dump_destination)

    dewiktionary_url = "https://kaikki.org/dewiktionary/raw-wiktextract-data.jsonl.gz"
    dewiktionary_destination = RAW_DIR / "downloads" / "dewiktionary.gz"
    download_file(session, dewiktionary_url, dewiktionary_destination)

    wikdict_url = "https://download.wikdict.com/dictionaries/sqlite/2/de-tr.sqlite3"
    wikdict_destination = RAW_DIR / "downloads" / "de-tr.sqlite3"
    download_file(session, wikdict_url, wikdict_destination)

    payload = {
        "trwiktionary": {
            "url": dump_url,
            "path": str(dump_destination),
        },
        "dewiktionary": {
            "url": dewiktionary_url,
            "path": str(dewiktionary_destination),
        },
        "wikdict_de_tr": {
            "url": wikdict_url,
            "path": str(wikdict_destination),
        },
    }
    write_json(INTERIM_DIR / "downloads.json", payload)
    return payload


def main() -> None:
    ensure_dirs()
    session = Session(last_fetch_by_host={}, robots_by_host={})

    manifest = {
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "datasets": download_primary_datasets(session),
        "autolexikon": fetch_autolexikon(session),
        "mein_autolexikon": fetch_mein_autolexikon(session),
        "kfztech": fetch_kfztech(session),
        "wirkaufendeinauto": fetch_wirkaufendeinauto(session),
        "t4_wiki": fetch_t4_wiki(session),
    }
    write_json(DATA_DIR / "fetch_manifest.json", manifest)
    print(json.dumps(
        {
            "datasets": list(manifest["datasets"].keys()),
            "autolexikon_seed_count": len(manifest["autolexikon"]["seeds"]),
            "mein_autolexikon_seed_count": len(manifest["mein_autolexikon"]["seeds"]),
            "wirkaufendeinauto_seed_count": len(manifest["wirkaufendeinauto"]["seeds"]),
            "t4_wiki_saved": manifest["t4_wiki"]["html_saved"],
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
