#!/usr/bin/env python
"""Desktop dictionary application with a simplified local-first UX."""

from __future__ import annotations

import copy
import json
import os
import queue
import random
import re
import sqlite3
import threading
import time
import tkinter as tk
import unicodedata
import webbrowser
from ctypes import byref, c_int, sizeof, windll
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

try:
    from PIL import Image, ImageOps, ImageTk

    PIL_AVAILABLE = True
except ModuleNotFoundError:
    Image = ImageOps = ImageTk = None
    PIL_AVAILABLE = False

try:
    import argostranslate.translate as argos_translate

    ARGOS_TRANSLATE_AVAILABLE = True
except ModuleNotFoundError:
    argos_translate = None
    ARGOS_TRANSLATE_AVAILABLE = False

try:
    from run_frontend import (
        build_runtime_record,
        fetch_dwds_definition,
        list_user_entries,
        lookup_german_definition,
        lookup_turkish_definition,
        lookup_turkish_definition_online,
        save_user_entry,
        validate_user_entry,
    )
except ModuleNotFoundError:
    from scripts.run_frontend import (
        build_runtime_record,
        fetch_dwds_definition,
        list_user_entries,
        lookup_german_definition,
        lookup_turkish_definition,
        lookup_turkish_definition_online,
        save_user_entry,
        validate_user_entry,
    )

try:
    from word_image_cache import (
        WORD_IMAGE_CACHE_LIMIT_BYTES,
        ensure_word_image_cached,
        image_cache_key,
        load_cached_word_image,
    )
except ModuleNotFoundError:
    from scripts.word_image_cache import (
        WORD_IMAGE_CACHE_LIMIT_BYTES,
        ensure_word_image_cached,
        image_cache_key,
        load_cached_word_image,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"
MANUAL_DIR = PROJECT_ROOT / "data" / "manual"
ASSETS_DIR = PROJECT_ROOT / "assets" / "trees"
BRANDING_DIR = PROJECT_ROOT / "assets" / "branding"
DICTIONARY_PATH = OUTPUT_DIR / "dictionary.json"
SUMMARY_PATH = OUTPUT_DIR / "source_summary.json"
SETTINGS_PATH = MANUAL_DIR / "desktop_settings.json"
ENTRY_HELP_PATH = MANUAL_DIR / "kelime_ekleme_yardimi.md"
TUTORIAL_PATH = MANUAL_DIR / "uygulama_tutorial.json"
USER_ENTRIES_PATH = MANUAL_DIR / "user_entries.json"
WIKDICT_PATH = PROJECT_ROOT / "data" / "raw" / "downloads" / "de-tr.sqlite3"
APP_ICON_PNG_PATH = BRANDING_DIR / "dictionary_logo.png"
APP_ICON_ICO_PATH = BRANDING_DIR / "dictionary_logo.ico"
HERO_TREE_IMAGE_PATH = ASSETS_DIR / "hero_tree.png"
DETAIL_TREE_IMAGE_PATH = ASSETS_DIR / "detail_tree.png"
HERO_TREE_BG_IMAGE_PATH = ASSETS_DIR / "hero_tree_bg.png"
LEAVES_BG_IMAGE_PATH = ASSETS_DIR / "leaves_bg.png"
HERO_TREE_MIRROR_IMAGE_PATH = ASSETS_DIR / "hero_tree_mirror.png"
DETAIL_TREE_MIRROR_IMAGE_PATH = ASSETS_DIR / "detail_tree_mirror.png"
HERO_TREE_BG_MIRROR_IMAGE_PATH = ASSETS_DIR / "hero_tree_bg_mirror.png"
HERO_TREE_BG_WARM_IMAGE_PATH = ASSETS_DIR / "hero_tree_bg_warm.png"
WINDOWS_APP_ID = "Ozan.AlmancaTurkceSozluk"
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
_google_translate_sentence_cache: dict[str, str] = {}
_libretranslate_text_cache: dict[str, dict] = {}
_argos_translate_text_cache = _libretranslate_text_cache
LIBRETRANSLATE_DEFAULT_URL = "https://libretranslate.com/translate"
LIBRETRANSLATE_PUBLIC_FALLBACK_URLS = (
    "https://translate.cutie.dating/translate",
    "https://translate.fedilab.app/translate",
)
LIBRETRANSLATE_TIMEOUT_SECONDS = 12
CUSTOM_ART_SUPPORTED_SUFFIXES = (
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.webp",
    "*.bmp",
    "*.gif",
    "*.tif",
    "*.tiff",
)

BACKGROUND_IMAGE_OPTIONS = {
    "none": {"label": "Kapalı", "path": None},
    "tree": {"label": "Yumuşak Orman", "path": HERO_TREE_BG_IMAGE_PATH},
    "tall_tree": {"label": "Dik Ağaç", "path": HERO_TREE_IMAGE_PATH},
    "nature_line": {"label": "İnce Doğa Çizimi", "path": DETAIL_TREE_IMAGE_PATH},
    "leaves_bg": {"label": "Yaprak Dokusu", "path": LEAVES_BG_IMAGE_PATH},
    "tall_tree_mirror": {"label": "Dik Ağaç Sağ", "path": HERO_TREE_MIRROR_IMAGE_PATH},
    "nature_line_mirror": {"label": "İnce Çizim Sağ", "path": DETAIL_TREE_MIRROR_IMAGE_PATH},
    "tree_mirror": {"label": "Yumuşak Orman Sağ", "path": HERO_TREE_BG_MIRROR_IMAGE_PATH},
    "tree_warm": {"label": "Sıcak Orman", "path": HERO_TREE_BG_WARM_IMAGE_PATH},
}

ART_SLOT_LIMITS = {
    "hero": (300, 110),
    "search": (88, 66),
    "results": (128, 96),
    "detail": (150, 115),
}

ART_SLOT_EXPANDED_LIMITS = {
    "hero": (420, 150),
    "search": (150, 104),
    "results": (210, 150),
    "detail": (240, 180),
}

ART_SLOT_LAYOUTS = {
    "hero": {"min_width": 1460, "anchor": "ne", "relx": 1.0, "rely": 0.0, "x": 34, "y": 18},
    "search": {"min_width": 1700, "anchor": "ne", "relx": 1.0, "rely": 0.0, "x": 18, "y": 10},
    "results": {"min_width": 1620, "anchor": "se", "relx": 1.0, "rely": 1.0, "x": 24, "y": 18},
    "detail": {"min_width": 1320, "anchor": "se", "relx": 1.0, "rely": 1.0, "x": 32, "y": 18},
}

RIGHT_ART_SIDEBAR_WIDTH = 360
RIGHT_ART_MAIN_SIZE = (320, 320)
RIGHT_ART_ACCENT_SIZE = (320, 210)
RIGHT_ART_SIDEBAR_WIDTH_EXPANDED = 420
RIGHT_ART_MAIN_SIZE_EXPANDED = (380, 380)
RIGHT_ART_ACCENT_SIZE_EXPANDED = (380, 250)
RIGHT_ART_SIDEBAR_MIN_WIDTH = 280
MAIN_CONTENT_MIN_WIDTH = 760
RIGHT_ART_FRAME_BORDER = 1
RIGHT_ART_CARD_HORIZONTAL_GAP = 18
ART_LAYOUT_PRESETS = {
    "quarter": {"label": "1/4 doğa • 2/4 sözlük • 1/4 doğa", "side_ratio": 0.25},
    "soft": {"label": "1/5 doğa • 3/5 sözlük • 1/5 doğa", "side_ratio": 0.20},
    "wide": {"label": "3/10 doğa • 4/10 sözlük • 3/10 doğa", "side_ratio": 0.30},
    "thirds": {"label": "1/3 doğa • 1/3 sözlük • 1/3 doğa", "side_ratio": 1 / 3},
}

ART_SLOT_CONFIGS = {
    "right_main": {"label": "Doğa ana fotoğrafı", "setting_key": "hero_background_art", "target_size": RIGHT_ART_MAIN_SIZE},
    "right_accent": {"label": "Doğa ikinci fotoğrafı", "setting_key": "detail_background_art", "target_size": RIGHT_ART_ACCENT_SIZE},
    "hero": {"label": "Üst başlık alanı", "setting_key": "hero_banner_art", "target_size": ART_SLOT_LIMITS["hero"]},
    "search": {"label": "Arama kartı köşesi", "setting_key": "search_background_art", "target_size": ART_SLOT_LIMITS["search"]},
    "results": {"label": "Sonuç boş durumu", "setting_key": "results_background_art", "target_size": ART_SLOT_LIMITS["results"]},
    "detail": {"label": "Tanım kartı köşesi", "setting_key": "compact_background_art", "target_size": ART_SLOT_LIMITS["detail"]},
}
SETTINGS_VISIBLE_ART_SLOTS = ("right_main", "right_accent")
SETTINGS_HIDDEN_ART_SLOTS = tuple(
    slot_key for slot_key in ART_SLOT_CONFIGS if slot_key not in SETTINGS_VISIBLE_ART_SLOTS
)

SEARCH_ACTION_OPTIONS = {
    "clear": {"label": "Temizle"},
    "google_translate": {"label": "Google Çeviri"},
    "settings": {"label": "Ayarlar"},
    "new_entry": {"label": "Yeni Kelime", "style": "Primary.TButton"},
    "import_url": {"label": "URL Aktar"},
    "parallel_text_import": {"label": "Metin Eşleme"},
    "mini_quiz": {"label": "Mini Quiz"},
    "reload_data": {"label": "Yenile"},
}
MAX_SEARCH_ACTION_BUTTONS = 4
SEARCH_DEBOUNCE_MS = 110

UI_POS_CHOICES = [
    "isim",
    "fiil",
    "sıfat",
    "zarf",
    "ifade",
    "edat",
    "zamir",
    "bağlaç",
    "ünlem",
    "kısaltma",
    "belirsiz",
]

IMPORT_POS_CHOICES = UI_POS_CHOICES

URL_IMPORT_TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß]{3,}(?:-[A-Za-zÄÖÜäöüß]{2,})*")
MAX_IMPORT_CANDIDATES = 80
GERMAN_IMPORT_STOPWORDS = {
    # --- original stopwords (kept intact) ---
    "aber",
    "alle",
    "allem",
    "allen",
    "aller",
    "alles",
    "als",
    "also",
    "am",
    "an",
    "auch",
    "auf",
    "aus",
    "bei",
    "beim",
    "bin",
    "bis",
    "bist",
    "da",
    "dabei",
    "damit",
    "danach",
    "dann",
    "das",
    "dass",
    "dein",
    "deine",
    "dem",
    "den",
    "denn",
    "der",
    "des",
    "dessen",
    "deshalb",
    "die",
    "dies",
    "diese",
    "dieser",
    "dieses",
    "doch",
    "dort",
    "du",
    "durch",
    "ein",
    "eine",
    "einem",
    "einen",
    "einer",
    "eines",
    "er",
    "es",
    "etwas",
    "euch",
    "euer",
    "eure",
    "für",
    "gegen",
    "gewesen",
    "hab",
    "habe",
    "haben",
    "hat",
    "hatte",
    "hattest",
    "hier",
    "hin",
    "hinter",
    "ich",
    "ihr",
    "ihre",
    "im",
    "in",
    "indem",
    "ins",
    "ist",
    "jede",
    "jeder",
    "jedes",
    "jetzt",
    "kann",
    "kannst",
    "kein",
    "keine",
    "mit",
    "muss",
    "musst",
    "nach",
    "neben",
    "nicht",
    "noch",
    "nun",
    "oder",
    "ohne",
    "sehr",
    "sein",
    "seine",
    "sich",
    "sie",
    "sind",
    "so",
    "solche",
    "soll",
    "sollte",
    "sondern",
    "sonst",
    "über",
    "um",
    "und",
    "uns",
    "unter",
    "vom",
    "von",
    "vor",
    "war",
    "waren",
    "warst",
    "was",
    "weg",
    "weil",
    "weiter",
    "welche",
    "welcher",
    "wenn",
    "wer",
    "werde",
    "werden",
    "wie",
    "wieder",
    "wir",
    "wird",
    "wirst",
    "wo",
    "wurde",
    "wurden",
    "zu",
    "zum",
    "zur",
    "zwar",
    "zwischen",
    # --- common adjective inflections ---
    "gut", "gute", "guten", "gutem", "guter", "gutes",
    "groß", "große", "großen", "großem", "großer", "großes",
    "klein", "kleine", "kleinen", "kleinem", "kleiner", "kleines",
    "neu", "neue", "neuen", "neuem", "neuer", "neues",
    "alt", "alte", "alten", "altem", "alter", "altes",
    "lang", "lange", "langen", "langem", "langer", "langes",
    "kurz", "kurze", "kurzen", "kurzem", "kurzer", "kurzes",
    "viel", "viele", "vielen", "vielem", "vieler", "vieles",
    "wenig", "wenige", "wenigen", "wenigem", "weniger",
    "ganz", "ganze", "ganzen", "ganzem", "ganzer", "ganzes",
    "ander", "andere", "anderen", "anderem", "anderer", "anderes",
    "erst", "erste", "ersten", "erstem", "erster", "erstes",
    "letzt", "letzte", "letzten", "letztem", "letzter", "letztes",
    "recht", "rechte", "rechten",
    "wichtig", "wichtige", "wichtigen",
    "eigen", "eigene", "eigenen",
    "gleich", "gleiche", "gleichen",
    "bekannt", "bekannte", "bekannten",
    "jung", "junge", "jungen",
    "stark", "starke", "starken",
    "schwer", "schwere", "schweren",
    # --- common adverbs and particles ---
    "immer", "schon", "auch", "sehr", "nur", "gern", "gerne",
    "fast", "etwa", "eher", "daher", "damals", "dazu",
    "deswegen", "trotzdem", "dennoch", "jedoch", "allerdings",
    "außerdem", "zudem", "ebenfalls", "bereits", "meist", "meistens",
    "manchmal", "oft", "häufig", "selten", "früher", "später",
    "zuerst", "zuletzt", "endlich", "plötzlich", "sofort", "soeben",
    "bisher", "seitdem", "davor", "davon", "daran", "darin",
    "darauf", "darum", "darüber", "darunter", "dafür", "dagegen",
    "dadurch", "dahinter",
    # --- modal verb forms ---
    "können", "konnte", "konntest", "konnten", "könnte", "könntest", "könnten",
    "müssen", "musste", "musstest", "mussten", "müsste", "müsstest", "müssten",
    "sollst", "sollen", "solltest", "sollten",
    "will", "willst", "wollen", "wollte", "wolltest", "wollten",
    "darf", "darfst", "dürfen", "durfte", "durftest", "durften",
    "dürfte", "dürftest", "dürften",
    "mag", "magst", "mögen", "mochte", "mochtest", "mochten",
    "möchte", "möchtest", "möchten",
    # --- sein/haben/werden conjugations ---
    "bist", "seid", "wäre", "wärst", "wären", "wärt",
    "sei", "seist", "seien",
    "habt", "hatten", "hattet", "hätte", "hättest", "hätten", "hättet", "gehabt",
    "werde", "wirst", "werdet", "wurden", "wurdet",
    "würde", "würdest", "würden", "würdet", "geworden",
    # --- common verb forms (3rd person / past) ---
    "geht", "ging", "gingen",
    "kommt", "kam", "kamen",
    "macht", "machte", "machten",
    "sagt", "sagte", "sagten",
    "gibt", "gab", "gaben",
    "steht", "stand", "standen",
    "liegt", "lag", "lagen",
    "sieht", "sah", "sahen",
    "nimmt", "nahm", "nahmen",
    "hält", "hielt", "hielten",
    "lässt", "ließ", "ließen",
    "bringt", "brachte", "brachten",
    "denkt", "dachte", "dachten",
    "weiß", "wusste", "wussten",
    "findet", "fand", "fanden",
    "zeigt", "zeigte", "zeigten",
    "spielt", "spielte", "spielten",
    "heißt", "hieß", "hießen",
    "bleibt", "blieb", "blieben",
    # --- common generic nouns (too generic to be useful) ---
    "Jahr", "Jahre", "Jahren",
    "Zeit", "Zeiten",
    "Teil", "Teile", "Teilen",
    "Form", "Formen",
    "Typ", "Typen",
    "Art", "Arten",
    "Fall", "Fälle",
    "Punkt", "Punkte",
    "Zahl", "Zahlen",
    "Ende", "Anfang",
    "Bereich", "Bereiche",
    "Grund", "Gründe",
    "Beispiel", "Beispiele",
    "Ergebnis", "Ergebnisse",
    "Problem", "Probleme",
    "Frage", "Fragen",
    "Antwort", "Antworten",
    "Möglichkeit", "Möglichkeiten",
    "Bedeutung", "Bedeutungen",
    # --- English words that appear on German pages ---
    "the", "and", "for", "that", "this", "with", "from", "are",
    "was", "has", "have", "been", "they", "them", "their", "about",
    "what", "which", "when", "where", "how", "can", "will", "not",
    "but", "more", "also", "some", "than", "then", "there", "here",
    "other", "used", "based", "see",
    # --- months ---
    "Januar", "Februar", "März", "April", "Juni", "Juli",
    "August", "September", "Oktober", "November", "Dezember",
    # --- days of the week ---
    "Montag", "Dienstag", "Mittwoch", "Donnerstag",
    "Freitag", "Samstag", "Sonntag",
    # --- ordinals ---
    "zweite", "zweiten", "zweitem", "zweiter", "zweites",
    "dritte", "dritten", "drittem", "dritter", "drittes",
    "vierte", "vierten",
    "fünfte", "fünften",
    "sechste", "sechsten",
    # --- pronouns ---
    "unser", "unsere", "unseren", "unserem", "unserer",
    "eurem", "eurer",
    "jener", "jene", "jenen", "jenem",
    "jeden", "jedem",
    "mancher", "manche", "manchen",
    # --- prepositions / conjunctions ---
    "obwohl", "während", "bevor", "nachdem", "sobald", "solange",
    "falls", "sofern", "wohingegen", "gegenüber",
    "innerhalb", "außerhalb", "oberhalb", "unterhalb",
    "anstatt", "anstelle", "aufgrund", "mithilfe",
    "bezüglich", "hinsichtlich", "laut", "gemäß", "zufolge",
    "entsprechend",
}

SORT_OPTIONS = {
    "ilgili": "En ilgili",
    "almanca": "Almanca A-Z",
    "turkce": "Türkçe A-Z",
    "kaynak": "Kaynağı güçlü olanlar",
    "seviye": "Seviyeye göre (A1→C2)",
    "frekans": "Sıklığa göre",
}

CEFR_ORDER = {"A1": 0, "A2": 1, "B1": 2, "B2": 3, "C1": 4, "C2": 5}
CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

SOURCE_MODE_LABELS = {
    "all": "Tüm kaynaklar",
    "preferred_only": "Seçtiğim kaynaklar",
}

REVIEW_STATUS_LABELS = {
    "manuel-dogrulandi": "Manuel doğrulandı",
    "kaynak-izli": "Kaynakla destekleniyor",
    "kullanici-eklemesi": "Kullanıcı eklemesi",
}

THEMES = {
    "krem": {
        "label": "Krem",
        "bg": "#f3efe5",
        "panel": "#fbf8f2",
        "surface": "#ffffff",
        "surface_soft": "#f5f0e7",
        "hero": "#f7f3eb",
        "ink": "#1e2b27",
        "muted": "#61706a",
        "accent": "#1e6a59",
        "accent_soft": "#dfeee9",
        "line": "#d8d0c2",
    },
    "orman": {
        "label": "Orman",
        "bg": "#e7efe9",
        "panel": "#f4faf6",
        "surface": "#ffffff",
        "surface_soft": "#eaf3ed",
        "hero": "#eef6f1",
        "ink": "#183229",
        "muted": "#587166",
        "accent": "#245f46",
        "accent_soft": "#deece4",
        "line": "#ccd9d1",
    },
    "deniz": {
        "label": "Deniz",
        "bg": "#e9f1f2",
        "panel": "#f5fbfb",
        "surface": "#ffffff",
        "surface_soft": "#eaf2f2",
        "hero": "#eef6f7",
        "ink": "#18343a",
        "muted": "#5a7178",
        "accent": "#216f79",
        "accent_soft": "#dfeef0",
        "line": "#cfdbde",
    },
    "arduvaz": {
        "label": "Arduvaz",
        "bg": "#ecf0f5",
        "panel": "#f7f9fc",
        "surface": "#ffffff",
        "surface_soft": "#eef2f7",
        "hero": "#f2f5f9",
        "ink": "#22313e",
        "muted": "#61707f",
        "accent": "#4b647d",
        "accent_soft": "#e3ebf2",
        "line": "#d6dde6",
    },
    "light_forest": {
        "label": "Light Forest",
        "bg": "#edf4ef",
        "panel": "#f7fbf8",
        "surface": "#ffffff",
        "surface_soft": "#edf5ef",
        "hero": "#f1f8f3",
        "ink": "#1f3429",
        "muted": "#61786b",
        "accent": "#3b6f55",
        "accent_soft": "#dcebdc",
        "line": "#cfddd1",
    },
    "forest": {
        "label": "Forest",
        "bg": "#dfe9e0",
        "panel": "#eef5ef",
        "surface": "#f9fcf9",
        "surface_soft": "#e5efe6",
        "hero": "#e8f1e9",
        "ink": "#163126",
        "muted": "#4e695c",
        "accent": "#285a41",
        "accent_soft": "#d3e4d7",
        "line": "#bed1c3",
    },
    "sage_forest": {
        "label": "Sage Forest",
        "bg": "#e4ece6",
        "panel": "#eef4ef",
        "surface": "#f8fbf8",
        "surface_soft": "#e7efe8",
        "hero": "#e8f0ea",
        "ink": "#23342c",
        "muted": "#607168",
        "accent": "#4f6f5a",
        "accent_soft": "#dce7df",
        "line": "#c9d6cb",
    },
    "dark_forest": {
        "label": "Dark Forest",
        "bg": "#122019",
        "panel": "#182821",
        "surface": "#1f3229",
        "surface_soft": "#24382f",
        "hero": "#1b2d24",
        "ink": "#edf5ef",
        "muted": "#adc2b5",
        "accent": "#4f9b73",
        "accent_soft": "#2c4539",
        "line": "#365246",
    },
    "pine_night": {
        "label": "Pine Night",
        "bg": "#0f1a1a",
        "panel": "#162425",
        "surface": "#1d2d2e",
        "surface_soft": "#233637",
        "hero": "#182728",
        "ink": "#edf6f4",
        "muted": "#a8beb9",
        "accent": "#4e8c84",
        "accent_soft": "#294340",
        "line": "#355654",
    },
    "moss_shadow": {
        "label": "Moss Shadow",
        "bg": "#171d14",
        "panel": "#20271d",
        "surface": "#293126",
        "surface_soft": "#30392d",
        "hero": "#242c21",
        "ink": "#f3f6ee",
        "muted": "#bac4ae",
        "accent": "#809b58",
        "accent_soft": "#39442e",
        "line": "#4a5740",
    },
}

FONT_PRESETS = {
    "modern": {
        "label": "Modern",
        "ui": "Segoe UI",
        "title": "Georgia",
        "content": "Segoe UI",
    },
    "kitap": {
        "label": "Kitap",
        "ui": "Cambria",
        "title": "Palatino Linotype",
        "content": "Cambria",
    },
    "net": {
        "label": "Net",
        "ui": "Verdana",
        "title": "Trebuchet MS",
        "content": "Verdana",
    },
    "klasik": {
        "label": "Klasik",
        "ui": "Tahoma",
        "title": "Georgia",
        "content": "Tahoma",
    },
}

DEFAULT_SETTINGS = {
    "theme": "krem",
    "font_preset": "modern",
    "show_examples": True,
    "show_notes": False,
    "remember_search": True,
    "search_action_buttons": ["clear", "settings", "new_entry"],
    "show_stats": False,
    "show_quick_access": False,
    "show_results_panel": False,
    "show_extended_details": False,
    "show_detail_actions": False,
    "show_shortcuts_hint": True,
    "note_only": False,
    "pos_filter": "",
    "seviye_filter": "",
    "category_filter": "",
    "source_filter": "",
    "preferred_sources": [],
    "source_mode": "all",
    "sort_mode": "ilgili",
    "result_limit": 250,
    "content_font_size": 14,
    "translation_font_size": 18,
    "meta_font_size": 11,
    "libretranslate_url": os.getenv("LIBRETRANSLATE_URL", LIBRETRANSLATE_DEFAULT_URL),
    "libretranslate_api_key": os.getenv("LIBRETRANSLATE_API_KEY", ""),
    "llm_api_url": os.getenv("OLLAMA_API_URL", "http://127.0.0.1:11434/v1/chat/completions"),
    "llm_api_key": os.getenv("LLM_API_KEY", ""),
    "llm_model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
    "last_search": "",
    "recent_searches": [],
    "pinned_records": [],
    "allow_art_customization": False,
    "allow_art_sidebar_resize": False,
    "art_layout_preset": "quarter",
    "show_background_art": True,
    "show_art_right_main": True,
    "show_art_right_accent": True,
    "show_art_hero": False,
    "show_art_search": False,
    "show_art_results": False,
    "show_art_detail": False,
    "expand_art_right_main": False,
    "expand_art_right_accent": False,
    "expand_art_hero": False,
    "expand_art_search": False,
    "expand_art_results": False,
    "expand_art_detail": False,
    "custom_art_slots": {},
    "hero_background_art": "tree",
    "hero_banner_art": "none",
    "search_background_art": "none",
    "results_background_art": "none",
    "detail_background_art": "nature_line",
    "compact_background_art": "none",
    "art_sidebar_width": RIGHT_ART_SIDEBAR_WIDTH,
    "window_geometry": "1440x900+70+50",
    "start_maximized": True,
    "window_state": "zoomed",
}


def enforce_visible_art_settings(settings: dict) -> dict:
    settings["show_stats"] = False
    settings["show_quick_access"] = False
    settings["show_results_panel"] = True
    settings["show_background_art"] = True
    settings["allow_art_sidebar_resize"] = False
    settings["art_layout_preset"] = DEFAULT_SETTINGS["art_layout_preset"]
    settings["art_sidebar_width"] = RIGHT_ART_SIDEBAR_WIDTH
    custom_art_slots = sanitize_custom_art_slots(settings.get("custom_art_slots", {}))
    has_any_art_slot_enabled = any(bool(settings.get(f"show_art_{slot_key}")) for slot_key in ART_SLOT_CONFIGS)
    if bool(settings.get("show_background_art", DEFAULT_SETTINGS["show_background_art"])) and not has_any_art_slot_enabled:
        settings["show_art_right_main"] = True
        settings["show_art_right_accent"] = True
    settings["custom_art_slots"] = {
        slot_key: config
        for slot_key, config in custom_art_slots.items()
        if slot_key in ART_SLOT_CONFIGS
    }
    for slot_key in SETTINGS_HIDDEN_ART_SLOTS:
        settings[f"show_art_{slot_key}"] = False
        settings[f"expand_art_{slot_key}"] = False
        setting_key = ART_SLOT_CONFIGS[slot_key]["setting_key"]
        settings[setting_key] = DEFAULT_SETTINGS[setting_key]
    return settings


MAX_RECENT_SEARCHES = 8
MAX_PINNED_RECORDS = 12
MINI_QUIZ_QUESTION_COUNT = 5
MINI_QUIZ_OPTION_COUNT = 4
WIKTIONARY_GENDER_TIMEOUT_SECONDS = 2.5
GOOGLE_TRANSLATE_SENTENCE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
GOOGLE_TRANSLATE_TIMEOUT_SECONDS = 8
GOOGLE_TRANSLATE_MAX_SENTENCE_CHARS = 420
LLM_CHAT_COMPLETIONS_FALLBACK_URL = "http://127.0.0.1:11434/v1/chat/completions"
PARALLEL_TEXT_BATCH_UNIT_LIMIT = 4
PARALLEL_TEXT_BATCH_MAX_CHARS = 1700
PARALLEL_TEXT_MIN_CONFIDENCE = 0.58
LOCAL_PARALLEL_IMPORT_STOPWORDS = {
    "erste",
    "ersten",
    "erster",
    "erstes",
    "ihn",
    "ihm",
    "ihm",
    "ihre",
    "ihrer",
    "ihrer",
    "seine",
    "seiner",
    "seinen",
    "dieser",
    "diese",
    "dieses",
}
LLM_MODEL_PRESETS = (
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "qwen2.5:7b",
    "llama3.1:8b",
    "gemma3:4b",
    "mistral:7b",
)
GEMINI_MODEL_PRESETS = ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro")
GROQ_MODEL_PRESETS = ("llama-3.1-8b-instant", "llama-3.3-70b-versatile", "gemma2-9b-it", "mixtral-8x7b-32768")
GEMINI_CHUNK_SIZE = 12000       # Her parçada maksimum karakter sayısı (~3600 token)
GEMINI_MAX_TOTAL_CHARS = 120000 # Toplam maksimum karakter (tüm sayfa) — 10 parça max
GEMINI_INTER_CHUNK_DELAY = 10.0  # Groq için parçalar arası bekleme (saniye) — TPM limiti
GEMINI_INTER_CHUNK_DELAY_FAST = 2.0  # Gemini/yerel için bekleme (çok daha az limit)
LOCAL_MODEL_PRESETS = ("qwen2.5:7b", "llama3.1:8b", "gemma3:4b", "mistral:7b")
GOOGLE_GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
LLM_SERVICE_OPTIONS = ("Groq (ücretsiz)", "Google Gemini (ücretsiz)", "Yerel (Ollama)", "Özel")
URL_IMPORT_AI_BATCH_SIZE = 24
URL_IMPORT_AI_MAX_WORDS = 72


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    normalized = normalized.replace("ß", "ss")
    return " ".join(normalized.split())


def ascii_fold(text: str) -> str:
    """Strip diacritics for fuzzy search (ü→u, ö→o, ş→s, ı→i, ç→c etc.).
    Allows searching without special characters to still find matches."""
    # Handle Turkish dotless-i specially (no combining form in NFD)
    t = text.replace("ı", "i").replace("İ", "i")
    # NFD decomposition + remove combining characters
    nfd = unicodedata.normalize("NFD", t)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def normalize_whitespace(text: object) -> str:
    return " ".join(str(text or "").split())


MOJIBAKE_MARKERS = ("Ã", "Ä", "Å", "â€", "Â", "�")
TEXTUAL_TK_OPTION_KEYS = {"text", "label", "message", "title"}
SEQUENCE_TK_OPTION_KEYS = {"values"}
TURKISH_TEXT_SAFETY_INSTALLED = False


def needs_mojibake_repair(text: object) -> bool:
    value = str(text or "")
    if not value:
        return False
    return any(marker in value for marker in MOJIBAKE_MARKERS)


def repair_mojibake_text(text: object) -> str:
    value = str(text or "")
    if not value:
        return ""
    repaired = value
    for _ in range(3):
        if not needs_mojibake_repair(repaired):
            break
        try:
            candidate = repaired.encode("latin-1").decode("utf-8")
        except UnicodeError:
            break
        if candidate == repaired:
            break
        repaired = candidate
    return repaired


def repair_tk_option_value(option_name: str, value):
    if option_name in TEXTUAL_TK_OPTION_KEYS and isinstance(value, str):
        return repair_mojibake_text(value)
    if option_name in SEQUENCE_TK_OPTION_KEYS and isinstance(value, (list, tuple)):
        repaired_values = [repair_mojibake_text(item) if isinstance(item, str) else item for item in value]
        return tuple(repaired_values) if isinstance(value, tuple) else repaired_values
    return value


def repair_tk_option_dict(options):
    if not isinstance(options, dict):
        return options
    return {key: repair_tk_option_value(str(key), value) for key, value in options.items()}


def patch_tk_widget_text_options(widget_class) -> None:
    if getattr(widget_class, "_turkish_text_safety_installed", False):
        return

    original_init = widget_class.__init__
    original_configure = getattr(widget_class, "configure", None)

    def patched_init(self, *args, **kwargs):
        return original_init(self, *args, **repair_tk_option_dict(kwargs))

    widget_class.__init__ = patched_init

    if callable(original_configure):
        def patched_configure(self, cnf=None, **kwargs):
            repaired_cnf = repair_tk_option_dict(cnf) if isinstance(cnf, dict) else cnf
            return original_configure(self, repaired_cnf, **repair_tk_option_dict(kwargs))

        widget_class.configure = patched_configure
        widget_class.config = patched_configure

    widget_class._turkish_text_safety_installed = True


def patch_tk_menu_methods() -> None:
    if getattr(tk.Menu, "_turkish_text_safety_installed", False):
        return

    for method_name in ("add_command", "add_checkbutton", "add_radiobutton", "add_cascade", "insert"):
        original_method = getattr(tk.Menu, method_name)

        def make_wrapper(method):
            def wrapped(self, *args, **kwargs):
                return method(self, *args, **repair_tk_option_dict(kwargs))

            return wrapped

        setattr(tk.Menu, method_name, make_wrapper(original_method))

    original_entryconfigure = tk.Menu.entryconfigure

    def patched_entryconfigure(self, index, cnf=None, **kwargs):
        repaired_cnf = repair_tk_option_dict(cnf) if isinstance(cnf, dict) else cnf
        return original_entryconfigure(self, index, repaired_cnf, **repair_tk_option_dict(kwargs))

    tk.Menu.entryconfigure = patched_entryconfigure
    tk.Menu._turkish_text_safety_installed = True


def patch_tk_stringvar() -> None:
    if getattr(tk.StringVar, "_turkish_text_safety_installed", False):
        return

    original_init = tk.StringVar.__init__
    original_set = tk.StringVar.set

    def patched_init(self, master=None, value=None, name=None):
        repaired_value = repair_mojibake_text(value) if isinstance(value, str) else value
        return original_init(self, master=master, value=repaired_value, name=name)

    def patched_set(self, value):
        repaired_value = repair_mojibake_text(value) if isinstance(value, str) else value
        return original_set(self, repaired_value)

    tk.StringVar.__init__ = patched_init
    tk.StringVar.set = patched_set
    tk.StringVar._turkish_text_safety_installed = True


def patch_tk_misc_title() -> None:
    if getattr(tk.Wm, "_turkish_text_safety_title_installed", False):
        return

    original_title = tk.Wm.title

    def patched_title(self, string=None):
        if string is None:
            return original_title(self)
        return original_title(self, repair_mojibake_text(string))

    tk.Wm.title = patched_title
    tk.Wm._turkish_text_safety_title_installed = True


def patch_tk_text_insert() -> None:
    if getattr(tk.Text, "_turkish_text_safety_insert_installed", False):
        return

    original_insert = tk.Text.insert

    def patched_insert(self, index, chars, *args):
        repaired_chars = repair_mojibake_text(chars) if isinstance(chars, str) else chars
        return original_insert(self, index, repaired_chars, *args)

    tk.Text.insert = patched_insert
    tk.Text._turkish_text_safety_insert_installed = True


def patch_tk_listbox_insert() -> None:
    if getattr(tk.Listbox, "_turkish_text_safety_insert_installed", False):
        return

    original_insert = tk.Listbox.insert

    def patched_insert(self, index, *elements):
        repaired_elements = tuple(repair_mojibake_text(item) if isinstance(item, str) else item for item in elements)
        return original_insert(self, index, *repaired_elements)

    tk.Listbox.insert = patched_insert
    tk.Listbox._turkish_text_safety_insert_installed = True


def patch_ttk_notebook_methods() -> None:
    if getattr(ttk.Notebook, "_turkish_text_safety_installed", False):
        return

    original_add = ttk.Notebook.add
    original_insert = ttk.Notebook.insert
    original_tab = ttk.Notebook.tab

    def patched_add(self, child, **kwargs):
        return original_add(self, child, **repair_tk_option_dict(kwargs))

    def patched_insert(self, pos, child, **kwargs):
        return original_insert(self, pos, child, **repair_tk_option_dict(kwargs))

    def patched_tab(self, tab_id, option=None, **kwargs):
        return original_tab(self, tab_id, option=option, **repair_tk_option_dict(kwargs))

    ttk.Notebook.add = patched_add
    ttk.Notebook.insert = patched_insert
    ttk.Notebook.tab = patched_tab
    ttk.Notebook._turkish_text_safety_installed = True


def patch_ttk_treeview_methods() -> None:
    if getattr(ttk.Treeview, "_turkish_text_safety_heading_installed", False):
        return

    original_heading = ttk.Treeview.heading
    original_insert = ttk.Treeview.insert
    original_item = ttk.Treeview.item

    def patched_heading(self, column, option=None, **kwargs):
        return original_heading(self, column, option=option, **repair_tk_option_dict(kwargs))

    def patched_insert(self, parent, index, iid=None, **kwargs):
        return original_insert(self, parent, index, iid=iid, **repair_tk_option_dict(kwargs))

    def patched_item(self, item, option=None, **kwargs):
        return original_item(self, item, option=option, **repair_tk_option_dict(kwargs))

    ttk.Treeview.heading = patched_heading
    ttk.Treeview.insert = patched_insert
    ttk.Treeview.item = patched_item
    ttk.Treeview._turkish_text_safety_heading_installed = True


def patch_messagebox_text() -> None:
    if getattr(messagebox, "_turkish_text_safety_installed", False):
        return

    def wrap_messagebox(function_name: str) -> None:
        original_function = getattr(messagebox, function_name, None)
        if not callable(original_function):
            return

        def wrapped(title=None, message=None, *args, **kwargs):
            repaired_title = repair_mojibake_text(title) if isinstance(title, str) else title
            repaired_message = repair_mojibake_text(message) if isinstance(message, str) else message
            if isinstance(kwargs.get("detail"), str):
                kwargs["detail"] = repair_mojibake_text(kwargs["detail"])
            return original_function(repaired_title, repaired_message, *args, **kwargs)

        setattr(messagebox, function_name, wrapped)

    for function_name in (
        "showinfo",
        "showwarning",
        "showerror",
        "askquestion",
        "askokcancel",
        "askyesno",
        "askyesnocancel",
        "askretrycancel",
    ):
        wrap_messagebox(function_name)

    messagebox._turkish_text_safety_installed = True


def repair_widget_tree_texts(root: tk.Misc) -> None:
    if root is None:
        return

    try:
        current_text = root.cget("text")
    except Exception:
        current_text = None
    if isinstance(current_text, str) and needs_mojibake_repair(current_text):
        try:
            root.configure(text=repair_mojibake_text(current_text))
        except Exception:
            pass

    try:
        current_values = root.cget("values")
    except Exception:
        current_values = None
    if isinstance(current_values, (list, tuple)) and any(isinstance(item, str) and needs_mojibake_repair(item) for item in current_values):
        try:
            root.configure(values=repair_tk_option_value("values", current_values))
        except Exception:
            pass

    if isinstance(root, ttk.Notebook):
        for tab_id in root.tabs():
            tab_text = root.tab(tab_id, "text")
            if isinstance(tab_text, str) and needs_mojibake_repair(tab_text):
                root.tab(tab_id, text=repair_mojibake_text(tab_text))

    try:
        child_widgets = root.winfo_children()
    except Exception:
        child_widgets = []

    for child in child_widgets:
        repair_widget_tree_texts(child)


def install_turkish_text_safety() -> None:
    global TURKISH_TEXT_SAFETY_INSTALLED
    if TURKISH_TEXT_SAFETY_INSTALLED:
        return

    patch_tk_stringvar()
    patch_tk_misc_title()
    patch_tk_text_insert()
    patch_tk_listbox_insert()
    patch_tk_menu_methods()
    patch_ttk_notebook_methods()
    patch_ttk_treeview_methods()
    patch_messagebox_text()

    for widget_class in (
        tk.Label,
        tk.Button,
        tk.Checkbutton,
        tk.Radiobutton,
        tk.LabelFrame,
        ttk.Label,
        ttk.Button,
        ttk.Checkbutton,
        ttk.Radiobutton,
        ttk.LabelFrame,
        ttk.Combobox,
    ):
        patch_tk_widget_text_options(widget_class)

    TURKISH_TEXT_SAFETY_INSTALLED = True


install_turkish_text_safety()


def hex_to_colorref(color: str) -> int:
    cleaned = str(color or "").lstrip("#")
    if len(cleaned) != 6:
        return 0
    red = int(cleaned[0:2], 16)
    green = int(cleaned[2:4], 16)
    blue = int(cleaned[4:6], 16)
    return red | (green << 8) | (blue << 16)


def color_is_dark(color: str) -> bool:
    cleaned = str(color or "").lstrip("#")
    if len(cleaned) != 6:
        return False
    red = int(cleaned[0:2], 16)
    green = int(cleaned[2:4], 16)
    blue = int(cleaned[4:6], 16)
    luminance = (0.299 * red) + (0.587 * green) + (0.114 * blue)
    return luminance < 145


def deumlaut_text(text: str) -> str:
    return (
        str(text or "")
        .replace("Äu", "Au")
        .replace("äu", "au")
        .replace("Ä", "A")
        .replace("Ö", "O")
        .replace("Ü", "U")
        .replace("ä", "a")
        .replace("ö", "o")
        .replace("ü", "u")
    )


def umlaut_variants(text: str) -> list[str]:
    value = str(text or "")
    if not value:
        return []
    variants = [value]
    pair_map = {"au": "äu", "Au": "Äu"}
    single_map = {"a": "ä", "o": "ö", "u": "ü", "A": "Ä", "O": "Ö", "U": "Ü"}
    for index in range(len(value) - 2, -1, -1):
        pair = value[index : index + 2]
        if pair in pair_map:
            candidate = value[:index] + pair_map[pair] + value[index + 2 :]
            if candidate not in variants:
                variants.append(candidate)
            break
    for index in range(len(value) - 1, -1, -1):
        char = value[index]
        if char in single_map:
            candidate = value[:index] + single_map[char] + value[index + 1 :]
            if candidate not in variants:
                variants.append(candidate)
            break
    return variants


def split_multi_value(text: str) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for part in str(text or "").split(";"):
        item = part.strip()
        if not item:
            continue
        key = normalize_text(item)
        if key in seen:
            continue
        seen.add(key)
        values.append(item)
    return values


def safe_json_load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def strip_known_article(term: str) -> str:
    pieces = str(term or "").strip().split(" ", 1)
    if len(pieces) == 2 and normalize_text(pieces[0]) in {"der", "die", "das"}:
        return pieces[1].strip()
    return str(term or "").strip()


def normalize_import_term(term: str) -> str:
    normalized = normalize_text(strip_known_article(term))
    return re.sub(r"[^\wäöüß-]+", "", normalized, flags=re.IGNORECASE)


def guess_import_pos(term: str) -> str:
    clean = strip_known_article(term)
    if not clean:
        return "belirsiz"
    lower = clean.casefold()
    if clean[:1].isupper():
        return "isim"
    if lower.endswith(("en", "eln", "ern")) and len(lower) >= 5:
        return "fiil"
    if lower.endswith(("ig", "lich", "isch", "bar", "los", "sam", "haft", "voll")):
        return "sıfat"
    if lower.endswith(("weise",)):
        return "zarf"
    if "-" in clean:
        return "ifade"
    return "belirsiz"


class VisibleTextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "address", "article", "blockquote", "br", "div",
        "figcaption", "h1", "h2", "h3", "h4", "h5", "h6",
        "li", "main", "p", "section", "td", "th", "tr",
    }
    # Tamamen atlanan etiketler: içerikleri de dahil değil
    SKIP_TAGS = {
        "head", "script", "style", "noscript", "svg", "canvas",
        "nav", "footer", "header",   # gezinti/üstbilgi/altbilgi — içerik değil
        "aside",                      # kenar çubuk — genellikle reklam/link
        "button", "form", "input", "select", "textarea",  # form öğeleri
        "figure",                     # resim açıklamaları (genellikle kısa, gürültülü)
    }
    MAIN_TAGS = {"main", "article"}
    # Bu id/class değerleri olan elementler atlanır (dipnot, TOC, nav vb.)
    SKIP_CLASSES = {
        "references", "reflist", "reference", "footnotes",
        "toc", "toccolours", "mw-references-wrap",
        "navbox", "navbox-inner", "navbox-group",
        "mw-editsection", "mw-jump-link",
        "sidebar", "sistersitebox", "noprint",
        "catlinks", "printfooter",
        "cookie", "banner", "advertisement", "ad", "ads",
        "breadcrumb", "pagination", "menu", "dropdown",
        "related", "recommendation", "teaser",
    }
    SKIP_IDS = {
        "toc", "references", "catlinks", "mw-navigation", "p-search",
        "nav", "footer", "header", "sidebar", "menu", "cookie-banner",
        "related-articles", "breadcrumb",
    }

    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.main_depth = 0
        self.all_chunks: list[str] = []
        self.main_chunks: list[str] = []

    def _should_skip_attrs(self, attrs: list) -> bool:
        attr_dict = dict(attrs)
        el_id = attr_dict.get("id", "")
        el_classes = set((attr_dict.get("class", "") or "").split())
        if el_id in self.SKIP_IDS:
            return True
        if el_classes & self.SKIP_CLASSES:
            return True
        return False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.SKIP_TAGS or self._should_skip_attrs(attrs):
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in self.MAIN_TAGS:
            self.main_depth += 1
        if tag in self.BLOCK_TAGS:
            self._append_break()

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag in self.MAIN_TAGS and self.main_depth:
            self.main_depth -= 1
        if tag in self.BLOCK_TAGS:
            self._append_break()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        cleaned = data.strip()
        if not cleaned:
            return
        self.all_chunks.append(cleaned)
        if self.main_depth:
            self.main_chunks.append(cleaned)

    def _append_break(self) -> None:
        self.all_chunks.append("\n")
        if self.main_depth:
            self.main_chunks.append("\n")

    def get_text(self) -> str:
        # Paragraf yapısını koru — chunk'ları birleştir ama satır sonlarını cümle ayıracı olarak sakla
        def _join_chunks(chunks: list[str]) -> str:
            parts: list[str] = []
            for chunk in chunks:
                if chunk == "\n":
                    if parts and parts[-1] != "\n":
                        parts.append("\n")
                else:
                    stripped = chunk.strip()
                    if stripped:
                        parts.append(stripped)
            return " ".join(
                (p if p == "\n" else p)
                for p in parts
            ).strip()

        main_text = _join_chunks(self.main_chunks)
        body_text = _join_chunks(self.all_chunks)
        chosen = main_text if len(main_text) >= 200 else body_text
        # Fazladan boşlukları temizle ama satır sonlarını koru
        chosen = re.sub(r"[ \t]{2,}", " ", chosen)
        chosen = re.sub(r"\n{3,}", "\n\n", chosen)
        return chosen.strip()


def _ascii_safe_url(url: str) -> str:
    """URL'de ASCII dışı karakter varsa (ö, ü, ä …) düzgün encode et."""
    try:
        url.encode("ascii")
        return url  # zaten ASCII, dokunma
    except UnicodeEncodeError:
        from urllib.parse import urlparse, quote
        p = urlparse(url)
        safe_path  = quote(p.path,  safe="/:@!$&'()*+,;=")
        safe_query = quote(p.query, safe="=&+:@!$'()*,;")
        safe_frag  = quote(p.fragment, safe="")
        return p._replace(path=safe_path, query=safe_query, fragment=safe_frag).geturl()


def fetch_visible_text_from_url(url: str) -> tuple[str, str]:
    request = Request(
        _ascii_safe_url(url),
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DictionaryDesktop/1.0",
            "Accept-Language": "de,en;q=0.8,tr;q=0.6",
        },
    )
    with urlopen(request, timeout=15) as response:
        final_url = response.geturl()
        raw = response.read(2_500_000)
        charset = response.headers.get_content_charset() or "utf-8"
        html = raw.decode(charset, errors="replace")
    parser = VisibleTextExtractor()
    parser.feed(html)
    text = parser.get_text()
    if not text:
        raise ValueError("URL içeriğinden görünür metin çıkarılamadı.")
    return final_url, text


def lookup_import_translation(term: str, cursor: sqlite3.Cursor | None) -> dict:
    if cursor is None:
        return {"translation": "", "source": "Öneri yok"}

    lookup_terms = [term.strip()]
    lower = strip_known_article(term).casefold()
    if lower and lower not in {item.casefold() for item in lookup_terms}:
        lookup_terms.append(lower)
    if lower.endswith("iert") and len(lower) > 6:
        lookup_terms.append(lower[:-4] + "ieren")
    if lower.endswith("test") and len(lower) > 6:
        lookup_terms.append(lower[:-4] + "en")
    if lower.endswith("tet") and len(lower) > 5:
        lookup_terms.append(lower[:-3] + "en")
    if lower.endswith("st") and len(lower) >= 6:
        lookup_terms.append(lower[:-2] + "en")
    if lower.endswith("te") and len(lower) >= 6:
        lookup_terms.append(lower[:-2] + "en")
    if lower.endswith("t") and len(lower) >= 6:
        root = lower[:-1]
        # Skip if root ends in typical adjective/noun suffixes to avoid false verb matches
        if not root.endswith(("ig", "lich", "isch", "bar", "sam", "haft", "voll", "los")):
            lookup_terms.append(root + "en")
    # Noun plural / case-form stripping (Hunde→Hund, Hundes→Hund, Tieren→Tier, Autos→Auto)
    # These run as fallbacks: only used when the full form isn't in WikDict directly.
    if lower.endswith("en") and len(lower) >= 6:
        lookup_terms.append(lower[:-2])          # Hunden→Hund, Impfungen→Impfung
    if lower.endswith("es") and len(lower) >= 6:
        lookup_terms.append(lower[:-2])          # Hundes→Hund, Tisches→Tisch
    if lower.endswith("e") and len(lower) >= 5:
        lookup_terms.append(lower[:-1])          # Hunde→Hund, Tiere→Tier
    if lower.endswith("s") and not lower.endswith("ss") and len(lower) >= 5:
        lookup_terms.append(lower[:-1])          # Autos→Auto, Tages→Tage (then -e strip)

    seen_forms: set[str] = set()
    row = None
    for lookup_term in lookup_terms:
        normalized = normalize_text(lookup_term)
        if not normalized or normalized in seen_forms:
            continue
        seen_forms.add(normalized)
        row = cursor.execute(
            """
            select written_rep, trans_list
            from simple_translation
            where lower(written_rep) = lower(?)
            order by rel_importance desc, max_score desc
            limit 1
            """,
            (lookup_term,),
        ).fetchone()
        if row:
            break

    if row is None:
        return {"translation": "", "source": "Öneri yok"}

    translations: list[str] = []
    seen: set[str] = set()
    for part in str(row[1] or "").split("|"):
        cleaned = part.strip()
        key = normalize_text(cleaned)
        if not cleaned or key in seen:
            continue
        seen.add(key)
        translations.append(cleaned)
    return {
        "translation": ", ".join(translations[:4]),
        "source": "WikDict önerisi" if translations else "Öneri yok",
        "written_rep": str(row[0]) if row else "",
    }


def split_text_into_sentences(text: str) -> list[str]:
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    if not collapsed:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])", collapsed)
    sentences = []
    seen: set[str] = set()
    for part in parts:
        sentence = part.strip(" \t\r\n-–;")
        if len(sentence) < 12:
            continue
        key = normalize_text(sentence)
        if not key or key in seen:
            continue
        seen.add(key)
        sentences.append(sentence)
    return sentences


def split_parallel_text_units(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []

    paragraphs = [normalize_whitespace(part) for part in re.split(r"(?:\r?\n){2,}", raw)]
    paragraphs = [part for part in paragraphs if part]
    if len(paragraphs) > 1:
        return paragraphs

    collapsed = normalize_whitespace(raw)
    if not collapsed:
        return []
    parts = re.split(r"(?<=[.!?…])\s+|(?<=;)\s+", collapsed)
    units: list[str] = []
    seen: set[str] = set()
    for part in parts:
        unit = part.strip(" \t\r\n-â€“;")
        if len(unit) < 8:
            continue
        key = normalize_text(unit)
        if not key or key in seen:
            continue
        seen.add(key)
        units.append(unit)
    return units or [collapsed]


def build_parallel_text_batches(german_text: str, turkish_text: str) -> list[tuple[str, str]]:
    german_units = split_parallel_text_units(german_text)
    turkish_units = split_parallel_text_units(turkish_text)
    german_fallback = normalize_whitespace(german_text)
    turkish_fallback = normalize_whitespace(turkish_text)
    if not german_units or not turkish_units:
        if german_fallback and turkish_fallback:
            return [(german_fallback, turkish_fallback)]
        return []

    aligned_units: list[tuple[str, str]] = []
    if len(german_units) == len(turkish_units):
        aligned_units = list(zip(german_units, turkish_units))
    else:
        batch_count = max(
            1,
            max(
                (len(german_units) + PARALLEL_TEXT_BATCH_UNIT_LIMIT - 1) // PARALLEL_TEXT_BATCH_UNIT_LIMIT,
                (len(turkish_units) + PARALLEL_TEXT_BATCH_UNIT_LIMIT - 1) // PARALLEL_TEXT_BATCH_UNIT_LIMIT,
            ),
        )
        batch_count = min(batch_count, max(len(german_units), len(turkish_units)))
        for index in range(batch_count):
            german_start = round(index * len(german_units) / batch_count)
            german_end = round((index + 1) * len(german_units) / batch_count)
            turkish_start = round(index * len(turkish_units) / batch_count)
            turkish_end = round((index + 1) * len(turkish_units) / batch_count)
            german_chunk = " ".join(german_units[german_start:german_end]).strip()
            turkish_chunk = " ".join(turkish_units[turkish_start:turkish_end]).strip()
            if german_chunk and turkish_chunk:
                aligned_units.append((german_chunk, turkish_chunk))

    if not aligned_units and german_fallback and turkish_fallback:
        aligned_units.append((german_fallback, turkish_fallback))

    batches: list[tuple[str, str]] = []
    current_german_parts: list[str] = []
    current_turkish_parts: list[str] = []
    for german_unit, turkish_unit in aligned_units:
        proposed_german = normalize_whitespace(" ".join([*current_german_parts, german_unit]))
        proposed_turkish = normalize_whitespace(" ".join([*current_turkish_parts, turkish_unit]))
        if current_german_parts and (
            len(current_german_parts) >= PARALLEL_TEXT_BATCH_UNIT_LIMIT
            or len(proposed_german) > PARALLEL_TEXT_BATCH_MAX_CHARS
            or len(proposed_turkish) > PARALLEL_TEXT_BATCH_MAX_CHARS
        ):
            batches.append((normalize_whitespace(" ".join(current_german_parts)), normalize_whitespace(" ".join(current_turkish_parts))))
            current_german_parts = [german_unit]
            current_turkish_parts = [turkish_unit]
            continue
        current_german_parts.append(german_unit)
        current_turkish_parts.append(turkish_unit)

    if current_german_parts and current_turkish_parts:
        batches.append((normalize_whitespace(" ".join(current_german_parts)), normalize_whitespace(" ".join(current_turkish_parts))))

    return [(german_chunk, turkish_chunk) for german_chunk, turkish_chunk in batches if german_chunk and turkish_chunk]


def build_candidate_examples(text: str) -> dict[str, str]:
    sentence_map: dict[str, str] = {}
    for sentence in split_text_into_sentences(text):
        for token in URL_IMPORT_TOKEN_RE.findall(sentence):
            normalized = normalize_import_term(token)
            if not normalized or normalized in sentence_map:
                continue
            sentence_map[normalized] = sentence
    return sentence_map


def translate_german_sentence_to_turkish(sentence: str) -> str:
    normalized_sentence = normalize_whitespace(sentence)
    if not normalized_sentence:
        return ""
    cached = _google_translate_sentence_cache.get(normalized_sentence)
    if cached is not None:
        return cached

    shortened = normalized_sentence[:GOOGLE_TRANSLATE_MAX_SENTENCE_CHARS]
    query = urlencode(
        {
            "client": "gtx",
            "sl": "de",
            "tl": "tr",
            "dt": "t",
            "q": shortened,
        },
        doseq=True,
    )
    url = f"{GOOGLE_TRANSLATE_SENTENCE_ENDPOINT}?{query}"
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        payload = json.loads(urlopen(request, timeout=GOOGLE_TRANSLATE_TIMEOUT_SECONDS).read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        _google_translate_sentence_cache[normalized_sentence] = ""
        return ""

    translated_parts: list[str] = []
    if isinstance(payload, list) and payload:
        first_block = payload[0]
        if isinstance(first_block, list):
            for item in first_block:
                if isinstance(item, list) and item:
                    translated_text = normalize_whitespace(str(item[0] or ""))
                    if translated_text:
                        translated_parts.append(translated_text)

    translated_sentence = normalize_whitespace(" ".join(translated_parts))
    _google_translate_sentence_cache[normalized_sentence] = translated_sentence
    return translated_sentence


def translate_german_text_locally(text: str) -> dict:
    normalized_text = normalize_whitespace(text)
    if not normalized_text:
        return {"status": "idle", "translation": "", "source": "Yerel çeviri bekleniyor."}
    cached = _argos_translate_text_cache.get(normalized_text)
    if cached is not None:
        return cached
    if not ARGOS_TRANSLATE_AVAILABLE or argos_translate is None:
        result = {
            "status": "unavailable",
            "translation": "",
            "source": "Argos Translate kurulu değil.",
        }
        _argos_translate_text_cache[normalized_text] = result
        return result
    try:
        translated_text = normalize_whitespace(argos_translate.translate(normalized_text, "de", "tr"))
    except Exception as exc:
        result = {
            "status": "error",
            "translation": "",
            "source": f"Yerel çeviri kullanılamadı: {exc}",
        }
        _argos_translate_text_cache[normalized_text] = result
        return result
    if not translated_text:
        result = {
            "status": "error",
            "translation": "",
            "source": "Yerel çeviri boş döndü.",
        }
        _argos_translate_text_cache[normalized_text] = result
        return result
    result = {
        "status": "ok",
        "translation": translated_text,
        "source": "Argos Translate (açık kaynak, yerel)",
    }
    _argos_translate_text_cache[normalized_text] = result
    return result


def build_libretranslate_url(api_url: str) -> str:
    cleaned = str(api_url or "").strip()
    if not cleaned:
        return LIBRETRANSLATE_DEFAULT_URL
    return cleaned if cleaned.endswith("/translate") else f"{cleaned.rstrip('/')}/translate"


def is_managed_libretranslate_url(api_url: str) -> bool:
    try:
        hostname = (urlparse(str(api_url or "").strip()).hostname or "").casefold()
    except Exception:
        return False
    return hostname in {"libretranslate.com", "www.libretranslate.com"}


def build_libretranslate_candidate_urls(api_url: str, api_key: str = "") -> list[str]:
    primary = build_libretranslate_url(api_url)
    candidates = [primary]
    if not api_key and is_managed_libretranslate_url(primary):
        candidates = [*LIBRETRANSLATE_PUBLIC_FALLBACK_URLS, primary]
    unique_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = build_libretranslate_url(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_candidates.append(normalized)
    return unique_candidates


def translate_german_text_with_libretranslate(text: str, api_url: str, api_key: str = "") -> dict:
    normalized_text = normalize_whitespace(text)
    if not normalized_text:
        return {"status": "idle", "translation": "", "source": "LibreTranslate çevirisi bekleniyor."}

    endpoint = build_libretranslate_url(api_url)
    cache_key = f"{endpoint}|{normalized_text}"
    cached = _libretranslate_text_cache.get(cache_key)
    if cached is not None:
        return cached

    request_payload = {
        "q": normalized_text,
        "source": "de",
        "target": "tr",
        "format": "text",
    }
    if api_key:
        request_payload["api_key"] = api_key
    last_result: dict | None = None
    for candidate_url in build_libretranslate_candidate_urls(api_url, api_key):
        try:
            request = Request(
                candidate_url,
                data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DictionaryDesktop/1.0",
                },
                method="POST",
            )
            with urlopen(request, timeout=LIBRETRANSLATE_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = ""
            try:
                detail = normalize_whitespace(exc.read().decode("utf-8", errors="replace"))
            except Exception:
                detail = ""
            detail_lower = detail.casefold()
            if (
                not api_key
                and is_managed_libretranslate_url(candidate_url)
                and ("api key" in detail_lower or "portal.libretranslate.com" in detail_lower)
            ):
                last_result = {
                    "status": "unavailable",
                    "translation": "",
                    "source": (
                        "libretranslate.com artik API anahtari istiyor. Ayarlara bir API key girin "
                        "veya self-hosted / public mirror bir LibreTranslate adresi kullanin."
                    ),
                }
                continue
            last_result = {
                "status": "error",
                "translation": "",
                "source": detail or f"LibreTranslate HTTP hatasi: {exc.code}",
            }
            continue
        except (URLError, TimeoutError, OSError) as exc:
            last_result = {
                "status": "offline",
                "translation": "",
                "source": f"Internet baglantisi yok veya LibreTranslate hizmetine ulasilamadi: {exc}",
            }
            continue
        except Exception as exc:
            last_result = {
                "status": "error",
                "translation": "",
                "source": f"LibreTranslate cevirisi alinamadi: {exc}",
            }
            continue

        translated_text = normalize_whitespace(payload.get("translatedText", ""))
        error_text = normalize_whitespace(payload.get("error", ""))
        if error_text:
            error_lower = error_text.casefold()
            if (
                not api_key
                and is_managed_libretranslate_url(candidate_url)
                and ("api key" in error_lower or "portal.libretranslate.com" in error_lower)
            ):
                last_result = {
                    "status": "unavailable",
                    "translation": "",
                    "source": (
                        "libretranslate.com artik API anahtari istiyor. Ayarlara bir API key girin "
                        "veya self-hosted / public mirror bir LibreTranslate adresi kullanin."
                    ),
                }
                continue
            last_result = {"status": "error", "translation": "", "source": error_text}
            continue
        if not translated_text:
            last_result = {"status": "error", "translation": "", "source": "LibreTranslate bos yanit dondu."}
            continue

        provider_label = "LibreTranslate (cevrimici ceviri)"
        if candidate_url != endpoint:
            provider_label = f"LibreTranslate public mirror ({urlparse(candidate_url).netloc})"
        result = {
            "status": "ok",
            "translation": translated_text,
            "source": provider_label,
        }
        _libretranslate_text_cache[cache_key] = result
        return result

    result = last_result or {
        "status": "unavailable",
        "translation": "",
        "source": "LibreTranslate ayari hazir degil.",
    }
    _libretranslate_text_cache[cache_key] = result
    return result


def apply_url_example_translations(candidates: list[dict]) -> None:
    if not candidates:
        return

    sentence_translations: dict[str, str] = {}
    for item in candidates:
        sentence = normalize_whitespace(item.get("ornek_almanca", ""))
        if not sentence or sentence in sentence_translations:
            continue
        sentence_translations[sentence] = translate_german_sentence_to_turkish(sentence)

    for item in candidates:
        sentence = normalize_whitespace(item.get("ornek_almanca", ""))
        if not sentence:
            continue
        translated_sentence = sentence_translations.get(sentence, "")
        if translated_sentence:
            item["ornek_turkce"] = translated_sentence
        example_items = item.get("ornekler", [])
        if example_items and isinstance(example_items[0], dict):
            if translated_sentence:
                example_items[0]["turkce"] = translated_sentence
            example_items[0]["not"] = (
                "Kelimenin kaynak sayfadaki gerçek kullanım cümlesi. Türkçe çeviri Google Çeviri ile otomatik üretildi."
                if translated_sentence
                else "Kelimenin kaynak sayfadaki gerçek kullanım cümlesi."
            )


def extract_url_import_candidates(text: str, existing_terms: set[str], cursor: sqlite3.Cursor | None) -> list[dict]:
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    example_sentences = build_candidate_examples(text)

    lowercase_seen: set[str] = set()
    for token in URL_IMPORT_TOKEN_RE.findall(text):
        normalized = normalize_import_term(token)
        if not normalized:
            continue
        if token[:1].islower():
            lowercase_seen.add(normalized)

    for token in URL_IMPORT_TOKEN_RE.findall(text):
        normalized = normalize_import_term(token)
        if not normalized or normalized in existing_terms:
            continue
        if normalized in GERMAN_IMPORT_STOPWORDS:
            continue
        if len(normalized) < 4 or len(normalized) > 32:
            continue
        counts[normalized] += 1
        current_label = labels.get(normalized)
        if current_label is None or (token[:1].isupper() and not current_label[:1].isupper()):
            labels[normalized] = token

    candidates: list[dict] = []
    for normalized, frequency in counts.most_common(MAX_IMPORT_CANDIDATES):
        german = labels.get(normalized, normalized)
        suggestion = lookup_import_translation(german, cursor)
        # Skip likely proper nouns: only appeared capitalised, no translation, and rare
        if (
            suggestion["source"] == "Öneri yok"
            and normalized not in lowercase_seen
            and frequency <= 1
        ):
            continue
        # Skip inflected forms whose WikDict base form is already in our dictionary
        wr_key = normalize_import_term(suggestion.get("written_rep", ""))
        if wr_key and wr_key != normalized and wr_key in existing_terms:
            continue
        example_sentence = example_sentences.get(normalized, "")
        example_items = []
        if example_sentence:
            example_items.append(
                {
                    "almanca": example_sentence,
                    "turkce": "",
                    "kaynak": "URL içeriği",
                    "not": "Kelimenin kaynak sayfadaki gerçek kullanım cümlesi.",
                }
            )
        candidates.append(
            {
                "id": normalized,
                "almanca": german,
                "turkce": suggestion["translation"],
                "tur": guess_import_pos(german),
                "artikel": "",
                "kaynak_etiketi": suggestion["source"],
                "frekans": frequency,
                "ornek_almanca": example_sentence,
                "ornek_turkce": "",
                "ornekler": example_items,
                "ekle": True,
            }
        )
    apply_url_example_translations(candidates)
    return candidates


def collect_url_import_candidates(url: str, existing_terms: set[str]) -> tuple[str, list[dict]]:
    final_url, text = fetch_visible_text_from_url(url)
    connection = sqlite3.connect(str(WIKDICT_PATH)) if WIKDICT_PATH.exists() else None
    try:
        cursor = connection.cursor() if connection else None
        candidates = extract_url_import_candidates(text, existing_terms, cursor)
    finally:
        if connection is not None:
            connection.close()
    return final_url, candidates


def split_translation_variants(value: str) -> list[str]:
    raw = normalize_whitespace(value)
    if not raw:
        return []
    parts = [raw, *re.split(r"[;,/|•\n]+", raw)]
    variants: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = normalize_whitespace(re.sub(r"^\d+[.)]\s*", "", part)).strip(" -–—:()[]{}")
        key = normalize_text(cleaned)
        if not cleaned or key in seen:
            continue
        seen.add(key)
        variants.append(cleaned)
    return variants


def build_existing_meaning_index(records: list[dict]) -> dict[str, dict]:
    by_word: dict[str, set[str]] = {}
    by_word_pos: dict[tuple[str, str], set[str]] = {}
    labels: dict[str, list[str]] = {}
    for record in records:
        word_key = normalize_import_term(record.get("almanca", ""))
        pos_key = normalize_text(record.get("tur", ""))
        if not word_key:
            continue
        display_value = normalize_whitespace(record.get("turkce", ""))
        variants = split_translation_variants(record.get("turkce", ""))
        if not variants:
            continue
        normalized_variants = {normalize_text(item) for item in variants if normalize_text(item)}
        if not normalized_variants:
            continue
        by_word.setdefault(word_key, set()).update(normalized_variants)
        by_word_pos.setdefault((word_key, pos_key), set()).update(normalized_variants)
        label_bucket = labels.setdefault(word_key, [])
        if display_value and display_value not in label_bucket:
            label_bucket.append(display_value)
    return {"by_word": by_word, "by_word_pos": by_word_pos, "labels": labels}


def normalize_openai_import_pos(value: str, fallback: str = "belirsiz") -> str:
    normalized = normalize_text(value)
    mapping = {
        "isim": "isim",
        "noun": "isim",
        "substantiv": "isim",
        "noun phrase": "isim",
        "fiil": "fiil",
        "verb": "fiil",
        "sıfat": "sıfat",
        "sifat": "sıfat",
        "adjektiv": "sıfat",
        "adjective": "sıfat",
        "zarf": "zarf",
        "adverb": "zarf",
        "ifade": "ifade",
        "phrase": "ifade",
        "redewendung": "ifade",
        "belirsiz": "belirsiz",
        "unknown": "belirsiz",
    }
    return mapping.get(normalized, fallback)


def normalize_openai_confidence(value: object, default: float = 0.0) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, confidence))


def extract_url_word_inventory(text: str, cursor: sqlite3.Cursor | None) -> list[dict]:
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    example_sentences = build_candidate_examples(text)
    for token in URL_IMPORT_TOKEN_RE.findall(text):
        normalized = normalize_import_term(token)
        if not normalized or normalized in GERMAN_IMPORT_STOPWORDS:
            continue
        if len(normalized) < 4 or len(normalized) > 32:
            continue
        counts[normalized] += 1
        current_label = labels.get(normalized)
        if current_label is None or (token[:1].isupper() and not current_label[:1].isupper()):
            labels[normalized] = token

    inventory: list[dict] = []
    for normalized, frequency in counts.most_common(URL_IMPORT_AI_MAX_WORDS):
        german = labels.get(normalized, normalized)
        suggestion = lookup_import_translation(german, cursor)
        inventory.append(
            {
                "id": normalized,
                "normalized": normalized,
                "almanca": german,
                "tur": guess_import_pos(german),
                "artikel": "",
                "frekans": frequency,
                "kaynak_etiketi": suggestion["source"],
                "turkce_oneri": suggestion["translation"],
                "ornek_almanca": example_sentences.get(normalized, ""),
            }
        )
    return inventory


def find_local_translation_evidence(translation_value: str, turkish_text: str) -> tuple[str, float]:
    normalized_chunk = normalize_text(turkish_text)
    if not normalized_chunk:
        return "", 0.0

    padded_chunk = f" {normalized_chunk} "
    chunk_tokens = set(re.findall(r"\w+", normalized_chunk, flags=re.UNICODE))
    raw_variants = [normalize_whitespace(part) for part in re.split(r"[;,/|\n]+", str(translation_value or ""))]
    variants: list[str] = []
    seen_variants: set[str] = set()
    for variant in raw_variants:
        normalized_variant = normalize_text(variant)
        if not normalized_variant or normalized_variant in seen_variants:
            continue
        seen_variants.add(normalized_variant)
        variants.append(variant)

    for variant in variants:
        normalized_variant = normalize_text(variant)
        if not normalized_variant:
            continue
        if f" {normalized_variant} " in padded_chunk:
            confidence = 0.8 if " " in normalized_variant else 0.74
            return variant, confidence
        variant_tokens = [token for token in re.findall(r"\w+", normalized_variant, flags=re.UNICODE) if token]
        if len(variant_tokens) >= 2 and all(token in chunk_tokens for token in variant_tokens):
            return variant, 0.62
    return "", 0.0


def collect_parallel_text_import_scan_local(
    german_text: str,
    turkish_text: str,
    existing_meaning_index: dict[str, dict],
) -> tuple[list[dict], str]:
    batches = build_parallel_text_batches(german_text, turkish_text)
    if not batches:
        return [], "Metin esleme icin hem Almanca hem Turkce metin gerekli."

    by_word = existing_meaning_index.get("by_word", {})
    by_word_pos = existing_meaning_index.get("by_word_pos", {})
    labels = existing_meaning_index.get("labels", {})
    candidate_map: dict[tuple[str, str], dict] = {}

    connection = sqlite3.connect(str(WIKDICT_PATH)) if WIKDICT_PATH.exists() else None
    if connection is None:
        return [], "Yerel metin esleme icin gerekli sozluk verisi bulunamadi."

    try:
        cursor = connection.cursor()
        for german_chunk, turkish_chunk in batches:
            inventory = extract_url_word_inventory(german_chunk, cursor)
            for item in inventory:
                translation_hint = normalize_whitespace(item.get("turkce", "")) or normalize_whitespace(item.get("turkce_oneri", ""))
                if not translation_hint:
                    continue

                evidence, confidence = find_local_translation_evidence(translation_hint, turkish_chunk)
                if not evidence:
                    continue

                normalized_word = normalize_import_term(item.get("almanca", ""))
                if not normalized_word or normalized_word in LOCAL_PARALLEL_IMPORT_STOPWORDS:
                    continue

                display_word = normalize_whitespace(item.get("almanca", ""))
                part_of_speech = item.get("tur", "belirsiz") or "belirsiz"
                if part_of_speech == "belirsiz":
                    continue
                if display_word and not display_word[:1].isupper() and evidence[:1].isupper() and part_of_speech != "zarf":
                    continue
                existing_for_word = by_word.get(normalized_word, set())
                existing_for_pos = by_word_pos.get((normalized_word, normalize_text(part_of_speech)), set())
                existing_labels = labels.get(normalized_word, [])

                for meaning in [normalize_whitespace(part) for part in re.split(r"[;,/|\n]+", translation_hint)]:
                    meaning_key = normalize_text(meaning)
                    if not meaning_key:
                        continue
                    if meaning_key in existing_for_word or meaning_key in existing_for_pos:
                        continue

                    matched_evidence, matched_confidence = find_local_translation_evidence(meaning, turkish_chunk)
                    if not matched_evidence:
                        continue

                    dedupe_key = (normalized_word, meaning_key)
                    candidate = {
                        "id": f"local::{normalized_word}::{meaning_key}",
                        "almanca": normalize_whitespace(item.get("almanca", "")),
                        "mevcut_turkce": ", ".join(existing_labels[:4]),
                        "turkce": meaning,
                        "tur": part_of_speech,
                        "artikel": "",
                        "kaynak_etiketi": "Yerel metin esleme",
                        "frekans": item.get("frekans", 1),
                        "ornek_almanca": normalize_whitespace(item.get("ornek_almanca", "")) or german_chunk,
                        "ornek_turkce": normalize_whitespace(turkish_chunk),
                        "ornekler": [
                            {
                                "almanca": normalize_whitespace(item.get("ornek_almanca", "")) or german_chunk,
                                "turkce": normalize_whitespace(turkish_chunk),
                                "kaynak": "Metin esleme",
                                "not": f"Yerel sozluk ipucuyla bulundu. Eslesme kaniti: {matched_evidence}",
                            }
                        ],
                        "ekle": True,
                        "guven": matched_confidence or confidence,
                        "eslesme_kaniti": matched_evidence or evidence,
                        "not": f"Yerel sozluk ipucuyla Almanca ve Turkce metin arasinda bulundu. Eslesme kaniti: {matched_evidence or evidence}",
                        "kaynak": "local-text-import",
                        "ceviri_durumu": "yerel-metin-esleme",
                        "ceviri_inceleme_notu": (
                            "Bu kayit model kullanmadan, yerel sozluk onerisi ile Turkce metin icinde bulunan "
                            f"eslesmeye gore hazirlandi. Kanit: {matched_evidence or evidence}"
                        ),
                        "ceviri_kaynaklari": [
                            {
                                "almanca": "WikDict onerisi",
                                "turkce": meaning,
                                "kaynak": "Yerel esleme",
                                "not": matched_evidence or evidence,
                            }
                        ],
                    }
                    existing_candidate = candidate_map.get(dedupe_key)
                    if existing_candidate is None or normalize_openai_confidence(candidate.get("guven", 0.0)) > normalize_openai_confidence(existing_candidate.get("guven", 0.0)):
                        candidate_map[dedupe_key] = candidate
    finally:
        connection.close()

    candidates = sorted(
        candidate_map.values(),
        key=lambda item: (-normalize_openai_confidence(item.get("guven", 0.0)), item.get("almanca", ""), item.get("turkce", "")),
    )
    if not candidates:
        return [], "Yerel metin esleme yeni kayit bulamadi; Turkce tarafta desteklenen anlam cikmadi."

    note = f"Yerel metin esleme {len(candidates)} kayit hazirladi."
    if len(batches) > 1:
        note += f" Metin {len(batches)} parcada analiz edildi."
    return candidates, note


def build_llm_api_url(api_url: str) -> str:
    cleaned = str(api_url or "").strip()
    if not cleaned:
        return LLM_CHAT_COMPLETIONS_FALLBACK_URL
    lowered = cleaned.casefold().rstrip("/")
    if lowered.endswith("/chat/completions"):
        return cleaned
    if lowered.endswith("/v1"):
        return f"{cleaned.rstrip('/')}/chat/completions"
    if lowered.endswith("/api/chat"):
        return cleaned
    return f"{cleaned.rstrip('/')}/v1/chat/completions"


def format_llm_label(model: str, api_url: str) -> str:
    model_name = normalize_whitespace(model) or "Yerel model"
    try:
        host = urlparse(build_llm_api_url(api_url)).netloc or "yerel"
    except Exception:
        host = "yerel"
    return f"{model_name} ({host})"


def request_llm_json(
    api_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_payload: dict,
    timeout_seconds: int,
) -> dict:
    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AlmancaTurkceSozluk/desktop",
    }
    cleaned_api_key = str(api_key or "").strip()
    if cleaned_api_key:
        headers["Authorization"] = f"Bearer {cleaned_api_key}"
    encoded_body = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    retry_delays = [5, 15]  # hata alınırsa 5s, sonra 15s bekle
    last_exc: Exception | None = None
    for attempt in range(len(retry_delays) + 1):
        if attempt > 0:
            time.sleep(retry_delays[attempt - 1])
        try:
            request = Request(
                build_llm_api_url(api_url),
                data=encoded_body,
                headers=headers,
                method="POST",
            )
            with urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429 and attempt < len(retry_delays):
                last_exc = exc
                continue  # bekle ve tekrar dene
            raise
    raise last_exc  # type: ignore[misc]


def extract_openai_message_content(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()
    return ""


def extract_json_object_from_text(text: str) -> dict:
    cleaned = str(text or "").strip()
    if not cleaned:
        raise ValueError("Model boş yanıt döndürdü.")
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Model yanıtı JSON nesnesi değil.")
    json_str = cleaned[start : end + 1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as parse_err:
        # Model yanıtı token limiti nedeniyle yarım kesilebilir.
        # Hata konumuna kadar geri gidip son tam entry'yi bul.
        cutoff = parse_err.pos
        for search_str in (json_str[:cutoff], json_str):
            last_comma_entry = search_str.rfind("},")
            last_close = search_str.rfind("}")
            for boundary in (last_comma_entry, last_close):
                if boundary <= 0:
                    continue
                repaired = search_str[: boundary + 1].rstrip().rstrip(",") + "]}"
                try:
                    result = json.loads(repaired)
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"Model yanıtı geçerli JSON değil: {parse_err}")


def request_openai_meaning_batch(
    api_url: str,
    api_key: str,
    model: str,
    page_url: str,
    items: list[dict],
) -> list[dict]:
    system_prompt = (
        "You prepare German-to-Turkish dictionary suggestions from a webpage. "
        "Return only JSON. For each item, suggest short Turkish dictionary meanings based on the example sentence and page context. "
        "Keep meanings concise, distinct, and in Turkish. Do not invent meanings unrelated to the sentence. "
        "If the article is unknown, leave it empty. If the word is not a meaningful German dictionary candidate, return an empty meanings array."
    )
    user_payload = {
        "page_url": page_url,
        "instructions": {
            "return_shape": {
                "entries": [
                    {
                        "word": "German lemma",
                        "part_of_speech": "isim | fiil | sıfat | zarf | ifade | belirsiz",
                        "article": "der | die | das | ''",
                        "meanings": ["short Turkish meaning"],
                        "usage_sentence": "German example sentence from the page",
                    }
                ]
            }
        },
        "items": items,
    }
    payload = request_llm_json(api_url, api_key, model, system_prompt, user_payload, 45)
    content = extract_openai_message_content(payload)
    result = extract_json_object_from_text(content)
    entries = result.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("Model yanıtı beklenen 'entries' alanını içermiyor.")
    normalized_entries: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        word = normalize_whitespace(entry.get("word", ""))
        part_of_speech = normalize_openai_import_pos(entry.get("part_of_speech", "belirsiz"))
        article = normalize_whitespace(entry.get("article", ""))
        article = article if article in {"", "der", "die", "das"} else ""
        usage_sentence = normalize_whitespace(entry.get("usage_sentence", ""))
        meanings: list[str] = []
        for meaning in entry.get("meanings", []) if isinstance(entry.get("meanings", []), list) else []:
            cleaned = normalize_whitespace(str(meaning))
            if cleaned and cleaned not in meanings:
                meanings.append(cleaned)
        if not word:
            continue
        normalized_entries.append(
            {
                "word": word,
                "part_of_speech": part_of_speech,
                "article": article,
                "meanings": meanings[:5],
                "usage_sentence": usage_sentence,
            }
        )
    return normalized_entries


def request_openai_parallel_text_batch(
    api_url: str,
    api_key: str,
    model: str,
    german_text: str,
    turkish_text: str,
) -> list[dict]:
    system_prompt = (
        "You align a German source text with its Turkish translation and prepare dictionary candidates. "
        "Return only JSON. Extract only meaningful German lemmas or short expressions that have a clear Turkish meaning in the provided translation. "
        "Ignore articles, pronouns, very common function words, names, and punctuation-only items. "
        "Prefer canonical lemma forms. Meanings must be short Turkish dictionary glosses. "
        "If a mapping is not reasonably supported by the parallel text, omit it."
    )
    user_payload = {
        "source_language": "de",
        "target_language": "tr",
        "instructions": {
            "return_shape": {
                "entries": [
                    {
                        "word": "German lemma",
                        "part_of_speech": "isim | fiil | sıfat | zarf | ifade | belirsiz",
                        "article": "der | die | das | ''",
                        "meanings": ["short Turkish meaning"],
                        "german_sentence": "supporting German sentence",
                        "turkish_sentence": "supporting Turkish sentence",
                    }
                ]
            }
        },
        "german_text": normalize_whitespace(german_text),
        "turkish_text": normalize_whitespace(turkish_text),
    }
    payload = request_llm_json(api_url, api_key, model, system_prompt, user_payload, 60)
    content = extract_openai_message_content(payload)
    result = extract_json_object_from_text(content)
    entries = result.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("Model yanıtı beklenen 'entries' alanını içermiyor.")
    normalized_entries: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        word = normalize_whitespace(entry.get("word", ""))
        part_of_speech = normalize_openai_import_pos(entry.get("part_of_speech", "belirsiz"))
        article = normalize_whitespace(entry.get("article", ""))
        article = article if article in {"", "der", "die", "das"} else ""
        german_sentence = normalize_whitespace(entry.get("german_sentence", ""))
        turkish_sentence = normalize_whitespace(entry.get("turkish_sentence", ""))
        meanings: list[str] = []
        for meaning in entry.get("meanings", []) if isinstance(entry.get("meanings", []), list) else []:
            cleaned = normalize_whitespace(str(meaning))
            if cleaned and cleaned not in meanings:
                meanings.append(cleaned)
        if not word or not meanings:
            continue
        normalized_entries.append(
            {
                "word": word,
                "part_of_speech": part_of_speech,
                "article": article,
                "meanings": meanings[:6],
                "german_sentence": german_sentence,
                "turkish_sentence": turkish_sentence,
            }
        )
    return normalized_entries


def request_openai_parallel_text_batch_strict(
    api_url: str,
    api_key: str,
    model: str,
    german_text: str,
    turkish_text: str,
) -> list[dict]:
    system_prompt = (
        "You align a German source text with its Turkish translation and prepare dictionary candidates. "
        "Return only JSON. Extract only meaningful German lemmas or short expressions that are explicitly supported by the Turkish translation. "
        "Every entry must be backed by one German support sentence and one Turkish support sentence copied from the provided texts. "
        "Provide a short Turkish evidence phrase copied from the Turkish sentence and a confidence score between 0 and 1. "
        "Ignore articles, pronouns, very common function words, names, and punctuation-only items. "
        "Prefer canonical lemma forms. Meanings must be short Turkish dictionary glosses. "
        "If confidence would be below 0.60 or the mapping is not reasonably supported by the parallel text, omit it."
    )
    user_payload = {
        "source_language": "de",
        "target_language": "tr",
        "instructions": {
            "return_shape": {
                "entries": [
                    {
                        "word": "German lemma",
                        "part_of_speech": "isim | fiil | sıfat | zarf | ifade | belirsiz",
                        "article": "der | die | das | ''",
                        "meanings": ["short Turkish meaning"],
                        "german_sentence": "supporting German sentence",
                        "turkish_sentence": "supporting Turkish sentence",
                        "turkish_evidence": "short Turkish phrase copied from the translation",
                        "confidence": 0.0,
                    }
                ]
            }
        },
        "german_text": normalize_whitespace(german_text),
        "turkish_text": normalize_whitespace(turkish_text),
    }
    payload = request_llm_json(api_url, api_key, model, system_prompt, user_payload, 60)
    content = extract_openai_message_content(payload)
    result = extract_json_object_from_text(content)
    entries = result.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("Model yanıtı beklenen 'entries' alanını içermiyor.")

    normalized_entries: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        word = normalize_whitespace(entry.get("word", ""))
        part_of_speech = normalize_openai_import_pos(entry.get("part_of_speech", "belirsiz"))
        article = normalize_whitespace(entry.get("article", ""))
        article = article if article in {"", "der", "die", "das"} else ""
        german_sentence = normalize_whitespace(entry.get("german_sentence", ""))
        turkish_sentence = normalize_whitespace(entry.get("turkish_sentence", ""))
        turkish_evidence = normalize_whitespace(entry.get("turkish_evidence", ""))
        confidence = normalize_openai_confidence(entry.get("confidence", 0.0))
        meanings: list[str] = []
        for meaning in entry.get("meanings", []) if isinstance(entry.get("meanings", []), list) else []:
            cleaned = normalize_whitespace(str(meaning))
            if cleaned and cleaned not in meanings:
                meanings.append(cleaned)
        if not word or not meanings:
            continue
        normalized_entries.append(
            {
                "word": word,
                "part_of_speech": part_of_speech,
                "article": article,
                "meanings": meanings[:6],
                "german_sentence": german_sentence,
                "turkish_sentence": turkish_sentence,
                "turkish_evidence": turkish_evidence,
                "confidence": confidence,
            }
        )
    return normalized_entries


def extract_openai_meaning_candidates(
    page_url: str,
    inventory: list[dict],
    existing_meaning_index: dict[str, dict],
    api_url: str,
    api_key: str,
    model: str,
) -> tuple[list[dict], str]:
    if not model.strip():
        return [], "Model anlam onerileri icin bir model adi girin."

    inventory_map = {item["normalized"]: item for item in inventory}
    labels = existing_meaning_index.get("labels", {})
    by_word = existing_meaning_index.get("by_word", {})
    by_word_pos = existing_meaning_index.get("by_word_pos", {})
    seen_keys: set[tuple[str, str]] = set()
    candidates: list[dict] = []

    for start in range(0, len(inventory), URL_IMPORT_AI_BATCH_SIZE):
        chunk = inventory[start : start + URL_IMPORT_AI_BATCH_SIZE]
        request_items = []
        for item in chunk:
            request_items.append(
                {
                    "word": item.get("almanca", ""),
                    "part_of_speech_guess": item.get("tur", "belirsiz"),
                    "example_sentence": item.get("ornek_almanca", ""),
                    "local_translation_hint": item.get("turkce_oneri", ""),
                    "existing_meanings": labels.get(item["normalized"], []),
                }
            )
        batch_entries = request_openai_meaning_batch(api_url, api_key, model, page_url, request_items)
        for entry in batch_entries:
            normalized_word = normalize_import_term(entry.get("word", ""))
            base_item = inventory_map.get(normalized_word)
            if not normalized_word or base_item is None:
                continue
            part_of_speech = normalize_openai_import_pos(entry.get("part_of_speech", ""), base_item.get("tur", "belirsiz"))
            existing_for_word = by_word.get(normalized_word, set())
            existing_for_pos = by_word_pos.get((normalized_word, normalize_text(part_of_speech)), set())
            existing_labels = labels.get(normalized_word, [])
            for meaning in entry.get("meanings", []):
                meaning_key = normalize_text(meaning)
                if not meaning_key:
                    continue
                if meaning_key in existing_for_word or meaning_key in existing_for_pos:
                    continue
                dedupe_key = (normalized_word, meaning_key)
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                example_sentence = normalize_whitespace(entry.get("usage_sentence", "")) or base_item.get("ornek_almanca", "")
                example_items = []
                if example_sentence:
                    example_items.append(
                        {
                            "almanca": example_sentence,
                            "turkce": "",
                            "kaynak": "URL içeriği",
                            "not": "Kelimenin kaynak sayfadaki gerçek kullanım cümlesi.",
                        }
                    )
                candidates.append(
                    {
                        "id": f"{normalized_word}::{meaning_key}",
                        "almanca": base_item.get("almanca", entry.get("word", "")),
                        "mevcut_turkce": ", ".join(existing_labels[:4]),
                        "turkce": meaning,
                        "tur": part_of_speech,
                        "artikel": entry.get("article", "") if part_of_speech == "isim" else "",
                        "kaynak_etiketi": format_llm_label(model, api_url),
                        "frekans": base_item.get("frekans", 0),
                        "ornek_almanca": example_sentence,
                        "ornek_turkce": "",
                        "ornekler": example_items,
                        "ekle": True,
                        "not": f"Model anlam onerisi; kaynak URL: {page_url}",
                        "kaynak": "llm-url-import",
                        "ceviri_durumu": "model-oneri",
                        "ceviri_inceleme_notu": "Bu anlam, URL baglamina gore yerel/uyumlu model tarafindan onerildi ve kullanici onayiyla eklendi.",
                        "ceviri_kaynaklari": [
                            {
                                "almanca": format_llm_label(model, api_url),
                                "turkce": "Model anlam onerisi",
                                "kaynak": "Yerel/Uyumlu model",
                                "not": page_url,
                            }
                        ],
                    }
                )

    if not candidates:
        return [], "Model sekmesinde yeni veya eksik anlam bulunamadi."
    return candidates, f"Model sekmesi {len(candidates)} yeni veya eksik anlam onerdi."


def test_llm_connection(api_url: str, api_key: str, model: str) -> tuple[bool, str]:
    """Gemini/LLM bağlantısını test eder. (başarılı, mesaj) döndürür."""
    if not api_key.strip():
        return False, "API anahtarı girilmemiş. Ayarlar → Kelime Ekle / Aktar → AI Modeli bölümünden girin."
    if not model.strip():
        return False, "Model adı girilmemiş."
    try:
        payload = request_llm_json(
            api_url, api_key, model,
            "You are a test assistant. Reply with a single word.",
            {"test": "Say OK."},
            10,
        )
        content = extract_openai_message_content(payload)
        if content:
            return True, f"✓ Bağlantı başarılı — {format_llm_label(model, api_url)}"
        return False, "Model boş yanıt döndürdü."
    except Exception as exc:
        msg = str(exc)
        if "429" in msg:
            return False, "⚠ API anahtarı geçerli, istek limiti doldu (429). 1 dakika bekleyip doğrudan 'URL'yi Tara'ya basın — API Test gerekmez."
        if "401" in msg or "API key" in msg.lower() or "api_key" in msg.lower():
            return False, "✗ Geçersiz API anahtarı (401). Anahtarı kontrol edin."
        if "403" in msg:
            return False, "✗ Erişim reddedildi (403). Anahtarın bu model için yetkisi var mı?"
        if "404" in msg:
            return False, "✗ Model bulunamadı (404). Model adını kontrol edin."
        return False, f"✗ Bağlantı hatası: {msg[:120]}"


def chunk_text(text: str, max_chars: int = GEMINI_CHUNK_SIZE) -> list[str]:
    """Metni cümle/paragraf sınırlarında parçalara böler."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        candidate = remaining[:max_chars]
        # Önce paragraf sonu, sonra cümle sonu ara
        cut = -1
        for sep in ("\n", ". ", "! ", "? ", "; "):
            pos = candidate.rfind(sep)
            if pos > max_chars // 3:
                cut = pos + len(sep)
                break
        if cut < 0:
            cut = max_chars
        chunk = remaining[:cut].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].strip()
    return chunks


_GERMAN_MARKERS = re.compile(
    r"ä|ß"                                    # Türkçede olmayan Almanca karakterler
    r"|(?<!\w)(der|die|das|den|dem|des"
    r"|ein|eine|einen|einem|einer"
    r"|ist|sind|hat|haben|wird|werden"
    r"|verliert|verlieren|macht|machen"
    r"|nicht|auch|oder|und|aber|wenn"
    r"|durch|nach|über|unter|zwischen"
    r"|gegen|ohne|beim|vom|zum|zur"
    r"|dieser|dieses|diesem|diesen|diese"
    r"|er|sie|es|wir|ihr|man|sie|Sie"
    r"|können|müssen|sollen|wollen|dürfen|mögen"
    r"|wurde|wurden|worden|gewesen|geworden)(?!\w)",
    re.IGNORECASE,
)

# Türkçeye özgü karakterler ve kelimeler — bunlar varsa metin Türkçedir
_TURKISH_MARKERS = re.compile(
    r"[ışğ]"                                  # Türkçeye özgü harfler (Almancada yok)
    r"|(?<!\w)(bir|bu|şu|ve|de|da|ile|için"
    r"|olan|olan|gibi|kadar|daha|çok|nasıl"
    r"|ama|veya|ya|ki|mi|mı|mu|mü"
    r"|değil|var|yok|olarak|ise|eğer)(?!\w)",
    re.IGNORECASE,
)

def _looks_like_german(text: str) -> bool:
    """Verilen metnin Türkçe değil Almanca olup olmadığını tespit eder.

    Bir metin hem Almanca hem Türkçe işaretleri içeriyorsa Almanca sayılmaz
    (karma dil durumu, muhtemelen Türkçe açıklama içinde Almanca örnek).
    """
    if not text:
        return False
    # Önce Türkçe kontrol: net Türkçe işaretleri varsa Almanca değil
    turkish_matches = _TURKISH_MARKERS.findall(text)
    has_turkish_specific = bool(re.search(r"[ışğ]", text))
    if has_turkish_specific or len(turkish_matches) >= 3:
        return False
    # Almanca kontrol
    german_matches = _GERMAN_MARKERS.findall(text)
    has_umlaut_ae_ss = bool(re.search(r"ä|ß", text))
    return has_umlaut_ae_ss or len(german_matches) >= 2


def _process_gemini_entries(
    entries: list,
    existing_terms: set[str],
    existing_meaning_index: dict,
    seen: set[str],
    page_url: str,
    api_url: str,
    api_key: str,
    model: str,
    llm_label: str = "",
    seen_existing_out: set[str] | None = None,
) -> list[dict]:
    """Gemini'den gelen entry listesini sözlük adaylarına dönüştürür."""
    by_word = existing_meaning_index.get("by_word", {})
    labels = existing_meaning_index.get("labels", {})
    candidates: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        word = normalize_whitespace(entry.get("word", ""))
        if not word:
            continue
        # Sayı / büyük harf kısaltma / çok kısa kelimeleri atla
        if _should_skip_entry(word):
            continue
        normalized = normalize_import_term(word)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        pos = normalize_openai_import_pos(entry.get("part_of_speech", ""), "belirsiz")
        # --- Partizip / çekimli sıfat POS düzeltmesi ---
        pos = _correct_participial_pos(word, pos)
        article = normalize_whitespace(entry.get("article", ""))
        article = article if article in {"", "der", "die", "das"} else ""
        if pos != "isim":
            article = ""
        trennbar_raw = entry.get("trennbar")
        trennbar = True if str(trennbar_raw).lower() == "true" else (False if str(trennbar_raw).lower() == "false" else None)
        verb_typ_raw = normalize_whitespace(str(entry.get("verb_typ") or "")).lower()
        verb_typ = verb_typ_raw if verb_typ_raw in {"schwach", "stark"} else None
        gecisli_raw = normalize_whitespace(str(entry.get("gecisli") or "")).lower()
        gecisli = gecisli_raw if gecisli_raw in {"transitiv", "intransitiv", "reflexiv"} else None
        not_gramatik = normalize_whitespace(str(entry.get("not_gramatik") or ""))
        example = normalize_whitespace(entry.get("example_sentence", ""))
        raw_example_tr = normalize_whitespace(entry.get("example_translation", ""))
        # Almanca döndürülmüşse örnek çeviriyi boş bırak
        example_tr = "" if _looks_like_german(raw_example_tr) else raw_example_tr
        meanings: list[str] = []
        for m in (entry.get("meanings") or []):
            cleaned = normalize_whitespace(str(m))
            # Almanca döndürülmüş anlamları filtrele
            if cleaned and cleaned not in meanings and not _looks_like_german(cleaned):
                meanings.append(cleaned)
        if not meanings:
            continue
        existing_for_word = by_word.get(normalized, set())
        existing_labels = labels.get(normalized, [])
        if normalized in existing_terms:
            display_meanings = [m for m in meanings if normalize_text(m) not in existing_for_word]
            if not display_meanings:
                # Word exists and has no new meanings — record it as "seen" for frekans increment
                if seen_existing_out is not None:
                    seen_existing_out.add(normalized)
                continue
        else:
            display_meanings = meanings
        example_items = []
        if example:
            example_items.append({
                "almanca": example,
                "turkce": example_tr,
                "kaynak": llm_label,
                "not": "Kelimenin kaynak sayfadaki gerçek kullanım cümlesi.",
            })
        candidates.append({
            "id": f"llm::{normalized}::{normalize_text(display_meanings[0])}",
            "almanca": word,
            "mevcut_turkce": ", ".join(existing_labels[:4]) if existing_labels else "",
            "turkce": "; ".join(display_meanings),
            "tur": pos,
            "artikel": article,
            "trennbar": trennbar,
            "verb_typ": verb_typ,
            "gecisli": gecisli,
            "kaynak_etiketi": llm_label,
            "frekans": 0,
            "ornek_almanca": example,
            "ornek_turkce": example_tr,
            "ornekler": example_items,
            "ekle": True,
            "not": f"{llm_label} tam metin çevirisi; kaynak URL: {page_url}",
            "kaynak": "URL Aktarma",
            "ceviri_durumu": "model-oneri",
            "ceviri_inceleme_notu": f"Bu kayıt, URL metninin {llm_label} tam metin çevirisiyle oluşturuldu ve kullanıcı onayıyla eklendi.",
            "ceviri_kaynaklari": [{
                "almanca": llm_label,
                "turkce": f"{llm_label} tam metin çevirisi",
                "kaynak": llm_label,
                "not": page_url,
            }],
            **({"not_gramatik": not_gramatik} if not_gramatik else {}),
        })
    return candidates


# Sayı / URL / e-posta / kısaltma desenlerini LLM'e göndermeden temizle
# NOT: 1-2 harfli kelimeleri SİLMİYORUZ — Almanca makaleler/edatlar (der/die/in/an)
# bağlamı korumak için gerekli; LLM bunlar olmadan article tespiti yapamaz.
_CHUNK_NOISE = re.compile(
    r"https?://\S+"                          # URL
    r"|www\.\S+"                             # www adresi
    r"|\S+@\S+\.\S+"                         # e-posta
    r"|\b\d[\d.,:/\-–%°\'\"]*\w{0,3}\b"     # sayılar (29, 3.5, 100%, 2024, €49, 5km, 100ps)
    r"|\b[A-Z]{3,}\d*\b"                     # tamamen büyük harf kısaltma (BMW, HTML, ABS; 2+ değil, çünkü "PS" vb. bağlamda lazım)
    , re.UNICODE
)

def _clean_chunk_for_llm(text: str) -> str:
    """Sayı, URL, kısaltma, çok kısa kelimeleri chunk'tan temizle."""
    cleaned = _CHUNK_NOISE.sub(" ", text)
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    return cleaned


# LLM sonuçlarını filtrele: sayı / özel isim / çok kısa
_WORD_IS_NUMBER    = re.compile(r"^\d[\d.,:/\-–%°]*$")
_WORD_IS_ALLCAPS   = re.compile(r"^[A-ZÄÖÜ]{2,}[\d]*$")        # BMW, PDF, ABS …
_WORD_TOO_SHORT    = re.compile(r"^\w{1,2}$")

def _should_skip_entry(word: str) -> bool:
    """Çevrilmemesi gereken kelimeyi filtrele."""
    w = word.strip()
    if not w:
        return True
    if _WORD_IS_NUMBER.match(w):       # 29, 3.5, 100%
        return True
    if _WORD_IS_ALLCAPS.match(w):      # BMW, PDF, HTML
        return True
    if _WORD_TOO_SHORT.match(w):       # a, an, ok
        return True
    if w[0].isdigit():                 # 29er, 3M
        return True
    return False


# Partizip 1: -end + çekim ekleri
_PARTIZIP1 = re.compile(
    r"[a-züäöß]{3,}end(?:e[mnrs]?|er|es)?$",
    re.IGNORECASE,
)
# Partizip 2: ge- + en az 2 kök harfi + (t | et | en | eten | enen …)
# gemacht=ge+mach+t, gefahren=ge+fahr+en, gebrochenen=ge+brochene+n
_PARTIZIP2 = re.compile(
    r"^ge[a-züäöß]{2,}[a-züäöß](?:ete[mnrs]?|ene[mnrs]?|eten|enen|et|en|t)$",
    re.IGNORECASE,
)
# Çekimli sıfat ekleri: -em / -es (bunlar ASLA fiil olamaz, güvenli filtre)
# {3,} → 'gutes','neues','altes','gutes' gibi kısa sıfatları da yakalar
_ADJ_EM_ES = re.compile(r"[a-züäöß]{3,}(?:em|es)$", re.IGNORECASE)

# Partizip 2 ama aynı zamanda sık kullanılan fiil (gehen, gelten, geben…)
# NOT: gemacht/gelernt burada YOK — bunlar gerçek Partizip-2, sıfat olarak düzeltilebilir
_COMMON_VERBS_GE = {"gehen", "geben", "gelten", "geraten", "genießen",
                    "gelingen", "geschehen", "gestehen", "gewinnen"}

# Güvenilir çoğul son ekleri → isim (küçük harfli bile olsa)
_RELIABLE_PLURAL_SUFFIX = re.compile(
    r"[a-züäöß]+(ungen|ionen|ationen|heiten|keiten|schaften)$",
    re.IGNORECASE,
)

# Türetilmiş sıfat ekleri + çekim eki (-en) → sıfat
# Örnek: soziale, technischen, natürlichen, digitalen, rechtliche
_DECLINED_ADJ_SUFFIX = re.compile(
    r"[a-züäöß]+(lich|ig|isch|ell|al|är|iv|ativ|ional|ion)en$",
    re.IGNORECASE,
)

# Üstünlük derecesi (superlativ) → sıfat
# Örnek: schnellsten, kleinsten, besten, größten, höchsten
_SUPERLATIVE = re.compile(
    r"[a-züäöß]{3,}st(?:en|em|er|es|e)$",
    re.IGNORECASE,
)

def _correct_participial_pos(word: str, pos: str) -> str:
    """
    LLM yanlış POS verirse düzelt:
    - Partizip 1 (-end, -ende, …)           → sıfat
    - Partizip 2 (ge-…-t/-en) adjectival    → sıfat
    - Çekimli sıfat (-em/-es)               → sıfat
    - Türetilmiş sıfat eki + -en            → sıfat  (-lichen/-ischen/-igen vb.)
    - Üstünlük derecesi (-sten/-stem vb.)   → sıfat
    - Güvenilir çoğul son ekleri            → isim   (-ungen/-heiten/-keiten vb.)
    - Tek-kelime "ifade" etiketleri         → isim
    """
    w = word.strip()
    wl = w.lower()

    # 1) Partizip 1 kontrolü (uzunluk > 5, -end ile bitiyor)
    if len(w) > 5 and _PARTIZIP1.match(wl):
        # "Abend" gibi isimler karışmasın: küçük harfle başlıyorsa güvenli
        if w[0].islower() or pos == "fiil":
            return "sıfat"

    # 2) Partizip 2 kontrolü
    if len(w) > 6 and _PARTIZIP2.match(wl) and wl not in _COMMON_VERBS_GE:
        if pos == "fiil":
            return "sıfat"

    # 3) Çekimli sıfat: -em / -es ekleri asla fiil olamaz (kleinem, schönes…)
    if pos == "fiil" and _ADJ_EM_ES.match(wl) and w[0].islower():
        return "sıfat"

    # 4) Türetilmiş sıfat + çekim eki -en → sıfat  (soziale→sozial, technischen→technisch)
    if pos in ("fiil", "isim", "ifade") and _DECLINED_ADJ_SUFFIX.match(wl) and w[0].islower():
        return "sıfat"

    # 5) Üstünlük derecesi -st+çekim → sıfat  (schnellsten, kleinsten, besten)
    if pos in ("fiil", "isim", "ifade") and _SUPERLATIVE.match(wl) and w[0].islower():
        return "sıfat"

    # 6) Güvenilir çoğul son ekleri → isim  (Handlungen, Nationen, Schönheiten)
    if pos in ("fiil", "ifade") and _RELIABLE_PLURAL_SUFFIX.match(wl):
        return "isim"

    # 7) Tek kelimeden oluşan "ifade" → büyük ihtimalle isim
    if pos == "ifade" and " " not in w:
        return "isim"

    return pos


def extract_gemini_full_text_candidates(
    text: str,
    page_url: str,
    existing_terms: set[str],
    existing_meaning_index: dict,
    api_url: str,
    api_key: str,
    model: str,
    progress_callback=None,
) -> tuple[list[dict], str, set[str]]:
    """Metni parçalara bölerek seçili AI modeline gönderir ve kelime adaylarını döndürür."""
    if not api_key.strip() or not model.strip():
        return [], "API anahtarı veya model adı eksik.", set()

    chunks = chunk_text(text[:GEMINI_MAX_TOTAL_CHARS], GEMINI_CHUNK_SIZE)
    if not chunks:
        return [], "Metinden parça çıkarılamadı."

    # URL'den alan bağlamını çıkar
    try:
        from urllib.parse import urlparse as _up
        _url_lower = (page_url or "").lower()
        _domain_hints = {
            "auto": "automotive, vehicles, engines, car technology",
            "kfz": "automotive, motor vehicles",
            "motor": "motors, automotive",
            "fahr": "driving, vehicles, transportation",
            "tech": "technology, engineering",
            "wissen": "science, knowledge, education",
            "nachrichten": "news, current events, politics",
            "wirtschaft": "economics, business, finance",
            "gesund": "health, medicine",
            "medizin": "medicine, healthcare",
            "politik": "politics, government",
            "sport": "sports, athletics",
            "kultur": "culture, arts",
            "wiki": "encyclopedic, general knowledge",
        }
        _topic_hint = ""
        for kw, hint in _domain_hints.items():
            if kw in _url_lower:
                _topic_hint = f" The source is a {hint} article — pay special attention to domain-specific vocabulary."
                break
    except Exception:
        _topic_hint = ""

    llm_label = format_llm_label(model, api_url)
    system_prompt = (
        "You are a German-Turkish dictionary assistant. "
        f"You receive a German text chunk extracted from a web page.{_topic_hint} "
        "Extract AS MANY meaningful German words and short expressions as possible from the text. "
        "Be GENEROUS — prefer to include rather than exclude. "
        "Nouns, verbs, adjectives, adverbs, compound words, technical terms — extract ALL of them. "
        "For each word provide its Turkish translation, part of speech, and article (if noun). "
        "Also include an example sentence from the text (in German) and its Turkish translation. "
        "Do NOT include conjugation tables — store only the infinitive form for verbs. "
        "Return ONLY valid JSON. "
        "\n\nCRITICAL LANGUAGE RULE: The 'meanings' array and 'example_translation' field MUST contain ONLY Turkish text. "
        "NEVER write German words, German sentences, or German phrases in the 'meanings' or 'example_translation' fields. "
        "If you cannot translate a word to Turkish, write 'bilinmiyor' — but NEVER write German as the Turkish translation. "
        "Example of WRONG output: meanings: ['verliert die Kontrolle'] — this is German, not Turkish. "
        "Example of CORRECT output: meanings: ['kontrolü kaybetmek', 'dengesini yitirmek']. "
        "\n\nSKIP ONLY the following (keep this list short — be generous otherwise): "
        "1. NUMBERS: pure numbers, years, measurements, percentages, prices — e.g. 29, 2024, 100%, 3.5, €499. "
        "2. PROPER NOUNS: brand names (BMW, VW, Toyota, Bosch), person names (Hans, Maria, Schmidt), "
        "   specific city/country names (Berlin, Deutschland). "
        "3. NON-GERMAN WORDS: English words (speed, update), Latin phrases — unless they are loanwords used in German. "
        "4. RAW ABBREVIATIONS: PDF, HTML, km/h, °C — unless the abbreviation has a clear German meaning. "
        "5. VERY SHORT fragments: single letters, words under 3 characters. "
        "6. PURE FUNCTION WORDS (only the most basic): der, die, das, und, oder, aber, nicht, auch, mit, von, "
        "   zu, in, an, auf, für, um, als, wenn, dass, ein, eine. "
        "\nInclude: ALL genuine German nouns, verbs, adjectives, adverbs, compound words, technical vocabulary, "
        "domain-specific terms, and even less common or specialized words — these are valuable for a dictionary. "
        "Aim for at least 20-40 entries per text chunk. Meanings must be short Turkish glosses, not full sentences."
        "\n\nLEMMATIZATION RULES — always use the base/dictionary form as 'word': "
        "- Verbs: INFINITIVE form only. fahren (NOT fährt / fuhr / gefahren / fahrend). "
        "- Separable verbs (trennbare Verben): include a note if the verb is separable. "
        "  Examples: aufmachen (auf- is separable), anrufen (an- is separable), einsteigen (ein- is separable). "
        "  Add 'trennbar: true' or 'trennbar: false' in the entry if you can identify it. "
        "- STRONG vs WEAK verbs: "
        "  Weak (regular) verbs add -te in Präteritum (machte, lernte, spielte). "
        "  Strong (irregular) verbs change their vowel (fuhr, lief, aß, gab). "
        "  For each verb, add field 'verb_typ': 'schwach' or 'stark'. "
        "  -ieren verbs are ALWAYS schwach: Partizip II = -iert (no ge-!). "
        "  Example: telefonieren → telefoniert (NOT getelefoniert). "
        "- TRANSITIVITY: add field 'gecisli': 'transitiv' (has direct object), "
        "  'intransitiv' (no direct object), or 'reflexiv' (sich + verb). "
        "- PERFEKT AUXILIARY: add field 'perfekt_yardimci': 'haben' or 'sein'. "
        "  Use 'sein' for: motion/movement verbs, change-of-state verbs, bleiben, sein, werden. "
        "  Use 'haben' for all others (default). "
        "- Nouns: nominative SINGULAR. Auto (NOT Autos / Autos). "
        "- Adjectives: POSITIVE degree, NO case endings. schön (NOT schöner / schönen / schönem / schönes). "
        "  Examples: 'großen' → 'groß', 'kleinem' → 'klein', 'schneller' → 'schnell'. "
        "\n\nPARTIZIP RULES — critical, do NOT get these wrong: "
        "- PARTIZIP 1 (Präsenspartizip): words ending in -end / -ende / -enden / -endem / -ender / -endes. "
        "  Examples: fahrend, laufend, brennend, fahrende, laufenden. "
        "  → part_of_speech = 'sifat'. word = the -end form (e.g. 'fahrend'). "
        "  → NEVER label Partizip-1 words as 'fiil'. "
        "- PARTIZIP 2 (Perfektpartizip) used as adjective: ge-...-t or ge-...-en words modifying a noun. "
        "  Examples: 'ein gefahrenes Auto', 'die gemachte Arbeit', 'der gebrochene Arm'. "
        "  → part_of_speech = 'sifat'. word = the Partizip-2 form (e.g. 'gefahren', 'gemacht'). "
        "  → NEVER label adjectival Partizip-2 as 'fiil'. "
        "- If you see the BASE VERB in the text (infinitive or conjugated), label it 'fiil'. "
        "  Store ONLY the infinitive form as 'word' — NO conjugation tables needed. "
        "\n\nADJECTIVE DEGREE RULES — never label these as 'fiil' or 'isim': "
        "- KOMPARATIV (comparative): adjective root + -er suffix. "
        "  Examples: schneller, größer, besser, höher, stärker, älter, jünger. "
        "  → part_of_speech = 'sifat'. word = base adjective (schnell, groß, gut, hoch, stark, alt, jung). "
        "  → CRITICAL: 'schneller' means 'faster', NOT the verb 'schnellen'. "
        "  → Do NOT confuse comparative -er with verb infinitives or noun agents (-er nouns like Fahrer). "
        "    Tip: if the word has a clear comparative meaning ('more X'), label it 'sifat'. "
        "- SUPERLATIV (superlative): adjective root + -(e)sten / -(e)stem / -(e)ster / -(e)stes / -(e)ste. "
        "  Examples: schnellsten, größten, besten, höchsten, stärksten. "
        "  → part_of_speech = 'sifat'. word = base adjective. "
        "\n\nDECLINED ADJECTIVE RULES: "
        "- Adjectives with case endings (-en/-em/-es/-er/-e) are still adjectives, not verbs or nouns. "
        "  Examples: soziale, technischen, natürlichen, digitalen, wirtschaftliche, rechtliche. "
        "  → part_of_speech = 'sifat'. word = base form WITHOUT ending (sozial, technisch, natürlich). "
        "- Adjectives derived with -lich/-ig/-isch/-ell/-al/-iv always stay 'sifat' even when declined: "
        "  'wirtschaftlichen' → wirtschaftlich (sifat), 'digitale' → digital (sifat). "
        "\n\nNOUN SUFFIX RULES: "
        "- Words ending in -ung/-ungen/-ion/-ionen/-heit/-heiten/-keit/-keiten/-schaft/-schaften "
        "  are ALWAYS nouns (isim), never verbs. "
        "  Examples: Handlung, Nationen, Schönheit, Möglichkeiten, Gesellschaft. "
        "- Conjugated verb forms (fährt, laufen, machte, haben) should NOT be stored as 'isim'. "
        "  If you encounter a conjugated verb, either use the infinitive as 'fiil' or skip it. "
        "\n\nCOLLOCATION & USAGE NOTES: "
        "- For verbs, note which CASE/PREPOSITION they govern in the 'not_gramatik' field: "
        "  e.g. 'warten auf + Akk.', 'helfen + Dat.', 'sich freuen über + Akk.' "
        "- For adjectives, note common collocations if visible in text. "
        "\n\nVERB CLASSIFICATION REMINDERS: "
        "- -ieren verbs: ALWAYS weak (schwach), ALWAYS inseparable (trennbar=false), "
        "  Partizip II = remove -ieren, add -iert (NO ge- prefix!). "
        "  Examples: telefonieren→telefoniert, organisieren→organisiert, fotografieren→fotografiert. "
        "- REFLEXIVE verbs: include 'sich' in the word field (e.g. 'sich freuen', 'sich erinnern'). "
        "  Set gecisli='reflexiv'. "
        "- SEPARABLE verbs: use | to mark the separation point in your notes "
        "  (e.g. 'auf|machen' means 'auf' separates: 'ich mache auf'). "
    )
    instructions = {
        "return_shape": {
            "entries": [{
                "word": "German lemma — ALWAYS base form: infinitive for verbs, nom.sg for nouns, positive for adjectives",
                "part_of_speech": "isim | fiil | sifat | zarf | ifade | belirsiz",
                "article": "der | die | das | '' (only for nouns)",
                "meanings": ["Turkish meaning 1", "Turkish meaning 2 (optional)"],
                "example_sentence": "A German sentence from the text using this word",
                "example_translation": "Turkish translation of the example (MUST be Turkish, not German)",
                "trennbar": "true | false | null (for separable/inseparable/unknown verbs)",
                "not_gramatik": "grammatical note: case government, collocation etc.",
            }]
        }
    }

    seen: set[str] = set()
    seen_existing: set[str] = set()
    all_candidates: list[dict] = []
    skipped = 0
    last_error: str = ""
    _scan_start = time.time()

    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(i + 1, len(chunks),
                f"Parça {i + 1}/{len(chunks)} işleniyor... ({len(all_candidates)} kelime bulundu)")

        if i > 0:
            # API türüne göre bekleme süresi: Groq=10s, Gemini=2s, Yerel=0.5s
            _delay = (
                GEMINI_INTER_CHUNK_DELAY if "groq.com" in api_url
                else 0.5 if ("127.0.0.1" in api_url or "localhost" in api_url)
                else GEMINI_INTER_CHUNK_DELAY_FAST
            )
            time.sleep(_delay)

        user_payload = {
            "source_url": page_url,
            "instructions": instructions,
            "german_text": _clean_chunk_for_llm(chunk),
        }
        try:
            payload = request_llm_json(api_url, api_key, model, system_prompt, user_payload, 60)
            content = extract_openai_message_content(payload)
            result = extract_json_object_from_text(content)
            entries = result.get("entries", [])
            if not isinstance(entries, list) or not entries:
                if progress_callback:
                    progress_callback(i + 1, len(chunks),
                        f"Parça {i + 1}: Model boş yanıt döndürdü. Toplam: {len(all_candidates)} kelime.")
                continue
            before = len(all_candidates)
            chunk_candidates = _process_gemini_entries(
                entries, existing_terms, existing_meaning_index,
                seen, page_url, api_url, api_key, model, llm_label,
                seen_existing_out=seen_existing,
            )
            all_candidates.extend(chunk_candidates)
            added = len(all_candidates) - before
            if progress_callback:
                progress_callback(i + 1, len(chunks),
                    f"Parça {i + 1}: {len(entries)} giriş → {added} yeni kelime. Toplam: {len(all_candidates)}.")
        except Exception as chunk_exc:
            skipped += 1
            last_error = str(chunk_exc)
            print(f"[{llm_label}] Parça {i + 1} HATA: {last_error}", flush=True)
            if progress_callback:
                progress_callback(i + 1, len(chunks),
                    f"Parça {i + 1} HATA: {last_error[:120]}")
            continue

    if skipped == len(chunks) and last_error:
        if "429" in last_error:
            raise RuntimeError(
                f"API istek limiti aşıldı (429) — {llm_label}\n"
                "• 1-2 dakika bekleyip tekrar deneyin.\n"
                "• 'API Test' butonunu kullanmayın — gereksiz kota harcar."
            )
        raise RuntimeError(f"Tüm parçalar başarısız oldu. Son hata: {last_error}")

    # Improvement 4: Detailed summary after all chunks processed
    if progress_callback:
        elapsed = time.time() - _scan_start
        elapsed_str = f"{elapsed:.0f}s" if elapsed < 60 else f"{elapsed / 60:.1f}dk"
        skipped_note = f", {skipped} parça atlandı" if skipped else ""
        summary_msg = (
            f"Tamamlandı — {len(all_candidates)} yeni kelime bulundu, "
            f"{len(seen_existing)} mevcut kelime görüldü{skipped_note}. "
            f"Süre: {elapsed_str}"
        )
        progress_callback(len(chunks), len(chunks), summary_msg)

    if not all_candidates:
        return [], f"{llm_label} taraması yeni veya eksik çevirili kelime bulamadı.", seen_existing
    note = f"{llm_label} — {len(chunks)} parçadan {len(all_candidates)} kelime bulundu."
    if skipped:
        note += f" ({skipped} parça hata nedeniyle atlandı)"
    return all_candidates, note, seen_existing


def collect_url_import_scan(
    url: str,
    existing_terms: set[str],
    existing_meaning_index: dict[str, dict],
    api_url: str,
    api_key: str,
    model: str,
    progress_callback=None,
) -> tuple[str, list[dict], list[dict], str, set[str]]:
    final_url, text = fetch_visible_text_from_url(url)

    # Improvement 1: Show character count and estimated chunk count
    char_count = len(text)
    effective_text = text[:GEMINI_MAX_TOTAL_CHARS]
    estimated_chunks = len(chunk_text(effective_text, GEMINI_CHUNK_SIZE))
    if progress_callback:
        progress_callback(0, estimated_chunks,
            f"Sayfa metni alındı: {char_count:,} karakter → {estimated_chunks} parça işlenecek")

    # Improvement 2: Warn if extracted text is suspiciously short
    if char_count < 500:
        if progress_callback:
            progress_callback(0, estimated_chunks,
                f"⚠ Sayfadan çok az metin alındı ({char_count} karakter). "
                "Sayfa JavaScript ile yüklenmiş olabilir.")

    connection = sqlite3.connect(str(WIKDICT_PATH)) if WIKDICT_PATH.exists() else None
    seen_existing: set[str] = set()
    try:
        cursor = connection.cursor() if connection else None
        if api_key.strip() and model.strip():
            # AI varsa: tam metni modele gönder, sonuçları ikiye ayır
            # Yeni kelimeler (sözlükte yok) → birinci sekme (local_candidates)
            # Mevcut kelimeler, eksik anlam → ikinci sekme (ai_candidates)
            try:
                all_gemini, ai_note, seen_existing = extract_gemini_full_text_candidates(
                    text, final_url, existing_terms, existing_meaning_index, api_url, api_key, model,
                    progress_callback=progress_callback,
                )
                local_candidates = [c for c in all_gemini if not c.get("mevcut_turkce")]
                ai_candidates = [c for c in all_gemini if c.get("mevcut_turkce")]
            except Exception as exc:
                local_candidates = extract_url_import_candidates(text, existing_terms, cursor)
                ai_candidates = []
                ai_note = f"AI taraması başarısız, yerel taramaya dönüldü: {exc}"
        else:
            # API anahtarı yok → WikDict ile yerel tarama
            local_candidates = extract_url_import_candidates(text, existing_terms, cursor)
            inventory = extract_url_word_inventory(text, cursor)
            try:
                ai_candidates, ai_note = extract_openai_meaning_candidates(final_url, inventory, existing_meaning_index, api_url, api_key, model)
            except Exception as exc:
                ai_candidates, ai_note = [], f"Model anlam onerileri alinamadi. {exc}"
        apply_url_example_translations(ai_candidates)
    finally:
        if connection is not None:
            connection.close()
    return final_url, local_candidates, ai_candidates, ai_note, seen_existing


def increment_frekans_for_seen_terms(seen: set[str]) -> int:
    """URL taramasında mevcut bulunan kelimelerin frekans sayacını 1 artırır.

    Hem base dictionary.json hem de user_entries.json üzerinde çalışır.
    Döndürülen değer: kaç kayıtta güncelleme yapıldı.
    """
    if not seen:
        return 0
    updated = 0

    # --- Base dictionary ---
    base_records = safe_json_load(DICTIONARY_PATH, [])
    base_changed = False
    for record in base_records:
        norm = normalize_import_term(record.get("almanca", ""))
        if norm in seen:
            record["frekans"] = int(record.get("frekans") or 0) + 1
            updated += 1
            base_changed = True
    if base_changed:
        write_json_file(DICTIONARY_PATH, base_records)

    # --- User entries ---
    user_payload_raw = safe_json_load(
        USER_ENTRIES_PATH,
        {"source_name": "kullanici-ekleme", "default_note": "", "records": []},
    )
    user_records = user_payload_raw.get("records", [])
    user_changed = False
    for record in user_records:
        norm = normalize_import_term(record.get("almanca", ""))
        if norm in seen:
            record["frekans"] = int(record.get("frekans") or 0) + 1
            updated += 1
            user_changed = True
    if user_changed:
        write_json_file(USER_ENTRIES_PATH, user_payload_raw)

    return updated


def collect_parallel_text_import_scan(
    german_text: str,
    turkish_text: str,
    existing_meaning_index: dict[str, dict],
    api_url: str,
    api_key: str,
    model: str,
) -> tuple[list[dict], str]:
    if not model.strip():
        return collect_parallel_text_import_scan_local(german_text, turkish_text, existing_meaning_index)

    entries = request_openai_parallel_text_batch(api_url, api_key, model, german_text, turkish_text)
    by_word = existing_meaning_index.get("by_word", {})
    by_word_pos = existing_meaning_index.get("by_word_pos", {})
    labels = existing_meaning_index.get("labels", {})
    seen_keys: set[tuple[str, str]] = set()
    candidates: list[dict] = []

    for entry in entries:
        normalized_word = normalize_import_term(entry.get("word", ""))
        if not normalized_word:
            continue
        part_of_speech = normalize_openai_import_pos(entry.get("part_of_speech", ""), "belirsiz")
        existing_for_word = by_word.get(normalized_word, set())
        existing_for_pos = by_word_pos.get((normalized_word, normalize_text(part_of_speech)), set())
        existing_labels = labels.get(normalized_word, [])
        example_sentence = normalize_whitespace(entry.get("german_sentence", ""))
        example_translation = normalize_whitespace(entry.get("turkish_sentence", ""))
        example_items = []
        if example_sentence or example_translation:
            example_items.append(
                {
                    "almanca": example_sentence,
                    "turkce": example_translation,
                    "kaynak": "Metin eşleme",
                    "not": "Almanca kaynak metin ile Türkçe çeviriden çıkarıldı.",
                }
            )
        for meaning in entry.get("meanings", []):
            meaning_key = normalize_text(meaning)
            if not meaning_key:
                continue
            if meaning_key in existing_for_word or meaning_key in existing_for_pos:
                continue
            dedupe_key = (normalized_word, meaning_key)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            candidates.append(
                {
                    "id": f"text::{normalized_word}::{meaning_key}",
                    "almanca": normalize_whitespace(entry.get("word", "")),
                    "mevcut_turkce": ", ".join(existing_labels[:4]),
                    "turkce": meaning,
                    "tur": part_of_speech,
                    "artikel": entry.get("article", "") if part_of_speech == "isim" else "",
                    "kaynak_etiketi": format_llm_label(model, api_url),
                    "frekans": 1,
                    "ornek_almanca": example_sentence,
                    "ornek_turkce": example_translation,
                    "ornekler": example_items,
                    "ekle": True,
                    "not": "Almanca metin ile Türkçe çeviri birlikte analiz edilerek önerildi.",
                    "kaynak": "llm-text-import",
                    "ceviri_durumu": "model-metin-esleme",
                    "ceviri_inceleme_notu": "Bu kayit, kullanici tarafindan girilen Almanca metin ve Turkce ceviri eslestirilerek yerel/uyumlu model ile onerildi.",
                    "ceviri_kaynaklari": [
                        {
                            "almanca": format_llm_label(model, api_url),
                            "turkce": "Metin esleme onerisi",
                            "kaynak": "Yerel/Uyumlu model",
                            "not": "Almanca kaynak metin + Türkçe çeviri",
                        }
                    ],
                }
            )

    if not candidates:
        return [], "Metin esleme sekmesinde sozluge eklenecek yeni kelime veya eksik anlam bulunamadi."
    return candidates, f"Metin esleme sekmesi {len(candidates)} yeni veya eksik anlam hazirladi."


def collect_parallel_text_import_scan_strict(
    german_text: str,
    turkish_text: str,
    existing_meaning_index: dict[str, dict],
    api_url: str,
    api_key: str,
    model: str,
) -> tuple[list[dict], str]:
    if not model.strip():
        return collect_parallel_text_import_scan_local(german_text, turkish_text, existing_meaning_index)

    batches = build_parallel_text_batches(german_text, turkish_text)
    if not batches:
        return [], "Metin esleme icin hem Almanca hem Turkce metin gerekli."

    by_word = existing_meaning_index.get("by_word", {})
    by_word_pos = existing_meaning_index.get("by_word_pos", {})
    labels = existing_meaning_index.get("labels", {})
    candidate_map: dict[tuple[str, str], dict] = {}
    filtered_by_confidence = 0

    try:
        for german_chunk, turkish_chunk in batches:
            entries = request_openai_parallel_text_batch_strict(api_url, api_key, model, german_chunk, turkish_chunk)
            for entry in entries:
                confidence = normalize_openai_confidence(entry.get("confidence", 0.0))
                evidence = normalize_whitespace(entry.get("turkish_evidence", ""))
                if confidence < PARALLEL_TEXT_MIN_CONFIDENCE or not evidence:
                    filtered_by_confidence += 1
                    continue

                normalized_word = normalize_import_term(entry.get("word", ""))
                if not normalized_word or normalized_word in GERMAN_IMPORT_STOPWORDS:
                    continue

                part_of_speech = normalize_openai_import_pos(entry.get("part_of_speech", ""), "belirsiz")
                existing_for_word = by_word.get(normalized_word, set())
                existing_for_pos = by_word_pos.get((normalized_word, normalize_text(part_of_speech)), set())
                existing_labels = labels.get(normalized_word, [])
                example_sentence = normalize_whitespace(entry.get("german_sentence", "")) or german_chunk
                example_translation = normalize_whitespace(entry.get("turkish_sentence", "")) or turkish_chunk
                example_items = []
                if example_sentence or example_translation:
                    example_items.append(
                        {
                            "almanca": example_sentence,
                            "turkce": example_translation,
                            "kaynak": "Metin esleme",
                            "not": f"Paralel metinden cikarildi. Eslesme kaniti: {evidence}",
                        }
                    )
                for meaning in entry.get("meanings", []):
                    meaning_key = normalize_text(meaning)
                    if not meaning_key:
                        continue
                    if meaning_key in existing_for_word or meaning_key in existing_for_pos:
                        continue

                    dedupe_key = (normalized_word, meaning_key)
                    candidate = {
                        "id": f"text::{normalized_word}::{meaning_key}",
                        "almanca": normalize_whitespace(entry.get("word", "")),
                        "mevcut_turkce": ", ".join(existing_labels[:4]),
                        "turkce": meaning,
                        "tur": part_of_speech,
                        "artikel": entry.get("article", "") if part_of_speech == "isim" else "",
                        "kaynak_etiketi": format_llm_label(model, api_url),
                        "frekans": 1,
                        "ornek_almanca": example_sentence,
                        "ornek_turkce": example_translation,
                        "ornekler": example_items,
                        "ekle": True,
                        "guven": confidence,
                        "eslesme_kaniti": evidence,
                        "not": f"Almanca metin ile Turkce ceviri birlikte analiz edilerek onerildi. Eslesme kaniti: {evidence}",
                        "kaynak": "llm-text-import",
                        "ceviri_durumu": "model-metin-esleme",
                        "ceviri_inceleme_notu": (
                            "Bu kayit, kullanici tarafindan girilen Almanca metin ve Turkce ceviri eslestirilerek "
                            f"yerel/uyumlu model ile onerildi. Guven: %{round(confidence * 100)}. Kanit: {evidence}"
                        ),
                        "ceviri_kaynaklari": [
                            {
                                "almanca": format_llm_label(model, api_url),
                                "turkce": "Metin esleme onerisi",
                                "kaynak": "Yerel/Uyumlu model",
                                "not": f"Kanit: {evidence}",
                            }
                        ],
                    }
                    existing_candidate = candidate_map.get(dedupe_key)
                    if existing_candidate is None or confidence > normalize_openai_confidence(existing_candidate.get("guven", 0.0)):
                        candidate_map[dedupe_key] = candidate
    except Exception as exc:
        local_candidates, local_note = collect_parallel_text_import_scan_local(german_text, turkish_text, existing_meaning_index)
        if local_candidates:
            return local_candidates, f"Model kullanilamadi, yerel eslemeye donuldu. {local_note} Hata: {exc}"
        return [], f"Model esleme basarisiz oldu ve yerel esleme de yeni kayit bulamadi. Hata: {exc}"

    candidates = sorted(
        candidate_map.values(),
        key=lambda item: (-normalize_openai_confidence(item.get("guven", 0.0)), item.get("almanca", ""), item.get("turkce", "")),
    )
    if not candidates:
        if filtered_by_confidence:
            return [], "Metin esleme tamamlandi ama dusuk guvenli adaylar elendi; eklenecek kayit bulunamadi."
        return [], "Metin esleme ekraninda sozluge eklenecek yeni kelime veya eksik anlam bulunamadi."

    note = f"Metin esleme ekrani {len(candidates)} yeni veya eksik anlam hazirladi."
    if len(batches) > 1:
        note += f" Metin {len(batches)} parcada analiz edildi."
    if filtered_by_confidence:
        note += f" {filtered_by_confidence} zayif aday otomatik elendi."
    return candidates, note

def resolve_background_image_path(option_key: str) -> Path | None:
    option = BACKGROUND_IMAGE_OPTIONS.get(option_key, BACKGROUND_IMAGE_OPTIONS["none"])
    path = option.get("path")
    if not path:
        return None
    return path if path.exists() else None


def clamp_float(value: object, minimum: float, maximum: float, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, numeric))


def sanitize_custom_art_config(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    path_text = str(value.get("path", "") or "").strip()
    return {
        "path": path_text,
        "zoom": clamp_float(value.get("zoom", 1.0), 1.0, 4.0, 1.0),
        "focus_x": clamp_float(value.get("focus_x", 0.5), 0.0, 1.0, 0.5),
        "focus_y": clamp_float(value.get("focus_y", 0.5), 0.0, 1.0, 0.5),
    }


def sanitize_custom_art_slots(value: object) -> dict[str, dict]:
    if not isinstance(value, dict):
        return {}
    sanitized: dict[str, dict] = {}
    for slot_key in ART_SLOT_CONFIGS:
        config = sanitize_custom_art_config(value.get(slot_key))
        if config.get("path"):
            sanitized[slot_key] = config
    return sanitized


REMOVED_SEARCH_ACTIONS = {"google_translate"}

def sanitize_search_action_buttons(value: object) -> list[str]:
    items = value if isinstance(value, list) else DEFAULT_SETTINGS["search_action_buttons"]
    selected: list[str] = []
    for item in items:
        key = str(item).strip()
        if key in REMOVED_SEARCH_ACTIONS:
            continue
        if key in SEARCH_ACTION_OPTIONS and key not in selected:
            selected.append(key)
        if len(selected) >= MAX_SEARCH_ACTION_BUTTONS:
            break
    if not selected:
        return [k for k in DEFAULT_SETTINGS["search_action_buttons"] if k not in REMOVED_SEARCH_ACTIONS]
    return selected


def crop_image_to_frame(
    image: "Image.Image",
    target_size: tuple[int, int],
    zoom: float = 1.0,
    focus_x: float = 0.5,
    focus_y: float = 0.5,
) -> "Image.Image":
    target_width, target_height = target_size
    width, height = image.size
    if width <= 0 or height <= 0 or target_width <= 0 or target_height <= 0:
        return image.copy()

    target_ratio = target_width / target_height
    image_ratio = width / height
    if image_ratio > target_ratio:
        base_crop_height = height
        base_crop_width = int(round(height * target_ratio))
    else:
        base_crop_width = width
        base_crop_height = int(round(width / target_ratio))

    zoom = clamp_float(zoom, 1.0, 4.0, 1.0)
    crop_width = max(1, min(width, int(round(base_crop_width / zoom))))
    crop_height = max(1, min(height, int(round(base_crop_height / zoom))))
    max_x = max(0, width - crop_width)
    max_y = max(0, height - crop_height)
    focus_x = clamp_float(focus_x, 0.0, 1.0, 0.5)
    focus_y = clamp_float(focus_y, 0.0, 1.0, 0.5)
    left = int(round(max_x * focus_x))
    top = int(round(max_y * focus_y))
    left = max(0, min(max_x, left))
    top = max(0, min(max_y, top))
    crop_box = (left, top, left + crop_width, top + crop_height)
    cropped = image.crop(crop_box)
    return cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)


def load_custom_slot_photo_image(path_text: str, target_size: tuple[int, int], crop_config: dict | None = None):
    if not PIL_AVAILABLE or not path_text:
        return None
    path = Path(path_text)
    if not path.exists():
        return None
    crop_config = sanitize_custom_art_config(crop_config or {"path": path_text})
    with Image.open(path) as source_image:
        image = ImageOps.exif_transpose(source_image)
    rendered = crop_image_to_frame(
        image.convert("RGBA"),
        target_size=target_size,
        zoom=crop_config.get("zoom", 1.0),
        focus_x=crop_config.get("focus_x", 0.5),
        focus_y=crop_config.get("focus_y", 0.5),
    )
    return ImageTk.PhotoImage(rendered)


def load_slot_photo_image(
    option_key: str,
    slot_key: str,
    target_size: tuple[int, int] | None = None,
    horizontal_focus: str = "center",
    vertical_focus: str = "center",
) -> tk.PhotoImage | None:
    path = resolve_background_image_path(option_key)
    if path is None:
        return None
    if PIL_AVAILABLE:
        focus_x = 0.0 if horizontal_focus == "left" else 1.0 if horizontal_focus == "right" else 0.5
        focus_y = 0.0 if vertical_focus == "top" else 1.0 if vertical_focus == "bottom" else 0.5
        return load_custom_slot_photo_image(
            str(path),
            target_size or ART_SLOT_LIMITS.get(slot_key, (320, 220)),
            {"path": str(path), "zoom": 1.0, "focus_x": focus_x, "focus_y": focus_y},
        )
    image = tk.PhotoImage(file=str(path))
    max_width, max_height = target_size or ART_SLOT_LIMITS.get(slot_key, (320, 220))
    scale_limits = [1]
    if image.width() >= max_width:
        scale_limits.append(max(1, image.width() // max_width))
    if image.height() >= max_height:
        scale_limits.append(max(1, image.height() // max_height))
    scale = min(scale_limits)
    if target_size is None and slot_key in {"search", "results"}:
        scale = max(scale, 2)
    if target_size is None and slot_key != "hero" and option_key in {"tall_tree", "nature_line"}:
        scale = max(scale, 2)
    if target_size is None and slot_key == "hero" and option_key in {"tall_tree", "nature_line"}:
        scale = max(scale, 3)
    if scale > 1:
        image = image.subsample(scale, scale)

    crop_width = min(max_width, image.width())
    crop_height = min(max_height, image.height())

    if horizontal_focus == "right":
        start_x = max(0, image.width() - crop_width)
    elif horizontal_focus == "left":
        start_x = 0
    else:
        start_x = max(0, (image.width() - crop_width) // 2)

    if vertical_focus == "bottom":
        start_y = max(0, image.height() - crop_height)
    elif vertical_focus == "top":
        start_y = 0
    else:
        start_y = max(0, (image.height() - crop_height) // 2)

    if crop_width == image.width() and crop_height == image.height():
        return image

    cropped = tk.PhotoImage()
    cropped.tk.call(
        cropped,
        "copy",
        image,
        "-from",
        start_x,
        start_y,
        start_x + crop_width,
        start_y + crop_height,
    )
    return cropped


def record_key(record: dict) -> tuple[str, str, str]:
    return (
        normalize_text(record.get("almanca", "")),
        normalize_text(record.get("tur", "")),
        normalize_text(record.get("turkce", "")),
    )


def serialize_record_key(key: tuple[str, str, str]) -> str:
    return "||".join(key)


def format_source_item(item: dict) -> str:
    label = (item.get("ad") or item.get("url") or "Kaynak").strip()
    note = (item.get("not") or "").strip()
    return f"{label} | {note}" if note else label


def build_meta_line(record: dict) -> str:
    parts = []
    if record.get("tur"):
        parts.append(record["tur"])
    seviye = str(record.get("seviye", "") or "").strip()
    if seviye:
        parts.append(seviye)
    cogul = str(record.get("cogul", "") or "").strip()
    if cogul:
        parts.append(f"Pl: {cogul}")
    if record.get("tur") == "fiil":
        trennbar = record.get("trennbar")
        if trennbar is True:
            parts.append("⇄ trennbar")
        elif trennbar is False:
            parts.append("untrennbar")
        verb_typ = str(record.get("verb_typ") or "").strip()
        almanca = str(record.get("almanca") or "").strip()
        if verb_typ == "stark":
            parts.append("★ stark")
        elif verb_typ == "schwach" and almanca.endswith("ieren"):
            parts.append("★ -ieren")
    partizip2 = str(record.get("partizip2", "") or "").strip()
    if partizip2:
        parts.append(f"P2: {partizip2}")
    categories = record.get("kategoriler") or []
    if categories:
        parts.append(", ".join(categories[:2]))
    sources = record.get("_source_names") or []
    if sources:
        if len(sources) == 1:
            parts.append(sources[0])
        else:
            parts.append(f"{sources[0]} +{len(sources) - 1}")
    sinonim_list = record.get("sinonim") or []
    if isinstance(sinonim_list, list) and sinonim_list:
        count = len(sinonim_list)
        parts.append(f"≈ {count} eşanlamlı")
    return " • ".join(parts)


def prepare_record(record: dict) -> dict:
    prepared = dict(record)
    artikel = prepared.get("artikel", "") or ""
    almanca = prepared.get("almanca", "") or ""
    turkce = prepared.get("turkce", "") or ""
    aciklama_turkce = prepared.get("aciklama_turkce", "") or ""

    prepared["_word"] = f"{artikel} {almanca}".strip() if artikel else almanca
    source_names = split_multi_value(prepared.get("kaynak", ""))
    prepared["_source_names"] = source_names
    prepared["_source_urls"] = split_multi_value(prepared.get("kaynak_url", ""))
    prepared["_translation_sources"] = [
        item for item in prepared.get("ceviri_kaynaklari", []) if isinstance(item, dict) and any(item.values())
    ]
    prepared["_primary_source"] = source_names[0] if source_names else "Kaynak belirtilmedi"
    prepared["_meta_line"] = build_meta_line(prepared)

    sinonim = prepared.get("sinonim")
    antonim = prepared.get("antonim")
    kelime_ailesi = prepared.get("kelime_ailesi")
    ornekler = prepared.get("ornekler") or []

    blob_raw = " ".join([
        almanca,
        artikel,
        turkce,
        aciklama_turkce,
        prepared.get("tur", ""),
        prepared.get("cogul", ""),
        prepared.get("partizip2", ""),
        prepared.get("acilim_almanca", ""),
        prepared.get("seviye", ""),
        "trennbar" if prepared.get("trennbar") is True else "",
        prepared.get("trennbar_prefix", ""),
        prepared.get("verb_typ", ""),
        prepared.get("gecisli", ""),
        " ".join(prepared.get("kategoriler") or []),
        " ".join(prepared.get("ilgili_kayitlar") or []),
        " ".join(sinonim if isinstance(sinonim, list) else []),
        " ".join(antonim if isinstance(antonim, list) else []),
        " ".join(kelime_ailesi if isinstance(kelime_ailesi, list) else []),
        prepared.get("kaynak", ""),
        prepared.get("ornek_almanca", ""),
        prepared.get("not", ""),
        " ".join(o.get("almanca", "") for o in ornekler if isinstance(o, dict) and o.get("almanca")),
    ])
    prepared["_search_blob"] = normalize_text(blob_raw)

    # ASCII-folded version so searching without diacritics still works
    # e.g. "arac" finds "araç", "surucu" finds "sürücü", "fuhrerschein" finds "Führerschein"
    # Optimizasyon: ascii_fold sadece ana alanlara uygulanıyor (ornekler hariç)
    _ascii_fold_core = normalize_text(f"{almanca} {artikel} {turkce} {aciklama_turkce} {prepared.get('cogul', '')} {prepared.get('partizip2', '')} {prepared.get('acilim_almanca', '')}")
    ascii_blob = ascii_fold(_ascii_fold_core)
    if ascii_blob != _ascii_fold_core:
        prepared["_search_blob"] = prepared["_search_blob"] + " " + ascii_blob
    return prepared


def should_hide_record(record: dict) -> bool:
    word = str(record.get("almanca", "")).strip()
    source = normalize_text(record.get("kaynak", ""))
    if len(word) == 1 and source == "dewiktionary":
        return True
    return False


def format_display_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    text = re.sub(r"(?<!\n)\n(?=\d+\.\s)", "\n\n", text)
    return text


def write_settings(payload: dict) -> None:
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_json_file(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_editor_examples(example_de: str, example_tr: str, existing_examples: list | None) -> list[dict]:
    clean_de = normalize_whitespace(example_de)
    clean_tr = normalize_whitespace(example_tr)
    examples: list[dict] = []
    if clean_de or clean_tr:
        examples.append({"almanca": clean_de, "turkce": clean_tr})
    for item in existing_examples or []:
        if not isinstance(item, dict):
            continue
        normalized_item = {
            "almanca": normalize_whitespace(item.get("almanca", "")),
            "turkce": normalize_whitespace(item.get("turkce", "")),
            "etiket_turkce": normalize_whitespace(item.get("etiket_turkce", "")),
            "kaynak": normalize_whitespace(item.get("kaynak", "")),
            "not": normalize_whitespace(item.get("not", "")),
        }
        if not any(normalized_item.values()):
            continue
        if clean_de and normalized_item["almanca"] == clean_de and normalized_item["turkce"] == clean_tr:
            continue
        examples.append({key: value for key, value in normalized_item.items() if value})
    return examples


def build_dataset_editor_payload(original: dict, edited: dict) -> dict:
    payload = {key: copy.deepcopy(value) for key, value in original.items() if not str(key).startswith("_")}
    payload.update(
        {
            "almanca": normalize_whitespace(edited.get("almanca", "")),
            "artikel": normalize_whitespace(edited.get("artikel", "")),
            "turkce": normalize_whitespace(edited.get("turkce", "")),
            "tur": normalize_whitespace(edited.get("tur", "")),
            "aciklama_turkce": normalize_whitespace(edited.get("aciklama_turkce", "")),
            "not": normalize_whitespace(edited.get("not", "")),
            "kaynak": normalize_whitespace(edited.get("kaynak", "")),
            "kaynak_url": normalize_whitespace(edited.get("kaynak_url", "")),
            "ceviri_inceleme_notu": normalize_whitespace(edited.get("ceviri_inceleme_notu", "")),
            "ornek_almanca": normalize_whitespace(edited.get("ornek_almanca", "")),
            "ornek_turkce": normalize_whitespace(edited.get("ornek_turkce", "")),
        }
    )
    payload["ornekler"] = build_editor_examples(
        payload.get("ornek_almanca", ""),
        payload.get("ornek_turkce", ""),
        payload.get("ornekler", []),
    )
    return payload


def save_dataset_editor_record(storage_source: str, original_key: tuple[str, str, str], payload: dict) -> dict:
    if storage_source == "user":
        raw_payload = safe_json_load(
            USER_ENTRIES_PATH,
            {"source_name": "kullanici-ekleme", "default_note": "Arayuzden manuel olarak eklendi.", "records": []},
        )
        records = raw_payload.setdefault("records", [])
        for index, current in enumerate(records):
            if record_key(current) == original_key:
                records[index] = payload
                break
        else:
            records.append(payload)
        write_json_file(USER_ENTRIES_PATH, raw_payload)
    else:
        records = safe_json_load(DICTIONARY_PATH, [])
        for index, current in enumerate(records):
            if record_key(current) == original_key:
                records[index] = payload
                break
        else:
            records.append(payload)
        write_json_file(DICTIONARY_PATH, records)

    saved = prepare_record(payload)
    saved["_storage_source"] = storage_source
    return saved


class ThemeDropdown(ttk.Frame):
    def __init__(self, parent, variable: tk.StringVar) -> None:
        super().__init__(parent)
        self.variable = variable
        self.columnconfigure(1, weight=1)

        self.swatch = tk.Canvas(self, width=18, height=18, highlightthickness=0, bd=0)
        self.swatch.grid(row=0, column=0, sticky="w")

        self.button = tk.Menubutton(self, textvariable=self.variable, relief="solid", borderwidth=1, anchor="w")
        self.button.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        self.menu = tk.Menu(self.button, tearoff=False)
        self.button.configure(menu=self.menu)

        for key, theme in THEMES.items():
            self.menu.add_radiobutton(
                label=f"   {theme['label']}",
                value=theme["label"],
                variable=self.variable,
                command=self.sync_from_value,
                background=theme["accent_soft"],
                activebackground=theme["accent"],
                activeforeground="#ffffff",
                selectcolor=theme["accent"],
            )

        self.variable.trace_add("write", self.sync_from_value)
        self.sync_from_value()

    def sync_from_value(self, *_args) -> None:
        theme = next((value for value in THEMES.values() if value["label"] == self.variable.get()), THEMES["krem"])
        self.swatch.configure(bg=theme["surface"])
        self.swatch.delete("all")
        self.swatch.create_rectangle(1, 1, 17, 17, fill=theme["accent"], outline=theme["line"])
        self.button.configure(bg=theme["surface"], fg=theme["ink"], activebackground=theme["accent_soft"], activeforeground=theme["ink"])


class HoverTip:
    def __init__(self, widget, text: str, delay_ms: int = 850) -> None:
        self.widget = widget
        self.text = text.strip()
        self.delay_ms = delay_ms
        self.tip_window: tk.Toplevel | None = None
        self.after_id: str | None = None
        self.widget.bind("<Enter>", self.schedule_show, add="+")
        self.widget.bind("<Leave>", self.hide, add="+")
        self.widget.bind("<ButtonPress>", self.hide, add="+")
        self.widget.bind("<Destroy>", self.hide, add="+")

    def schedule_show(self, _event=None) -> None:
        self.cancel_scheduled_show()
        self.after_id = self.widget.after(self.delay_ms, self.show)

    def cancel_scheduled_show(self) -> None:
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def show(self) -> None:
        self.after_id = None
        if self.tip_window or not self.text:
            return
        if not self.is_pointer_over_widget():
            return
        pointer_x = self.widget.winfo_pointerx()
        pointer_y = self.widget.winfo_pointery()
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.attributes("-topmost", True)
        label = tk.Label(
            self.tip_window,
            text=self.text,
            justify="left",
            wraplength=260,
            bg="#fffbe7",
            fg="#2f3f34",
            relief="solid",
            bd=1,
            padx=8,
            pady=5,
        )
        label.pack()
        self.tip_window.update_idletasks()
        x = pointer_x + 18
        y = pointer_y + 20
        screen_width = self.widget.winfo_screenwidth()
        screen_height = self.widget.winfo_screenheight()
        tip_width = self.tip_window.winfo_reqwidth()
        tip_height = self.tip_window.winfo_reqheight()
        if x + tip_width > screen_width - 12:
            x = max(12, screen_width - tip_width - 12)
        if y + tip_height > screen_height - 12:
            y = max(12, pointer_y - tip_height - 18)
        self.tip_window.wm_geometry(f"+{x}+{y}")

    def is_pointer_over_widget(self) -> bool:
        try:
            pointer_x = self.widget.winfo_pointerx()
            pointer_y = self.widget.winfo_pointery()
            hovered_widget = self.widget.winfo_containing(pointer_x, pointer_y)
        except tk.TclError:
            return False
        while hovered_widget is not None:
            if hovered_widget == self.widget:
                return True
            hovered_widget = hovered_widget.master
        return False

    def hide(self, _event=None) -> None:
        self.cancel_scheduled_show()
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None


class ImageCropDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        slot_label: str,
        image_path: str,
        target_size: tuple[int, int],
        initial_config: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Görseli Kırp")
        self.transient(parent)
        self.grab_set()
        self.geometry("720x620")
        self.minsize(680, 580)

        self.slot_label = slot_label
        self.image_path = image_path
        self.target_size = target_size
        self.result: dict | None = None
        self.preview_image = None
        with Image.open(image_path) as source_image:
            self.source_image = ImageOps.exif_transpose(source_image).convert("RGBA")
        self.zoom_var = tk.DoubleVar(value=clamp_float((initial_config or {}).get("zoom", 1.0), 1.0, 4.0, 1.0))
        self.focus_x_var = tk.DoubleVar(value=clamp_float((initial_config or {}).get("focus_x", 0.5), 0.0, 1.0, 0.5))
        self.focus_y_var = tk.DoubleVar(value=clamp_float((initial_config or {}).get("focus_y", 0.5), 0.0, 1.0, 0.5))

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        info = ttk.Frame(self, padding=(16, 14, 16, 8))
        info.grid(row=0, column=0, sticky="ew")
        info.columnconfigure(0, weight=1)
        ttk.Label(
            info,
            text=f"{slot_label} için görseli ayarlayın",
            style="Section.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            info,
            text=f"Hedef alan: {target_size[0]} × {target_size[1]} px. Zoom ve konumu değiştirerek kırpma alanını kendiniz ayarlayabilirsiniz.",
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        preview_card = ttk.LabelFrame(self, text="Önizleme", padding=12)
        preview_card.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        preview_card.columnconfigure(0, weight=1)
        preview_card.rowconfigure(0, weight=1)
        self.preview_label = tk.Label(preview_card, bd=0)
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        controls = ttk.LabelFrame(self, text="Kırpma Ayarı", padding=12)
        controls.grid(row=2, column=0, sticky="ew", padx=16)
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Yakınlık").grid(row=0, column=0, sticky="w")
        ttk.Scale(controls, from_=1.0, to=4.0, variable=self.zoom_var, orient="horizontal", command=self.refresh_preview).grid(
            row=0, column=1, sticky="ew", padx=(10, 0)
        )
        ttk.Label(controls, textvariable=tk.StringVar(value="")).grid_remove()

        ttk.Label(controls, text="Yatay konum").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Scale(controls, from_=0.0, to=1.0, variable=self.focus_x_var, orient="horizontal", command=self.refresh_preview).grid(
            row=1, column=1, sticky="ew", padx=(10, 0), pady=(10, 0)
        )

        ttk.Label(controls, text="Dikey konum").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Scale(controls, from_=0.0, to=1.0, variable=self.focus_y_var, orient="horizontal", command=self.refresh_preview).grid(
            row=2, column=1, sticky="ew", padx=(10, 0), pady=(10, 0)
        )

        button_row = ttk.Frame(self, padding=(16, 12, 16, 16))
        button_row.grid(row=3, column=0, sticky="e")
        ttk.Button(button_row, text="Sıfırla", command=self.reset_values).grid(row=0, column=0)
        ttk.Button(button_row, text="İptal", command=self.destroy).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(button_row, text="Uygula", style="Primary.TButton", command=self.apply).grid(row=0, column=2, padx=(8, 0))

        self.zoom_var.trace_add("write", self.refresh_preview)
        self.focus_x_var.trace_add("write", self.refresh_preview)
        self.focus_y_var.trace_add("write", self.refresh_preview)
        self.refresh_preview()

    def reset_values(self) -> None:
        self.zoom_var.set(1.0)
        self.focus_x_var.set(0.5)
        self.focus_y_var.set(0.5)

    def refresh_preview(self, *_args) -> None:
        preview_size = self.target_size
        rendered = crop_image_to_frame(
            self.source_image,
            preview_size,
            zoom=self.zoom_var.get(),
            focus_x=self.focus_x_var.get(),
            focus_y=self.focus_y_var.get(),
        )
        self.preview_image = ImageTk.PhotoImage(rendered)
        self.preview_label.configure(image=self.preview_image)

    def apply(self) -> None:
        self.result = {
            "path": self.image_path,
            "zoom": clamp_float(self.zoom_var.get(), 1.0, 4.0, 1.0),
            "focus_x": clamp_float(self.focus_x_var.get(), 0.0, 1.0, 0.5),
            "focus_y": clamp_float(self.focus_y_var.get(), 0.0, 1.0, 0.5),
        }
        self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, app: "DesktopDictionaryApp") -> None:
        super().__init__(app)
        self.app = app
        self.title("Ayarlar")
        self.transient(app)
        self.grab_set()
        self.geometry("840x660")
        self.minsize(760, 600)

        self.pos_var = tk.StringVar(value=app.settings.get("pos_filter", "") or "Hepsi")
        self.seviye_filter_var = tk.StringVar(value="Hepsi" if not app.settings.get("seviye_filter") else app.settings["seviye_filter"])
        self.category_var = tk.StringVar(value=app.settings.get("category_filter", "") or "Hepsi")
        self.source_var = tk.StringVar(value=app.settings.get("source_filter", "") or "Tümü")
        self.note_only_var = tk.BooleanVar(value=bool(app.settings.get("note_only", False)))
        self.result_limit_var = tk.IntVar(value=safe_int(app.settings.get("result_limit"), DEFAULT_SETTINGS["result_limit"]))
        self.content_font_size_var = tk.IntVar(
            value=safe_int(app.settings.get("content_font_size"), DEFAULT_SETTINGS["content_font_size"])
        )
        self.translation_font_size_var = tk.IntVar(
            value=safe_int(app.settings.get("translation_font_size"), DEFAULT_SETTINGS["translation_font_size"])
        )
        self.meta_font_size_var = tk.IntVar(
            value=safe_int(app.settings.get("meta_font_size"), DEFAULT_SETTINGS["meta_font_size"])
        )
        self.libretranslate_url_var = tk.StringVar(
            value=str(app.settings.get("libretranslate_url", DEFAULT_SETTINGS["libretranslate_url"]) or "")
        )
        self.libretranslate_api_key_var = tk.StringVar(
            value=str(app.settings.get("libretranslate_api_key", DEFAULT_SETTINGS["libretranslate_api_key"]) or "")
        )
        self.sort_mode_var = tk.StringVar(
            value=SORT_OPTIONS.get(app.settings.get("sort_mode", DEFAULT_SETTINGS["sort_mode"]), SORT_OPTIONS["ilgili"])
        )
        self.theme_var = tk.StringVar(
            value=THEMES.get(app.settings.get("theme", DEFAULT_SETTINGS["theme"]), THEMES["krem"])["label"]
        )
        self.font_preset_var = tk.StringVar(
            value=FONT_PRESETS.get(app.settings.get("font_preset", DEFAULT_SETTINGS["font_preset"]), FONT_PRESETS["modern"])[
                "label"
            ]
        )
        self.show_examples_var = tk.BooleanVar(value=bool(app.settings.get("show_examples", True)))
        self.show_notes_var = tk.BooleanVar(value=bool(app.settings.get("show_notes", False)))
        self.remember_search_var = tk.BooleanVar(value=bool(app.settings.get("remember_search", True)))
        self.search_action_vars = {
            key: tk.BooleanVar(value=key in sanitize_search_action_buttons(app.settings.get("search_action_buttons", [])))
            for key in SEARCH_ACTION_OPTIONS
        }
        self.show_stats_var = tk.BooleanVar(value=bool(app.settings.get("show_stats", False)))
        self.show_quick_access_var = tk.BooleanVar(value=bool(app.settings.get("show_quick_access", False)))
        self.show_results_panel_var = tk.BooleanVar(value=bool(app.settings.get("show_results_panel", False)))
        self.show_extended_details_var = tk.BooleanVar(value=bool(app.settings.get("show_extended_details", False)))
        self.show_detail_actions_var = tk.BooleanVar(value=bool(app.settings.get("show_detail_actions", False)))
        self.allow_art_customization_var = tk.BooleanVar(value=bool(app.settings.get("allow_art_customization", False)))
        self.allow_art_sidebar_resize_var = tk.BooleanVar(value=bool(app.settings.get("allow_art_sidebar_resize", False)))
        self.art_layout_preset_var = tk.StringVar(
            value=ART_LAYOUT_PRESETS.get(
                app.settings.get("art_layout_preset", DEFAULT_SETTINGS["art_layout_preset"]),
                ART_LAYOUT_PRESETS[DEFAULT_SETTINGS["art_layout_preset"]],
            )["label"]
        )
        self.show_background_art_var = tk.BooleanVar(value=bool(app.settings.get("show_background_art", True)))
        self.show_art_right_main_var = tk.BooleanVar(value=bool(app.settings.get("show_art_right_main", True)))
        self.show_art_right_accent_var = tk.BooleanVar(value=bool(app.settings.get("show_art_right_accent", True)))
        self.show_art_hero_var = tk.BooleanVar(value=bool(app.settings.get("show_art_hero", False)))
        self.show_art_search_var = tk.BooleanVar(value=bool(app.settings.get("show_art_search", False)))
        self.show_art_results_var = tk.BooleanVar(value=bool(app.settings.get("show_art_results", False)))
        self.show_art_detail_var = tk.BooleanVar(value=bool(app.settings.get("show_art_detail", False)))
        self.expand_art_right_main_var = tk.BooleanVar(value=bool(app.settings.get("expand_art_right_main", False)))
        self.expand_art_right_accent_var = tk.BooleanVar(value=bool(app.settings.get("expand_art_right_accent", False)))
        self.expand_art_hero_var = tk.BooleanVar(value=bool(app.settings.get("expand_art_hero", False)))
        self.expand_art_search_var = tk.BooleanVar(value=bool(app.settings.get("expand_art_search", False)))
        self.expand_art_results_var = tk.BooleanVar(value=bool(app.settings.get("expand_art_results", False)))
        self.expand_art_detail_var = tk.BooleanVar(value=bool(app.settings.get("expand_art_detail", False)))
        self.hero_background_art_var = tk.StringVar(
            value=BACKGROUND_IMAGE_OPTIONS.get(
                app.settings.get("hero_background_art", DEFAULT_SETTINGS["hero_background_art"]),
                BACKGROUND_IMAGE_OPTIONS[DEFAULT_SETTINGS["hero_background_art"]],
            )["label"]
        )
        self.hero_banner_art_var = tk.StringVar(
            value=BACKGROUND_IMAGE_OPTIONS.get(
                app.settings.get("hero_banner_art", DEFAULT_SETTINGS["hero_banner_art"]),
                BACKGROUND_IMAGE_OPTIONS[DEFAULT_SETTINGS["hero_banner_art"]],
            )["label"]
        )
        self.search_background_art_var = tk.StringVar(
            value=BACKGROUND_IMAGE_OPTIONS.get(
                app.settings.get("search_background_art", DEFAULT_SETTINGS["search_background_art"]),
                BACKGROUND_IMAGE_OPTIONS[DEFAULT_SETTINGS["search_background_art"]],
            )["label"]
        )
        self.results_background_art_var = tk.StringVar(
            value=BACKGROUND_IMAGE_OPTIONS.get(
                app.settings.get("results_background_art", DEFAULT_SETTINGS["results_background_art"]),
                BACKGROUND_IMAGE_OPTIONS[DEFAULT_SETTINGS["results_background_art"]],
            )["label"]
        )
        self.detail_background_art_var = tk.StringVar(
            value=BACKGROUND_IMAGE_OPTIONS.get(
                app.settings.get("detail_background_art", DEFAULT_SETTINGS["detail_background_art"]),
                BACKGROUND_IMAGE_OPTIONS[DEFAULT_SETTINGS["detail_background_art"]],
            )["label"]
        )
        self.compact_background_art_var = tk.StringVar(
            value=BACKGROUND_IMAGE_OPTIONS.get(
                app.settings.get("compact_background_art", DEFAULT_SETTINGS["compact_background_art"]),
                BACKGROUND_IMAGE_OPTIONS[DEFAULT_SETTINGS["compact_background_art"]],
            )["label"]
        )
        self.source_mode_var = tk.StringVar(value=app.settings.get("source_mode", DEFAULT_SETTINGS["source_mode"]))
        self.import_url_var = tk.StringVar()
        self.llm_api_url_var = tk.StringVar(
            value=str(app.settings.get("llm_api_url", DEFAULT_SETTINGS["llm_api_url"]) or DEFAULT_SETTINGS["llm_api_url"])
        )
        self.llm_api_key_var = tk.StringVar(
            value=str(app.settings.get("llm_api_key", "") or os.getenv("LLM_API_KEY", ""))
        )
        self.llm_model_var = tk.StringVar(
            value=str(app.settings.get("llm_model", DEFAULT_SETTINGS["llm_model"]) or DEFAULT_SETTINGS["llm_model"])
        )
        _cur_llm_url = str(app.settings.get("llm_api_url", DEFAULT_SETTINGS["llm_api_url"]) or "")
        _init_service = (
            "Groq (ücretsiz)" if "groq.com" in _cur_llm_url
            else "Google Gemini (ücretsiz)" if "googleapis.com" in _cur_llm_url
            else "Yerel (Ollama)" if ("11434" in _cur_llm_url or "ollama" in _cur_llm_url.casefold())
            else "Özel"
        )
        self.llm_service_var = tk.StringVar(value=_init_service)
        self.original_settings = copy.deepcopy(app.settings)
        self.custom_art_slots = sanitize_custom_art_slots(app.settings.get("custom_art_slots", {}))
        self.preview_applied = False
        self.auto_preview_job: str | None = None
        self.auto_preview_delay_ms = 180
        self.auto_preview_enabled = False
        self.hover_tips: list[HoverTip] = []
        self.font_preview_card: tk.Frame | None = None
        self.font_preview_word_label: tk.Label | None = None
        self.font_preview_meta_label: tk.Label | None = None
        self.art_controls: list[
            tuple[str, tk.BooleanVar, tk.BooleanVar, ttk.Checkbutton, ttk.Combobox, ttk.Checkbutton, ttk.Button, ttk.Button, ttk.Button, ttk.Label]
        ] = []
        self.search_actions_status_var = tk.StringVar(value="")
        self._updating_search_action_vars = False
        self.settings_scroll_canvases: list[tk.Canvas] = []
        self.show_background_art_check: ttk.Checkbutton | None = None
        self.art_layout_combo: ttk.Combobox | None = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=16, pady=(16, 8))

        search_shell, search_tab = self.create_scrollable_tab(self.notebook)
        view_shell, view_tab = self.create_scrollable_tab(self.notebook)
        sources_shell, sources_tab = self.create_scrollable_tab(self.notebook)
        import_shell, import_tab = self.create_scrollable_tab(self.notebook)

        self.notebook.add(search_shell, text="Arama ve Liste")
        self.notebook.add(view_shell, text="Görünüm")
        self.notebook.add(sources_shell, text="Kaynak Seçimi")
        self.notebook.add(import_shell, text="Kelime Ekle / Aktar")

        self._build_search_tab(search_tab)
        self._build_view_tab(view_tab)
        self._build_sources_tab(sources_tab)
        self._build_import_tab(import_tab)
        repair_widget_tree_texts(self)
        self.register_auto_preview_watchers()
        self.auto_preview_enabled = True

        self.footer = ttk.Frame(self, padding=(16, 0, 16, 16))
        self.footer.grid(row=1, column=0, sticky="ew")
        self.footer.columnconfigure(0, weight=1)
        ttk.Button(self.footer, text="Varsayılanlara dön", command=self.reset_to_defaults).grid(row=0, column=0, sticky="w")
        ttk.Button(self.footer, text="İptal", command=self.cancel).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(self.footer, text="Kaydet", style="Primary.TButton", command=self.save).grid(row=0, column=2, padx=(8, 0))
        self.apply_dialog_theme()
        self.after(0, self.bring_to_front)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self._app_map_bind_id = self.app.bind("<Map>", self._on_app_restored, add="+")

    def _on_app_restored(self, _event=None) -> None:
        if self.winfo_exists():
            self.lift()
            self.focus_force()

    def bring_to_front(self) -> None:
        self.lift()
        self.focus_force()

    def destroy(self) -> None:
        self.cancel_auto_preview()
        try:
            self.app.unbind("<Map>", self._app_map_bind_id)
        except Exception:
            pass
        if getattr(self.app, "settings_dialog", None) is self:
            self.app.settings_dialog = None
        super().destroy()

    def apply_dialog_theme(self, palette: dict | None = None) -> None:
        active_palette = palette or THEMES.get(self.app.settings.get("theme", DEFAULT_SETTINGS["theme"]), THEMES["krem"])
        self.configure(bg=active_palette["bg"])
        for canvas in self.settings_scroll_canvases:
            canvas.configure(bg=active_palette["panel"], highlightbackground=active_palette["line"], highlightcolor=active_palette["line"])
        self.app.apply_window_chrome(self, active_palette)

    def create_scrollable_tab(self, notebook: ttk.Notebook) -> tuple[ttk.Frame, ttk.Frame]:
        shell = ttk.Frame(notebook)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        canvas = tk.Canvas(shell, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=18)

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def sync_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_content_width(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        content.bind("<Configure>", sync_scroll_region)
        canvas.bind("<Configure>", sync_content_width)

        def on_mousewheel(event) -> str:
            delta = 0
            if getattr(event, "delta", 0):
                delta = int(-event.delta / 120)
            elif getattr(event, "num", None) == 4:
                delta = -1
            elif getattr(event, "num", None) == 5:
                delta = 1
            if delta:
                canvas.yview_scroll(delta, "units")
            return "break"

        def bind_mousewheel(_event=None) -> None:
            canvas.bind_all("<MouseWheel>", on_mousewheel)
            canvas.bind_all("<Button-4>", on_mousewheel)
            canvas.bind_all("<Button-5>", on_mousewheel)

        def unbind_mousewheel(_event=None) -> None:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        for widget in (shell, canvas, content):
            widget.bind("<Enter>", bind_mousewheel, add=True)
            widget.bind("<Leave>", unbind_mousewheel, add=True)

        self.settings_scroll_canvases.append(canvas)
        return shell, content

    def cancel(self) -> None:
        self.cancel_auto_preview()
        if self.preview_applied:
            self.app.apply_settings(copy.deepcopy(self.original_settings))
        self.destroy()

    def register_auto_preview_watchers(self) -> None:
        watched_variables = [
            self.pos_var,
            self.category_var,
            self.source_var,
            self.note_only_var,
            self.result_limit_var,
            self.content_font_size_var,
            self.translation_font_size_var,
            self.meta_font_size_var,
            self.sort_mode_var,
            self.theme_var,
            self.font_preset_var,
            self.show_examples_var,
            self.show_notes_var,
            self.remember_search_var,
            self.show_stats_var,
            self.show_quick_access_var,
            self.show_results_panel_var,
            self.show_extended_details_var,
            self.show_detail_actions_var,
            self.allow_art_customization_var,
            self.allow_art_sidebar_resize_var,
            self.art_layout_preset_var,
            self.show_background_art_var,
            self.show_art_right_main_var,
            self.show_art_right_accent_var,
            self.show_art_hero_var,
            self.show_art_search_var,
            self.show_art_results_var,
            self.show_art_detail_var,
            self.expand_art_right_main_var,
            self.expand_art_right_accent_var,
            self.expand_art_hero_var,
            self.expand_art_search_var,
            self.expand_art_results_var,
            self.expand_art_detail_var,
            self.hero_background_art_var,
            self.hero_banner_art_var,
            self.search_background_art_var,
            self.results_background_art_var,
            self.detail_background_art_var,
            self.compact_background_art_var,
            self.source_mode_var,
            self.llm_api_url_var,
            self.llm_api_key_var,
            self.llm_model_var,
            self.llm_service_var,
        ]
        for variable in watched_variables:
            variable.trace_add("write", self.schedule_auto_preview)
        if hasattr(self, "source_list"):
            self.source_list.bind("<<ListboxSelect>>", self.schedule_auto_preview, add=True)

    def cancel_auto_preview(self) -> None:
        if self.auto_preview_job:
            self.after_cancel(self.auto_preview_job)
            self.auto_preview_job = None

    def schedule_auto_preview(self, *_args) -> None:
        if not self.auto_preview_enabled or not self.winfo_exists():
            return
        self.cancel_auto_preview()
        self.auto_preview_job = self.after(self.auto_preview_delay_ms, self.preview)

    def get_custom_art_config(self, slot_key: str) -> dict:
        return sanitize_custom_art_config(self.custom_art_slots.get(slot_key))

    def choose_custom_art(self, slot_key: str) -> None:
        if not PIL_AVAILABLE:
            messagebox.showerror(
                "Görsel Seç",
                "PNG, JPEG ve diğer popüler biçimleri kullanmak için Pillow gerekir. Bu bilgisayarda yüklenemedi.",
                parent=self,
            )
            return
        selected_path = filedialog.askopenfilename(
            parent=self,
            title="Bilgisayardan Görsel Seç",
            filetypes=[
                ("Görsel dosyaları", " ".join(CUSTOM_ART_SUPPORTED_SUFFIXES)),
                ("PNG", "*.png"),
                ("JPEG", "*.jpg *.jpeg"),
                ("WebP", "*.webp"),
                ("BMP", "*.bmp"),
                ("GIF", "*.gif"),
                ("TIFF", "*.tif *.tiff"),
                ("Tüm dosyalar", "*.*"),
            ],
        )
        if not selected_path:
            return
        self.edit_custom_art_crop(slot_key, selected_path)

    def edit_custom_art_crop(self, slot_key: str, image_path: str | None = None) -> None:
        config = self.get_custom_art_config(slot_key)
        selected_path = str(image_path or config.get("path", "")).strip()
        if not selected_path:
            messagebox.showinfo("Kırpma", "Önce bu alan için bilgisayarınızdan bir görsel seçin.", parent=self)
            return
        if not Path(selected_path).exists():
            messagebox.showerror("Kırpma", "Seçilen görsel bulunamadı.", parent=self)
            return
        try:
            crop_dialog = ImageCropDialog(
                self,
                ART_SLOT_CONFIGS[slot_key]["label"],
                selected_path,
                ART_SLOT_CONFIGS[slot_key]["target_size"],
                initial_config=config if config.get("path") == selected_path else {"path": selected_path},
            )
        except Exception as exc:
            messagebox.showerror("Kırpma", f"Görsel açılamadı: {exc}", parent=self)
            return
        self.wait_window(crop_dialog)
        if not crop_dialog.result:
            return
        self.custom_art_slots[slot_key] = sanitize_custom_art_config(crop_dialog.result)
        self.update_art_control_states()
        self.schedule_auto_preview()

    def clear_custom_art(self, slot_key: str) -> None:
        self.custom_art_slots.pop(slot_key, None)
        self.update_art_control_states()
        self.schedule_auto_preview()

    def update_art_status_label(self, label: ttk.Label, slot_key: str) -> None:
        config = self.get_custom_art_config(slot_key)
        path_text = str(config.get("path", "")).strip()
        if not path_text:
            label.configure(text="Yerleşik görsel kullanılır.")
            return
        path = Path(path_text)
        if path.exists():
            label.configure(text=f"Özel dosya: {path.name}")
        else:
            label.configure(text="Özel dosya bulunamadı. Yerleşik görsele dönüldü.")

    def get_selected_search_actions(self) -> list[str]:
        selected = [key for key in SEARCH_ACTION_OPTIONS if self.search_action_vars[key].get()]
        return selected[:MAX_SEARCH_ACTION_BUTTONS]

    def on_search_action_toggle(self, changed_key: str) -> None:
        if self._updating_search_action_vars:
            return
        selected = [key for key in SEARCH_ACTION_OPTIONS if self.search_action_vars[key].get()]
        if len(selected) > MAX_SEARCH_ACTION_BUTTONS:
            self._updating_search_action_vars = True
            self.search_action_vars[changed_key].set(False)
            self._updating_search_action_vars = False
            self.search_actions_status_var.set(f"En fazla {MAX_SEARCH_ACTION_BUTTONS} düğme seçebilirsiniz.")
            return
        labels = [SEARCH_ACTION_OPTIONS[key]["label"] for key in selected]
        self.search_actions_status_var.set(
            "Seçili düğmeler: " + ", ".join(labels) if labels else "En az bir düğme seçin."
        )
        self.schedule_auto_preview()

    def _build_search_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Label(
            parent,
            text="Varsayılan liste davranışını buradan belirleyin. Ana ekranda daha az kontrol gösterilir.",
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        ttk.Label(parent, text="Sıralama", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Combobox(
            parent,
            textvariable=self.sort_mode_var,
            values=list(SORT_OPTIONS.values()),
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=8)

        ttk.Label(parent, text="Ekranda en çok", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=8)
        ttk.Spinbox(parent, from_=50, to=1000, increment=25, textvariable=self.result_limit_var).grid(
            row=2, column=1, sticky="ew", pady=8
        )

        ttk.Label(parent, text="Varsayılan tür", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=8)
        ttk.Combobox(parent, textvariable=self.pos_var, values=["Hepsi", *self.app.pos_values], state="readonly").grid(
            row=3, column=1, sticky="ew", pady=8
        )

        ttk.Label(parent, text="Seviye filtresi (CEFR)", style="Section.TLabel").grid(row=4, column=0, sticky="w", pady=8)
        ttk.Combobox(
            parent,
            textvariable=self.seviye_filter_var,
            values=["Hepsi", *CEFR_LEVELS],
            state="readonly",
        ).grid(row=4, column=1, sticky="ew", pady=8)

        ttk.Label(parent, text="Varsayılan kategori", style="Section.TLabel").grid(row=5, column=0, sticky="w", pady=8)
        ttk.Combobox(
            parent,
            textvariable=self.category_var,
            values=["Hepsi", *self.app.category_values],
            state="readonly",
        ).grid(row=5, column=1, sticky="ew", pady=8)

        ttk.Label(parent, text="Varsayılan kaynak", style="Section.TLabel").grid(row=6, column=0, sticky="w", pady=8)
        ttk.Combobox(
            parent,
            textvariable=self.source_var,
            values=["Tümü", *self.app.source_values],
            state="readonly",
        ).grid(row=6, column=1, sticky="ew", pady=8)

        ttk.Checkbutton(parent, text="Sadece notu olan kayıtları göster", variable=self.note_only_var).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(14, 4)
        )

        actions_box = ttk.LabelFrame(parent, text="Arama Yanı Düğmeleri", padding=12)
        actions_box.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        actions_box.columnconfigure(0, weight=1)
        ttk.Label(
            actions_box,
            text=f"Arama çubuğunun yanındaki hızlı düğmeleri buradan seçin. En fazla {MAX_SEARCH_ACTION_BUTTONS} tane gösterilir.",
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        for index, (key, item) in enumerate(SEARCH_ACTION_OPTIONS.items(), start=1):
            check = ttk.Checkbutton(
                actions_box,
                text=item["label"],
                variable=self.search_action_vars[key],
                command=lambda value=key: self.on_search_action_toggle(value),
            )
            check.grid(row=index, column=0, sticky="w", pady=3)

        ttk.Label(actions_box, textvariable=self.search_actions_status_var, style="Muted.TLabel", wraplength=620, justify="left").grid(
            row=len(SEARCH_ACTION_OPTIONS) + 1, column=0, sticky="w", pady=(8, 0)
        )
        self.on_search_action_toggle("")

        translation_box = ttk.LabelFrame(parent, text="LibreTranslate", padding=12)
        translation_box.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        translation_box.columnconfigure(0, weight=1)
        ttk.Label(
            translation_box,
            text=(
                "Arama kutusunun altindaki ceviri karti internet uzerinden LibreTranslate API cagrisi yapar. "
                "libretranslate.com resmi endpoint'i API key isteyebilir; anahtar yoksa uygulama docs'ta listelenen public mirror'lari dener."
            ),
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(translation_box, text="API adresi", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(translation_box, textvariable=self.libretranslate_url_var).grid(row=2, column=0, sticky="ew")
        ttk.Label(translation_box, text="API anahtari (resmi endpoint icin gerekebilir)", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 6))
        ttk.Entry(translation_box, textvariable=self.libretranslate_api_key_var, show="*").grid(row=4, column=0, sticky="ew")

    def _build_view_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Label(
            parent,
            text="Görünüm ayarları sadece masaüstü arayüzünü etkiler. Sözlük verisi değişmez.",
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ttk.Label(
            parent,
            text="Bazı seçeneklerin üstüne kısa süre bekleyince ne işe yaradığını anlatan not görünür.",
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(parent, text="Tema", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=8)
        self.theme_dropdown = ThemeDropdown(parent, self.theme_var)
        self.theme_dropdown.grid(row=2, column=1, sticky="ew", pady=8)

        ttk.Label(parent, text="Yazı stili", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=8)
        ttk.Combobox(
            parent,
            textvariable=self.font_preset_var,
            values=[item["label"] for item in FONT_PRESETS.values()],
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", pady=8)

        self.font_preview_card = tk.Frame(parent, bd=1, highlightthickness=1, padx=14, pady=10)
        self.font_preview_card.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        self.font_preview_card.columnconfigure(0, weight=1)
        self.font_preview_word_label = tk.Label(self.font_preview_card, anchor="w")
        self.font_preview_word_label.grid(row=0, column=0, sticky="w")
        self.font_preview_meta_label = tk.Label(self.font_preview_card, anchor="w", justify="left")
        self.font_preview_meta_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.font_preset_var.trace_add("write", self.refresh_font_preview)
        self.content_font_size_var.trace_add("write", self.refresh_font_preview)
        self.translation_font_size_var.trace_add("write", self.refresh_font_preview)
        self.meta_font_size_var.trace_add("write", self.refresh_font_preview)
        self.theme_var.trace_add("write", self.refresh_font_preview)
        self.refresh_font_preview()

        self.theme_preview_row = ttk.Frame(parent)
        self.theme_preview_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        self.theme_preview_buttons: list[tk.Button] = []
        preview_columns = 4
        for column_index in range(preview_columns):
            self.theme_preview_row.columnconfigure(column_index, weight=1)
        for index, (theme_key, theme) in enumerate(THEMES.items()):
            button = tk.Button(
                self.theme_preview_row,
                text=theme["label"],
                width=12,
                relief="flat",
                command=lambda value=theme["label"]: self.theme_var.set(value),
            )
            button.grid(
                row=index // preview_columns,
                column=index % preview_columns,
                padx=(0, 8),
                pady=(0, 8),
                sticky="ew",
            )
            self.theme_preview_buttons.append(button)
        self.refresh_theme_preview_buttons()
        self.theme_var.trace_add("write", self.refresh_theme_preview_buttons)

        ttk.Label(parent, text="Tanım yazısı boyutu", style="Section.TLabel").grid(row=6, column=0, sticky="w", pady=8)
        ttk.Spinbox(parent, from_=11, to=22, increment=1, textvariable=self.content_font_size_var).grid(
            row=6, column=1, sticky="ew", pady=8
        )

        ttk.Label(parent, text="Türkçe tanım boyutu", style="Section.TLabel").grid(row=7, column=0, sticky="w", pady=8)
        ttk.Spinbox(parent, from_=14, to=30, increment=1, textvariable=self.translation_font_size_var).grid(
            row=7, column=1, sticky="ew", pady=8
        )

        ttk.Label(parent, text="Kısa bilgi boyutu", style="Section.TLabel").grid(row=8, column=0, sticky="w", pady=8)
        ttk.Spinbox(parent, from_=9, to=22, increment=1, textvariable=self.meta_font_size_var).grid(
            row=8, column=1, sticky="ew", pady=8
        )

        show_examples_check = ttk.Checkbutton(parent, text="Örnek cümleleri göster", variable=self.show_examples_var)
        show_examples_check.grid(row=9, column=0, columnspan=2, sticky="w", pady=6)
        self.hover_tips.append(HoverTip(show_examples_check, "Kelimenin örnek kullanım cümleleri varsa detay alanında görünür."))

        show_notes_check = ttk.Checkbutton(parent, text="Notları göster", variable=self.show_notes_var)
        show_notes_check.grid(row=10, column=0, columnspan=2, sticky="w", pady=6)
        self.hover_tips.append(HoverTip(show_notes_check, "Kayıtta özel not varsa detay alanında gösterir. Not yoksa ek bir satır açılmaz."))

        remember_search_check = ttk.Checkbutton(parent, text="Son aramayı yeniden açılışta hatırla", variable=self.remember_search_var)
        remember_search_check.grid(row=11, column=0, columnspan=2, sticky="w", pady=6)
        self.hover_tips.append(HoverTip(remember_search_check, "Program tekrar açıldığında son arama kutuya hazır gelir."))

        art_box = ttk.LabelFrame(parent, text="Doğa Görselleri", padding=12)
        art_box.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        art_box.columnconfigure(0, weight=1)
        unlock_art_check = ttk.Checkbutton(
            art_box,
            text="Doğa paneli seçeneklerini düzenlemeye aç",
            variable=self.allow_art_customization_var,
            command=self.update_art_control_states,
        )
        unlock_art_check.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.hover_tips.append(HoverTip(unlock_art_check, "Kapalıyken doğa görselleri çalışır ama bu bölümden değiştirilemez."))
        allow_resize_check = ttk.Checkbutton(
            art_box,
            text="Doğa panellerini sürükleyerek değiştir",
            variable=self.allow_art_sidebar_resize_var,
        )
        allow_resize_check.grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.hover_tips.append(HoverTip(allow_resize_check, "Kapalıyken iki doğa paneli seçtiğiniz oranla sabit kalır; kullanıcı ayırıcıları sürükleyemez."))
        layout_row = ttk.Frame(art_box)
        layout_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        layout_row.columnconfigure(1, weight=1)
        ttk.Label(layout_row, text="Panel oranı", style="Section.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.art_layout_combo = ttk.Combobox(
            layout_row,
            textvariable=self.art_layout_preset_var,
            values=[item["label"] for item in ART_LAYOUT_PRESETS.values()],
            state="readonly",
        )
        self.art_layout_combo.grid(row=0, column=1, sticky="ew")
        self.hover_tips.append(HoverTip(self.art_layout_combo, "Doğa ve sözlük alanlarının ekrandaki yatay oranını seçer."))
        self.show_background_art_check = ttk.Checkbutton(
            art_box, text="Arka planda doğa görsellerini kullan", variable=self.show_background_art_var
        )
        self.show_background_art_check.grid(row=3, column=0, sticky="w", pady=(0, 8))
        self.hover_tips.append(HoverTip(self.show_background_art_check, "Sol ve sağdaki dekoratif doğa panellerini açar veya kapatır."))
        art_values = [item["label"] for item in BACKGROUND_IMAGE_OPTIONS.values()]

        def add_art_row(
            row: int,
            slot_key: str,
            label: str,
            enabled_var: tk.BooleanVar,
            expand_var: tk.BooleanVar,
            art_var: tk.StringVar,
            tip_text: str,
        ) -> None:
            row_frame = ttk.Frame(art_box)
            row_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            row_frame.columnconfigure(0, weight=1)

            check = ttk.Checkbutton(row_frame, text=label, variable=enabled_var, command=self.update_art_control_states)
            check.grid(row=0, column=0, sticky="w")

            control_row = ttk.Frame(row_frame)
            control_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
            control_row.columnconfigure(0, weight=1)

            combo = ttk.Combobox(control_row, textvariable=art_var, values=art_values, state="readonly")
            combo.grid(row=0, column=0, sticky="ew")
            expand_check = ttk.Checkbutton(control_row, text="Geniş", variable=expand_var, command=self.update_art_control_states)
            expand_check.grid(row=0, column=1, sticky="w", padx=(10, 0))

            button_row = ttk.Frame(row_frame)
            button_row.grid(row=2, column=0, sticky="w", pady=(6, 0))
            file_button = ttk.Button(button_row, text="Bilgisayardan Aç", command=lambda key=slot_key: self.choose_custom_art(key))
            file_button.grid(row=0, column=0, sticky="w")
            crop_button = ttk.Button(button_row, text="Kırp", command=lambda key=slot_key: self.edit_custom_art_crop(key))
            crop_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
            clear_button = ttk.Button(button_row, text="Temizle", command=lambda key=slot_key: self.clear_custom_art(key))
            clear_button.grid(row=0, column=2, sticky="w", padx=(8, 0))

            status_label = ttk.Label(row_frame, style="Muted.TLabel")
            status_label.grid(row=3, column=0, sticky="w", pady=(6, 0))
            self.art_controls.append((slot_key, enabled_var, expand_var, check, combo, expand_check, file_button, crop_button, clear_button, status_label))
            if slot_key not in SETTINGS_VISIBLE_ART_SLOTS:
                row_frame.grid_remove()
            self.hover_tips.append(HoverTip(check, tip_text))
            self.hover_tips.append(HoverTip(expand_check, "İşaretlerseniz bu görselin kapladığı alan büyür."))
            self.hover_tips.append(HoverTip(file_button, "Bilgisayarınızdaki görsellerden seçer. PNG, JPEG, WebP, BMP, GIF ve TIFF desteklenir."))
            self.hover_tips.append(HoverTip(crop_button, "Seçilen özel dosyada hangi bölümün görüneceğini ayarlarsınız."))
            self.hover_tips.append(HoverTip(clear_button, "Bu alan için seçilmiş özel dosyayı kaldırır ve yerleşik seçime döner."))

        add_art_row(4, "right_main", "Doğa ana fotoğrafı", self.show_art_right_main_var, self.expand_art_right_main_var, self.hero_background_art_var, "Sol ve sağ doğa panellerindeki büyük manzara kartlarında görünür.")
        add_art_row(5, "right_accent", "Doğa ikinci fotoğrafı", self.show_art_right_accent_var, self.expand_art_right_accent_var, self.detail_background_art_var, "Yeterli yükseklik olduğunda iki yandaki ikinci doğa kartlarında görünür.")
        ttk.Label(
            art_box,
            text="Doğa fotoğrafları yalnızca sol ve sağ yan paneller için kullanılır. Görünmeyen eski köşe alanlarının ayarları kaldırıldı.",
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=10, column=0, sticky="w", pady=(4, 0))
        add_art_row(6, "hero", "Ust baslik alani", self.show_art_hero_var, self.expand_art_hero_var, self.hero_banner_art_var, "Basligin sag tarafindaki guvenli gorsel alaninda gorunur.")
        add_art_row(7, "search", "Arama karti kosesi", self.show_art_search_var, self.expand_art_search_var, self.search_background_art_var, "Arama kartinin kosesinde sozlugu kapatmadan gorunur.")
        add_art_row(8, "results", "Sonuc bos durumu", self.show_art_results_var, self.expand_art_results_var, self.results_background_art_var, "Sonuc alani bosken kullanilan guvenli fotograf alanidir.")
        add_art_row(9, "detail", "Tanim karti kosesi", self.show_art_detail_var, self.expand_art_detail_var, self.compact_background_art_var, "Detay kartinin kosesinde, metni kapatmadan gorunur.")
        ttk.Label(
            art_box,
            text="Fotograflar sadece sozluk arayuzuyle cakismayan guvenli alanlara yerlestirilir. Orta sozluk paneli her zaman gorunur kalir.",
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=11, column=0, sticky="w", pady=(6, 0))
        allow_resize_check.grid_remove()
        layout_row.grid_remove()
        self.show_background_art_check.configure(text="Sozluk icindeki guvenli fotograf alanlarini kullan")
        self.show_background_art_check.grid_configure(row=1)
        info_labels = art_box.grid_slaves(row=10, column=0)
        if info_labels:
            info_labels[0].configure(
                text="Fotograflar sadece sozluk arayuzuyle cakismayan guvenli alanlara yerlestirilir. Sozluk paneli her zaman gorunur kalir."
            )
        duplicate_info_labels = art_box.grid_slaves(row=11, column=0)
        if duplicate_info_labels:
            duplicate_info_labels[0].grid_remove()
        self.show_background_art_var.trace_add("write", self.update_art_control_states)
        for variable in [
            self.show_art_right_main_var,
            self.show_art_right_accent_var,
            self.show_art_hero_var,
            self.show_art_search_var,
            self.show_art_results_var,
            self.show_art_detail_var,
            self.expand_art_right_main_var,
            self.expand_art_right_accent_var,
            self.expand_art_hero_var,
            self.expand_art_search_var,
            self.expand_art_results_var,
            self.expand_art_detail_var,
        ]:
            variable.trace_add("write", self.update_art_control_states)
        self.update_art_control_states()

        extras_box = ttk.LabelFrame(parent, text="Ek Bölümler", padding=12)
        extras_box.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        extras_box.columnconfigure(0, weight=1)
        ttk.Checkbutton(extras_box, text="Bilgi kartlarını göster", variable=self.show_stats_var).grid(
            row=0, column=0, sticky="w", pady=4
        )
        ttk.Checkbutton(extras_box, text="Hızlı erişim alanını göster", variable=self.show_quick_access_var).grid(
            row=1, column=0, sticky="w", pady=4
        )
        ttk.Checkbutton(extras_box, text="Sonuç listesini göster", variable=self.show_results_panel_var).grid(
            row=2, column=0, sticky="w", pady=4
        )
        ttk.Checkbutton(extras_box, text="Gelişmiş sekmeleri göster", variable=self.show_extended_details_var).grid(
            row=3, column=0, sticky="w", pady=4
        )
        ttk.Checkbutton(extras_box, text="Kaynak ve favori düğmelerini göster", variable=self.show_detail_actions_var).grid(
            row=4, column=0, sticky="w", pady=4
        )

        ttk.Label(
            parent,
            text="Son aramalar ve favori kelimeler ana ekrandaki hızlı erişim bölümünde görünür.",
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=14, column=0, columnspan=2, sticky="w", pady=(16, 0))

    def refresh_theme_preview_buttons(self, *_args) -> None:
        current_label = self.theme_var.get()
        for button, theme in zip(self.theme_preview_buttons, THEMES.values()):
            is_selected = theme["label"] == current_label
            button.configure(
                bg=theme["accent_soft"],
                fg=theme["ink"],
                activebackground=theme["accent"],
                activeforeground="#ffffff",
                highlightbackground=theme["line"],
                highlightthickness=2 if is_selected else 1,
                bd=0,
                padx=10,
                pady=4,
            )

    def refresh_font_preview(self, *_args) -> None:
        if not self.font_preview_card or not self.font_preview_word_label or not self.font_preview_meta_label:
            return
        preset = next((item for item in FONT_PRESETS.values() if item["label"] == self.font_preset_var.get()), FONT_PRESETS["modern"])
        theme = next((item for item in THEMES.values() if item["label"] == self.theme_var.get()), THEMES["krem"])
        content_size = max(11, min(22, safe_int(self.content_font_size_var.get(), DEFAULT_SETTINGS["content_font_size"])))
        translation_size = max(14, min(30, safe_int(self.translation_font_size_var.get(), DEFAULT_SETTINGS["translation_font_size"])))
        meta_size = max(9, min(22, safe_int(self.meta_font_size_var.get(), DEFAULT_SETTINGS["meta_font_size"])))
        self.font_preview_card.configure(bg=theme["surface"], highlightbackground=theme["line"], highlightcolor=theme["line"])
        self.font_preview_word_label.configure(
            text="der Baum",
            bg=theme["surface"],
            fg=theme["ink"],
            font=(preset["title"], max(content_size + 4, 16), "bold"),
        )
        self.font_preview_meta_label.configure(
            text=f"ağaç • kısa bilgi örneği ({translation_size}/{meta_size})",
            bg=theme["surface"],
            fg=theme["muted"],
            font=(preset["content"], content_size),
        )

    def update_art_control_states(self, *_args) -> None:
        customization_enabled = bool(self.allow_art_customization_var.get())
        if self.show_background_art_check is not None:
            self.show_background_art_check.configure(state="normal" if customization_enabled else "disabled")
        if self.art_layout_combo is not None:
            self.art_layout_combo.configure(
                state="readonly" if customization_enabled and bool(self.show_background_art_var.get()) else "disabled"
            )
        global_enabled = customization_enabled and bool(self.show_background_art_var.get())
        for slot_key, enabled_var, expand_var, row_check, combo, expand_check, file_button, crop_button, clear_button, status_label in self.art_controls:
            row_check.configure(state="normal" if customization_enabled else "disabled")
            slot_enabled = global_enabled and enabled_var.get()
            has_custom_file = bool(self.get_custom_art_config(slot_key).get("path"))
            combo.configure(state="readonly" if slot_enabled else "disabled")
            expand_check.configure(state="normal" if slot_enabled else "disabled")
            file_button.configure(state="normal" if slot_enabled else "disabled")
            crop_button.configure(state="normal" if slot_enabled and has_custom_file and PIL_AVAILABLE else "disabled")
            clear_button.configure(state="normal" if slot_enabled and has_custom_file else "disabled")
            self.update_art_status_label(status_label, slot_key)

    def _build_sources_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)

        ttk.Label(
            parent,
            text="Kaynakları tamamen kapatmak yerine burada öncelik vereceğiniz kaynakları seçebilirsiniz.",
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 14))

        mode_wrap = ttk.Frame(parent)
        mode_wrap.grid(row=1, column=0, sticky="w")
        ttk.Radiobutton(mode_wrap, text="Tüm kaynakları kullan", value="all", variable=self.source_mode_var).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Radiobutton(
            mode_wrap,
            text="Sadece seçtiklerimi öne çıkar",
            value="preferred_only",
            variable=self.source_mode_var,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        ttk.Label(parent, text="Öncelikli kaynaklar", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=(14, 8))
        self.source_list = tk.Listbox(parent, selectmode="extended", exportselection=False, height=12)
        self.source_list.grid(row=3, column=0, sticky="nsew")

        for source_name in self.app.source_values:
            count = self.app.source_counts.get(source_name, 0)
            self.source_list.insert("end", f"{source_name} ({count})")

        selected = set(self.app.settings.get("preferred_sources", []))
        for index, source_name in enumerate(self.app.source_values):
            if source_name in selected:
                self.source_list.selection_set(index)

        button_row = ttk.Frame(parent)
        button_row.grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Button(button_row, text="Tümünü seç", command=self.select_all_sources).grid(row=0, column=0)
        ttk.Button(button_row, text="Temizle", command=self.clear_sources).grid(row=0, column=1, padx=(8, 0))

    def _build_import_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        ttk.Label(
            parent,
            text="Yeni kelime eklemek veya bir sayfadaki kelimeleri topluca taratmak için bu bölümü kullanın.",
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 14))

        entry_box = ttk.LabelFrame(parent, text="Tek kelime", padding=14)
        entry_box.grid(row=1, column=0, sticky="ew")
        entry_box.columnconfigure(0, weight=1)
        ttk.Label(
            entry_box,
            text="Almanca ve Türkçe karşılığı elinizdeyse doğrudan sakin ekleme formunu açabilirsiniz.",
            style="Muted.TLabel",
            wraplength=580,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(entry_box, text="Tek Kelime Ekle", command=self.launch_entry_dialog).grid(row=1, column=0, sticky="w", pady=(12, 0))

        import_box = ttk.LabelFrame(parent, text="URL'den kelime tara", padding=14)
        import_box.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        import_box.columnconfigure(0, weight=1)
        ttk.Label(
            import_box,
            text="Bir bağlantı girin. Uygulama sayfadaki görünür metni tarar, sözlükte olmayan Almanca kelimeleri çıkarır ve eklemeden önce size onay ekranı açar.",
            style="Muted.TLabel",
            wraplength=580,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ttk.Entry(import_box, textvariable=self.import_url_var).grid(row=1, column=0, sticky="ew", pady=(12, 8))
        ttk.Button(import_box, text="URL'yi Tara", style="Primary.TButton", command=self.launch_import_dialog).grid(
            row=2, column=0, sticky="w"
        )

        pair_box = ttk.LabelFrame(parent, text="Almanca metin + Türkçe çeviri", padding=14)
        pair_box.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        pair_box.columnconfigure(0, weight=1)
        ttk.Label(
            pair_box,
            text=(
                "Bu akış ayrı bir ekranda çalışır. Almanca metni ve Türkçe çevirisini karşılaştırır, "
                "sadece güçlü kanıtlı eşleşmeleri aday listesine alır."
            ),
            style="Muted.TLabel",
            wraplength=580,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(pair_box, text="Metinleri Karşılaştır", style="Primary.TButton", command=self.launch_parallel_text_import_dialog).grid(
            row=1, column=0, sticky="w", pady=(12, 0)
        )

        ai_box = ttk.LabelFrame(parent, text="AI Modeli", padding=14)
        ai_box.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        ai_box.columnconfigure(0, weight=1)
        ai_box.columnconfigure(1, weight=1)
        ttk.Label(
            ai_box,
            text="URL taramasındaki AI sekmesi ve metin eşleme özelliği için kullanılacak servisi seçin. Yapılandırılmazsa metin eşleme yerel sözlük moduna döner.",
            style="Muted.TLabel",
            wraplength=580,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(ai_box, text="Servis", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 6))
        ttk.Combobox(
            ai_box,
            textvariable=self.llm_service_var,
            values=list(LLM_SERVICE_OPTIONS),
            state="readonly",
        ).grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Label(ai_box, text="API anahtarı", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 6))
        ttk.Entry(ai_box, textvariable=self.llm_api_key_var, show="*").grid(row=4, column=0, columnspan=2, sticky="ew")
        ai_key_hint = ttk.Label(
            ai_box,
            text="Ücretsiz API anahtarı: aistudio.google.com/apikey",
            style="Muted.TLabel",
            wraplength=580,
            justify="left",
        )
        ai_key_hint.grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Label(ai_box, text="Model", style="Section.TLabel").grid(row=6, column=0, sticky="w", pady=(12, 6))
        ai_model_combo = ttk.Combobox(
            ai_box,
            textvariable=self.llm_model_var,
            values=list(GEMINI_MODEL_PRESETS),
        )
        ai_model_combo.grid(row=7, column=0, sticky="ew")
        ai_url_label = ttk.Label(ai_box, text="API adresi (özel)", style="Section.TLabel")
        ai_url_entry = ttk.Entry(ai_box, textvariable=self.llm_api_url_var)

        def _on_llm_service_change(*_):
            svc = self.llm_service_var.get()
            if svc == "Groq (ücretsiz)":
                self.llm_api_url_var.set(GROQ_API_URL)
                ai_model_combo.configure(values=list(GROQ_MODEL_PRESETS))
                if self.llm_model_var.get() not in GROQ_MODEL_PRESETS:
                    self.llm_model_var.set(GROQ_MODEL_PRESETS[0])
                ai_key_hint.grid()
                ai_url_label.grid_remove()
                ai_url_entry.grid_remove()
            elif svc == "Google Gemini (ücretsiz)":
                self.llm_api_url_var.set(GOOGLE_GEMINI_API_URL)
                ai_model_combo.configure(values=list(GEMINI_MODEL_PRESETS))
                if self.llm_model_var.get() not in GEMINI_MODEL_PRESETS:
                    self.llm_model_var.set(GEMINI_MODEL_PRESETS[0])
                ai_key_hint.grid()
                ai_url_label.grid_remove()
                ai_url_entry.grid_remove()
            elif svc == "Yerel (Ollama)":
                self.llm_api_url_var.set(LLM_CHAT_COMPLETIONS_FALLBACK_URL)
                ai_model_combo.configure(values=list(LOCAL_MODEL_PRESETS))
                if self.llm_model_var.get() not in LOCAL_MODEL_PRESETS:
                    self.llm_model_var.set(LOCAL_MODEL_PRESETS[0])
                ai_key_hint.grid_remove()
                ai_url_label.grid_remove()
                ai_url_entry.grid_remove()
            else:
                ai_model_combo.configure(values=list(LLM_MODEL_PRESETS))
                ai_key_hint.grid_remove()
                ai_url_label.grid(row=8, column=0, sticky="w", pady=(12, 6))
                ai_url_entry.grid(row=9, column=0, columnspan=2, sticky="ew")

        self.llm_service_var.trace_add("write", _on_llm_service_change)
        _on_llm_service_change()


    def launch_entry_dialog(self) -> None:
        self.destroy()
        self.app.after(10, self.app.open_entry_dialog)

    def launch_import_dialog(self) -> None:
        url = self.import_url_var.get().strip()
        if not url:
            messagebox.showerror("Kelime Aktar", "Önce bir URL girin.", parent=self)
            return
        self.destroy()
        self.app.after(10, lambda value=url: self.app.open_import_dialog(value))

    def launch_parallel_text_import_dialog(self) -> None:
        self.destroy()
        self.app.after(10, self.app.open_parallel_text_import_dialog)

    def select_all_sources(self) -> None:
        self.source_list.selection_set(0, "end")
        self.schedule_auto_preview()

    def clear_sources(self) -> None:
        self.source_list.selection_clear(0, "end")
        self.schedule_auto_preview()

    def reset_to_defaults(self) -> None:
        self.pos_var.set("Hepsi")
        self.category_var.set("Hepsi")
        self.source_var.set("Tümü")
        self.note_only_var.set(bool(DEFAULT_SETTINGS["note_only"]))
        self.result_limit_var.set(DEFAULT_SETTINGS["result_limit"])
        self.content_font_size_var.set(DEFAULT_SETTINGS["content_font_size"])
        self.translation_font_size_var.set(DEFAULT_SETTINGS["translation_font_size"])
        self.meta_font_size_var.set(DEFAULT_SETTINGS["meta_font_size"])
        self.font_preset_var.set(FONT_PRESETS[DEFAULT_SETTINGS["font_preset"]]["label"])
        self.sort_mode_var.set(SORT_OPTIONS[DEFAULT_SETTINGS["sort_mode"]])
        self.theme_var.set(THEMES[DEFAULT_SETTINGS["theme"]]["label"])
        self.show_examples_var.set(bool(DEFAULT_SETTINGS["show_examples"]))
        self.show_notes_var.set(bool(DEFAULT_SETTINGS["show_notes"]))
        self.remember_search_var.set(bool(DEFAULT_SETTINGS["remember_search"]))
        self._updating_search_action_vars = True
        default_actions = sanitize_search_action_buttons(DEFAULT_SETTINGS["search_action_buttons"])
        for key, variable in self.search_action_vars.items():
            variable.set(key in default_actions)
        self._updating_search_action_vars = False
        self.on_search_action_toggle("")
        self.allow_art_customization_var.set(bool(DEFAULT_SETTINGS["allow_art_customization"]))
        self.allow_art_sidebar_resize_var.set(bool(DEFAULT_SETTINGS["allow_art_sidebar_resize"]))
        self.art_layout_preset_var.set(ART_LAYOUT_PRESETS[DEFAULT_SETTINGS["art_layout_preset"]]["label"])
        self.show_background_art_var.set(bool(DEFAULT_SETTINGS["show_background_art"]))
        self.show_art_right_main_var.set(bool(DEFAULT_SETTINGS["show_art_right_main"]))
        self.show_art_right_accent_var.set(bool(DEFAULT_SETTINGS["show_art_right_accent"]))
        self.show_art_hero_var.set(bool(DEFAULT_SETTINGS["show_art_hero"]))
        self.show_art_search_var.set(bool(DEFAULT_SETTINGS["show_art_search"]))
        self.show_art_results_var.set(bool(DEFAULT_SETTINGS["show_art_results"]))
        self.show_art_detail_var.set(bool(DEFAULT_SETTINGS["show_art_detail"]))
        self.expand_art_right_main_var.set(bool(DEFAULT_SETTINGS["expand_art_right_main"]))
        self.expand_art_right_accent_var.set(bool(DEFAULT_SETTINGS["expand_art_right_accent"]))
        self.expand_art_hero_var.set(bool(DEFAULT_SETTINGS["expand_art_hero"]))
        self.expand_art_search_var.set(bool(DEFAULT_SETTINGS["expand_art_search"]))
        self.expand_art_results_var.set(bool(DEFAULT_SETTINGS["expand_art_results"]))
        self.expand_art_detail_var.set(bool(DEFAULT_SETTINGS["expand_art_detail"]))
        self.custom_art_slots = {}
        self.hero_background_art_var.set(BACKGROUND_IMAGE_OPTIONS[DEFAULT_SETTINGS["hero_background_art"]]["label"])
        self.hero_banner_art_var.set(BACKGROUND_IMAGE_OPTIONS[DEFAULT_SETTINGS["hero_banner_art"]]["label"])
        self.search_background_art_var.set(BACKGROUND_IMAGE_OPTIONS[DEFAULT_SETTINGS["search_background_art"]]["label"])
        self.results_background_art_var.set(BACKGROUND_IMAGE_OPTIONS[DEFAULT_SETTINGS["results_background_art"]]["label"])
        self.detail_background_art_var.set(BACKGROUND_IMAGE_OPTIONS[DEFAULT_SETTINGS["detail_background_art"]]["label"])
        self.compact_background_art_var.set(BACKGROUND_IMAGE_OPTIONS[DEFAULT_SETTINGS["compact_background_art"]]["label"])
        self.show_stats_var.set(bool(DEFAULT_SETTINGS["show_stats"]))
        self.show_quick_access_var.set(bool(DEFAULT_SETTINGS["show_quick_access"]))
        self.show_results_panel_var.set(bool(DEFAULT_SETTINGS["show_results_panel"]))
        self.show_extended_details_var.set(bool(DEFAULT_SETTINGS["show_extended_details"]))
        self.show_detail_actions_var.set(bool(DEFAULT_SETTINGS["show_detail_actions"]))
        self.source_mode_var.set(DEFAULT_SETTINGS["source_mode"])
        self.libretranslate_url_var.set(DEFAULT_SETTINGS["libretranslate_url"])
        self.libretranslate_api_key_var.set(DEFAULT_SETTINGS["libretranslate_api_key"])
        self.llm_api_url_var.set(DEFAULT_SETTINGS["llm_api_url"])
        self.llm_api_key_var.set(DEFAULT_SETTINGS["llm_api_key"])
        self.llm_model_var.set(DEFAULT_SETTINGS["llm_model"])
        self.llm_service_var.set("Groq (ücretsiz)")
        self.clear_sources()
        self.update_art_control_states()

    def build_payload(self) -> dict:
        selected_sources = [self.app.source_values[index] for index in self.source_list.curselection()]
        theme_key = next(
            (key for key, value in THEMES.items() if value["label"] == self.theme_var.get()),
            DEFAULT_SETTINGS["theme"],
        )
        sort_key = next(
            (key for key, value in SORT_OPTIONS.items() if value == self.sort_mode_var.get()),
            DEFAULT_SETTINGS["sort_mode"],
        )
        font_preset_key = next(
            (key for key, value in FONT_PRESETS.items() if value["label"] == self.font_preset_var.get()),
            DEFAULT_SETTINGS["font_preset"],
        )
        llm_model_value = self.llm_model_var.get().strip() or DEFAULT_SETTINGS["llm_model"]
        art_layout_preset_key = next(
            (key for key, value in ART_LAYOUT_PRESETS.items() if value["label"] == self.art_layout_preset_var.get()),
            DEFAULT_SETTINGS["art_layout_preset"],
        )
        hero_art_key = next(
            (key for key, value in BACKGROUND_IMAGE_OPTIONS.items() if value["label"] == self.hero_background_art_var.get()),
            DEFAULT_SETTINGS["hero_background_art"],
        )
        search_art_key = next(
            (key for key, value in BACKGROUND_IMAGE_OPTIONS.items() if value["label"] == self.search_background_art_var.get()),
            DEFAULT_SETTINGS["search_background_art"],
        )
        results_art_key = next(
            (key for key, value in BACKGROUND_IMAGE_OPTIONS.items() if value["label"] == self.results_background_art_var.get()),
            DEFAULT_SETTINGS["results_background_art"],
        )
        detail_art_key = next(
            (key for key, value in BACKGROUND_IMAGE_OPTIONS.items() if value["label"] == self.detail_background_art_var.get()),
            DEFAULT_SETTINGS["detail_background_art"],
        )
        hero_banner_art_key = next(
            (key for key, value in BACKGROUND_IMAGE_OPTIONS.items() if value["label"] == self.hero_banner_art_var.get()),
            DEFAULT_SETTINGS["hero_banner_art"],
        )
        compact_art_key = next(
            (key for key, value in BACKGROUND_IMAGE_OPTIONS.items() if value["label"] == self.compact_background_art_var.get()),
            DEFAULT_SETTINGS["compact_background_art"],
        )

        payload = copy.deepcopy(self.app.settings)
        payload.update(
            {
                "theme": theme_key,
                "font_preset": font_preset_key,
                "show_examples": bool(self.show_examples_var.get()),
                "show_notes": bool(self.show_notes_var.get()),
                "remember_search": bool(self.remember_search_var.get()),
                "search_action_buttons": self.get_selected_search_actions(),
                "allow_art_customization": bool(self.allow_art_customization_var.get()),
                "allow_art_sidebar_resize": bool(self.allow_art_sidebar_resize_var.get()),
                "art_layout_preset": art_layout_preset_key,
                "show_background_art": bool(self.show_background_art_var.get()),
                "show_art_right_main": bool(self.show_art_right_main_var.get()),
                "show_art_right_accent": bool(self.show_art_right_accent_var.get()),
                "show_art_hero": bool(self.show_art_hero_var.get()),
                "show_art_search": bool(self.show_art_search_var.get()),
                "show_art_results": bool(self.show_art_results_var.get()),
                "show_art_detail": bool(self.show_art_detail_var.get()),
                "expand_art_right_main": bool(self.expand_art_right_main_var.get()),
                "expand_art_right_accent": bool(self.expand_art_right_accent_var.get()),
                "expand_art_hero": bool(self.expand_art_hero_var.get()),
                "expand_art_search": bool(self.expand_art_search_var.get()),
                "expand_art_results": bool(self.expand_art_results_var.get()),
                "expand_art_detail": bool(self.expand_art_detail_var.get()),
                "custom_art_slots": copy.deepcopy(sanitize_custom_art_slots(self.custom_art_slots)),
                "hero_background_art": hero_art_key,
                "hero_banner_art": hero_banner_art_key,
                "search_background_art": search_art_key,
                "results_background_art": results_art_key,
                "detail_background_art": detail_art_key,
                "compact_background_art": compact_art_key,
                "show_stats": bool(self.show_stats_var.get()),
                "show_quick_access": bool(self.show_quick_access_var.get()),
                "show_results_panel": bool(self.show_results_panel_var.get()),
                "show_extended_details": bool(self.show_extended_details_var.get()),
                "show_detail_actions": bool(self.show_detail_actions_var.get()),
                "note_only": bool(self.note_only_var.get()),
                "pos_filter": "" if self.pos_var.get() == "Hepsi" else self.pos_var.get(),
                "seviye_filter": "" if self.seviye_filter_var.get() == "Hepsi" else self.seviye_filter_var.get(),
                "category_filter": "" if self.category_var.get() == "Hepsi" else self.category_var.get(),
                "source_filter": "" if self.source_var.get() in ("Tümü", "Hepsi", "") else self.source_var.get(),
                "preferred_sources": selected_sources,
                "source_mode": self.source_mode_var.get(),
                "sort_mode": sort_key,
                "result_limit": max(50, min(1000, safe_int(self.result_limit_var.get(), DEFAULT_SETTINGS["result_limit"]))),
                "content_font_size": max(11, min(22, safe_int(self.content_font_size_var.get(), DEFAULT_SETTINGS["content_font_size"]))),
                "translation_font_size": max(14, min(30, safe_int(self.translation_font_size_var.get(), DEFAULT_SETTINGS["translation_font_size"]))),
                "meta_font_size": max(9, min(22, safe_int(self.meta_font_size_var.get(), DEFAULT_SETTINGS["meta_font_size"]))),
                "libretranslate_url": build_libretranslate_url(self.libretranslate_url_var.get()),
                "libretranslate_api_key": self.libretranslate_api_key_var.get().strip(),
                "llm_api_url": build_llm_api_url(self.llm_api_url_var.get()),
                "llm_api_key": self.llm_api_key_var.get().strip(),
                "llm_model": llm_model_value,
            }
        )
        payload = enforce_visible_art_settings(payload)
        return payload

    def preview(self) -> None:
        self.auto_preview_job = None
        payload = self.build_payload()
        self.app.apply_settings(payload)
        self.preview_applied = True

    def save(self) -> None:
        self.cancel_auto_preview()
        payload = self.build_payload()
        self.app.apply_settings(payload)
        self.preview_applied = False
        self.original_settings = copy.deepcopy(payload)
        self.destroy()


class EntryDialog(tk.Toplevel):
    def __init__(self, app: "DesktopDictionaryApp") -> None:
        super().__init__(app)
        self.app = app
        self.title("Yeni Kelime Ekle")
        self.transient(app)
        self.grab_set()
        self.geometry("590x560")
        self.minsize(560, 520)

        self.pos_var = tk.StringVar(value="isim")
        self.article_var = tk.StringVar(value="")
        self.german_var = tk.StringVar()
        self.turkish_var = tk.StringVar()
        self.description_var = tk.StringVar()
        self.note_var = tk.StringVar()
        self.source_url_var = tk.StringVar()
        self.show_optional_var = tk.BooleanVar(value=False)
        self.category_var = tk.StringVar(value="Algılanan kategori: -")
        self.helper_var = tk.StringVar(value="Zorunlu alanlar: Almanca, Türkçe ve tür.")

        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Yeni kelime ekle", style="DialogTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text="Önce temel bilgileri girin. İsteğe bağlı ayrıntılar yalnızca gerekirse açılır.",
            style="Muted.TLabel",
            wraplength=500,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 14))

        required_box = ttk.LabelFrame(frame, text="Gerekli Bilgiler", padding=14)
        required_box.grid(row=2, column=0, sticky="ew")
        required_box.columnconfigure(1, weight=1)

        ttk.Label(required_box, text="Tür", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 8))
        self.pos_combo = ttk.Combobox(required_box, textvariable=self.pos_var, values=UI_POS_CHOICES, state="readonly")
        self.pos_combo.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(required_box, text="Artikel", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 8))
        self.article_combo = ttk.Combobox(
            required_box,
            textvariable=self.article_var,
            values=["", "der", "die", "das"],
            state="readonly",
        )
        self.article_combo.grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(required_box, text="Almanca", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Entry(required_box, textvariable=self.german_var).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(required_box, text="Türkçe", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Entry(required_box, textvariable=self.turkish_var).grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(
            frame,
            text="İsteğe bağlı ayrıntıları göster",
            variable=self.show_optional_var,
            command=self.toggle_optional,
        ).grid(row=3, column=0, sticky="w", pady=(14, 8))

        self.optional_box = ttk.LabelFrame(frame, text="İsteğe Bağlı Ayrıntılar", padding=14)
        self.optional_box.columnconfigure(1, weight=1)
        ttk.Label(self.optional_box, text="Kısa açıklama", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=6, padx=(0, 8)
        )
        ttk.Entry(self.optional_box, textvariable=self.description_var).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Label(self.optional_box, text="Not", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Entry(self.optional_box, textvariable=self.note_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(self.optional_box, text="Kaynak bağlantısı", style="Section.TLabel").grid(
            row=2, column=0, sticky="w", pady=6, padx=(0, 8)
        )
        ttk.Entry(self.optional_box, textvariable=self.source_url_var).grid(row=2, column=1, sticky="ew", pady=6)

        info_box = ttk.Frame(frame, style="SoftPanel.TFrame", padding=14)
        info_box.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        info_box.columnconfigure(0, weight=1)
        ttk.Label(info_box, textvariable=self.category_var, style="Section.TLabel", wraplength=500, justify="left").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(info_box, textvariable=self.helper_var, style="Muted.TLabel", wraplength=500, justify="left").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )

        footer = ttk.Frame(frame, padding=(0, 16, 0, 0))
        footer.grid(row=6, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="Vazgeç", command=self.destroy).grid(row=0, column=1)
        ttk.Button(footer, text="Kaydet", style="Primary.TButton", command=self.save).grid(row=0, column=2, padx=(8, 0))

        self.toggle_optional()
        for variable in [self.german_var, self.turkish_var, self.description_var, self.note_var, self.source_url_var]:
            variable.trace_add("write", self.update_preview)
        self.pos_var.trace_add("write", self.on_pos_changed)
        self.on_pos_changed()
        self.update_preview()

    def toggle_optional(self) -> None:
        if self.show_optional_var.get():
            self.optional_box.grid(row=4, column=0, sticky="ew")
        else:
            self.optional_box.grid_remove()

    def on_pos_changed(self, *_args) -> None:
        is_noun = self.pos_var.get() == "isim"
        self.article_combo.configure(state="readonly" if is_noun else "disabled")
        if not is_noun:
            self.article_var.set("")
        self.update_preview()

    def payload(self) -> dict:
        return {
            "almanca": self.german_var.get().strip(),
            "artikel": self.article_var.get().strip(),
            "turkce": self.turkish_var.get().strip(),
            "tur": self.pos_var.get().strip(),
            "aciklama_turkce": self.description_var.get().strip(),
            "not": self.note_var.get().strip(),
            "kaynak_url": self.source_url_var.get().strip(),
        }

    def update_preview(self, *_args) -> None:
        payload = self.payload()
        validation = validate_user_entry(payload)
        if validation.get("status") == "error":
            self.category_var.set("Algılanan kategori: -")
            self.helper_var.set(validation.get("note", "Zorunlu alanları doldurun."))
            return

        categories = build_runtime_record(payload).get("kategoriler", ["genel"])
        self.category_var.set(f"Algılanan kategori: {', '.join(categories)}")
        self.helper_var.set("Bu kayıt kaydedildiğinde sonuç listesinde hemen görünecek.")

    def save(self) -> None:
        payload = self.payload()
        validation = validate_user_entry(payload)
        if validation.get("status") == "error":
            messagebox.showerror("Yeni Kelime", validation.get("note", "Kayıt doğrulanamadı."), parent=self)
            return

        saved = save_user_entry(payload)
        self.app.reload_data(select_key=record_key(saved))
        messagebox.showinfo("Yeni Kelime", "Kelime kaydedildi. Sonuç listesinde hemen kullanılabilir.", parent=self)
        self.destroy()


class DatasetEditorDialog(tk.Toplevel):
    def __init__(self, app: "DesktopDictionaryApp") -> None:
        super().__init__(app)
        self.app = app
        self.title("Veri Seti Editörü")
        self.transient(app)
        self.geometry("1220x760")
        self.minsize(980, 620)

        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Sözlük kayıtları burada düzenlenebilir.")
        self.source_var = tk.StringVar(value="-")
        self.selected_original_key: tuple[str, str, str] | None = None
        self.selected_storage_source = "base"
        self.selected_record: dict | None = None
        self.filtered_records: list[dict] = []
        self.tree_keys: dict[str, tuple[str, str, str]] = {}

        self.word_var = tk.StringVar()
        self.article_var = tk.StringVar()
        self.translation_var = tk.StringVar()
        self.pos_var = tk.StringVar(value="isim")
        self.source_name_var = tk.StringVar()
        self.source_url_var = tk.StringVar()

        shell = ttk.Frame(self, padding=16)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=4)
        shell.columnconfigure(1, weight=5)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="Panel.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Veri Seti Editörü", style="DialogTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Çeviri düzeltmek, örnek cümle eklemek ve veri setini iyileştirmek için geliştirici editörü.",
            style="Muted.TLabel",
            wraplength=920,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        left = ttk.Frame(shell, style="Panel.TFrame")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)

        ttk.Label(left, text="Kayıt Ara", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(left, textvariable=self.search_var).grid(row=1, column=0, sticky="ew", pady=(8, 10))
        self.tree = ttk.Treeview(left, columns=("word", "translation", "source"), show="headings", height=20)
        self.tree.heading("word", text="Almanca")
        self.tree.heading("translation", text="Türkçe")
        self.tree.heading("source", text="Depo")
        self.tree.column("word", width=180, anchor="w")
        self.tree.column("translation", width=180, anchor="w")
        self.tree.column("source", width=100, anchor="w")
        self.tree.grid(row=2, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=2, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll.set)

        right = ttk.Frame(shell, style="Panel.TFrame")
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)
        right.rowconfigure(7, weight=1)
        right.rowconfigure(8, weight=1)
        right.rowconfigure(9, weight=1)
        right.rowconfigure(10, weight=1)

        ttk.Label(right, text="Depo", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Label(right, textvariable=self.source_var, style="Muted.TLabel").grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(right, text="Almanca", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Entry(right, textvariable=self.word_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(right, text="Artikel", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Combobox(right, textvariable=self.article_var, values=["", "der", "die", "das"], state="readonly").grid(
            row=2, column=1, sticky="ew", pady=6
        )
        ttk.Label(right, text="Tür", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Combobox(right, textvariable=self.pos_var, values=UI_POS_CHOICES, state="readonly").grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Label(right, text="Türkçe", style="Section.TLabel").grid(row=4, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Entry(right, textvariable=self.translation_var).grid(row=4, column=1, sticky="ew", pady=6)
        ttk.Label(right, text="Kaynak", style="Section.TLabel").grid(row=5, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Entry(right, textvariable=self.source_name_var).grid(row=5, column=1, sticky="ew", pady=6)
        ttk.Label(right, text="Kaynak URL", style="Section.TLabel").grid(row=6, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Entry(right, textvariable=self.source_url_var).grid(row=6, column=1, sticky="ew", pady=6)

        self.description_text = self._add_text_field(right, 7, "Kısa açıklama")
        self.example_de_text = self._add_text_field(right, 8, "Örnek Almanca cümle")
        self.example_tr_text = self._add_text_field(right, 9, "Örnek Türkçe cümle")
        self.note_text = self._add_text_field(right, 10, "Not / çeviri inceleme")

        ttk.Label(right, textvariable=self.status_var, style="Muted.TLabel", wraplength=520, justify="left").grid(
            row=11, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        footer = ttk.Frame(shell, style="Panel.TFrame")
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="Ana Ekranda Aç", command=self.open_selected_in_main_app).grid(row=0, column=1)
        ttk.Button(footer, text="Kaydı Yeniden Yükle", command=self.reload_selected_record).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(footer, text="Kaydet", style="Primary.TButton", command=self.save_selected_record).grid(row=0, column=3, padx=(8, 0))

        self.search_var.trace_add("write", self.on_search_changed)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.apply_theme()
        self.refresh_records()

    def _add_text_field(self, parent: ttk.Frame, row: int, label: str) -> tk.Text:
        ttk.Label(parent, text=label, style="Section.TLabel").grid(row=row, column=0, sticky="nw", pady=6, padx=(0, 8))
        widget = tk.Text(parent, height=4, wrap="word", relief="flat", padx=10, pady=10)
        widget.grid(row=row, column=1, sticky="nsew", pady=6)
        return widget

    def apply_theme(self) -> None:
        palette = self.app.active_palette
        self.configure(bg=palette["bg"])
        self.app.apply_window_chrome(self, palette)
        for widget in [self.description_text, self.example_de_text, self.example_tr_text, self.note_text]:
            widget.configure(
                bg=palette["surface_soft"],
                fg=palette["ink"],
                highlightbackground=palette["line"],
                highlightcolor=palette["accent"],
                insertbackground=palette["accent"],
                selectbackground=palette["accent_soft"],
                selectforeground=palette["ink"],
                highlightthickness=1,
                bd=0,
            )

    def bring_to_front(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def on_close(self) -> None:
        self.app.dataset_editor_dialog = None
        self.destroy()

    def get_text(self, widget: tk.Text) -> str:
        return widget.get("1.0", "end").strip()

    def set_text(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", normalize_whitespace(value))

    def on_search_changed(self, *_args) -> None:
        self.refresh_records()

    def refresh_records(self) -> None:
        search = normalize_text(self.search_var.get())
        self.tree.delete(*self.tree.get_children())
        self.tree_keys.clear()
        records = self.app.records
        if search:
            records = [
                item
                for item in self.app.records
                if search in normalize_text(item.get("almanca", ""))
                or search in normalize_text(item.get("turkce", ""))
                or search in normalize_text(item.get("aciklama_turkce", ""))
            ]
        self.filtered_records = records
        for index, record in enumerate(records):
            item_id = f"editor-{index}"
            source_label = "Kullanıcı" if record.get("_storage_source") == "user" else "Ana veri"
            self.tree.insert("", "end", iid=item_id, values=(record.get("_word") or record.get("almanca", ""), record.get("turkce", ""), source_label))
            self.tree_keys[item_id] = record_key(record)
        self.status_var.set(f"{len(records)} kayıt listeleniyor.")
        if records:
            first = next(iter(self.tree.get_children()), None)
            if first:
                self.tree.selection_set(first)
                self.tree.focus(first)
                self.on_tree_select()

    def find_filtered_record(self, key: tuple[str, str, str]) -> dict | None:
        for record in self.filtered_records:
            if record_key(record) == key:
                return record
        return None

    def on_tree_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        record = self.find_filtered_record(self.tree_keys.get(selection[0], ("", "", "")))
        if not record:
            return
        self.selected_record = record
        self.selected_original_key = record_key(record)
        self.selected_storage_source = str(record.get("_storage_source", "base"))
        self.source_var.set("Kullanıcı kayıtları" if self.selected_storage_source == "user" else "Ana veri seti")
        self.word_var.set(record.get("almanca", ""))
        self.article_var.set(record.get("artikel", ""))
        self.translation_var.set(record.get("turkce", ""))
        self.pos_var.set(record.get("tur", "isim") or "isim")
        self.source_name_var.set(record.get("kaynak", ""))
        self.source_url_var.set(record.get("kaynak_url", ""))
        self.set_text(self.description_text, record.get("aciklama_turkce", ""))
        self.set_text(self.example_de_text, record.get("ornek_almanca", ""))
        self.set_text(self.example_tr_text, record.get("ornek_turkce", ""))
        combined_note = "\n\n".join(part for part in [record.get("ceviri_inceleme_notu", ""), record.get("not", "")] if normalize_whitespace(part))
        self.set_text(self.note_text, combined_note)
        self.status_var.set(f"{record.get('_word') or record.get('almanca', '')} düzenleniyor.")

    def build_payload(self) -> dict:
        original = self.selected_record or {}
        note_text = self.get_text(self.note_text)
        return build_dataset_editor_payload(
            original,
            {
                "almanca": self.word_var.get(),
                "artikel": self.article_var.get(),
                "turkce": self.translation_var.get(),
                "tur": self.pos_var.get(),
                "aciklama_turkce": self.get_text(self.description_text),
                "ornek_almanca": self.get_text(self.example_de_text),
                "ornek_turkce": self.get_text(self.example_tr_text),
                "kaynak": self.source_name_var.get(),
                "kaynak_url": self.source_url_var.get(),
                "ceviri_inceleme_notu": note_text,
                "not": note_text,
            },
        )

    def reload_selected_record(self) -> None:
        if not self.selected_original_key:
            return
        self.app.reload_data(select_key=self.selected_original_key)
        self.refresh_records()

    def open_selected_in_main_app(self) -> None:
        if not self.selected_record:
            return
        self.app.apply_search_term(self.selected_record.get("almanca", ""))
        self.app.focus_force()

    def save_selected_record(self) -> None:
        if not self.selected_record or not self.selected_original_key:
            return
        payload = self.build_payload()
        validation = validate_user_entry(payload)
        if validation.get("status") == "error":
            messagebox.showerror("Veri Seti Editörü", validation.get("note", "Kayıt doğrulanamadı."), parent=self)
            return
        saved = save_dataset_editor_record(self.selected_storage_source, self.selected_original_key, payload)
        self.selected_original_key = record_key(saved)
        self.app.reload_data(select_key=self.selected_original_key)
        self.refresh_records()
        self.status_var.set("Kayıt veri dosyasına kaydedildi.")
        messagebox.showinfo("Veri Seti Editörü", "Kayıt güncellendi.", parent=self)


class UrlImportDialog(tk.Toplevel):
    def __init__(self, app: "DesktopDictionaryApp", initial_url: str = "") -> None:
        super().__init__(app)
        self.app = app
        self.title("URL'den Kelime Aktar")
        self.transient(app)
        self.grab_set()
        self.geometry("1040x720")
        self.minsize(920, 640)

        self.url_var = tk.StringVar(value=initial_url.strip())
        self.status_var = tk.StringVar(
            value="Bir URL girin. Sayfadaki görünür metin taranır, sözlükte olmayan kelimeler aşağıda hazırlanır."
        )
        self.summary_var = tk.StringVar(value="Henüz tarama yapılmadı.")
        self.word_var = tk.StringVar(value="-")
        self.source_var = tk.StringVar(value="Kaynak önerisi: -")
        self.frequency_var = tk.StringVar(value="Metinde tekrar: -")
        self.include_var = tk.BooleanVar(value=True)
        self.translation_var = tk.StringVar()
        self.pos_var = tk.StringVar(value="belirsiz")
        self.article_var = tk.StringVar(value="")
        self.form_note_var = tk.StringVar(value="Çeviri ve tür alanlarını kaydetmeden önce düzenleyebilirsiniz.")

        self.scan_button: ttk.Button | None = None
        self.save_button: ttk.Button | None = None
        self.tree: ttk.Treeview | None = None
        self.translation_entry: ttk.Entry | None = None
        self.include_check: ttk.Checkbutton | None = None
        self.is_scanning = False
        self.form_loading = False
        self.current_candidate_id: str | None = None
        self.candidates: list[dict] = []
        self.candidate_map: dict[str, dict] = {}

        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=3)
        frame.columnconfigure(1, weight=2)
        frame.rowconfigure(2, weight=1)

        ttk.Label(frame, text="URL'den kelime aktar", style="DialogTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            frame,
            text="Aşağıdaki kelimeler sözlükte yok. İsterseniz çeviri ve tür bilgisini düzenleyip topluca ekleyebilirsiniz.",
            style="Muted.TLabel",
            wraplength=920,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 14))

        url_row = ttk.Frame(frame)
        url_row.grid(row=2, column=0, columnspan=2, sticky="ew")
        url_row.columnconfigure(0, weight=1)
        url_entry = ttk.Entry(url_row, textvariable=self.url_var)
        url_entry.grid(row=0, column=0, sticky="ew")
        url_entry.bind("<Return>", lambda _event: self.start_scan())
        self.scan_button = ttk.Button(url_row, text="URL'yi Tara", style="Primary.TButton", command=self.start_scan)
        self.scan_button.grid(row=0, column=1, padx=(10, 0))

        ttk.Label(frame, textvariable=self.status_var, style="Meta.TLabel", wraplength=920, justify="left").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(10, 12)
        )

        list_box = ttk.LabelFrame(frame, text="Yeni kelimeler", padding=12)
        list_box.grid(row=4, column=0, sticky="nsew", padx=(0, 10))
        list_box.columnconfigure(0, weight=1)
        list_box.rowconfigure(1, weight=1)
        ttk.Label(list_box, textvariable=self.summary_var, style="Muted.TLabel", wraplength=520, justify="left").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )
        tree_wrap = ttk.Frame(list_box)
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_wrap,
            columns=("word", "translation", "pos", "source", "count", "state"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("word", text="Almanca")
        self.tree.heading("translation", text="Türkçe öneri")
        self.tree.heading("pos", text="Tür")
        self.tree.heading("source", text="Kaynak")
        self.tree.heading("count", text="Tekrar")
        self.tree.heading("state", text="Durum")
        self.tree.column("word", width=160, anchor="w")
        self.tree.column("translation", width=210, anchor="w")
        self.tree.column("pos", width=90, anchor="w")
        self.tree.column("source", width=120, anchor="w")
        self.tree.column("count", width=70, anchor="center")
        self.tree.column("state", width=80, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        editor = ttk.LabelFrame(frame, text="Seçili kelime", padding=12)
        editor.grid(row=4, column=1, sticky="nsew")
        editor.columnconfigure(1, weight=1)

        ttk.Label(editor, text="Almanca", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Label(editor, textvariable=self.word_var, style="Section.TLabel", wraplength=280, justify="left").grid(
            row=0, column=1, sticky="w", pady=6
        )
        ttk.Label(editor, text="Türkçe", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 8))
        self.translation_entry = ttk.Entry(editor, textvariable=self.translation_var)
        self.translation_entry.grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(editor, text="Tür", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 8))
        self.pos_combo = ttk.Combobox(editor, textvariable=self.pos_var, values=IMPORT_POS_CHOICES, state="readonly")
        self.pos_combo.grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(editor, text="Artikel", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=6, padx=(0, 8))
        self.article_combo = ttk.Combobox(editor, textvariable=self.article_var, values=["", "der", "die", "das"], state="readonly")
        self.article_combo.grid(row=3, column=1, sticky="ew", pady=6)
        self.include_check = ttk.Checkbutton(editor, text="Bu kelimeyi aktar", variable=self.include_var, command=self.update_current_candidate)
        self.include_check.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 4))

        info_box = ttk.Frame(editor, style="SoftPanel.TFrame", padding=12)
        info_box.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        info_box.columnconfigure(0, weight=1)
        ttk.Label(info_box, textvariable=self.source_var, style="Section.TLabel", wraplength=280, justify="left").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(info_box, textvariable=self.frequency_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(info_box, textvariable=self.form_note_var, style="Muted.TLabel", wraplength=280, justify="left").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )

        footer = ttk.Frame(frame, padding=(0, 16, 0, 0))
        footer.grid(row=5, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="İptal", command=self.destroy).grid(row=0, column=1)
        self.save_button = ttk.Button(footer, text="Seçilenleri Sözlüğe Aktar", style="Primary.TButton", command=self.save_selected)
        self.save_button.grid(row=0, column=2, padx=(8, 0))

        for variable in [self.translation_var, self.pos_var, self.article_var]:
            variable.trace_add("write", self.on_editor_change)
        self.pos_var.trace_add("write", self.on_pos_change)

        self.set_editor_state(False)
        if initial_url.strip():
            self.after(120, self.start_scan)

    def bring_to_front(self) -> None:
        self.lift()
        self.focus_force()

    def destroy(self) -> None:
        self.candidates.clear()
        self.candidate_map.clear()
        self.current_candidate_id = None
        if getattr(self.app, "import_dialog", None) is self:
            self.app.import_dialog = None
        super().destroy()

    def set_initial_url(self, url: str) -> None:
        self.url_var.set(url.strip())

    def set_editor_state(self, enabled: bool) -> None:
        state = "readonly" if enabled else "disabled"
        entry_state = "normal" if enabled else "disabled"
        self.pos_combo.configure(state=state)
        self.article_combo.configure(state=state if self.pos_var.get() == "isim" else "disabled")
        if self.translation_entry is not None:
            self.translation_entry.configure(state=entry_state)
        if self.include_check is not None:
            self.include_check.configure(state="normal" if enabled else "disabled")
        if self.tree is not None:
            if enabled:
                self.tree.state(("!disabled",))
            else:
                self.tree.state(("disabled",))
        if self.save_button is not None:
            self.save_button.configure(state="normal" if enabled and self.candidates else "disabled")

    def start_scan(self) -> None:
        if self.is_scanning:
            return
        raw_url = self.url_var.get().strip()
        if not raw_url:
            messagebox.showerror("Kelime Aktar", "Önce bir URL girin.", parent=self)
            return
        if not re.match(r"^https?://", raw_url, flags=re.IGNORECASE):
            raw_url = f"https://{raw_url}"
            self.url_var.set(raw_url)

        self.is_scanning = True
        self.candidates = []
        self.candidate_map = {}
        self.current_candidate_id = None
        if self.tree is not None:
            self.tree.delete(*self.tree.get_children())
        self.word_var.set("-")
        self.translation_var.set("")
        self.pos_var.set("belirsiz")
        self.article_var.set("")
        self.include_var.set(False)
        self.source_var.set("Kaynak önerisi: -")
        self.frequency_var.set("Metinde tekrar: -")
        self.set_editor_state(False)
        self.status_var.set("URL taranıyor. Görünür metin çekiliyor ve yeni kelimeler hazırlanıyor...")
        self.summary_var.set("Tarama sürüyor...")
        if self.scan_button is not None:
            self.scan_button.configure(state="disabled")
        if self.save_button is not None:
            self.save_button.configure(state="disabled")
        existing_terms = self.app.get_existing_german_terms()
        worker = threading.Thread(target=self._scan_worker, args=(raw_url, existing_terms), daemon=True)
        worker.start()

    def _scan_worker(self, url: str, existing_terms: set[str]) -> None:
        try:
            final_url, candidates = collect_url_import_candidates(url, existing_terms)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            self.after(0, lambda: self.on_scan_failed(str(exc)))
            return
        except Exception as exc:  # pragma: no cover - defensive UI fallback
            self.after(0, lambda: self.on_scan_failed(f"Beklenmeyen hata: {exc}"))
            return
        self.after(0, lambda: self.on_scan_complete(final_url, candidates))

    def on_scan_failed(self, message: str) -> None:
        self.is_scanning = False
        if not self.winfo_exists():
            return
        if self.scan_button is not None:
            self.scan_button.configure(state="normal")
        self.status_var.set(f"Tarama başarısız oldu. {message}")
        self.summary_var.set("Yeni kelime hazırlanamadı.")

    def on_scan_complete(self, final_url: str, candidates: list[dict]) -> None:
        self.is_scanning = False
        if not self.winfo_exists():
            return
        if self.scan_button is not None:
            self.scan_button.configure(state="normal")

        self.candidates = []
        self.candidate_map = {}
        self.current_candidate_id = None
        if self.tree is not None:
            self.tree.delete(*self.tree.get_children())

        for candidate in candidates:
            candidate["kaynak_url"] = final_url
            candidate["not"] = f"URL'den aktarıldı: {final_url}"
            self.candidates.append(candidate)
            self.candidate_map[candidate["id"]] = candidate
            if self.tree is not None:
                self.tree.insert(
                    "",
                    "end",
                    iid=candidate["id"],
                    values=self.row_values(candidate),
                )

        if not candidates:
            self.word_var.set("-")
            self.translation_var.set("")
            self.pos_var.set("belirsiz")
            self.article_var.set("")
            self.include_var.set(False)
            self.source_var.set("Kaynak önerisi: -")
            self.frequency_var.set("Metinde tekrar: -")
            self.status_var.set("Yeni kelime bulunamadı. Sayfadaki kelimeler zaten sözlükte olabilir veya görünür metin çok sınırlıdır.")
            self.summary_var.set("Taranan sayfada sözlüğe eklenecek yeni kelime çıkmadı.")
            self.set_editor_state(False)
            return

        selected_count = sum(1 for item in candidates if item.get("ekle"))
        self.status_var.set(f"{len(candidates)} yeni kelime bulundu. Çevirileri düzenleyip ardından sözlüğe aktarabilirsiniz.")
        self.summary_var.set(f"{len(candidates)} yeni kelime hazır. Şu an {selected_count} tanesi aktarılacak olarak işaretli.")
        self.set_editor_state(True)
        if self.save_button is not None:
            self.save_button.configure(state="normal")
        if self.tree is not None:
            first_id = candidates[0]["id"]
            self.tree.selection_set(first_id)
            self.tree.focus(first_id)
            self.tree.see(first_id)
        self.load_candidate(candidates[0]["id"])

    def row_values(self, candidate: dict) -> tuple:
        return (
            candidate.get("almanca", ""),
            candidate.get("turkce", ""),
            candidate.get("tur", ""),
            candidate.get("kaynak_etiketi", ""),
            candidate.get("frekans", 0),
            "Ekle" if candidate.get("ekle", True) else "Atla",
        )

    def on_tree_select(self, _event=None) -> None:
        if self.tree is None:
            return
        selection = self.tree.selection()
        if not selection:
            return
        self.load_candidate(selection[0])

    def load_candidate(self, candidate_id: str) -> None:
        candidate = self.candidate_map.get(candidate_id)
        if not candidate:
            return
        self.current_candidate_id = candidate_id
        self.form_loading = True
        self.word_var.set(candidate.get("almanca", "-"))
        self.translation_var.set(candidate.get("turkce", ""))
        self.pos_var.set(candidate.get("tur", "belirsiz") or "belirsiz")
        self.article_var.set(candidate.get("artikel", ""))
        self.include_var.set(bool(candidate.get("ekle", True)))
        self.source_var.set(f"Kaynak önerisi: {candidate.get('kaynak_etiketi', 'Öneri yok')}")
        self.frequency_var.set(f"Metinde tekrar: {candidate.get('frekans', 0)}")
        if candidate.get("ornek_almanca"):
            self.form_note_var.set("Kaynak sayfadaki gerçek kullanım cümlesi örnekler bölümüne kaydedilecek.")
        elif candidate.get("kaynak_etiketi") == "Öneri yok":
            self.form_note_var.set("Bu kelime için otomatik çeviri bulunamadı. İsterseniz Türkçesini elle yazıp kaydedebilirsiniz.")
        else:
            self.form_note_var.set("Çeviri yerel kaynaktan önerildi. Kaydetmeden önce dilediğiniz gibi düzenleyebilirsiniz.")
        self.on_pos_change()
        self.form_loading = False

    def on_editor_change(self, *_args) -> None:
        if self.form_loading:
            return
        self.update_current_candidate()

    def on_pos_change(self, *_args) -> None:
        is_noun = self.pos_var.get() == "isim"
        if not is_noun and self.article_var.get():
            self.article_var.set("")
        self.article_combo.configure(state="readonly" if is_noun and self.current_candidate_id else "disabled")

    def update_current_candidate(self) -> None:
        candidate = self.candidate_map.get(self.current_candidate_id or "")
        if not candidate:
            return
        candidate["turkce"] = self.translation_var.get().strip()
        candidate["tur"] = self.pos_var.get().strip() or "belirsiz"
        candidate["artikel"] = self.article_var.get().strip() if candidate["tur"] == "isim" else ""
        candidate["ekle"] = bool(self.include_var.get())
        if self.tree is not None:
            self.tree.item(candidate["id"], values=self.row_values(candidate))
        selected_count = sum(1 for item in self.candidates if item.get("ekle"))
        self.summary_var.set(f"{len(self.candidates)} yeni kelime hazır. Şu an {selected_count} tanesi aktarılacak olarak işaretli.")

    def save_selected(self) -> None:
        selected = [item for item in self.candidates if item.get("ekle")]
        if not selected:
            messagebox.showinfo("Kelime Aktar", "Aktarılacak kelime seçili değil.", parent=self)
            return

        first_key = None
        for item in selected:
            payload = {
                "almanca": item.get("almanca", "").strip(),
                "artikel": item.get("artikel", "").strip(),
                "turkce": item.get("turkce", "").strip(),
                "tur": item.get("tur", "").strip(),
                "aciklama_turkce": "",
                "ornek_almanca": item.get("ornek_almanca", ""),
                "ornek_turkce": item.get("ornek_turkce", ""),
                "ornekler": item.get("ornekler", []),
                "not": item.get("not", ""),
                "kaynak_url": item.get("kaynak_url", ""),
            }
            validation = validate_user_entry(payload)
            if validation.get("status") == "error":
                if self.tree is not None:
                    self.tree.selection_set(item["id"])
                    self.tree.focus(item["id"])
                    self.tree.see(item["id"])
                self.load_candidate(item["id"])
                messagebox.showerror("Kelime Aktar", validation.get("note", "Bu kayıt kaydedilemedi."), parent=self)
                return

        for item in selected:
            saved = save_user_entry(
                {
                    "almanca": item.get("almanca", "").strip(),
                    "artikel": item.get("artikel", "").strip(),
                    "turkce": item.get("turkce", "").strip(),
                    "tur": item.get("tur", "").strip(),
                    "aciklama_turkce": "",
                    "ornek_almanca": item.get("ornek_almanca", ""),
                    "ornek_turkce": item.get("ornek_turkce", ""),
                    "ornekler": item.get("ornekler", []),
                    "not": item.get("not", ""),
                    "kaynak_url": item.get("kaynak_url", ""),
                }
            )
            if first_key is None:
                first_key = record_key(saved)

        self.app.reload_data(select_key=first_key)
        messagebox.showinfo(
            "Kelime Aktar",
            f"{len(selected)} kelime sözlüğe kalıcı olarak eklendi. Uygulama açıkken hemen kullanılabilir.",
            parent=self,
        )
        self.destroy()


class MiniQuizDialog(tk.Toplevel):
    def __init__(self, app: "DesktopDictionaryApp") -> None:
        super().__init__(app)
        self.app = app
        self.title("Mini Quiz")
        self.transient(app)
        self.geometry("760x560")
        self.minsize(700, 520)

        self.quiz_pool = self.build_quiz_pool()
        self.question_limit = min(MINI_QUIZ_QUESTION_COUNT, len(self.quiz_pool))
        self.pending_records: list[dict] = []
        self.current_question: dict | None = None
        self.current_question_number = 0
        self.answered_count = 0
        self.score = 0
        self.answer_locked = False

        self.progress_var = tk.StringVar(value="Mini quiz hazırlanıyor...")
        self.score_var = tk.StringVar(value="Puan: 0")
        self.word_var = tk.StringVar(value="Kelime havuzu hazırlanıyor")
        self.meta_var = tk.StringVar(value="")
        self.prompt_var = tk.StringVar(value="En uygun Türkçe karşılığı seçin.")
        self.feedback_var = tk.StringVar(
            value="Sözlükteki mevcut kayıtlarla kısa bir alıştırma yapabilirsiniz. Her tur 5 soru hazırlar."
        )

        self.option_buttons: list[ttk.Button] = []
        self.next_button: ttk.Button | None = None
        self.search_button: ttk.Button | None = None

        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        ttk.Label(frame, text="Mini Quiz", style="DialogTitle.TLabel").grid(row=0, column=0, sticky="w")
        header = ttk.Frame(frame, style="SoftPanel.TFrame", padding=14)
        header.grid(row=1, column=0, sticky="ew", pady=(10, 12))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)
        ttk.Label(header, textvariable=self.progress_var, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.score_var, style="Muted.TLabel").grid(row=0, column=1, sticky="e", padx=(12, 0))

        content = ttk.Frame(frame)
        content.grid(row=2, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)

        prompt_box = ttk.Frame(content, style="SoftPanel.TFrame", padding=18)
        prompt_box.grid(row=0, column=0, sticky="ew")
        prompt_box.columnconfigure(0, weight=1)
        ttk.Label(prompt_box, textvariable=self.word_var, style="HeroTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            prompt_box,
            textvariable=self.meta_var,
            style="Meta.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(
            prompt_box,
            textvariable=self.prompt_var,
            style="Section.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(16, 0))

        options_box = ttk.LabelFrame(content, text="Cevaplar", padding=14)
        options_box.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        options_box.columnconfigure(0, weight=1)
        for index in range(MINI_QUIZ_OPTION_COUNT):
            button = ttk.Button(
                options_box,
                text=f"{self.option_label(index)} -",
                style="QuizOption.TButton",
                command=lambda value=index: self.answer_current_question(value),
            )
            button.grid(row=index, column=0, sticky="ew", pady=(0, 10))
            self.option_buttons.append(button)

        ttk.Label(
            frame,
            textvariable=self.feedback_var,
            style="Muted.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(14, 0))

        footer = ttk.Frame(frame, padding=(0, 16, 0, 0))
        footer.grid(row=4, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.search_button = ttk.Button(footer, text="Bu Kelimeyi Ara", command=self.search_current_word)
        self.search_button.grid(row=0, column=1)
        ttk.Button(footer, text="Baştan Başlat", command=self.start_quiz).grid(row=0, column=2, padx=(8, 0))
        self.next_button = ttk.Button(footer, text="Sonraki Soru", command=self.show_next_question)
        self.next_button.grid(row=0, column=3, padx=(8, 0))
        ttk.Button(footer, text="Kapat", command=self.destroy).grid(row=0, column=4, padx=(8, 0))

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.start_quiz()

    def bring_to_front(self) -> None:
        self.lift()
        self.focus_force()

    def destroy(self) -> None:
        self.pending_records.clear()
        self.current_question = None
        if getattr(self.app, "quiz_dialog", None) is self:
            self.app.quiz_dialog = None
        super().destroy()

    def option_label(self, index: int) -> str:
        return f"{chr(ord('A') + index)})"

    def build_quiz_pool(self) -> list[dict]:
        pool = []
        seen_keys: set[tuple[str, str]] = set()
        for record in self.app.records:
            word = str(record.get("_word") or record.get("almanca", "")).strip()
            translation = str(record.get("turkce", "")).strip()
            if not word or not translation or translation == "-":
                continue
            key = (normalize_text(word), normalize_text(translation))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            pool.append(record)
        return pool

    def start_quiz(self) -> None:
        if len(self.quiz_pool) < MINI_QUIZ_OPTION_COUNT:
            self.progress_var.set("Mini quiz kullanılamıyor")
            self.word_var.set("Yeterli kayıt yok")
            self.meta_var.set("")
            self.prompt_var.set("Quiz için en az dört farklı Türkçe karşılığı olan kayıt gerekiyor.")
            self.feedback_var.set("Sözlüğe birkaç kayıt daha ekledikten sonra bu özelliği kullanabilirsiniz.")
            self.disable_option_buttons()
            if self.next_button is not None:
                self.next_button.configure(state="disabled")
            if self.search_button is not None:
                self.search_button.configure(state="disabled")
            return

        self.pending_records = random.sample(self.quiz_pool, len(self.quiz_pool))
        self.current_question = None
        self.current_question_number = 0
        self.answered_count = 0
        self.score = 0
        self.score_var.set("Puan: 0")
        self.feedback_var.set("Şıklardan birini seçin. Her sorudan sonra doğru cevabı göreceksiniz.")
        self.show_next_question(force=True)

    def disable_option_buttons(self) -> None:
        for index, button in enumerate(self.option_buttons):
            button.configure(text=f"{self.option_label(index)} -", state="disabled", style="QuizOption.TButton")

    def build_options_for_record(self, record: dict) -> list[str]:
        correct_answer = str(record.get("turkce", "")).strip()
        correct_key = normalize_text(correct_answer)
        if not correct_answer:
            return []

        same_pos = [item for item in self.quiz_pool if item is not record and item.get("tur") == record.get("tur")]
        other_items = [item for item in self.quiz_pool if item is not record and item.get("tur") != record.get("tur")]
        random.shuffle(same_pos)
        random.shuffle(other_items)

        choices = [correct_answer]
        seen = {correct_key}
        for group in [same_pos, other_items]:
            for item in group:
                translation = str(item.get("turkce", "")).strip()
                translation_key = normalize_text(translation)
                if not translation or translation_key in seen:
                    continue
                seen.add(translation_key)
                choices.append(translation)
                if len(choices) == MINI_QUIZ_OPTION_COUNT:
                    random.shuffle(choices)
                    return choices
        return []

    def show_next_question(self, force: bool = False) -> None:
        if self.current_question and not self.answer_locked and not force:
            self.feedback_var.set("Önce bu soruya cevap verin. Sonra sonraki soruya geçebilirsiniz.")
            return

        if self.answered_count >= self.question_limit:
            self.show_final_state()
            return

        while self.pending_records:
            record = self.pending_records.pop(0)
            options = self.build_options_for_record(record)
            if not options:
                continue
            self.current_question_number = self.answered_count + 1
            self.current_question = {"record": record, "options": options}
            self.answer_locked = False
            self.progress_var.set(f"Soru {self.current_question_number} / {self.question_limit}")
            self.score_var.set(f"Puan: {self.score}")
            self.word_var.set(record.get("_word") or record.get("almanca", "-"))
            meta_line = record.get("_meta_line", "")
            self.meta_var.set(meta_line if meta_line else "Tür veya kaynak bilgisi yok.")
            self.prompt_var.set("Bu Almanca kelimenin en uygun Türkçe karşılığı hangisi?")
            self.feedback_var.set("Şıklardan birini seçin.")
            for index, button in enumerate(self.option_buttons):
                option_text = options[index]
                button.configure(
                    text=f"{self.option_label(index)} {option_text}",
                    state="normal",
                    style="QuizOption.TButton",
                    command=lambda value=index: self.answer_current_question(value),
                )
            if self.next_button is not None:
                self.next_button.configure(text="Sonraki Soru", state="disabled")
            if self.search_button is not None:
                self.search_button.configure(state="normal")
            return

        self.show_final_state()

    def answer_current_question(self, option_index: int) -> None:
        if self.answer_locked or not self.current_question:
            return
        options = self.current_question["options"]
        if option_index >= len(options):
            return
        record = self.current_question["record"]
        correct_answer = str(record.get("turkce", "")).strip()
        selected_answer = options[option_index]
        self.answer_locked = True
        self.answered_count += 1

        is_correct = normalize_text(selected_answer) == normalize_text(correct_answer)
        if is_correct:
            self.score += 1
            self.feedback_var.set("Doğru. İsterseniz bu kelimeyi ana ekranda açabilir veya sonraki soruya geçebilirsiniz.")
        else:
            self.feedback_var.set(f"Yanlış. Doğru cevap: {correct_answer}")

        self.score_var.set(f"Puan: {self.score}")
        correct_key = normalize_text(correct_answer)
        selected_key = normalize_text(selected_answer)
        for index, button in enumerate(self.option_buttons):
            option_text = options[index]
            option_key = normalize_text(option_text)
            prefix = self.option_label(index)
            style_name = "QuizOption.TButton"
            if option_key == correct_key:
                prefix = "Doğru"
                style_name = "QuizCorrect.TButton"
            elif option_key == selected_key and option_key != correct_key:
                prefix = "Seçtiğin"
                style_name = "QuizWrong.TButton"
            button.configure(text=f"{prefix} {option_text}", state="disabled", style=style_name)

        if self.next_button is not None:
            next_label = "Sonucu Gör" if self.answered_count >= self.question_limit else "Sonraki Soru"
            self.next_button.configure(text=next_label, state="normal")

    def show_final_state(self) -> None:
        self.current_question = None
        self.answer_locked = True
        self.progress_var.set("Mini quiz tamamlandı")
        self.score_var.set(f"Puan: {self.score} / {max(self.answered_count, 1)}")
        self.word_var.set("Kısa tur bitti")
        self.meta_var.set("İsterseniz hemen yeni bir tur başlatabilirsiniz.")
        self.prompt_var.set("Quiz menüden açılan hafif bir pratik alanı olarak kalır; ana ekranı kalabalıklaştırmaz.")
        self.feedback_var.set(
            f"{self.answered_count} soruda {self.score} doğru yaptınız. Yeni bir tur için 'Baştan Başlat' düğmesini kullanın."
        )
        self.disable_option_buttons()
        if self.search_button is not None:
            self.search_button.configure(state="disabled")
        if self.next_button is not None:
            self.next_button.configure(text="Sonraki Soru", state="disabled")

    def search_current_word(self) -> None:
        record = self.current_question["record"] if self.current_question else None
        if not record:
            return
        self.app.apply_search_term(record.get("almanca", ""))
        self.app.lift()
        self.app.focus_force()


class TutorialDialog(tk.Toplevel):
    def __init__(self, app: "DesktopDictionaryApp", tutorial_payload: dict, initial_section_id: str | None = None) -> None:
        super().__init__(app)
        self.app = app
        self.payload = tutorial_payload if isinstance(tutorial_payload, dict) else {}
        self.sections = [item for item in self.payload.get("sections", []) if isinstance(item, dict)]
        self.section_index_by_id = {
            str(item.get("id", "")).strip(): index for index, item in enumerate(self.sections) if str(item.get("id", "")).strip()
        }
        self.current_index = 0
        self.summary_var = tk.StringVar(value="")
        self.progress_var = tk.StringVar(value="")

        self.title(str(self.payload.get("title", "Program Tutoriali")))
        self.geometry("1020x720")
        self.minsize(860, 620)
        self.transient(app)
        self.configure(bg=app.active_palette["bg"])
        self.app.apply_window_chrome(self, self.app.active_palette)

        wrapper = ttk.Frame(self, style="Panel.TFrame", padding=16)
        wrapper.pack(fill="both", expand=True)
        wrapper.columnconfigure(0, weight=0)
        wrapper.columnconfigure(1, weight=1)
        wrapper.rowconfigure(1, weight=1)

        header = ttk.Frame(wrapper, style="Panel.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=str(self.payload.get("title", "Program Tutoriali")), style="DialogTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text=str(
                self.payload.get(
                    "intro",
                    "Istediginiz bolumden baslayin. Sol listeden bir baslik secin, alttaki dugmelerle sira sira ilerleyin.",
                )
            ),
            style="Muted.TLabel",
            wraplength=780,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        sidebar = ttk.Frame(wrapper, style="SoftPanel.TFrame", padding=12)
        sidebar.grid(row=1, column=0, sticky="nsw", pady=(14, 0), padx=(0, 14))
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(1, weight=1)
        ttk.Label(sidebar, text="Bolumler", style="Section.TLabel").grid(row=0, column=0, sticky="w")

        list_wrap = ttk.Frame(sidebar, style="ReadingCard.TFrame")
        list_wrap.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)
        self.section_listbox = tk.Listbox(list_wrap, exportselection=False, activestyle="none", width=34, height=18)
        self.section_listbox.grid(row=0, column=0, sticky="nsew")
        list_scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.section_listbox.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.section_listbox.configure(yscrollcommand=list_scroll.set)
        self.section_listbox.bind("<<ListboxSelect>>", self.on_section_select)
        self.section_listbox.bind("<Double-Button-1>", self.on_section_activate)
        self.section_listbox.bind("<Return>", self.on_section_activate)

        for index, section in enumerate(self.sections, start=1):
            title = str(section.get("title", f"Bolum {index}")).strip()
            summary = str(section.get("summary", "")).strip()
            list_label = f"{index}. {title}" if not summary else f"{index}. {title} - {summary}"
            self.section_listbox.insert("end", list_label)

        content_wrap = ttk.Frame(wrapper, style="Panel.TFrame")
        content_wrap.grid(row=1, column=1, sticky="nsew", pady=(14, 0))
        content_wrap.columnconfigure(0, weight=1)
        content_wrap.rowconfigure(2, weight=1)

        self.section_title_label = ttk.Label(content_wrap, text="", style="PanelTitle.TLabel")
        self.section_title_label.grid(row=0, column=0, sticky="w")
        ttk.Label(content_wrap, textvariable=self.summary_var, style="Muted.TLabel", wraplength=620, justify="left").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )

        text_wrap = ttk.Frame(content_wrap, style="ReadingCard.TFrame")
        text_wrap.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        text_wrap.columnconfigure(0, weight=1)
        text_wrap.rowconfigure(0, weight=1)
        self.content_text = tk.Text(text_wrap, wrap="word", relief="flat", padx=16, pady=16)
        self.content_text.grid(row=0, column=0, sticky="nsew")
        content_scroll = ttk.Scrollbar(text_wrap, orient="vertical", command=self.content_text.yview)
        content_scroll.grid(row=0, column=1, sticky="ns")
        self.content_text.configure(yscrollcommand=content_scroll.set)

        footer = ttk.Frame(wrapper, style="Panel.TFrame")
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        footer.columnconfigure(1, weight=1)
        self.prev_button = ttk.Button(footer, text="Onceki Bolum", command=lambda: self.step_section(-1))
        self.prev_button.grid(row=0, column=0, sticky="w")
        ttk.Label(footer, textvariable=self.progress_var, style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.next_button = ttk.Button(footer, text="Sonraki Bolum", command=lambda: self.step_section(1))
        self.next_button.grid(row=0, column=2, sticky="e")
        ttk.Button(footer, text="Kapat", command=self.destroy).grid(row=0, column=3, sticky="e", padx=(8, 0))

        self.content_text.configure(
            bg=self.app.active_palette["surface_soft"],
            fg=self.app.active_palette["ink"],
            highlightbackground=self.app.active_palette["line"],
            highlightcolor=self.app.active_palette["accent"],
            insertbackground=self.app.active_palette["accent"],
            selectbackground=self.app.active_palette["accent_soft"],
            selectforeground=self.app.active_palette["ink"],
            highlightthickness=1,
            bd=0,
        )
        self.section_listbox.configure(
            bg=self.app.active_palette["surface"],
            fg=self.app.active_palette["ink"],
            selectbackground=self.app.active_palette["accent_soft"],
            selectforeground=self.app.active_palette["ink"],
            highlightbackground=self.app.active_palette["line"],
            highlightcolor=self.app.active_palette["accent"],
            highlightthickness=1,
            bd=0,
        )

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Destroy>", self.on_destroy, add=True)
        self.show_section(section_id=initial_section_id)

    def on_destroy(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        if getattr(self.app, "tutorial_dialog", None) is self:
            self.app.tutorial_dialog = None

    def on_section_select(self, _event=None) -> None:
        selection = self.section_listbox.curselection()
        if not selection:
            return
        self.show_section(index=int(selection[0]))

    def on_section_activate(self, _event=None) -> str:
        self.on_section_select()
        return "break"

    def step_section(self, step: int) -> None:
        if not self.sections:
            return
        self.show_section(index=max(0, min(len(self.sections) - 1, self.current_index + step)))

    def show_section(self, section_id: str | None = None, index: int | None = None) -> None:
        if not self.sections:
            self.section_title_label.configure(text="Tutorial bulunamadi")
            self.summary_var.set("Tutorial dosyasi bos veya gecersiz.")
            self.content_text.configure(state="normal")
            self.content_text.delete("1.0", "end")
            self.content_text.insert("1.0", "Kullanilabilir tutorial icerigi bulunamadi.")
            self.content_text.configure(state="disabled")
            self.prev_button.configure(state="disabled")
            self.next_button.configure(state="disabled")
            self.progress_var.set("")
            return
        if index is None:
            index = self.section_index_by_id.get(str(section_id or "").strip(), 0)
        index = max(0, min(len(self.sections) - 1, int(index)))
        self.current_index = index
        section = self.sections[index]
        self.section_title_label.configure(text=str(section.get("title", f"Bolum {index + 1}")))
        self.summary_var.set(str(section.get("summary", "")).strip())
        self.progress_var.set(f"Bolum {index + 1} / {len(self.sections)}")
        self.content_text.configure(state="normal")
        self.content_text.delete("1.0", "end")
        self.content_text.insert("1.0", str(section.get("body", "")).strip())
        self.content_text.configure(state="disabled")
        self.content_text.yview_moveto(0)
        self.section_listbox.selection_clear(0, "end")
        self.section_listbox.selection_set(index)
        self.section_listbox.activate(index)
        self.section_listbox.see(index)
        self.prev_button.configure(state="disabled" if index == 0 else "normal")
        self.next_button.configure(state="disabled" if index >= len(self.sections) - 1 else "normal")


class DesktopDictionaryApp(tk.Tk):
    def __init__(self) -> None:
        try:
            windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
        except Exception:
            pass
        super().__init__()
        self.title("Almanca-Türkçe Sözlük")
        self.minsize(1240, 820)

        self.settings = self.load_settings()
        self.geometry(self.settings.get("window_geometry", DEFAULT_SETTINGS["window_geometry"]))
        if self.settings.get("start_maximized", True) or self.settings.get("window_state") == "zoomed":
            self.after(0, lambda: self.state("zoomed"))

        self.records: list[dict] = []
        self.filtered_records: list[dict] = []
        self.current_record: dict | None = None
        self.source_counts: dict[str, int] = {}
        self.pos_values: list[str] = []
        self.category_values: list[str] = []
        self.source_values: list[str] = []
        self.tree_keys: dict[str, tuple[str, str, str]] = {}
        self.current_source_urls: list[str] = []
        self.current_translation_sources: list[dict] = []
        self.compact_meaning_overviews: list[dict] = []
        self.definition_cache: dict[tuple[str, str], dict] = {}
        self.online_definition_cache: dict[tuple[str, str], dict] = {}
        self.gender_form_cache: dict[str, dict] = {}
        self.gender_form_pending_terms: set[str] = set()
        self.gender_form_result_queue: queue.Queue[tuple[str, tuple[str, str, str] | None]] = queue.Queue()
        self.local_translation_result_queue: queue.Queue[tuple[str, dict]] = queue.Queue()
        self.local_translation_pending_terms: set[str] = set()
        self.record_image_result_queue: queue.Queue[tuple[str, dict]] = queue.Queue()
        self.record_image_pending_terms: set[str] = set()
        self.current_local_translation_text = ""
        self.current_record_image_key = ""
        self.noun_record_index: dict[tuple[str, str], dict] = {}
        self.search_select_job: str | None = None
        self.search_refresh_job: str | None = None
        self.art_reload_job: str | None = None
        self.window_layout_job: str | None = None
        self.replace_search_on_next_key = False
        self.search_suggestion_records: list[dict] = []
        self.search_suggestions_paused = False
        self._updating_art_visibility = False
        self._applying_art_sidebar_width = False
        self.left_sidebar_main_image: tk.PhotoImage | None = None
        self.left_sidebar_accent_image: tk.PhotoImage | None = None
        self.right_sidebar_main_image: tk.PhotoImage | None = None
        self.right_sidebar_accent_image: tk.PhotoImage | None = None
        self.app_icon_image: tk.PhotoImage | None = None
        self.hero_bg_image: tk.PhotoImage | None = None
        self.search_bg_image: tk.PhotoImage | None = None
        self.results_bg_image: tk.PhotoImage | None = None
        self.leaves_bg_image: tk.PhotoImage | None = None
        self.record_image_photo: tk.PhotoImage | None = None
        self.record_image_preview_photo: tk.PhotoImage | None = None
        self.record_image_preview_dialog: tk.Toplevel | None = None
        self.current_record_image_path = ""
        self.settings_dialog: SettingsDialog | None = None
        self.import_dialog: UrlImportDialog | None = None
        self.parallel_text_import_dialog: tk.Toplevel | None = None
        self.quiz_dialog: MiniQuizDialog | None = None
        self.entry_help_dialog: tk.Toplevel | None = None
        self.tutorial_dialog: TutorialDialog | None = None
        self.dataset_editor_dialog: DatasetEditorDialog | None = None

        initial_search = self.settings.get("last_search", "") if self.settings.get("remember_search", True) else ""
        self.search_var = tk.StringVar(value=initial_search)
        self.result_summary_var = tk.StringVar(value="Sözlük yükleniyor...")
        self.search_status_var = tk.StringVar(value="Almanca kelime, Türkçe karşılık ya da kaynak adı yazarak başlayın.")
        self.local_translation_var = tk.StringVar(value="Almanca kelime veya cümle yazınca LibreTranslate çevirisi burada görünür.")
        self.local_translation_source_var = tk.StringVar(
            value="Çeviri motoru: LibreTranslate API. İnternet bağlantısı gerekir."
        )
        self.record_image_note_var = tk.StringVar(
            value="Açık kaynak görseller küçük boyutta indirilip çevrimdışı önbelleğe alınır."
        )
        self.filter_summary_var = tk.StringVar(value="")
        self.total_stat_var = tk.StringVar(value="-")
        self.visible_stat_var = tk.StringVar(value="-")
        self.quick_stat_var = tk.StringVar(value="-")
        self.word_var = tk.StringVar(value="Kelime seçin")
        self.translation_var = tk.StringVar(value="Seçili kaydın kısa özeti burada görünür.")
        self.meta_var = tk.StringVar(value="")
        self.shortcuts_var = tk.StringVar(value="Kısayollar: Ctrl+F ara, Ctrl+N yeni kelime, F10 ayarlar, Esc temizle  •  fahr* → önek arama, *fahrt → sonek, *fahr* → içerik")
        self.favorite_button_var = tk.StringVar(value="Favorilere Ekle")
        self.result_empty_title_var = tk.StringVar(value="")
        self.result_empty_body_var = tk.StringVar(value="")
        self.detail_empty_title_var = tk.StringVar(value="Aramaya başlayın")
        self.detail_empty_body_var = tk.StringVar(
            value="Üstteki arama alanına kelime yazın veya soldaki sonuçlardan birini seçin."
        )
        self.summary_caption_var = tk.StringVar(value="Kısa bilgi")
        self.source_status_var = tk.StringVar(value="Kaynak bilgisi seçili kayıtla birlikte görünür.")
        self.translation_status_var = tk.StringVar(value="Çeviri doğrulama bilgisi seçili kayıtla birlikte görünür.")
        self.definition_hint_var = tk.StringVar(value="Tanımlar, seçili kayıt için otomatik yüklenir.")
        self.compact_caption_var = tk.StringVar(value="Tanım")
        self.cogul_var = tk.StringVar(value="")
        self.partizip_var = tk.StringVar(value="")
        self.trennbar_var = tk.StringVar(value="")
        self.verb_typ_var = tk.StringVar(value="")
        self.gramatik_notu_var = tk.StringVar(value="")
        self.seviye_var = tk.StringVar(value="")
        self.menu_show_stats_var = tk.BooleanVar(value=bool(self.settings.get("show_stats", False)))
        self.menu_show_quick_access_var = tk.BooleanVar(value=bool(self.settings.get("show_quick_access", False)))
        self.menu_show_results_panel_var = tk.BooleanVar(value=bool(self.settings.get("show_results_panel", False)))
        self.menu_show_extended_details_var = tk.BooleanVar(value=bool(self.settings.get("show_extended_details", False)))
        self.menu_show_detail_actions_var = tk.BooleanVar(value=bool(self.settings.get("show_detail_actions", False)))
        self.active_palette = THEMES[self.settings.get("theme", DEFAULT_SETTINGS["theme"])]

        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.apply_window_icon()

        self._splash_overlay: tk.Toplevel | None = None
        self._build_ui()
        self.build_menu()
        repair_widget_tree_texts(self)
        self.apply_theme()
        self.bind_shortcuts()
        self.result_summary_var.set("Veri yükleniyor…")
        self._show_loading_overlay()
        threading.Thread(target=self._load_data_bg, daemon=True).start()
        self.queue_local_translation(self.search_var.get())
        self.after(180, self.process_gender_form_results)
        self.after(220, self.process_local_translation_results)
        self.after(260, self.process_record_image_results)
        self.after(100, self.search_entry.focus_set)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def load_settings(self) -> dict:
        settings = dict(DEFAULT_SETTINGS)
        settings.update(safe_json_load(SETTINGS_PATH, {}))

        for art_key in ["hero_background_art", "search_background_art", "results_background_art", "detail_background_art"]:
            if settings.get(art_key) == "leaves":
                settings[art_key] = "none"

        if settings.get("theme") not in THEMES:
            settings["theme"] = DEFAULT_SETTINGS["theme"]
        if settings.get("font_preset") not in FONT_PRESETS:
            settings["font_preset"] = DEFAULT_SETTINGS["font_preset"]
        if settings.get("sort_mode") not in SORT_OPTIONS:
            settings["sort_mode"] = DEFAULT_SETTINGS["sort_mode"]
        if settings.get("source_mode") not in SOURCE_MODE_LABELS:
            settings["source_mode"] = DEFAULT_SETTINGS["source_mode"]
        # source_filter her başlangıçta sıfırlanır — varsayılan mod tüm kaynakları arar
        settings["source_filter"] = ""
        if settings.get("llm_api_url") in (None, ""):
            settings["llm_api_url"] = settings.get("openai_api_url", DEFAULT_SETTINGS["llm_api_url"])
        if settings.get("llm_model") in (None, ""):
            settings["llm_model"] = settings.get("openai_model", DEFAULT_SETTINGS["llm_model"])
        if settings.get("llm_api_key") in (None, ""):
            settings["llm_api_key"] = settings.get("openai_api_key", DEFAULT_SETTINGS["llm_api_key"])
        if settings.get("art_layout_preset") not in ART_LAYOUT_PRESETS:
            settings["art_layout_preset"] = DEFAULT_SETTINGS["art_layout_preset"]
        settings["libretranslate_url"] = build_libretranslate_url(
            settings.get("libretranslate_url", DEFAULT_SETTINGS["libretranslate_url"])
        )
        settings["libretranslate_api_key"] = str(settings.get("libretranslate_api_key", "") or "").strip()
        settings["llm_api_url"] = build_llm_api_url(settings.get("llm_api_url", DEFAULT_SETTINGS["llm_api_url"]))
        settings["llm_api_key"] = str(settings.get("llm_api_key", "") or "").strip()
        settings["llm_model"] = str(settings.get("llm_model", DEFAULT_SETTINGS["llm_model"]) or DEFAULT_SETTINGS["llm_model"]).strip()

        settings["preferred_sources"] = [
            str(item).strip() for item in settings.get("preferred_sources", []) if str(item).strip()
        ]
        settings["search_action_buttons"] = sanitize_search_action_buttons(settings.get("search_action_buttons", []))
        settings["recent_searches"] = [
            str(item).strip() for item in settings.get("recent_searches", []) if str(item).strip()
        ][:MAX_RECENT_SEARCHES]
        settings["pinned_records"] = [
            str(item).strip() for item in settings.get("pinned_records", []) if str(item).strip()
        ][:MAX_PINNED_RECORDS]
        settings["result_limit"] = max(50, min(1000, safe_int(settings.get("result_limit"), DEFAULT_SETTINGS["result_limit"])))
        settings["content_font_size"] = max(
            11,
            min(22, safe_int(settings.get("content_font_size"), DEFAULT_SETTINGS["content_font_size"])),
        )
        settings["translation_font_size"] = max(
            14,
            min(30, safe_int(settings.get("translation_font_size"), DEFAULT_SETTINGS["translation_font_size"])),
        )
        settings["meta_font_size"] = max(
            9,
            min(22, safe_int(settings.get("meta_font_size"), DEFAULT_SETTINGS["meta_font_size"])),
        )
        settings["show_shortcuts_hint"] = bool(
            settings.get("show_shortcuts_hint", DEFAULT_SETTINGS["show_shortcuts_hint"])
        )
        settings["allow_art_customization"] = bool(
            settings.get("allow_art_customization", DEFAULT_SETTINGS["allow_art_customization"])
        )
        settings["allow_art_sidebar_resize"] = bool(
            settings.get("allow_art_sidebar_resize", DEFAULT_SETTINGS["allow_art_sidebar_resize"])
        )
        settings["show_background_art"] = bool(settings.get("show_background_art", DEFAULT_SETTINGS["show_background_art"]))
        for key in [
            "show_art_right_main",
            "show_art_right_accent",
            "show_art_hero",
            "show_art_search",
            "show_art_results",
            "show_art_detail",
            "expand_art_right_main",
            "expand_art_right_accent",
            "expand_art_hero",
            "expand_art_search",
            "expand_art_results",
            "expand_art_detail",
        ]:
            settings[key] = bool(settings.get(key, DEFAULT_SETTINGS[key]))
        settings["custom_art_slots"] = sanitize_custom_art_slots(settings.get("custom_art_slots", {}))
        if settings.get("hero_background_art") not in BACKGROUND_IMAGE_OPTIONS:
            settings["hero_background_art"] = DEFAULT_SETTINGS["hero_background_art"]
        if settings.get("hero_banner_art") not in BACKGROUND_IMAGE_OPTIONS:
            settings["hero_banner_art"] = DEFAULT_SETTINGS["hero_banner_art"]
        if settings.get("search_background_art") not in BACKGROUND_IMAGE_OPTIONS:
            settings["search_background_art"] = DEFAULT_SETTINGS["search_background_art"]
        if settings.get("results_background_art") not in BACKGROUND_IMAGE_OPTIONS:
            settings["results_background_art"] = DEFAULT_SETTINGS["results_background_art"]
        if settings.get("detail_background_art") not in BACKGROUND_IMAGE_OPTIONS:
            settings["detail_background_art"] = DEFAULT_SETTINGS["detail_background_art"]
        if settings.get("compact_background_art") not in BACKGROUND_IMAGE_OPTIONS:
            settings["compact_background_art"] = DEFAULT_SETTINGS["compact_background_art"]
        settings = enforce_visible_art_settings(settings)
        settings["art_sidebar_width"] = max(
            RIGHT_ART_SIDEBAR_MIN_WIDTH,
            safe_int(settings.get("art_sidebar_width"), DEFAULT_SETTINGS["art_sidebar_width"]),
        )
        settings["start_maximized"] = bool(settings.get("start_maximized", DEFAULT_SETTINGS["start_maximized"]))
        settings["window_state"] = str(settings.get("window_state", DEFAULT_SETTINGS["window_state"]))
        return settings

    def apply_window_chrome(self, window: tk.Misc, palette: dict | None = None) -> None:
        active_palette = palette or THEMES.get(self.settings.get("theme", DEFAULT_SETTINGS["theme"]), THEMES["krem"])
        try:
            window.configure(bg=active_palette["bg"])
        except Exception:
            pass
        try:
            window.update_idletasks()
            hwnd = window.winfo_id()
            dark_mode = c_int(1 if color_is_dark(active_palette["bg"]) else 0)
            border_color = c_int(hex_to_colorref(active_palette["line"]))
            caption_color = c_int(hex_to_colorref(active_palette["panel"]))
            text_color = c_int(hex_to_colorref(active_palette["ink"]))
            for attribute, value in (
                (DWMWA_USE_IMMERSIVE_DARK_MODE, dark_mode),
                (DWMWA_BORDER_COLOR, border_color),
                (DWMWA_CAPTION_COLOR, caption_color),
                (DWMWA_TEXT_COLOR, text_color),
            ):
                windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, byref(value), sizeof(value))
        except Exception:
            pass

    def refresh_dialog_themes(self, palette: dict) -> None:
        for dialog_name in ("settings_dialog", "import_dialog", "quiz_dialog", "dataset_editor_dialog"):
            dialog = getattr(self, dialog_name, None)
            if dialog is None or not dialog.winfo_exists():
                continue
            apply_method = getattr(dialog, "apply_dialog_theme", None)
            if callable(apply_method):
                apply_method(palette)
                continue
            apply_theme = getattr(dialog, "apply_theme", None)
            if callable(apply_theme):
                apply_theme()
            else:
                self.apply_window_chrome(dialog, palette)

    def bind_shortcuts(self) -> None:
        self.bind("<Control-f>", lambda _event: self.focus_search_entry(select_all=True))
        self.bind("<Control-comma>", lambda _event: self.open_settings())
        self.bind("<F10>", lambda _event: self.open_settings())
        self.bind("<Control-n>", lambda _event: self.open_entry_dialog())
        self.bind("<Control-Shift-I>", lambda _event: self.open_import_dialog())
        self.bind("<Control-Shift-M>", lambda _event: self.open_parallel_text_import_dialog())
        self.bind("<Control-d>", lambda _event: self.toggle_pin_current_record())
        self.bind("<Control-r>", lambda _event: self.reload_data())
        self.bind("<Escape>", lambda _event: self.clear_search())
        self.search_entry.bind("<Return>", self.on_search_submit)
        self.search_entry.bind("<Control-BackSpace>", self.on_search_clear_shortcut, add=True)
        self.search_entry.bind("<Control-Delete>", self.on_search_clear_shortcut, add=True)
        self.search_entry.bind("<KeyPress>", self.on_search_keypress, add=True)
        self.search_entry.bind("<Down>", self.on_search_suggestion_down, add=True)
        self.search_entry.bind("<Up>", self.on_search_suggestion_up, add=True)
        self.search_entry.bind("<FocusIn>", self.on_search_entry_focus_in, add=True)
        self.search_entry.bind("<FocusOut>", self.on_search_entry_focus_out, add=True)
        self.search_suggest_listbox.bind("<ButtonRelease-1>", self.on_search_suggestion_click, add=True)
        self.search_suggest_listbox.bind("<Return>", self.on_search_suggestion_submit, add=True)
        self.search_suggest_listbox.bind("<Double-Button-1>", self.on_search_suggestion_click, add=True)
        self.search_suggest_listbox.bind("<FocusOut>", self.on_search_entry_focus_out, add=True)
        self.result_tree.bind("<Return>", lambda _event: self.open_primary_source())
        self._bind_hover_scroll()

    def _bind_hover_scroll(self) -> None:
        """Fare nerede olursa olsun en yakın kaydırılabilir widget'ı scroll et (global handler)."""
        _scrollable_types = (tk.Text, tk.Listbox, tk.Canvas, ttk.Treeview)

        def _find_scrollable(widget: tk.BaseWidget):
            """Widget hiyerarşisinde yukarı çıkarak ilk kaydırılabilir widget'ı döndür."""
            w = widget
            while w:
                if isinstance(w, _scrollable_types):
                    return w
                try:
                    parent_name = w.winfo_parent()
                    if not parent_name:
                        break
                    w = w.nametowidget(parent_name)
                except (KeyError, AttributeError):
                    break
            return None

        def _on_mousewheel(event: tk.Event) -> str | None:
            widget = self.winfo_containing(event.x_root, event.y_root)
            if widget is None:
                return None
            target = _find_scrollable(widget)
            if target is None:
                return None
            target.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        def _on_scroll_up(event: tk.Event) -> str | None:
            widget = self.winfo_containing(event.x_root, event.y_root)
            if widget is None:
                return None
            target = _find_scrollable(widget)
            if target is None:
                return None
            target.yview_scroll(-1, "units")
            return "break"

        def _on_scroll_down(event: tk.Event) -> str | None:
            widget = self.winfo_containing(event.x_root, event.y_root)
            if widget is None:
                return None
            target = _find_scrollable(widget)
            if target is None:
                return None
            target.yview_scroll(1, "units")
            return "break"

        self.bind_all("<MouseWheel>", _on_mousewheel)
        self.bind_all("<Button-4>", _on_scroll_up)   # Linux yukarı
        self.bind_all("<Button-5>", _on_scroll_down)  # Linux aşağı

    def create_scrollable_tab(self, notebook: ttk.Notebook) -> tuple[ttk.Frame, ttk.Frame]:
        """Kaydırılabilir sekme oluştur (SettingsDialog ile paylaşılan yardımcı)."""
        if not hasattr(self, "_app_scroll_canvases"):
            self._app_scroll_canvases: list[tk.Canvas] = []

        shell = ttk.Frame(notebook)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        canvas = tk.Canvas(shell, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=18)

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def sync_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_content_width(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        content.bind("<Configure>", sync_scroll_region)
        canvas.bind("<Configure>", sync_content_width)

        def on_mousewheel(event) -> str:
            delta = 0
            if getattr(event, "delta", 0):
                delta = int(-event.delta / 120)
            elif getattr(event, "num", None) == 4:
                delta = -1
            elif getattr(event, "num", None) == 5:
                delta = 1
            if delta:
                canvas.yview_scroll(delta, "units")
            return "break"

        def bind_mousewheel(_event=None) -> None:
            canvas.bind_all("<MouseWheel>", on_mousewheel)
            canvas.bind_all("<Button-4>", on_mousewheel)
            canvas.bind_all("<Button-5>", on_mousewheel)

        def unbind_mousewheel(_event=None) -> None:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        for widget in (shell, canvas, content):
            widget.bind("<Enter>", bind_mousewheel, add=True)
            widget.bind("<Leave>", unbind_mousewheel, add=True)

        self._app_scroll_canvases.append(canvas)
        return shell, content

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0, minsize=0)
        self.rowconfigure(0, weight=1)

        self.outer_paned = tk.PanedWindow(
            self,
            orient="horizontal",
            opaqueresize=False,
            sashwidth=0,
            sashrelief="flat",
            bd=0,
            relief="flat",
        )
        self.outer_paned.grid(row=0, column=0, sticky="nsew")

        self.build_left_art_sidebar()

        self.main_shell = ttk.Frame(self.outer_paned, style="MainShell.TFrame")
        self.main_shell.columnconfigure(0, weight=1)
        self.main_shell.rowconfigure(1, weight=1)
        self.outer_paned.add(self.main_shell, stretch="always")

        hero = ttk.Frame(self.main_shell, style="HeroPanel.TFrame", padding=(22, 20, 22, 18))
        hero.grid(row=0, column=0, sticky="ew")
        hero.columnconfigure(0, weight=1)

        hero_head = ttk.Frame(hero, style="HeroPanel.TFrame")
        hero_head.grid(row=0, column=0, sticky="ew")
        hero_head.columnconfigure(0, weight=1)
        hero_head.columnconfigure(1, weight=0)

        title_box = ttk.Frame(hero_head, style="HeroPanel.TFrame")
        title_box.grid(row=0, column=0, sticky="w")
        ttk.Label(title_box, text="Almanca-Türkçe Sözlük", style="HeroTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            title_box,
            text="Hızlı arama için sade masaüstü görünümü. Önce ara, sonra sonucu seç ve ayrıntıyı gerektiğinde aç.",
            style="HeroBody.TLabel",
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.hero_side_frame = ttk.Frame(hero_head, style="HeroPanel.TFrame")
        self.hero_side_frame.grid(row=0, column=1, sticky="ne", padx=(20, 0))
        self.shortcuts_label = ttk.Label(self.hero_side_frame, textvariable=self.shortcuts_var, style="Shortcut.TLabel")
        self.shortcuts_label.grid(row=0, column=0, sticky="e")
        self.shortcuts_close_button = ttk.Button(
            self.hero_side_frame,
            text="×",
            width=2,
            style="ShortcutDismiss.TButton",
            command=self.hide_shortcuts_hint,
        )
        self.shortcuts_close_button.grid(row=0, column=1, sticky="e", padx=(8, 0))

        self.hero_bg_label = tk.Label(hero, bd=0, highlightthickness=0)
        self.hero_bg_label.place(relx=1.0, y=6, anchor="ne")
        self.hero_bg_label.lower()

        search_shell = ttk.Frame(hero, style="SearchShell.TFrame", padding=(16, 16, 16, 14))
        self.search_shell = search_shell
        search_shell.grid(row=1, column=0, sticky="ew", pady=(16, 10))
        search_shell.columnconfigure(0, weight=1)

        ttk.Label(search_shell, text="Ara", style="SearchLabel.TLabel").grid(row=0, column=0, sticky="w")
        action_row = ttk.Frame(search_shell, style="SearchShell.TFrame")
        action_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        action_row.columnconfigure(0, weight=1)

        self.search_entry = ttk.Entry(action_row, textvariable=self.search_var, style="Search.TEntry")
        self.search_entry.grid(row=0, column=0, sticky="ew")
        self.search_entry.configure(font=("Segoe UI", 15))
        self.search_actions_frame = ttk.Frame(action_row, style="SearchShell.TFrame")
        self.search_actions_frame.grid(row=0, column=1, sticky="e", padx=(10, 0))
        self.render_search_action_buttons()

        self.search_suggest_frame = tk.Frame(search_shell, bd=0, highlightthickness=1)
        self.search_suggest_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.search_suggest_frame.columnconfigure(0, weight=1)
        self.search_suggest_listbox = tk.Listbox(
            self.search_suggest_frame,
            activestyle="none",
            exportselection=False,
            height=6,
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        self.search_suggest_listbox.grid(row=0, column=0, sticky="ew")
        search_suggest_scroll = ttk.Scrollbar(
            self.search_suggest_frame,
            orient="vertical",
            command=self.search_suggest_listbox.yview,
        )
        search_suggest_scroll.grid(row=0, column=1, sticky="ns")
        self.search_suggest_listbox.configure(yscrollcommand=search_suggest_scroll.set)
        self.search_suggest_frame.grid_remove()

        ttk.Label(search_shell, textvariable=self.search_status_var, style="Meta.TLabel", wraplength=980, justify="left").grid(
            row=3, column=0, sticky="w", pady=(10, 2)
        )
        # LibreTranslate çeviri paneli kaldırıldı — alan boşaltıldı
        self.local_translation_frame = ttk.Frame(search_shell, style="SoftPanel.TFrame", padding=(12, 10))
        self.local_translation_frame.columnconfigure(0, weight=1)
        ttk.Label(self.local_translation_frame, text="LibreTranslate Çeviri", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            self.local_translation_frame,
            textvariable=self.local_translation_var,
            style="LocalAccent.TLabel",
            wraplength=940,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(
            self.local_translation_frame,
            textvariable=self.local_translation_source_var,
            style="Muted.TLabel",
            wraplength=940,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.search_bg_label = tk.Label(search_shell, bd=0, highlightthickness=0)
        self.search_bg_label.place(relx=1.0, rely=1.0, anchor="se", x=-12, y=-10)
        self.search_bg_label.lower()

        self.stats_row = ttk.Frame(hero, style="HeroPanel.TFrame")
        self.stats_row.grid(row=2, column=0, sticky="ew", pady=(2, 8))
        for column in range(3):
            self.stats_row.columnconfigure(column, weight=1)
        self._build_stat_card(self.stats_row, 0, "Toplam kayıt", self.total_stat_var)
        self._build_stat_card(self.stats_row, 1, "Görünen sonuç", self.visible_stat_var)
        self._build_stat_card(self.stats_row, 2, "Hızlı erişim", self.quick_stat_var)

        self.quick_frame = ttk.LabelFrame(hero, text="Hızlı Erişim", padding=12)
        self.quick_frame.grid(row=3, column=0, sticky="ew")
        self.quick_frame.columnconfigure(0, weight=1)
        self.quick_frame.columnconfigure(1, weight=1)

        recent_wrap = ttk.Frame(self.quick_frame)
        recent_wrap.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        recent_wrap.columnconfigure(0, weight=1)
        ttk.Label(recent_wrap, text="Son aramalar", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.recent_buttons_frame = ttk.Frame(recent_wrap)
        self.recent_buttons_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.recent_buttons_frame.columnconfigure(0, weight=1)

        pinned_wrap = ttk.Frame(self.quick_frame)
        pinned_wrap.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        pinned_wrap.columnconfigure(0, weight=1)
        ttk.Label(pinned_wrap, text="Favori kelimeler", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.pinned_buttons_frame = ttk.Frame(pinned_wrap)
        self.pinned_buttons_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.pinned_buttons_frame.columnconfigure(0, weight=1)

        self.body_paned = ttk.Panedwindow(self.main_shell, orient="horizontal", style="MainBody.TPanedwindow")
        self.body_paned.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 20))

        self.left_panel = ttk.Frame(self.body_paned, style="Panel.TFrame", padding=16)
        self.right_panel = ttk.Frame(self.body_paned, style="Panel.TFrame")
        self.body_paned.add(self.left_panel, weight=1)
        self.body_paned.add(self.right_panel, weight=1)

        left = self.left_panel
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)

        # Sağ panel: kaydırılabilir canvas (görsel gösterilince sekmelere ulaşılabilsin)
        self.right_panel.columnconfigure(0, weight=1)
        self.right_panel.rowconfigure(0, weight=1)
        self.right_scroll_canvas = tk.Canvas(self.right_panel, highlightthickness=0, bd=0)
        self.right_scroll_canvas.grid(row=0, column=0, sticky="nsew")
        self.right_scroll_bar = ttk.Scrollbar(self.right_panel, orient="vertical", command=self.right_scroll_canvas.yview)
        self.right_scroll_bar.grid(row=0, column=1, sticky="ns")
        self.right_scroll_canvas.configure(yscrollcommand=self.right_scroll_bar.set)
        right_inner = ttk.Frame(self.right_scroll_canvas, style="Panel.TFrame", padding=16)
        self._right_scroll_win = self.right_scroll_canvas.create_window((0, 0), window=right_inner, anchor="nw")
        right_inner.bind("<Configure>", lambda e: self.right_scroll_canvas.configure(
            scrollregion=self.right_scroll_canvas.bbox("all")
        ))
        self.right_scroll_canvas.bind("<Configure>", lambda e: self.right_scroll_canvas.itemconfigure(
            self._right_scroll_win, width=e.width
        ))

        def _right_mw_on(e=None):
            def _scroll(ev):
                self.right_scroll_canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units")
                return "break"
            self.right_scroll_canvas.bind_all("<MouseWheel>", _scroll)

        def _right_mw_off(e=None):
            self.right_scroll_canvas.unbind_all("<MouseWheel>")

        for _w in (self.right_scroll_canvas, right_inner):
            _w.bind("<Enter>", _right_mw_on, add=True)
            _w.bind("<Leave>", _right_mw_off, add=True)

        right = right_inner

        ttk.Label(left, text="Sonuçlar", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(left, textvariable=self.result_summary_var, style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 2))
        ttk.Label(left, textvariable=self.filter_summary_var, style="Muted.TLabel", wraplength=420, justify="left").grid(
            row=2, column=0, sticky="nw", pady=(0, 10)
        )

        result_body = ttk.Frame(left, style="Panel.TFrame")
        result_body.grid(row=3, column=0, sticky="nsew")
        result_body.columnconfigure(0, weight=1)
        result_body.rowconfigure(0, weight=1)

        self.tree_frame = ttk.Frame(result_body, style="Panel.TFrame")
        self.tree_frame.grid(row=0, column=0, sticky="nsew")
        self.tree_frame.columnconfigure(0, weight=1)
        self.tree_frame.rowconfigure(0, weight=1)

        self.result_tree = ttk.Treeview(
            self.tree_frame,
            columns=("word", "translation", "meta"),
            show="headings",
            selectmode="browse",
        )
        self.result_tree.heading("word", text="Almanca")
        self.result_tree.heading("translation", text="Türkçe")
        self.result_tree.heading("meta", text="Kısa bilgi")
        self.result_tree.column("word", width=220, anchor="w")
        self.result_tree.column("translation", width=190, anchor="w")
        self.result_tree.column("meta", width=250, anchor="w")
        self.result_tree.grid(row=0, column=0, sticky="nsew")

        tree_scroll = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.result_tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.result_tree.configure(yscrollcommand=tree_scroll.set)

        self.results_empty = ttk.Frame(result_body, style="SoftPanel.TFrame", padding=26)
        self.results_empty.columnconfigure(0, weight=1)
        ttk.Label(self.results_empty, textvariable=self.result_empty_title_var, style="EmptyTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            self.results_empty,
            textvariable=self.result_empty_body_var,
            style="Muted.TLabel",
            wraplength=420,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.results_empty_bg_label = tk.Label(self.results_empty, bd=0, highlightthickness=0)
        self.results_empty_bg_label.place(relx=1.0, rely=1.0, anchor="se", x=-14, y=-12)
        self.results_empty_bg_label.lower()

        right.columnconfigure(0, weight=1)

        self.detail_head = ttk.Frame(right, style="Panel.TFrame")
        self.detail_head.grid(row=0, column=0, sticky="ew")
        self.detail_head.columnconfigure(0, weight=1)

        ttk.Label(self.detail_head, textvariable=self.word_var, style="Word.TLabel").grid(row=0, column=0, sticky="w")
        self.detail_actions_frame = ttk.Frame(self.detail_head, style="Panel.TFrame")
        self.detail_actions_frame.grid(row=0, column=1, columnspan=2, sticky="e")
        ttk.Button(self.detail_actions_frame, textvariable=self.favorite_button_var, command=self.toggle_pin_current_record).grid(
            row=0, column=0, padx=(10, 0)
        )
        ttk.Button(self.detail_actions_frame, text="Kaynağı Aç", command=self.open_primary_source).grid(row=0, column=1, padx=(10, 0))

        self.translation_label = ttk.Label(self.detail_head, textvariable=self.translation_var, style="AccentText.TLabel", wraplength=720)
        self.translation_label.grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )
        self.cogul_label = ttk.Label(self.detail_head, textvariable=self.cogul_var, style="DetailInfo.TLabel", wraplength=720)
        self.cogul_label.grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.cogul_label.grid_remove()
        self.partizip_label = ttk.Label(self.detail_head, textvariable=self.partizip_var, style="DetailInfo.TLabel", wraplength=720)
        self.partizip_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.partizip_label.grid_remove()
        self.trennbar_label = ttk.Label(self.detail_head, textvariable=self.trennbar_var, style="DetailInfo.TLabel", wraplength=720)
        self.trennbar_label.grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.trennbar_label.grid_remove()
        self.verb_typ_label = ttk.Label(self.detail_head, textvariable=self.verb_typ_var, style="DetailInfo.TLabel", wraplength=720)
        self.verb_typ_label.grid(row=5, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.verb_typ_label.grid_remove()
        self.gramatik_notu_label = ttk.Label(self.detail_head, textvariable=self.gramatik_notu_var, style="DetailInfo.TLabel", wraplength=720)
        self.gramatik_notu_label.grid(row=6, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.gramatik_notu_label.grid_remove()
        self._kelime_ailesi_frame = ttk.Frame(self.detail_head, style="Panel.TFrame")
        self._kelime_ailesi_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        self._kelime_ailesi_frame.grid_remove()
        self._sinonim_frame = ttk.Frame(self.detail_head, style="Panel.TFrame")
        self._sinonim_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        self._sinonim_frame.grid_remove()
        self._antonim_frame = ttk.Frame(self.detail_head, style="Panel.TFrame")
        self._antonim_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        self._antonim_frame.grid_remove()
        self.seviye_label = ttk.Label(self.detail_head, textvariable=self.seviye_var, style="DetailInfo.TLabel")
        self.seviye_label.grid(row=8, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.seviye_label.grid_remove()
        self.detail_info_separator = tk.Frame(self.detail_head, height=1, bd=0)
        self.detail_info_separator.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        self.meta_label = ttk.Label(self.detail_head, textvariable=self.meta_var, style="DetailMeta.TLabel", wraplength=720, justify="left")
        self.meta_label.grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(0, 0)
        )
        # --- Referans sözlük butonları (her zaman görünür) ---
        self._ref_links: dict = {}
        self._ref_buttons_head: dict[str, ttk.Button] = {}
        self._ref_panel_current_key: str = ""
        self._ref_head_frame = ttk.Frame(self.detail_head, style="Panel.TFrame")
        self._ref_head_frame.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self._ref_head_frame.columnconfigure(0, weight=1)
        _btn_row = ttk.Frame(self._ref_head_frame, style="Panel.TFrame")
        _btn_row.grid(row=0, column=0, sticky="w")
        _ref_head_defs = [
            ("duden",         "Duden",         "Tarayicida acar (API mevcut degil)"),
            ("dwds",          "DWDS",          "Almanca kelime veri tabani - DWDS"),
            ("wiktionary_de", "Wiktionary DE", "Almanca Wiktionary"),
            ("tdk",           "TDK",           "Turkce karsilik icin TDK Sozluk"),
        ]
        for col, (key, label, tip) in enumerate(_ref_head_defs):
            btn = ttk.Button(
                _btn_row,
                text=label,
                state="disabled",
                command=lambda k=key: self._show_ref_inline(k),
            )
            btn.grid(row=0, column=col, padx=(0, 6))
            HoverTip(btn, tip)
            self._ref_buttons_head[key] = btn
        # Sonuç paneli (gizli, tıklanınca açılır)
        self._ref_result_panel = ttk.Frame(self._ref_head_frame, style="Panel.TFrame")
        self._ref_result_panel.columnconfigure(0, weight=1)
        self._ref_result_panel.rowconfigure(1, weight=1)
        self._ref_result_panel_visible = False
        _rp_title_row = ttk.Frame(self._ref_result_panel, style="Panel.TFrame")
        _rp_title_row.grid(row=0, column=0, sticky="ew", pady=(8, 4))
        _rp_title_row.columnconfigure(0, weight=1)
        self._ref_panel_title_var = tk.StringVar(value="")
        ttk.Label(_rp_title_row, textvariable=self._ref_panel_title_var, style="Section.TLabel", wraplength=400, anchor="w").grid(row=0, column=0, sticky="w")
        ttk.Button(_rp_title_row, text="Kapat", command=self._hide_ref_panel).grid(row=0, column=1, sticky="e", padx=(8, 0))
        _rp_wrap = ttk.Frame(self._ref_result_panel)
        _rp_wrap.grid(row=1, column=0, sticky="nsew")
        _rp_wrap.columnconfigure(0, weight=1)
        _rp_wrap.rowconfigure(0, weight=1)
        self._ref_panel_text = tk.Text(_rp_wrap, height=8, wrap="word", relief="flat", padx=10, pady=8)
        self._ref_panel_text.grid(row=0, column=0, sticky="nsew")
        _rp_scroll = ttk.Scrollbar(_rp_wrap, orient="vertical", command=self._ref_panel_text.yview)
        _rp_scroll.grid(row=0, column=1, sticky="ns")
        self._ref_panel_text.configure(yscrollcommand=_rp_scroll.set)
        self._ref_panel_open_btn = ttk.Button(
            self._ref_result_panel, text="Tarayicida Ac",
            command=lambda: self._open_ref_link(self._ref_panel_current_key)
        )
        self._ref_panel_open_btn.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.record_image_frame = ttk.Frame(self.detail_head, style="ReadingCard.TFrame", padding=10)
        self.record_image_frame.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self.record_image_frame.columnconfigure(0, weight=1)
        self.record_image_label = tk.Label(self.record_image_frame, bd=0, highlightthickness=0, anchor="center", cursor="hand2")
        self.record_image_label.grid(row=0, column=0, sticky="ew")
        self.record_image_label.bind("<Button-1>", self.open_record_image_preview)
        self.record_image_note_label = ttk.Label(
            self.record_image_frame,
            textvariable=self.record_image_note_var,
            style="ReadingMuted.TLabel",
            wraplength=720,
            justify="left",
        )
        self.record_image_note_label.grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.record_image_frame.grid_remove()

        self.summary_strip = ttk.Frame(right, style="SoftPanel.TFrame", padding=12)
        self.summary_strip.grid(row=1, column=0, sticky="ew", pady=(12, 12))
        self.summary_strip.columnconfigure(0, weight=1)
        ttk.Label(self.summary_strip, textvariable=self.summary_caption_var, style="Section.TLabel").grid(row=0, column=0, sticky="w")

        self.detail_stack = ttk.Frame(right, style="Panel.TFrame")
        self.detail_stack.grid(row=2, column=0, sticky="nsew")
        self.detail_stack.columnconfigure(0, weight=1)
        self.detail_stack.rowconfigure(0, weight=1)

        self.detail_empty = ttk.Frame(self.detail_stack, style="SoftPanel.TFrame", padding=28)
        self.detail_empty.grid(row=0, column=0, sticky="nsew")
        self.detail_empty.columnconfigure(0, weight=1)
        self.detail_empty.columnconfigure(1, weight=0)
        ttk.Label(self.detail_empty, textvariable=self.detail_empty_title_var, style="EmptyTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            self.detail_empty,
            textvariable=self.detail_empty_body_var,
            style="Muted.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.detail_empty_bg_label = tk.Label(self.detail_empty, bd=0, highlightthickness=0)
        self.detail_empty_bg_label.place(relx=1.0, rely=1.0, anchor="se", x=-14, y=-12)
        self.detail_empty_bg_label.lower()

        self.compact_detail = ttk.Frame(self.detail_stack, style="SoftPanel.TFrame", padding=18)
        self.compact_detail.grid(row=0, column=0, sticky="nsew")
        self.compact_detail.columnconfigure(0, weight=1)
        self.compact_detail.rowconfigure(1, weight=1)
        ttk.Label(self.compact_detail, textvariable=self.compact_caption_var, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.compact_scroll_wrap = ttk.Frame(self.compact_detail, style="ReadingCard.TFrame")
        self.compact_scroll_wrap.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.compact_scroll_wrap.columnconfigure(0, weight=1)
        self.compact_scroll_wrap.rowconfigure(0, weight=1)
        self.compact_scroll_canvas = tk.Canvas(self.compact_scroll_wrap, highlightthickness=0, bd=0)
        self.compact_scroll_canvas.grid(row=0, column=0, sticky="nsew")
        self.compact_scrollbar = ttk.Scrollbar(self.compact_scroll_wrap, orient="vertical", command=self.compact_scroll_canvas.yview)
        self.compact_scrollbar.grid(row=0, column=1, sticky="ns")
        self.compact_scroll_canvas.configure(yscrollcommand=self.compact_scrollbar.set)
        self.compact_scroll_body = ttk.Frame(self.compact_scroll_canvas, style="SoftPanel.TFrame")
        self.compact_scroll_body.columnconfigure(0, weight=1)
        self.compact_scroll_window = self.compact_scroll_canvas.create_window((0, 0), window=self.compact_scroll_body, anchor="nw")
        self.compact_scroll_body.bind(
            "<Configure>",
            self._on_compact_scroll_body_configure,
        )
        self.compact_scroll_canvas.bind(
            "<Configure>",
            lambda event: self.compact_scroll_canvas.itemconfigure(self.compact_scroll_window, width=event.width),
        )
        self.compact_record_image_frame = ttk.Frame(self.compact_scroll_body, style="ReadingCard.TFrame", padding=10)
        self.compact_record_image_frame.grid(row=0, column=0, sticky="ew")
        self.compact_record_image_frame.columnconfigure(0, weight=1)
        self.compact_record_image_label = tk.Label(
            self.compact_record_image_frame,
            bd=0,
            highlightthickness=0,
            anchor="center",
            cursor="hand2",
        )
        self.compact_record_image_label.grid(row=0, column=0, sticky="ew")
        self.compact_record_image_label.bind("<Button-1>", self.open_record_image_preview)
        self.compact_record_image_note_label = ttk.Label(
            self.compact_record_image_frame,
            textvariable=self.record_image_note_var,
            style="ReadingMuted.TLabel",
            wraplength=720,
            justify="left",
        )
        self.compact_record_image_note_label.grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.compact_record_image_frame.grid_remove()
        self.compact_text_wrap = ttk.Frame(self.compact_scroll_body, style="ReadingCard.TFrame")
        self.compact_text_wrap.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.compact_text_wrap.columnconfigure(0, weight=1)
        self.compact_text_wrap.rowconfigure(0, weight=1)
        self.compact_detail_text = tk.Text(self.compact_text_wrap, height=5, wrap="word", relief="flat", padx=10, pady=10)
        self.compact_detail_text.grid(row=0, column=0, sticky="nsew")
        self.compact_info_scroll = ttk.Scrollbar(self.compact_text_wrap, orient="vertical", command=self.compact_detail_text.yview)
        self.compact_info_scroll.grid(row=0, column=1, sticky="ns")
        self.compact_detail_text.configure(yscrollcommand=self.compact_info_scroll.set)

        ttk.Label(self.compact_scroll_body, text="Türkçe tanım", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=(14, 0))
        self.compact_meanings_label = ttk.Label(self.compact_scroll_body, text="Mümkün anlamlar", style="Section.TLabel")
        self.compact_meanings_label.grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.compact_meanings_wrap = ttk.Frame(self.compact_scroll_body, style="ReadingCard.TFrame")
        self.compact_meanings_wrap.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.compact_meanings_wrap.columnconfigure(0, weight=1)
        self.compact_meanings_listbox = tk.Listbox(self.compact_meanings_wrap, exportselection=False, height=4, activestyle="none")
        self.compact_meanings_listbox.grid(row=0, column=0, sticky="ew")
        self.compact_meanings_listbox.bind("<<ListboxSelect>>", self.on_compact_meaning_select)
        self.compact_meanings_listbox.bind("<Double-Button-1>", self.on_compact_meaning_activate)
        self.compact_meanings_listbox.bind("<Return>", self.on_compact_meaning_activate)
        self.compact_meanings_label.grid_remove()
        self.compact_meanings_wrap.grid_remove()
        self.compact_definition_wrap = ttk.Frame(self.compact_scroll_body, style="ReadingCard.TFrame")
        self.compact_definition_wrap.grid(row=5, column=0, sticky="nsew", pady=(10, 0))
        self.compact_definition_wrap.columnconfigure(0, weight=1)
        self.compact_definition_wrap.rowconfigure(0, weight=1)
        self.compact_definition_text = tk.Text(self.compact_definition_wrap, height=11, wrap="word", relief="flat", padx=10, pady=10)
        self.compact_definition_text.grid(row=0, column=0, sticky="nsew")
        self.compact_detail_scroll = ttk.Scrollbar(self.compact_definition_wrap, orient="vertical", command=self.compact_definition_text.yview)
        self.compact_detail_scroll.grid(row=0, column=1, sticky="ns")
        self.compact_definition_text.configure(yscrollcommand=self.compact_detail_scroll.set)
        self.compact_bg_label = tk.Label(self.compact_detail, bd=0, highlightthickness=0)
        self.compact_bg_label.place(relx=1.0, rely=1.0, anchor="se", x=-12, y=-12)
        self.compact_bg_label.lower()

        self.detail_content = ttk.Frame(self.detail_stack, style="Panel.TFrame")
        self.detail_content.grid(row=0, column=0, sticky="nsew")
        self.detail_content.columnconfigure(0, weight=1)
        self.detail_content.rowconfigure(0, weight=1)

        self.details_notebook = ttk.Notebook(self.detail_content, height=360)
        self.details_notebook.grid(row=0, column=0, sticky="nsew")

        _ov_shell, self.overview_tab = self.create_scrollable_tab(self.details_notebook)
        self.sources_tab = ttk.Frame(self.details_notebook, padding=12)
        self.translation_tab = ttk.Frame(self.details_notebook, padding=12)
        self.definition_tab = ttk.Frame(self.details_notebook, padding=12)
        self.examples_tab = ttk.Frame(self.details_notebook, padding=12)
        self.conjugations_tab = ttk.Frame(self.details_notebook, padding=12)
        self.details_notebook.add(_ov_shell, text="Kısa Bilgi")
        self.details_notebook.add(self.sources_tab, text="Kaynak İncele")
        self.details_notebook.add(self.translation_tab, text="Çeviri Kontrolü")
        self.details_notebook.add(self.definition_tab, text="Tanımlar")
        self.details_notebook.add(self.examples_tab, text="Örnekler")
        self.details_notebook.add(self.conjugations_tab, text="Cekimler")

        self._build_overview_tab()
        self._build_sources_tab()
        self._build_translation_tab()
        self._build_definition_tab()
        self._build_examples_tab()
        self._build_conjugations_tab()
        self.build_right_art_sidebar()
        self.right_art_sidebar.grid(row=0, column=1, sticky="nsew", padx=(0, 18), pady=(18, 20))
        self.load_tree_images()

        self.search_var.trace_add("write", self.on_search_changed)
        self.result_tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.related_listbox.bind("<Double-Button-1>", self.search_related_term)
        self.source_url_listbox.bind("<Double-Button-1>", lambda _event: self.open_selected_source())
        self.translation_source_listbox.bind("<Double-Button-1>", lambda _event: self.open_selected_translation_source())
        self.bind("<Configure>", self.on_window_configure, add=True)
        self.after(180, self.load_tree_images)

    def build_art_sidebar(self, side_key: str) -> None:
        frame_attr = f"{side_key}_art_sidebar"
        title_attr = f"{side_key}_art_title"
        main_card_attr = f"{side_key}_art_main_card"
        main_label_attr = f"{side_key}_art_main_label"
        accent_card_attr = f"{side_key}_art_accent_card"
        accent_label_attr = f"{side_key}_art_accent_label"
        padding = (18, 14, 0, 14) if side_key == "left" else (0, 14, 18, 14)

        sidebar = ttk.Frame(
            self,
            style="ArtSidebar.TFrame",
            padding=padding,
            width=self.settings.get("art_sidebar_width", RIGHT_ART_SIDEBAR_WIDTH),
        )
        sidebar.grid_propagate(False)
        sidebar.columnconfigure(0, weight=1)
        for row in range(6):
            sidebar.rowconfigure(row, weight=0)
        title = ttk.Label(
            sidebar,
            text="Doğa",
            style="Muted.TLabel",
            justify="left",
        )
        title.grid(row=0, column=0, sticky="nw", pady=(0, 12))
        title.configure(text="Doğa", style="ArtTitle.TLabel")
        if side_key == "right":
            title.configure(anchor="w", justify="left")
            title.grid_configure(sticky="w", padx=(6, 0), pady=(2, 10))
        else:
            title.grid_configure(sticky="w", padx=(4, 0), pady=(0, 10))

        main_card = ttk.Frame(sidebar, style="ArtCard.TFrame", width=RIGHT_ART_MAIN_SIZE[0], height=RIGHT_ART_MAIN_SIZE[1])
        main_card.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        main_card.grid_propagate(False)
        main_label = tk.Label(
            main_card,
            bd=RIGHT_ART_FRAME_BORDER,
            relief="solid",
            highlightthickness=0,
        )
        main_label.place(relx=0.5, rely=0.5, anchor="center")

        accent_card = ttk.Frame(
            sidebar,
            style="ArtCardSoft.TFrame",
            width=RIGHT_ART_ACCENT_SIZE[0],
            height=RIGHT_ART_ACCENT_SIZE[1],
        )
        accent_card.grid(row=4, column=0, sticky="ew", pady=(0, 0))
        accent_card.grid_propagate(False)
        accent_label = tk.Label(
            accent_card,
            bd=RIGHT_ART_FRAME_BORDER,
            relief="solid",
            highlightthickness=0,
        )
        accent_label.place(relx=0.5, rely=0.5, anchor="center")
        setattr(self, frame_attr, sidebar)
        setattr(self, title_attr, title)
        setattr(self, main_card_attr, main_card)
        setattr(self, main_label_attr, main_label)
        setattr(self, accent_card_attr, accent_card)
        setattr(self, accent_label_attr, accent_label)

    def build_left_art_sidebar(self) -> None:
        self.build_art_sidebar("left")

    def build_right_art_sidebar(self) -> None:
        self.build_art_sidebar("right")

    def _build_stat_card(self, parent: ttk.Frame, column: int, label: str, value_var: tk.StringVar) -> None:
        card = ttk.Frame(parent, style="Stat.TFrame", padding=(16, 12))
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=label, style="StatLabel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, textvariable=value_var, style="StatValue.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

    def build_menu(self) -> None:
        menubar = tk.Menu(self)

        app_menu = tk.Menu(menubar, tearoff=False)
        app_menu.add_command(label="Ayarlar", command=self.open_settings, accelerator="F10")
        app_menu.add_command(label="Yeni Kelime", command=self.open_entry_dialog, accelerator="Ctrl+N")
        app_menu.add_command(label="URL'den Kelime Aktar", command=self.open_import_dialog, accelerator="Ctrl+Shift+I")
        app_menu.add_command(
            label="Metin Eşleme ile Kelime Çıkar",
            command=self.open_parallel_text_import_dialog,
            accelerator="Ctrl+Shift+M",
        )
        app_menu.add_separator()
        app_menu.add_command(label="Yenile", command=self.reload_data, accelerator="Ctrl+R")
        app_menu.add_separator()
        app_menu.add_command(label="Kapat", command=self.on_close)
        menubar.add_cascade(label="Uygulama", menu=app_menu)

        search_menu = tk.Menu(menubar, tearoff=False)
        search_menu.add_command(label="Arama Kutusuna Git", command=lambda: self.focus_search_entry(select_all=True), accelerator="Ctrl+F")
        search_menu.add_command(label="Aramayı Temizle", command=self.clear_search, accelerator="Esc")
        search_menu.add_command(label="Google Çeviri'de Aç", command=self.open_google_translate_for_search)
        search_menu.add_command(label="Favorilere Ekle / Kaldır", command=self.toggle_pin_current_record, accelerator="Ctrl+D")
        search_menu.add_command(label="Kaynağı Aç", command=self.open_primary_source)
        menubar.add_cascade(label="Ara", menu=search_menu)

        tools_menu = tk.Menu(menubar, tearoff=False)
        tools_menu.add_command(label="Mini Quiz", command=self.open_quiz_dialog)
        tools_menu.add_command(label="Veri Seti Editörü (Geliştirici)", command=self.open_dataset_editor)
        tools_menu.add_separator()
        tools_menu.add_command(label="CSV Dışa Aktar...", command=self.export_to_csv)
        tools_menu.add_command(label="İstatistikler...", command=self.show_statistics)
        menubar.add_cascade(label="Araçlar", menu=tools_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_checkbutton(label="Bilgi Kartları", variable=self.menu_show_stats_var, command=self.toggle_stats_from_menu)
        view_menu.add_checkbutton(label="Hızlı Erişim", variable=self.menu_show_quick_access_var, command=self.toggle_quick_access_from_menu)
        view_menu.add_checkbutton(label="Sonuç Listesi", variable=self.menu_show_results_panel_var, command=self.toggle_results_panel_from_menu)
        view_menu.add_checkbutton(label="Gelişmiş Sekmeler", variable=self.menu_show_extended_details_var, command=self.toggle_extended_details_from_menu)
        view_menu.add_checkbutton(label="Detay Düğmeleri", variable=self.menu_show_detail_actions_var, command=self.toggle_detail_actions_from_menu)
        view_menu.add_separator()
        view_menu.add_command(label="Pencereyi Büyüt", command=lambda: self.state("zoomed"))
        menubar.add_cascade(label="Görünüm", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Program Tutoriali", command=self.show_tutorial)
        help_menu.add_command(label="Kelime Ekleme Rehberi", command=self.show_entry_help)
        help_menu.add_command(label="Kısayollar", command=self.show_shortcuts_help)
        menubar.add_cascade(label="Yardım", menu=help_menu)

        self.configure(menu=menubar)
        self.menubar = menubar

    def _build_overview_tab(self) -> None:
        self.overview_tab.columnconfigure(0, weight=1)

        ttk.Label(self.overview_tab, text="Anlam ve notlar", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        detail_text_wrap = ttk.Frame(self.overview_tab)
        detail_text_wrap.grid(row=1, column=0, sticky="ew", pady=(8, 14))
        detail_text_wrap.columnconfigure(0, weight=1)
        self.detail_text = tk.Text(detail_text_wrap, height=8, wrap="word", relief="flat", padx=10, pady=10)
        self.detail_text.grid(row=0, column=0, sticky="nsew")
        _dt_scroll = ttk.Scrollbar(detail_text_wrap, orient="vertical", command=self.detail_text.yview)
        _dt_scroll.grid(row=0, column=1, sticky="ns")
        self.detail_text.configure(yscrollcommand=_dt_scroll.set)

        ttk.Label(self.overview_tab, text="İlgili kayıtlar", style="Section.TLabel").grid(row=2, column=0, sticky="w")
        related_wrap = ttk.Frame(self.overview_tab)
        related_wrap.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        related_wrap.columnconfigure(0, weight=1)
        self.related_listbox = tk.Listbox(related_wrap, exportselection=False, height=5)
        self.related_listbox.grid(row=0, column=0, sticky="nsew")
        _rl_scroll = ttk.Scrollbar(related_wrap, orient="vertical", command=self.related_listbox.yview)
        _rl_scroll.grid(row=0, column=1, sticky="ns")
        self.related_listbox.configure(yscrollcommand=_rl_scroll.set)
        ttk.Button(related_wrap, text="Seçili terimi ara", command=self.search_related_term).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

    def _build_sources_tab(self) -> None:
        self.sources_tab.columnconfigure(0, weight=1)
        self.sources_tab.rowconfigure(2, weight=1)
        ttk.Label(self.sources_tab, textvariable=self.source_status_var, style="Muted.TLabel", wraplength=700, justify="left").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(self.sources_tab, text="Bağlantılar", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 8))
        src_wrap = ttk.Frame(self.sources_tab)
        src_wrap.grid(row=2, column=0, sticky="nsew")
        src_wrap.columnconfigure(0, weight=1)
        src_wrap.rowconfigure(0, weight=1)
        self.source_url_listbox = tk.Listbox(src_wrap, exportselection=False, height=6)
        self.source_url_listbox.grid(row=0, column=0, sticky="nsew")
        _src_scroll = ttk.Scrollbar(src_wrap, orient="vertical", command=self.source_url_listbox.yview)
        _src_scroll.grid(row=0, column=1, sticky="ns")
        self.source_url_listbox.configure(yscrollcommand=_src_scroll.set)
        ttk.Button(self.sources_tab, text="Seçili kaynağı aç", command=self.open_selected_source).grid(
            row=3, column=0, sticky="w", pady=(10, 0)
        )
        # --- Referans sözlükler ---
        ttk.Label(self.sources_tab, text="Referans Sözlükler", style="Section.TLabel").grid(
            row=4, column=0, sticky="w", pady=(18, 8)
        )
        self._ref_links: dict = {}
        ref_frame = ttk.Frame(self.sources_tab)
        ref_frame.grid(row=5, column=0, sticky="ew")
        ref_defs = [
            ("duden",        "Duden",        "Almanca yazım ve anlam sözlüğü"),
            ("dwds",         "DWDS",         "Almanca kelime veri tabanı"),
            ("wiktionary_de","Wiktionary DE", "Almanca Wiktionary"),
            ("tdk",          "TDK Sözlük",   "Türkçe karşılık için TDK"),
        ]
        self._ref_buttons: dict[str, ttk.Button] = {}
        for col, (key, label, tip) in enumerate(ref_defs):
            btn = ttk.Button(
                ref_frame,
                text=label,
                state="disabled",
                command=lambda k=key: self._show_ref_inline(k),
            )
            btn.grid(row=0, column=col, padx=(0, 8), sticky="w")
            HoverTip(btn, tip)
            self._ref_buttons[key] = btn
        # --- Eş/Zıt Anlamlılar ---
        ttk.Label(self.sources_tab, text="Eş/Zıt Anlamlılar", style="Section.TLabel").grid(
            row=6, column=0, sticky="w", pady=(18, 4)
        )
        self._sources_sinonim_frame = ttk.Frame(self.sources_tab)
        self._sources_sinonim_frame.grid(row=7, column=0, sticky="ew")
        self._sources_antonim_frame = ttk.Frame(self.sources_tab)
        self._sources_antonim_frame.grid(row=8, column=0, sticky="ew")

    def _build_translation_tab(self) -> None:
        self.translation_tab.columnconfigure(0, weight=1)
        self.translation_tab.rowconfigure(1, weight=1)
        self.translation_tab.rowconfigure(3, weight=1)

        ttk.Label(
            self.translation_tab,
            textvariable=self.translation_status_var,
            style="Section.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        tn_wrap = ttk.Frame(self.translation_tab)
        tn_wrap.grid(row=1, column=0, sticky="nsew", pady=(8, 12))
        tn_wrap.columnconfigure(0, weight=1)
        tn_wrap.rowconfigure(0, weight=1)
        self.translation_note = tk.Text(tn_wrap, height=6, wrap="word", relief="flat", padx=10, pady=10)
        self.translation_note.grid(row=0, column=0, sticky="nsew")
        _tn_scroll = ttk.Scrollbar(tn_wrap, orient="vertical", command=self.translation_note.yview)
        _tn_scroll.grid(row=0, column=1, sticky="ns")
        self.translation_note.configure(yscrollcommand=_tn_scroll.set)
        tsl_wrap = ttk.Frame(self.translation_tab)
        tsl_wrap.grid(row=3, column=0, sticky="nsew")
        tsl_wrap.columnconfigure(0, weight=1)
        tsl_wrap.rowconfigure(0, weight=1)
        self.translation_source_listbox = tk.Listbox(tsl_wrap, exportselection=False, height=10)
        self.translation_source_listbox.grid(row=0, column=0, sticky="nsew")
        _tsl_scroll = ttk.Scrollbar(tsl_wrap, orient="vertical", command=self.translation_source_listbox.yview)
        _tsl_scroll.grid(row=0, column=1, sticky="ns")
        self.translation_source_listbox.configure(yscrollcommand=_tsl_scroll.set)
        ttk.Button(
            self.translation_tab,
            text="Seçili doğrulama kaynağını aç",
            command=self.open_selected_translation_source,
        ).grid(row=4, column=0, sticky="w", pady=(10, 0))

    def _build_definition_tab(self) -> None:
        self.definition_tab.columnconfigure(0, weight=1)
        self.definition_tab.rowconfigure(2, weight=1)
        self.definition_tab.rowconfigure(4, weight=1)

        ttk.Label(self.definition_tab, textvariable=self.definition_hint_var, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        german_header = ttk.Frame(self.definition_tab)
        german_header.grid(row=1, column=0, sticky="ew")
        german_header.columnconfigure(0, weight=1)
        ttk.Label(german_header, text="Almanca tanım", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(german_header, text="+ DWDS", command=self.load_dwds_definition_on_demand).grid(row=0, column=1, sticky="e")
        dde_wrap = ttk.Frame(self.definition_tab)
        dde_wrap.grid(row=2, column=0, sticky="nsew", pady=(8, 12))
        dde_wrap.columnconfigure(0, weight=1)
        dde_wrap.rowconfigure(0, weight=1)
        self.definition_de_text = tk.Text(dde_wrap, height=8, wrap="word", relief="flat", padx=10, pady=10)
        self.definition_de_text.grid(row=0, column=0, sticky="nsew")
        _dde_scroll = ttk.Scrollbar(dde_wrap, orient="vertical", command=self.definition_de_text.yview)
        _dde_scroll.grid(row=0, column=1, sticky="ns")
        self.definition_de_text.configure(yscrollcommand=_dde_scroll.set)
        turkish_header = ttk.Frame(self.definition_tab)
        turkish_header.grid(row=3, column=0, sticky="ew")
        turkish_header.columnconfigure(0, weight=1)
        ttk.Label(turkish_header, text="Türkçe tanım", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(turkish_header, text="+ TDK", command=self.load_tdk_definition_on_demand).grid(row=0, column=1, sticky="e")
        dtr_wrap = ttk.Frame(self.definition_tab)
        dtr_wrap.grid(row=4, column=0, sticky="nsew", pady=(8, 0))
        dtr_wrap.columnconfigure(0, weight=1)
        dtr_wrap.rowconfigure(0, weight=1)
        self.definition_tr_text = tk.Text(dtr_wrap, height=8, wrap="word", relief="flat", padx=10, pady=10)
        self.definition_tr_text.grid(row=0, column=0, sticky="nsew")
        _dtr_scroll = ttk.Scrollbar(dtr_wrap, orient="vertical", command=self.definition_tr_text.yview)
        _dtr_scroll.grid(row=0, column=1, sticky="ns")
        self.definition_tr_text.configure(yscrollcommand=_dtr_scroll.set)

    def _build_examples_tab(self) -> None:
        self.examples_tab.columnconfigure(0, weight=1)
        self.examples_tab.rowconfigure(1, weight=1)

        ttk.Label(
            self.examples_tab,
            text="Örnekler varsayılan olarak sade tutulur. İsterseniz Ayarlar'dan tamamen kapatabilirsiniz.",
            style="Muted.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ex_wrap = ttk.Frame(self.examples_tab)
        ex_wrap.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        ex_wrap.columnconfigure(0, weight=1)
        ex_wrap.rowconfigure(0, weight=1)
        self.examples_text = tk.Text(ex_wrap, height=18, wrap="word", relief="flat", padx=10, pady=10)
        self.examples_text.grid(row=0, column=0, sticky="nsew")
        _ex_scroll = ttk.Scrollbar(ex_wrap, orient="vertical", command=self.examples_text.yview)
        _ex_scroll.grid(row=0, column=1, sticky="ns")
        self.examples_text.configure(yscrollcommand=_ex_scroll.set)
        self.examples_text.tag_configure("src_badge", foreground="#4a90d9", font=("Segoe UI", 9))

    def _build_conjugations_tab(self) -> None:
        self.conjugations_tab.columnconfigure(0, weight=1)
        self.conjugations_tab.rowconfigure(1, weight=1)
        self.conjugations_hint_var = tk.StringVar(
            value="Fiil cekimleri burada gorunur. URL taramasiyla eklenen fiiller otomatik doldurulur."
        )
        ttk.Label(
            self.conjugations_tab,
            textvariable=self.conjugations_hint_var,
            style="Muted.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        conj_wrap = ttk.Frame(self.conjugations_tab)
        conj_wrap.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        conj_wrap.columnconfigure(0, weight=1)
        conj_wrap.rowconfigure(0, weight=1)
        self.conjugations_text = tk.Text(conj_wrap, height=18, wrap="word", relief="flat", padx=12, pady=10)
        self.conjugations_text.grid(row=0, column=0, sticky="nsew")
        _conj_scroll = ttk.Scrollbar(conj_wrap, orient="vertical", command=self.conjugations_text.yview)
        _conj_scroll.grid(row=0, column=1, sticky="ns")
        self.conjugations_text.configure(yscrollcommand=_conj_scroll.set)

    def populate_conjugations(self, record: dict) -> None:
        cekimler = record.get("cekimler") or {}
        pos = str(record.get("tur", "")).strip().lower()
        if not cekimler:
            if pos == "fiil":
                msg = "Bu fiil icin cekim bilgisi henuz eklenmemis.\nURL taramasiyla yeniden tarayarak otomatik doldurabilirsiniz."
            else:
                msg = "Bu kayit bir fiil degil. Cekim tablosu yalnizca fiiller icin gecerlidir."
            self.set_text_widget(self.conjugations_text, msg)
            self.conjugations_hint_var.set("Fiil cekimleri")
            return

        word = self.get_record_display_word(record)
        self.conjugations_hint_var.set(f"Fiil cekimleri - {word}")
        lines: list[str] = []

        praesens = cekimler.get("präsens") or {}
        if isinstance(praesens, dict) and praesens:
            lines.append("= Praesens (Genis zaman) =")
            pronouns = ["ich", "du", "er/sie/es", "wir", "ihr", "sie/Sie"]
            shown: set[str] = set()
            for pronoun in pronouns:
                form = praesens.get(pronoun, "")
                if form:
                    lines.append(f"  {pronoun}  ->  {form}")
                    shown.add(pronoun)
            for k, v in praesens.items():
                if k not in shown and v:
                    lines.append(f"  {k}  ->  {v}")

        for tense, label in (
            ("perfekt",    "Perfekt (Gecmis zaman - haben/sein + Partizip II)"),
            ("präteritum", "Praeteritum (Hikaye gecmis)"),
            ("imperativ",  "Imperativ (Emir)"),
        ):
            val = cekimler.get(tense)
            if val and isinstance(val, str):
                if lines:
                    lines.append("")
                lines.append(f"= {label} =")
                lines.append(f"  {val}")

        self.set_text_widget(self.conjugations_text, "\n".join(lines) if lines else "Cekim verisi bos.")

    def apply_theme(self) -> None:
        palette = THEMES[self.settings.get("theme", DEFAULT_SETTINGS["theme"])]
        self.active_palette = palette
        font_preset = FONT_PRESETS[self.settings.get("font_preset", DEFAULT_SETTINGS["font_preset"])]
        content_font_size = self.settings.get("content_font_size", DEFAULT_SETTINGS["content_font_size"])
        translation_font_size = self.settings.get("translation_font_size", DEFAULT_SETTINGS["translation_font_size"])
        meta_font_size = self.settings.get("meta_font_size", DEFAULT_SETTINGS["meta_font_size"])
        ui_font = font_preset["ui"]
        title_font = font_preset["title"]
        content_font = font_preset["content"]
        self.configure(bg=palette["bg"])
        self.option_add("*Font", f"{{{ui_font}}} 10")
        self.outer_paned.configure(
            bg=palette["bg"],
            sashwidth=0,
            sashrelief="flat",
            proxybackground=palette["accent_soft"],
            proxyborderwidth=1,
            proxyrelief="flat",
            sashcursor="",
        )

        self.style.configure(".", background=palette["bg"], foreground=palette["ink"])
        self.style.configure("TFrame", background=palette["bg"])
        self.style.configure("MainShell.TFrame", background=palette["hero"])
        self.style.configure("HeroPanel.TFrame", background=palette["hero"])
        self.style.configure("Panel.TFrame", background=palette["panel"])
        self.style.configure("SoftPanel.TFrame", background=palette["surface_soft"])
        self.style.configure("ReadingCard.TFrame", background=palette["surface_soft"])
        self.style.configure("ArtSidebar.TFrame", background=palette["bg"])
        self.style.configure("MainBody.TPanedwindow", background=palette["hero"], sashthickness=0)
        self.style.configure("ArtCard.TFrame", background=palette["surface"])
        self.style.configure("ArtCardSoft.TFrame", background=palette["surface_soft"])
        self.style.configure("SearchShell.TFrame", background=palette["surface"])
        self.style.configure("Stat.TFrame", background=palette["surface"])
        self.style.configure("TLabel", background=palette["panel"], foreground=palette["ink"])
        self.style.configure("HeroTitle.TLabel", background=palette["hero"], foreground=palette["ink"], font=(title_font, 22, "bold"))
        self.style.configure("HeroBody.TLabel", background=palette["hero"], foreground=palette["muted"], font=(ui_font, 11))
        self.style.configure("Shortcut.TLabel", background=palette["hero"], foreground=palette["muted"], font=(ui_font, 9))
        self.style.configure(
            "ShortcutDismiss.TButton",
            background=palette["hero"],
            foreground=palette["muted"],
            padding=(4, 1),
            borderwidth=0,
        )
        self.style.map(
            "ShortcutDismiss.TButton",
            background=[("active", palette["accent_soft"])],
            foreground=[("active", palette["ink"])],
        )
        self.style.configure("SearchLabel.TLabel", background=palette["surface"], foreground=palette["muted"], font=(ui_font, 10, "bold"))
        self.style.configure("PanelTitle.TLabel", background=palette["panel"], foreground=palette["ink"], font=(title_font, 16, "bold"))
        self.style.configure("Word.TLabel", background=palette["panel"], foreground=palette["ink"], font=(title_font, 20, "bold"))
        self.style.configure(
            "AccentText.TLabel",
            background=palette["panel"],
            foreground=palette["accent"],
            font=(content_font, translation_font_size, "bold"),
        )
        self.style.configure(
            "LocalAccent.TLabel",
            background=palette["surface_soft"],
            foreground=palette["accent"],
            font=(content_font, max(12, translation_font_size - 1), "bold"),
        )
        self.style.configure(
            "DetailMeta.TLabel",
            background=palette["panel"],
            foreground=palette["muted"],
            font=(content_font, meta_font_size),
        )
        self.style.configure("Section.TLabel", background=palette["panel"], foreground=palette["ink"], font=(ui_font, 10, "bold"))
        self.style.configure("Muted.TLabel", background=palette["panel"], foreground=palette["muted"])
        self.style.configure("DetailInfo.TLabel", background=palette["panel"], foreground=palette["muted"], font=(ui_font, 9))
        self.style.configure("ReadingMuted.TLabel", background=palette["surface_soft"], foreground=palette["muted"])
        self.style.configure("ArtTitle.TLabel", background=palette["bg"], foreground=palette["ink"], font=(title_font, 13, "bold"))
        self.style.configure("ArtMuted.TLabel", background=palette["bg"], foreground=palette["muted"])
        self.style.configure("Meta.TLabel", background=palette["surface"], foreground=palette["muted"])
        self.style.configure("EmptyTitle.TLabel", background=palette["surface_soft"], foreground=palette["ink"], font=(title_font, 16, "bold"))
        self.style.configure("StatLabel.TLabel", background=palette["surface"], foreground=palette["muted"], font=(ui_font, 9))
        self.style.configure("StatValue.TLabel", background=palette["surface"], foreground=palette["ink"], font=(title_font, 16, "bold"))
        self.style.configure("DialogTitle.TLabel", background=palette["bg"], foreground=palette["ink"], font=(title_font, 18, "bold"))
        self.style.configure("TLabelFrame", background=palette["panel"], foreground=palette["ink"], bordercolor=palette["line"])
        self.style.configure("TLabelFrame.Label", background=palette["panel"], foreground=palette["ink"], font=(ui_font, 10, "bold"))
        self.style.configure("TNotebook", background=palette["panel"], borderwidth=0)
        self.style.configure("TNotebook.Tab", background=palette["accent_soft"], foreground=palette["ink"], padding=(14, 9))
        self.style.map("TNotebook.Tab", background=[("selected", palette["surface"])])
        self.style.configure("TEntry", fieldbackground=palette["surface"], foreground=palette["ink"], bordercolor=palette["line"])
        self.style.configure("Search.TEntry", fieldbackground=palette["surface"], foreground=palette["ink"], bordercolor=palette["line"])
        self.style.configure("TCombobox", fieldbackground=palette["surface"], foreground=palette["ink"], bordercolor=palette["line"])
        self.style.configure("TSpinbox", fieldbackground=palette["surface"], foreground=palette["ink"], bordercolor=palette["line"])
        self.style.configure(
            "Vertical.TScrollbar",
            background=palette["accent_soft"],
            troughcolor=palette["surface_soft"],
            bordercolor=palette["line"],
            arrowcolor=palette["ink"],
            darkcolor=palette["line"],
            lightcolor=palette["surface"],
            gripcount=0,
            relief="flat",
        )
        self.style.map(
            "Vertical.TScrollbar",
            background=[("active", palette["accent"]), ("pressed", palette["accent"])],
            arrowcolor=[("active", "#ffffff"), ("pressed", "#ffffff")],
        )
        self.style.configure(
            "Horizontal.TScrollbar",
            background=palette["accent_soft"],
            troughcolor=palette["surface_soft"],
            bordercolor=palette["line"],
            arrowcolor=palette["ink"],
            darkcolor=palette["line"],
            lightcolor=palette["surface"],
            gripcount=0,
            relief="flat",
        )
        self.style.map(
            "Horizontal.TScrollbar",
            background=[("active", palette["accent"]), ("pressed", palette["accent"])],
            arrowcolor=[("active", "#ffffff"), ("pressed", "#ffffff")],
        )
        self.style.configure("TButton", background=palette["surface"], foreground=palette["ink"], padding=(10, 8))
        self.style.configure("Primary.TButton", background=palette["accent"], foreground="#ffffff", padding=(12, 9))
        self.style.map("Primary.TButton", background=[("active", palette["accent"])])
        self.style.configure("Chip.TButton", background=palette["surface"], foreground=palette["ink"], padding=(10, 5))
        self.style.configure("ChipAlt.TButton", background="#f7d9d9", foreground="#7a1f1f", padding=(10, 5))
        self.style.map("ChipAlt.TButton", background=[("active", "#f0c8c8")])
        self.style.configure("QuizOption.TButton", background=palette["surface"], foreground=palette["ink"], padding=(12, 10))
        self.style.map(
            "QuizOption.TButton",
            background=[("active", palette["accent_soft"]), ("disabled", palette["surface"])],
            foreground=[("disabled", palette["ink"])],
        )
        self.style.configure("QuizCorrect.TButton", background="#d9f3df", foreground="#165c2b", padding=(12, 10))
        self.style.map(
            "QuizCorrect.TButton",
            background=[("active", "#d9f3df"), ("disabled", "#d9f3df")],
            foreground=[("disabled", "#165c2b")],
        )
        self.style.configure("QuizWrong.TButton", background="#f7d9d9", foreground="#7a1f1f", padding=(12, 10))
        self.style.map(
            "QuizWrong.TButton",
            background=[("active", "#f7d9d9"), ("disabled", "#f7d9d9")],
            foreground=[("disabled", "#7a1f1f")],
        )
        self.style.configure("TCheckbutton", background=palette["panel"], foreground=palette["ink"])
        self.style.configure("TRadiobutton", background=palette["panel"], foreground=palette["ink"])
        self.style.configure(
            "Treeview",
            background=palette["surface"],
            fieldbackground=palette["surface"],
            foreground=palette["ink"],
            bordercolor=palette["line"],
            rowheight=32,
        )
        self.style.configure("Treeview.Heading", background=palette["accent_soft"], foreground=palette["ink"])
        self.style.map("Treeview", background=[("selected", palette["accent_soft"])], foreground=[("selected", palette["ink"])])

        reading_bg = palette["surface_soft"]
        content_widgets = [
            self.compact_detail_text,
            self.compact_definition_text,
            self.detail_text,
            self.translation_note,
            self.definition_de_text,
            self.definition_tr_text,
            self.examples_text,
            self.conjugations_text,
            self._ref_panel_text,
            self.compact_meanings_listbox,
            self.related_listbox,
            self.source_url_listbox,
            self.translation_source_listbox,
        ]
        for widget in content_widgets:
            widget.configure(
                bg=reading_bg,
                fg=palette["ink"],
                highlightbackground=palette["line"],
                highlightcolor=palette["accent"],
                selectbackground=palette["accent_soft"],
                selectforeground=palette["ink"],
                highlightthickness=1,
                bd=0,
                font=(content_font, content_font_size),
            )
            if isinstance(widget, tk.Text):
                widget.configure(spacing1=2, spacing2=4, spacing3=10, insertbackground=palette["accent"])

        self.search_entry.configure(font=(ui_font, 15))
        self.search_suggest_frame.configure(bg=palette["surface"], highlightbackground=palette["line"], highlightcolor=palette["accent"])
        self.search_suggest_listbox.configure(
            bg=palette["surface"],
            fg=palette["ink"],
            selectbackground=palette["accent_soft"],
            selectforeground=palette["ink"],
            highlightbackground=palette["line"],
            highlightcolor=palette["accent"],
            font=(ui_font, 12),
        )

        self.hero_bg_label.configure(bg=palette["hero"])
        self.search_bg_label.configure(bg=palette["surface"])
        self.results_empty_bg_label.configure(bg=palette["surface_soft"])
        self.detail_empty_bg_label.configure(bg=palette["surface_soft"])
        self.compact_bg_label.configure(bg=palette["surface_soft"])
        self.compact_scroll_canvas.configure(bg=palette["surface_soft"], highlightbackground=palette["line"], highlightcolor=palette["accent"])
        self.right_scroll_canvas.configure(bg=palette["surface"])
        self.record_image_label.configure(bg=palette["surface_soft"], highlightbackground=palette["line"])
        self.compact_record_image_label.configure(bg=palette["surface_soft"], highlightbackground=palette["line"])
        for label in (self.left_art_main_label, self.right_art_main_label):
            label.configure(bg=palette["surface"], highlightbackground=palette["line"])
        for label in (self.left_art_accent_label, self.right_art_accent_label):
            label.configure(bg=palette["surface_soft"], highlightbackground=palette["line"])
        self.detail_info_separator.configure(bg=palette["line"])
        self.left_art_title.configure(style="ArtTitle.TLabel")
        self.right_art_title.configure(style="ArtTitle.TLabel")
        self.apply_window_chrome(self, palette)
        self.refresh_dialog_themes(palette)

        self.load_tree_images()
        self.update_quick_access()
        self.apply_layout_preferences()

    def hide_shortcuts_hint(self) -> None:
        self.settings["show_shortcuts_hint"] = False
        self.update_shortcuts_hint_visibility()

    def update_shortcuts_hint_visibility(self) -> None:
        if self.settings.get("show_shortcuts_hint", True):
            self.hero_side_frame.grid()
        else:
            self.hero_side_frame.grid_remove()

    def load_data(self) -> None:
        base_records = safe_json_load(DICTIONARY_PATH, [])
        user_records = list_user_entries()
        combined = [prepare_record({**item, "_storage_source": "base"}) for item in base_records]
        combined.extend(prepare_record({**item, "_storage_source": "user"}) for item in user_records)
        combined = [item for item in combined if not should_hide_record(item)]
        self.records = combined
        self.noun_record_index = {
            (normalize_text(item.get("almanca", "")), normalize_text(item.get("artikel", ""))): item
            for item in combined
            if item.get("tur") == "isim" and item.get("almanca") and item.get("artikel")
        }

        summary = safe_json_load(SUMMARY_PATH, {})
        self.source_counts = dict(summary.get("sources", {}))
        if user_records:
            self.source_counts["kullanici-ekleme"] = len(user_records)

        self.pos_values = sorted({item.get("tur", "") for item in combined if item.get("tur")}, key=str.casefold)
        self.category_values = sorted(
            {category for item in combined for category in item.get("kategoriler", []) if category},
            key=str.casefold,
        )
        self.source_values = sorted(
            {source for item in combined for source in item.get("_source_names", []) if source},
            key=str.casefold,
        )

    def _show_loading_overlay(self) -> None:
        """Durum çubuğunu 'yükleniyor' olarak ayarla — overlay gösterme, veri zaten hızlı geliyor."""
        # Overlay kullanmıyoruz: ~1.6 sn yeterince kısa, ana pencere baştan görünür olsun
        self._splash_overlay = None

    def _load_data_bg(self) -> None:
        """Veriyi arka plan thread'inde yükle, bitince main thread'e bildir."""
        try:
            base_records = safe_json_load(DICTIONARY_PATH, [])
            user_records = list_user_entries()
            combined = [prepare_record({**item, "_storage_source": "base"}) for item in base_records]
            combined.extend(prepare_record({**item, "_storage_source": "user"}) for item in user_records)
            combined = [item for item in combined if not should_hide_record(item)]

            noun_record_index = {
                (normalize_text(item.get("almanca", "")), normalize_text(item.get("artikel", ""))): item
                for item in combined
                if item.get("tur") == "isim" and item.get("almanca") and item.get("artikel")
            }

            summary = safe_json_load(SUMMARY_PATH, {})
            source_counts = dict(summary.get("sources", {}))
            if user_records:
                source_counts["kullanici-ekleme"] = len(user_records)

            pos_values = sorted({item.get("tur", "") for item in combined if item.get("tur")}, key=str.casefold)
            category_values = sorted(
                {category for item in combined for category in item.get("kategoriler", []) if category},
                key=str.casefold,
            )
            source_values = sorted(
                {source for item in combined for source in item.get("_source_names", []) if source},
                key=str.casefold,
            )

            self.after(0, lambda: self._on_data_ready(
                combined, noun_record_index, source_counts,
                pos_values, category_values, source_values
            ))
        except Exception as exc:
            import traceback as _tb
            err_text = _tb.format_exc()
            try:
                (PROJECT_ROOT / "desktop_error.log").write_text(err_text, encoding="utf-8")
            except Exception:
                pass

            def _on_load_error(e=exc):
                # Overlay'i her halükarda kapat
                if hasattr(self, "_splash_overlay") and self._splash_overlay is not None:
                    try:
                        self._splash_overlay.destroy()
                    except Exception:
                        pass
                    self._splash_overlay = None
                self.result_summary_var.set(f"Veri yükleme hatası: {e}")

            self.after(0, _on_load_error)

    def _on_data_ready(
        self,
        combined: list,
        noun_record_index: dict,
        source_counts: dict,
        pos_values: list,
        category_values: list,
        source_values: list,
    ) -> None:
        """Arka plan thread'i bitince main thread'de çağrılır."""
        import traceback as _tb
        # Splash overlay'i her halükarda gizle
        if hasattr(self, "_splash_overlay") and self._splash_overlay is not None:
            try:
                self._splash_overlay.destroy()
            except Exception:
                pass
            self._splash_overlay = None
        # Ana pencereyi öne getir
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass
        try:
            self.records = combined
            self.noun_record_index = noun_record_index
            self.source_counts = source_counts
            self.pos_values = pos_values
            self.category_values = category_values
            self.source_values = source_values
            self.refresh_records()
        except Exception as exc:
            err = _tb.format_exc()
            try:
                (PROJECT_ROOT / "desktop_error.log").write_text(err, encoding="utf-8")
            except Exception:
                pass
            self.result_summary_var.set(f"Veri yükleme hatası: {exc}")

    def export_to_csv(self) -> None:
        """Sözlüğü CSV formatında dışa aktar (Anki uyumlu)."""
        import csv
        from tkinter import filedialog, messagebox

        path = filedialog.asksaveasfilename(
            title="CSV olarak kaydet",
            defaultextension=".csv",
            filetypes=[("CSV dosyası", "*.csv"), ("Tüm dosyalar", "*.*")],
            initialfile="almanca-sozluk-export.csv",
        )
        if not path:
            return

        # Use currently filtered records if search is active, else all records
        records_to_export = self.filtered_records if self.filtered_records else self.records

        fieldnames = ["Almanca", "Artikel", "Türkçe", "Tür", "Seviye", "Çoğul", "Partizip II",
                      "Perfekt Yardımcı", "Örnek (Almanca)", "Örnek (Türkçe)", "Kaynak"]

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in records_to_export:
                    artikel = r.get("artikel", "") or ""
                    almanca = r.get("almanca", "") or ""
                    word_display = f"{artikel} {almanca}".strip() if artikel else almanca
                    writer.writerow({
                        "Almanca": word_display,
                        "Artikel": artikel,
                        "Türkçe": r.get("turkce", "") or "",
                        "Tür": r.get("tur", "") or "",
                        "Seviye": r.get("seviye", "") or "",
                        "Çoğul": r.get("cogul", "") or "",
                        "Partizip II": r.get("partizip2", "") or "",
                        "Perfekt Yardımcı": r.get("perfekt_yardimci", "") or "",
                        "Örnek (Almanca)": r.get("ornek_almanca", "") or "",
                        "Örnek (Türkçe)": r.get("ornek_turkce", "") or "",
                        "Kaynak": r.get("kaynak", "") or "",
                    })
            messagebox.showinfo("Dışa Aktarma", f"{len(records_to_export)} kayıt başarıyla dışa aktarıldı.\n{path}")
        except Exception as exc:
            messagebox.showerror("Hata", f"CSV oluşturulamadı: {exc}")

    def show_statistics(self) -> None:
        """Sözlük istatistiklerini göster."""
        # Count records
        total = len(self.records)
        by_tur = {}
        by_seviye = {}
        missing_artikel = 0
        missing_turkce = 0
        has_example = 0

        for r in self.records:
            tur = r.get("tur") or "bilinmiyor"
            by_tur[tur] = by_tur.get(tur, 0) + 1

            seviye = r.get("seviye") or "—"
            by_seviye[seviye] = by_seviye.get(seviye, 0) + 1

            if r.get("tur") == "isim" and not (r.get("artikel") or "").strip():
                missing_artikel += 1
            if not (r.get("turkce") or "").strip():
                missing_turkce += 1
            if (r.get("ornek_almanca") or "").strip():
                has_example += 1

        # Count cached images from manifest
        cached_images = 0
        try:
            import json as _json
            from pathlib import Path as _Path
            _manifest_path = _Path(__file__).resolve().parents[1] / "output" / "word_image_manifest.json"
            if _manifest_path.exists():
                with open(_manifest_path, encoding="utf-8") as _f:
                    _manifest = _json.load(_f)
                cached_images = len(_manifest.get("entries", {}))
        except Exception:
            cached_images = -1

        # Build display text
        lines = [
            f"Toplam giriş: {total}",
            "",
            "— Kelime türüne göre —",
        ]
        for tur, count in sorted(by_tur.items(), key=lambda x: -x[1]):
            lines.append(f"  {tur}: {count}")

        lines += ["", "— CEFR seviyesine göre —"]
        for seviye in ["A1", "A2", "B1", "B2", "C1", "C2", "—"]:
            count = by_seviye.get(seviye, 0)
            if count:
                lines.append(f"  {seviye}: {count}")

        lines += [
            "",
            "— Veri kalitesi —",
            f"  İsim ama artikelsiz: {missing_artikel}",
            f"  Türkçe çevirisi eksik: {missing_turkce}",
            f"  Örnek cümlesi olan: {has_example} / {total}",
        ]

        if cached_images >= 0:
            lines += [
                "",
                "— Görsel önbellek —",
                f"  Önbellekteki kelime görseli: {cached_images}",
            ]

        text = "\n".join(lines)

        # Create popup
        win = tk.Toplevel(self)
        win.title("Sözlük İstatistikleri")
        win.geometry("400x500")
        win.resizable(True, True)

        txt = tk.Text(win, font=("Segoe UI", 11), wrap="word", padx=16, pady=16)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", text)
        txt.configure(state="disabled")

        ttk.Button(win, text="Kapat", command=win.destroy).pack(pady=8)

    def reload_data(self, select_key: tuple[str, str, str] | None = None) -> None:
        self.load_data()
        self.refresh_records(select_key=select_key)

    def apply_settings(self, payload: dict) -> None:
        self.settings = copy.deepcopy(payload)
        self.settings["search_action_buttons"] = sanitize_search_action_buttons(self.settings.get("search_action_buttons", []))
        self.settings["llm_api_url"] = build_llm_api_url(self.settings.get("llm_api_url", DEFAULT_SETTINGS["llm_api_url"]))
        self.settings["llm_model"] = str(self.settings.get("llm_model", DEFAULT_SETTINGS["llm_model"]) or DEFAULT_SETTINGS["llm_model"]).strip()
        if self.settings.get("art_layout_preset") not in ART_LAYOUT_PRESETS:
            self.settings["art_layout_preset"] = DEFAULT_SETTINGS["art_layout_preset"]
        self.settings["llm_api_key"] = str(self.settings.get("llm_api_key", "") or "").strip()
        self.settings["recent_searches"] = self.settings.get("recent_searches", [])[:MAX_RECENT_SEARCHES]
        self.settings["pinned_records"] = self.settings.get("pinned_records", [])[:MAX_PINNED_RECORDS]
        self.sync_menu_toggles()
        self.apply_theme()
        self.render_search_action_buttons()
        self.refresh_records(select_key=record_key(self.current_record) if self.current_record else None)

    def sync_menu_toggles(self) -> None:
        self.menu_show_stats_var.set(bool(self.settings.get("show_stats", False)))
        self.menu_show_quick_access_var.set(bool(self.settings.get("show_quick_access", False)))
        self.menu_show_results_panel_var.set(bool(self.settings.get("show_results_panel", False)))
        self.menu_show_extended_details_var.set(bool(self.settings.get("show_extended_details", False)))
        self.menu_show_detail_actions_var.set(bool(self.settings.get("show_detail_actions", False)))

    def get_search_action_command(self, action_key: str):
        commands = {
            "clear": self.clear_search,
            "google_translate": self.open_google_translate_for_search,
            "settings": self.open_settings,
            "new_entry": self.open_entry_dialog,
            "import_url": self.open_import_dialog,
            "parallel_text_import": self.open_parallel_text_import_dialog,
            "mini_quiz": self.open_quiz_dialog,
            "reload_data": self.reload_data,
        }
        return commands.get(action_key)

    def render_search_action_buttons(self) -> None:
        if not hasattr(self, "search_actions_frame"):
            return
        for child in self.search_actions_frame.winfo_children():
            child.destroy()

        for index, action_key in enumerate(sanitize_search_action_buttons(self.settings.get("search_action_buttons", []))):
            action = SEARCH_ACTION_OPTIONS.get(action_key)
            command = self.get_search_action_command(action_key)
            if not action or command is None:
                continue
            style_name = action.get("style")
            kwargs = {"text": action["label"], "command": command}
            if style_name:
                kwargs["style"] = style_name
            ttk.Button(self.search_actions_frame, **kwargs).grid(row=0, column=index, padx=(0 if index == 0 else 10, 0))

    def apply_menu_toggle(self, key: str, value: bool) -> None:
        self.settings[key] = bool(value)
        self.sync_menu_toggles()
        self.apply_layout_preferences()
        self.refresh_records(select_key=record_key(self.current_record) if self.current_record else None)

    def toggle_stats_from_menu(self) -> None:
        self.apply_menu_toggle("show_stats", self.menu_show_stats_var.get())

    def toggle_quick_access_from_menu(self) -> None:
        self.apply_menu_toggle("show_quick_access", self.menu_show_quick_access_var.get())

    def toggle_results_panel_from_menu(self) -> None:
        self.apply_menu_toggle("show_results_panel", self.menu_show_results_panel_var.get())

    def toggle_extended_details_from_menu(self) -> None:
        self.apply_menu_toggle("show_extended_details", self.menu_show_extended_details_var.get())

    def toggle_detail_actions_from_menu(self) -> None:
        self.apply_menu_toggle("show_detail_actions", self.menu_show_detail_actions_var.get())

    def show_shortcuts_help(self) -> None:
        messagebox.showinfo(
            "Kısayollar",
            "Ctrl+F: arama kutusuna git\nCtrl+N: yeni kelime\nCtrl+Shift+I: URL'den kelime aktar\nCtrl+Shift+M: metin eşleme aç\nCtrl+D: favorilere ekle / kaldır\nCtrl+R: veriyi yenile\nF10: ayarlar\nEsc: aramayı temizle",
            parent=self,
        )

    def load_entry_help_text(self) -> str:
        default_text = (
            "# Kelime Ekleme Rehberi\n\n"
            "1. Yeni Kelime\n"
            "- Uygulama > Yeni Kelime menüsünü açın.\n"
            "- Almanca, Türkçe ve tür alanlarını doldurun.\n"
            "- İsim ekliyorsanız artikel seçin.\n"
            "- İsterseniz kısa açıklama, örnek Almanca cümle ve Türkçe çevirisini de yazın.\n"
            "- Kaydedince kayıt hemen sözlükte görünür.\n\n"
            "2. URL'den Kelime Aktar\n"
            "- Uygulama > URL'den Kelime Aktar menüsünü açın.\n"
            "- Sayfa bağlantısını yapıştırın ve taratın.\n"
            "- Uygulama sayfadaki Almanca kelimeleri çıkarır, sözlükte olanları ayıklar.\n"
            "- Yeni Kelimeler sekmesinde adayları tek tek kontrol edip seçin.\n"
            "- İsterseniz sadece Türkçesi bulunan veya bulunmayanları filtreleyin.\n"
            "- Eklerken örnek cümle ve bulunabilirse Türkçe cümle çevirisi de kayda yazılır.\n\n"
            "3. Almanca Metin + Türkçe Çeviri ile Kelime Çıkarma\n"
            "- Uygulama > Metin Eşleme ile Kelime Çıkar menüsünü açın.\n"
            "- Almanca metni ve onun Türkçe çevirisini girin.\n"
            "- Uygulama iki metni karşılaştırıp güçlü kanıtlı yeni kelime adayları çıkarır.\n"
            "- Önerileri onaylayarak sözlüğe ekleyin.\n\n"
            "4. İpucu\n"
            "- Aynı kelime için birden fazla anlam varsa arama sonrası sonuç listesinden doğru kaydı seçin.\n"
            "- Kullanıcı eklediği kayıtları hemen aratabilir.\n"
        )
        try:
            text = ENTRY_HELP_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            return default_text
        return text or default_text

    def default_tutorial_payload(self) -> dict:
        return {
            "title": "Program Tutoriali",
            "intro": "Istediginiz bolumden baslayin. Sol listeden bir baslik secin, isterseniz sirayla ilerleyin.",
            "sections": [
                {
                    "id": "hizli_baslangic",
                    "title": "Hizli Baslangic",
                    "summary": "Programi ilk kez acan kullanici icin genel akis.",
                    "body": (
                        "Bu uygulamanin temel akisi cok kisa:\n\n"
                        "1. Arama kutusuna Almanca ya da Turkce bir kelime yazin.\n"
                        "2. Eslesme varsa sonuc otomatik secilir.\n"
                        "3. Birden fazla anlam varsa sonuc listesi veya mumkun anlamlar alanindan dogru kaydi secin.\n"
                        "4. Ayrintida kisa bilgi, Turkce tanim, ornekler ve kaynaklar gorulur.\n\n"
                        "Baslamak icin en hizli yol ana ekranda Ctrl+F ile arama kutusuna gitmek ve bir kelime yazmaktir."
                    ),
                },
                {
                    "id": "arama",
                    "title": "Arama ve Oneriler",
                    "summary": "Dropdown onerileri, eslesme mantigi ve temizleme kisayollari.",
                    "body": (
                        "Arama kutusu yazdikca oneri acabilir.\n\n"
                        "- Yon tuslariyla oneriler arasinda gezebilirsiniz.\n"
                        "- Enter ile secili oneriyi acabilirsiniz.\n"
                        "- Esc aramayi temizler.\n"
                        "- Ctrl+Backspace ve Ctrl+Delete de arama metnini tamamen temizler.\n\n"
                        "Aramada hem Almanca hem Turkce taraf taranir. Cinsiyet varyanti olan isimlerde tek kayit ailesi mantigi kullanilir."
                    ),
                },
                {
                    "id": "anlamlar",
                    "title": "Coklu Anlam ve Detay Alani",
                    "summary": "Bir kelimenin birden fazla anlami oldugunda nasil ilerlenir.",
                    "body": (
                        "Bazi kelimeler birden fazla tanimla gelir.\n\n"
                        "- Sonuc ozetinde kac eslesme bulundugu yazilir.\n"
                        "- Mumkun anlamlar bolumunde kisa anlam listesi gorunur.\n"
                        "- Bir maddeye tiklayinca tanim metni ilgili bolume gider.\n\n"
                        "Ozellikle teknik kelimelerde once uygun anlami secmek, sonra kaynak ve ornek cumlelere bakmak en dogru yoldur."
                    ),
                },
                {
                    "id": "kelime_ekleme",
                    "title": "Yeni Kelime Ekleme",
                    "summary": "Elle tek tek kayit acma akisi.",
                    "body": (
                        "Tek bir kelimeyi hizlica eklemek icin Uygulama > Yeni Kelime yolunu kullanin.\n\n"
                        "Zorunlu alanlar:\n"
                        "- Almanca\n"
                        "- Turkce\n"
                        "- Tur\n\n"
                        "Isim ekliyorsaniz artikel de secin. Istege bagli olarak kisa aciklama, not ve kaynak baglantisi ekleyebilirsiniz.\n\n"
                        "Kaydet dediginizde kayit hemen kullanici veri setine yazilir ve aramada gorunur."
                    ),
                },
                {
                    "id": "url_aktar",
                    "title": "URL'den Kelime Aktarma",
                    "summary": "Bir sayfadaki yeni kelimeleri topluca cikarma.",
                    "body": (
                        "Uygulama > URL'den Kelime Aktar ile bir sayfayi analiz edebilirsiniz.\n\n"
                        "Genel akis:\n"
                        "1. URL yapistirin.\n"
                        "2. Analizi baslatin.\n"
                        "3. Yeni Kelimeler sekmesindeki adaylari kontrol edin.\n"
                        "4. Sadece Turkcesi bulunan veya bulunmayan adaylari filtreleyin.\n"
                        "5. Sectiklerinizi onayla ekleyin.\n\n"
                        "Bu akista kelimenin gectigi cumle bulunursa ornek cumle de kayda eklenir. Turkce cumle cevirisi bulunabilirse o da doldurulur."
                    ),
                },
                {
                    "id": "metin_esleme",
                    "title": "Almanca Metin ve Turkce Ceviri Esleme",
                    "summary": "Iki paralel metinden kelime adayi cikarimi.",
                    "body": (
                        "Uygulama > Metin Eslestirme ile Kelime Cikar secenegi iki metni karsilastirir.\n\n"
                        "- Almanca metni girin.\n"
                        "- Ayni metnin Turkce cevirisini girin.\n"
                        "- Sistem guclu kanitli kelime eslesmelerini ve ornek cumleleri toplar.\n"
                        "- Mevcut sozlukte olan kayitlar ayiklanmaya calisilir.\n"
                        "- Son karar yine sizdedir; ekleme onayla yapilir.\n\n"
                        "Bu ozellik veri setini buyuturken en hizli yollardan biridir."
                    ),
                },
                {
                    "id": "ceviri",
                    "title": "Ceviri Yardimcilari",
                    "summary": "LibreTranslate karti ve Google Ceviri entegrasyonu.",
                    "body": (
                        "Arama alaninin altinda LibreTranslate ceviri karti bulunur.\n\n"
                        "- Kisa Almanca cumlelerde internet varsa uygulama icinden ceviri gorebilirsiniz.\n"
                        "- Google Ceviri dugmesi arama metnini dogrudan Almanca -> Turkce seklinde acar.\n"
                        "- URL ve kelime ekleme akislarinda ornek cumle Turkcesi de otomatik uretilmeye calisilir.\n\n"
                        "Cevrimiçi ceviri hiz icin yararlidir; supheli kayitlarda insan kontrolu yine onemlidir."
                    ),
                },
                {
                    "id": "gorseller_ve_tema",
                    "title": "Tema ve Fotograf Alanlari",
                    "summary": "Temalar, renkler ve guvenli fotograf alanlari.",
                    "body": (
                        "Ayarlar ekraninda tema, yazi boyutu ve fotograf alanlari kontrol edilir.\n\n"
                        "- Fotograf alanlari artik sadece sozlugu kapatmayan guvenli slotlarda kullanilir.\n"
                        "- Ust baslik, arama karti, sonuc bos durumu ve tanim karti kosesi ayri ayri yonetilebilir.\n"
                        "- Ozel fotograf secerseniz dosya uygulama icinde bu guvenli alana yerlestirilir.\n\n"
                        "Kural sabittir: fotograf uyarlanir, sozluk kaybolmaz."
                    ),
                },
                {
                    "id": "veri_seti_editoru",
                    "title": "Veri Seti Editoru",
                    "summary": "Gelistiriciye ozel toplu duzeltme araci.",
                    "body": (
                        "Araclar > Veri Seti Editoru (Gelistirici) ile mevcut kayitlari duzenleyebilirsiniz.\n\n"
                        "Bu pencerede:\n"
                        "- mevcut kelimeyi arayabilir,\n"
                        "- Turkce ceviriyi duzeltebilir,\n"
                        "- kisa aciklama ve not ekleyebilir,\n"
                        "- ornek Almanca ve Turkce cumleleri duzenleyebilirsiniz.\n\n"
                        "Bu arac veri setini iyilestirmek icin tasarlanmistir; yaptigi degisiklikler dogrudan veri dosyasina yazilir."
                    ),
                },
                {
                    "id": "ipuclari",
                    "title": "Sorun Cozme ve Ipuclari",
                    "summary": "Takilma, eksik sonuc ve kararsiz kayitlar icin hizli kontrol listesi.",
                    "body": (
                        "Beklenmedik bir durumda su sirayla kontrol edin:\n\n"
                        "1. Arama cok genisse daha uzun bir parca yazin.\n"
                        "2. Birden fazla eslesme varsa sonuc listesini acin.\n"
                        "3. Ceviri supheliyse Veri Seti Editoru ile kaydi duzeltin.\n"
                        "4. Yeni veri eklerken once onay ekranini kontrol edin.\n"
                        "5. Ayarlarda sade gorunum acik oldugunda bazi paneller gizlenebilir; bu bir hata olmayabilir.\n\n"
                        "Yardim menusu altindaki tutorial ve rehberler uygulama icinde tekrar tekrar acilabilir."
                    ),
                },
            ],
        }

    def load_tutorial_payload(self) -> dict:
        default_payload = self.default_tutorial_payload()
        payload = safe_json_load(TUTORIAL_PATH, default_payload)
        if not isinstance(payload, dict):
            return default_payload

        sections: list[dict] = []
        for index, raw_item in enumerate(payload.get("sections", []), start=1):
            if not isinstance(raw_item, dict):
                continue
            section_id = str(raw_item.get("id", f"bolum_{index}") or f"bolum_{index}").strip()
            title = str(raw_item.get("title", f"Bolum {index}") or f"Bolum {index}").strip()
            summary = str(raw_item.get("summary", "") or "").strip()
            body = str(raw_item.get("body", "") or "").strip()
            if not body:
                continue
            sections.append({"id": section_id, "title": title, "summary": summary, "body": body})

        if not sections:
            return default_payload

        return {
            "title": str(payload.get("title", default_payload["title"]) or default_payload["title"]).strip(),
            "intro": str(payload.get("intro", default_payload["intro"]) or default_payload["intro"]).strip(),
            "sections": sections,
        }

    def show_tutorial(self, section_id: str | None = None) -> None:
        if self.tutorial_dialog and self.tutorial_dialog.winfo_exists():
            self.tutorial_dialog.deiconify()
            self.tutorial_dialog.lift()
            self.tutorial_dialog.focus_force()
            self.tutorial_dialog.show_section(section_id=section_id)
            return

        dialog = TutorialDialog(self, self.load_tutorial_payload(), initial_section_id=section_id)
        self.tutorial_dialog = dialog

    def show_entry_help(self) -> None:
        if self.entry_help_dialog and self.entry_help_dialog.winfo_exists():
            self.entry_help_dialog.deiconify()
            self.entry_help_dialog.lift()
            self.entry_help_dialog.focus_force()
            return

        dialog = tk.Toplevel(self)
        dialog.title("Kelime Ekleme Rehberi")
        dialog.geometry("760x620")
        dialog.minsize(620, 460)
        dialog.transient(self)
        dialog.configure(bg=self.active_palette["bg"])
        self.apply_window_chrome(dialog, self.active_palette)

        wrapper = ttk.Frame(dialog, style="Panel.TFrame", padding=16)
        wrapper.pack(fill="both", expand=True)
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(1, weight=1)

        ttk.Label(wrapper, text="Kelime Ekleme Rehberi", style="DialogTitle.TLabel").grid(row=0, column=0, sticky="w")

        text_wrap = ttk.Frame(wrapper, style="ReadingCard.TFrame")
        text_wrap.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        text_wrap.columnconfigure(0, weight=1)
        text_wrap.rowconfigure(0, weight=1)

        help_text = tk.Text(text_wrap, wrap="word", relief="flat", padx=14, pady=14)
        help_text.grid(row=0, column=0, sticky="nsew")
        help_scroll = ttk.Scrollbar(text_wrap, orient="vertical", command=help_text.yview)
        help_scroll.grid(row=0, column=1, sticky="ns")
        help_text.configure(yscrollcommand=help_scroll.set)
        help_text.insert("1.0", self.load_entry_help_text())
        help_text.configure(state="disabled")
        help_text.configure(
            bg=self.active_palette["surface_soft"],
            fg=self.active_palette["ink"],
            highlightbackground=self.active_palette["line"],
            highlightcolor=self.active_palette["accent"],
            insertbackground=self.active_palette["accent"],
            selectbackground=self.active_palette["accent_soft"],
            selectforeground=self.active_palette["ink"],
            highlightthickness=1,
            bd=0,
        )

        button_row = ttk.Frame(wrapper, style="Panel.TFrame")
        button_row.grid(row=2, column=0, sticky="e", pady=(12, 0))
        ttk.Button(button_row, text="Tutoriali Ac", command=lambda: self.show_tutorial("kelime_ekleme")).grid(row=0, column=0)
        ttk.Button(button_row, text="Kapat", command=dialog.destroy).grid(row=0, column=1, padx=(8, 0))

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.entry_help_dialog = dialog

    def apply_window_icon(self) -> None:
        try:
            if APP_ICON_ICO_PATH.exists():
                self.iconbitmap(default=str(APP_ICON_ICO_PATH))
            if APP_ICON_PNG_PATH.exists():
                self.app_icon_image = tk.PhotoImage(file=str(APP_ICON_PNG_PATH))
                self.iconphoto(True, self.app_icon_image)
        except Exception:
            self.app_icon_image = None

    def focus_search_entry(self, select_all: bool = False) -> None:
        self.search_entry.focus_set()
        if select_all:
            self.schedule_search_selection(10)

    def schedule_search_selection(self, delay_ms: int = 320) -> None:
        if self.search_select_job:
            self.after_cancel(self.search_select_job)
            self.search_select_job = None
        if not self.search_var.get().strip():
            return
        self.search_select_job = self.after(delay_ms, self.select_search_text)

    def select_search_text(self) -> None:
        self.search_select_job = None
        if not self.search_var.get().strip():
            return
        if self.focus_get() != self.search_entry:
            return
        self.search_entry.selection_range(0, "end")
        self.search_entry.icursor("end")

    def cancel_search_refresh(self) -> None:
        if self.search_refresh_job:
            self.after_cancel(self.search_refresh_job)
            self.search_refresh_job = None

    def schedule_search_refresh(self, delay_ms: int = SEARCH_DEBOUNCE_MS) -> None:
        self.cancel_search_refresh()
        self.search_refresh_job = self.after(delay_ms, self.run_search_refresh)

    def run_search_refresh(self) -> None:
        self.search_refresh_job = None
        self.refresh_records()

    def refresh_search_now(self) -> None:
        self.cancel_search_refresh()
        self.refresh_records()

    def queue_local_translation(self, text: str) -> None:
        normalized_text = normalize_whitespace(text)
        self.current_local_translation_text = normalized_text
        if not normalized_text:
            self.local_translation_var.set("Almanca kelime veya cümle yazınca açık kaynak yerel çeviri burada görünür.")
            self.local_translation_source_var.set("Yerel çeviri motoru: Argos Translate. İnternet sekmesi açmadan çalışır.")
            return
        cached = _argos_translate_text_cache.get(normalized_text)
        if cached is not None:
            self.apply_local_translation_result(normalized_text, cached)
            return
        if normalized_text in self.local_translation_pending_terms:
            self.local_translation_var.set("Yerel çeviri hazırlanıyor...")
            self.local_translation_source_var.set("Argos Translate arka planda çalışıyor.")
            return
        self.local_translation_pending_terms.add(normalized_text)
        self.local_translation_var.set("Yerel çeviri hazırlanıyor...")
        self.local_translation_source_var.set("Argos Translate arka planda çalışıyor.")
        threading.Thread(
            target=self._local_translation_worker,
            args=(normalized_text,),
            daemon=True,
        ).start()

    def _local_translation_worker(self, text: str) -> None:
        try:
            result = translate_german_text_locally(text)
        except Exception as exc:
            result = {
                "status": "error",
                "translation": "",
                "source": f"Yerel çeviri kullanılamadı: {exc}",
            }
        self.local_translation_result_queue.put((text, result))

    def process_local_translation_results(self) -> None:
        try:
            while True:
                text, result = self.local_translation_result_queue.get_nowait()
                self.local_translation_pending_terms.discard(text)
                if text == self.current_local_translation_text:
                    self.apply_local_translation_result(text, result)
        except queue.Empty:
            pass
        finally:
            if self.winfo_exists():
                self.after(220, self.process_local_translation_results)

    def apply_local_translation_result(self, text: str, result: dict) -> None:
        if text != self.current_local_translation_text:
            return
        status = result.get("status", "")
        translation = normalize_whitespace(result.get("translation", ""))
        source = normalize_whitespace(result.get("source", ""))
        if status == "ok" and translation:
            self.local_translation_var.set(translation)
            self.local_translation_source_var.set(source or "Argos Translate (açık kaynak, yerel)")
            return
        if status == "unavailable":
            self.local_translation_var.set("Yerel açık kaynak çeviri hazır değil.")
            self.local_translation_source_var.set(source or "Argos Translate kurulmadı veya dil paketi eksik.")
            return
        self.local_translation_var.set("Yerel çeviri üretilemedi.")
        self.local_translation_source_var.set(source or "Argos Translate bu ifade için sonuç üretemedi.")

    def queue_local_translation(self, text: str) -> None:
        normalized_text = normalize_whitespace(text)
        self.current_local_translation_text = normalized_text
        if not normalized_text:
            self.local_translation_var.set("Almanca kelime veya cümle yazınca LibreTranslate çevirisi burada görünür.")
            self.local_translation_source_var.set("Çeviri motoru: LibreTranslate API. İnternet bağlantısı gerekir.")
            return

        endpoint = build_libretranslate_url(self.settings.get("libretranslate_url", DEFAULT_SETTINGS["libretranslate_url"]))
        cache_key = f"{endpoint}|{normalized_text}"
        cached = _libretranslate_text_cache.get(cache_key)
        if cached is not None:
            self.apply_local_translation_result(normalized_text, cached)
            return

        if normalized_text in self.local_translation_pending_terms:
            self.local_translation_var.set("LibreTranslate çevirisi hazırlanıyor...")
            self.local_translation_source_var.set("İnternet üzerinden çeviri isteği gönderiliyor.")
            return

        self.local_translation_pending_terms.add(normalized_text)
        self.local_translation_var.set("LibreTranslate çevirisi hazırlanıyor...")
        self.local_translation_source_var.set("İnternet üzerinden çeviri isteği gönderiliyor.")
        threading.Thread(
            target=self._local_translation_worker,
            args=(normalized_text,),
            daemon=True,
        ).start()

    def _local_translation_worker(self, text: str) -> None:
        try:
            result = translate_german_text_with_libretranslate(
                text,
                self.settings.get("libretranslate_url", DEFAULT_SETTINGS["libretranslate_url"]),
                self.settings.get("libretranslate_api_key", DEFAULT_SETTINGS["libretranslate_api_key"]),
            )
        except Exception as exc:
            result = {
                "status": "error",
                "translation": "",
                "source": f"LibreTranslate çevirisi alınamadı: {exc}",
            }
        self.local_translation_result_queue.put((text, result))

    def apply_local_translation_result(self, text: str, result: dict) -> None:
        if text != self.current_local_translation_text:
            return

        status = result.get("status", "")
        translation = normalize_whitespace(repair_mojibake_text(result.get("translation", "")))
        source = normalize_whitespace(repair_mojibake_text(result.get("source", "")))
        if status == "ok" and translation:
            self.local_translation_var.set(translation)
            self.local_translation_source_var.set(source or "LibreTranslate (çevrimiçi çeviri)")
            return
        if status == "offline":
            self.local_translation_var.set("LibreTranslate çevirisi için internet bağlantısı gerekiyor.")
            self.local_translation_source_var.set(source or "Çevrimiçi çeviri hizmetine ulaşılamadı.")
            return
        if status == "unavailable":
            self.local_translation_var.set("LibreTranslate ayarı hazır değil.")
            self.local_translation_source_var.set(source or "API adresi veya erişim bilgisi eksik.")
            return

        self.local_translation_var.set("LibreTranslate çevirisi üretilemedi.")
        self.local_translation_source_var.set(source or "Çeviri servisi bu ifade için sonuç üretemedi.")

    def _on_compact_scroll_body_configure(self, _event=None) -> None:
        """Update compact canvas scrollregion after layout changes (including async image loads)."""
        if self.compact_scroll_canvas.winfo_exists():
            self.compact_scroll_body.update_idletasks()
            self.compact_scroll_canvas.configure(
                scrollregion=self.compact_scroll_canvas.bbox("all")
            )

    def sync_record_image_container_visibility(self) -> None:
        has_image = bool(self.record_image_photo)
        use_compact_container = not bool(self.settings.get("show_extended_details", False))
        if use_compact_container:
            self.record_image_frame.grid_remove()
            if has_image:
                self.compact_record_image_frame.grid()
            else:
                self.compact_record_image_frame.grid_remove()
        else:
            self.compact_record_image_frame.grid_remove()
            if has_image:
                self.record_image_frame.grid()
            else:
                self.record_image_frame.grid_remove()
        # Delayed scrollregion update so tkinter finishes computing layout first
        self.after(30, self._on_compact_scroll_body_configure)

    def should_show_results_panel(self) -> bool:
        if self.settings.get("show_results_panel", False):
            return True
        active_search = bool(self.search_var.get().strip())
        return active_search and len(self.filtered_records) > 1

    def get_record_image_term(self, record: dict | None) -> str:
        if not record:
            return ""
        return normalize_whitespace(record.get("almanca", "") or strip_known_article(record.get("_word", "")))

    def clear_record_image(self, note: str = "") -> None:
        self.close_record_image_preview()
        self.record_image_photo = None
        self.current_record_image_path = ""
        self.record_image_label.configure(image="", cursor="arrow")
        self.compact_record_image_label.configure(image="", cursor="arrow")
        self.compact_record_image_label.configure(image="", cursor="arrow")
        self.record_image_note_var.set(note or "Bu kayıt için açık kaynak görsel bulunursa burada görünür.")

    def load_record_image_photo(self, path_text: str) -> tk.PhotoImage | None:
        if not PIL_AVAILABLE or not path_text:
            return None
        path = Path(path_text)
        if not path.exists():
            return None
        target_width = max(220, min(460, self.right_panel.winfo_width() - 120 if self.right_panel.winfo_exists() else 380))
        target_height = 200
        with Image.open(path) as source_image:
            image = ImageOps.exif_transpose(source_image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")
            image.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image)

    def close_record_image_preview(self, *_args) -> None:
        dialog = self.record_image_preview_dialog
        self.record_image_preview_dialog = None
        self.record_image_preview_photo = None
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()

        self.sync_record_image_container_visibility()
        self.sync_record_image_container_visibility()

    def open_record_image_preview(self, _event=None) -> None:
        if not PIL_AVAILABLE or not self.current_record_image_path:
            return
        path = Path(self.current_record_image_path)
        if not path.exists():
            return

        self.close_record_image_preview()

        screen_width = max(900, int(self.winfo_screenwidth() * 0.82))
        screen_height = max(640, int(self.winfo_screenheight() * 0.82))
        image_max_width = max(520, screen_width - 80)
        image_max_height = max(420, screen_height - 140)

        with Image.open(path) as source_image:
            image = ImageOps.exif_transpose(source_image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")
            image.thumbnail((image_max_width, image_max_height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)

        palette = self.active_palette
        dialog = tk.Toplevel(self)
        dialog.title("Görsel Önizleme")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=palette["bg"])
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", self.close_record_image_preview)
        dialog.bind("<Escape>", self.close_record_image_preview)
        dialog.bind("<Key>", self.close_record_image_preview)
        self.apply_window_chrome(dialog, palette)

        wrapper = ttk.Frame(dialog, style="Panel.TFrame", padding=18)
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.columnconfigure(0, weight=1)

        image_label = tk.Label(wrapper, image=photo, bd=0, highlightthickness=0, bg=palette["panel"])
        image_label.grid(row=0, column=0, sticky="nsew")
        image_label.bind("<Button-1>", self.close_record_image_preview)

        hint = ttk.Label(
            wrapper,
            text="Kapatmak için herhangi bir tuşa basın, görsele tıklayın veya sağ üstteki X'i kullanın.",
            style="ReadingMuted.TLabel",
            justify="center",
            wraplength=image_max_width,
        )
        hint.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.lift()
        dialog.focus_force()

        self.record_image_preview_photo = photo
        self.record_image_preview_dialog = dialog

    def apply_record_image_result(self, record_key_text: str, payload: dict) -> None:
        if record_key_text != self.current_record_image_key:
            return
        status = payload.get("status", "")
        if status != "ok":
            if status == "cache_full":
                self.clear_record_image(
                    f"Kelime görsel önbelleği {WORD_IMAGE_CACHE_LIMIT_BYTES // (1024 * 1024)} MB sınırına ulaştı. Yeni görsel indirilmedi."
                )
            else:
                self.clear_record_image(payload.get("note", "Bu kayıt için uygun açık kaynak görsel bulunamadı."))
            return

        image_path = str(payload.get("path", "")).strip()
        photo = self.load_record_image_photo(image_path)
        if photo is None:
            self.clear_record_image("Görsel indirildi fakat önizleme hazırlanamadı.")
            return
        note_parts = []
        description = normalize_whitespace(payload.get("description", ""))
        attribution = normalize_whitespace(payload.get("attribution", ""))
        if description:
            note_parts.append(description)
        if attribution:
            note_parts.append(attribution)
        elif normalize_whitespace(payload.get("license", "")):
            note_parts.append(payload.get("license", ""))
        self.current_record_image_path = image_path
        self.record_image_photo = photo
        self.record_image_label.configure(image=photo, cursor="hand2")
        self.compact_record_image_label.configure(image=photo, cursor="hand2")
        self.record_image_note_var.set(" · ".join(note_parts) if note_parts else "Açık kaynak çevrimdışı görsel.")
        self.sync_record_image_container_visibility()

    def queue_record_image(self, record: dict | None) -> None:
        if not record:
            self.current_record_image_key = ""
            self.record_image_frame.grid_remove()
            self.compact_record_image_frame.grid_remove()
            self.clear_record_image("Bu kayıt için açık kaynak görsel bulunursa burada görünür.")
            return

        term = self.get_record_image_term(record)
        key_text = image_cache_key(term)
        self.current_record_image_key = key_text
        self.sync_record_image_container_visibility()
        if not term:
            self.clear_record_image("Bu kayıt için görsel aranacak bir Almanca terim bulunamadı.")
            return

        cached = load_cached_word_image(term)
        if cached.get("status") in {"ok", "not_found"}:
            self.apply_record_image_result(key_text, cached)
            return
        if key_text in self.record_image_pending_terms:
            self.clear_record_image("Açık kaynak görsel aranıyor ve küçük boyutta indiriliyor...")
            return
        self.record_image_pending_terms.add(key_text)
        self.clear_record_image("Açık kaynak görsel aranıyor ve küçük boyutta indiriliyor...")
        threading.Thread(target=self._record_image_worker, args=(term, key_text), daemon=True).start()

    def _record_image_worker(self, term: str, key_text: str) -> None:
        try:
            payload = ensure_word_image_cached(term)
        except Exception as exc:
            payload = {"status": "error", "note": f"Görsel indirilemedi: {exc}"}
        self.record_image_result_queue.put((key_text, payload))

    def process_record_image_results(self) -> None:
        try:
            while True:
                key_text, payload = self.record_image_result_queue.get_nowait()
                self.record_image_pending_terms.discard(key_text)
                if key_text == self.current_record_image_key:
                    self.apply_record_image_result(key_text, payload)
        except queue.Empty:
            pass
        finally:
            if self.winfo_exists():
                self.after(260, self.process_record_image_results)

    def clear_record_image(self, note: str = "") -> None:
        self.close_record_image_preview()
        self.record_image_photo = None
        self.current_record_image_path = ""
        self.record_image_label.configure(image="", cursor="arrow")
        note_text = repair_mojibake_text(note)
        self.record_image_note_var.set(note_text or "Bu kayıt için açık kaynak görsel bulunursa burada görünür.")

    def open_record_image_preview(self, _event=None) -> None:
        if not PIL_AVAILABLE or not self.current_record_image_path:
            return
        path = Path(self.current_record_image_path)
        if not path.exists():
            return

        self.close_record_image_preview()

        screen_width = max(900, int(self.winfo_screenwidth() * 0.82))
        screen_height = max(640, int(self.winfo_screenheight() * 0.82))
        image_max_width = max(520, screen_width - 80)
        image_max_height = max(420, screen_height - 140)

        with Image.open(path) as source_image:
            image = ImageOps.exif_transpose(source_image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")
            image.thumbnail((image_max_width, image_max_height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)

        palette = self.active_palette
        dialog = tk.Toplevel(self)
        dialog.title("Görsel Önizleme")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=palette["bg"])
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", self.close_record_image_preview)
        dialog.bind("<Escape>", self.close_record_image_preview)
        dialog.bind("<Key>", self.close_record_image_preview)
        self.apply_window_chrome(dialog, palette)

        wrapper = ttk.Frame(dialog, style="Panel.TFrame", padding=18)
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.columnconfigure(0, weight=1)

        image_label = tk.Label(wrapper, image=photo, bd=0, highlightthickness=0, bg=palette["panel"])
        image_label.grid(row=0, column=0, sticky="nsew")
        image_label.bind("<Button-1>", self.close_record_image_preview)

        hint = ttk.Label(
            wrapper,
            text="Kapatmak için herhangi bir tuşa basın, görsele tıklayın veya sağ üstteki X'i kullanın.",
            style="ReadingMuted.TLabel",
            justify="center",
            wraplength=image_max_width,
        )
        hint.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.lift()
        dialog.focus_force()

        self.record_image_preview_photo = photo
        self.record_image_preview_dialog = dialog

    def apply_record_image_result(self, record_key_text: str, payload: dict) -> None:
        if record_key_text != self.current_record_image_key:
            return
        status = payload.get("status", "")
        if status != "ok":
            if status == "cache_full":
                self.clear_record_image(
                    f"Kelime görsel önbelleği {WORD_IMAGE_CACHE_LIMIT_BYTES // (1024 * 1024)} MB sınırına ulaştı. Yeni görsel indirilmedi."
                )
            else:
                self.clear_record_image(repair_mojibake_text(payload.get("note", "Bu kayıt için uygun açık kaynak görsel bulunamadı.")))
            return

        image_path = str(payload.get("path", "")).strip()
        photo = self.load_record_image_photo(image_path)
        if photo is None:
            self.clear_record_image("Görsel indirildi fakat önizleme hazırlanamadı.")
            return

        description = normalize_whitespace(repair_mojibake_text(payload.get("description", "")))
        attribution = normalize_whitespace(repair_mojibake_text(payload.get("attribution", "")))
        license_text = normalize_whitespace(repair_mojibake_text(payload.get("license", "")))
        note_parts = []
        if description:
            note_parts.append(description)
        if attribution:
            note_parts.append(attribution)
        elif license_text:
            note_parts.append(license_text)

        self.current_record_image_path = image_path
        self.record_image_photo = photo
        self.record_image_label.configure(image=photo, cursor="hand2")
        self.record_image_note_var.set(" · ".join(note_parts) if note_parts else "Açık kaynak çevrimdışı görsel.")

    def clear_record_image(self, note: str = "") -> None:
        self.close_record_image_preview()
        self.record_image_photo = None
        self.current_record_image_path = ""
        self.record_image_label.configure(image="", cursor="arrow")
        self.compact_record_image_label.configure(image="", cursor="arrow")
        note_text = repair_mojibake_text(note)
        self.record_image_note_var.set(note_text or "Bu kayıt için açık kaynak görsel bulunursa burada görünür.")
        self.sync_record_image_container_visibility()

    def apply_record_image_result(self, record_key_text: str, payload: dict) -> None:
        if record_key_text != self.current_record_image_key:
            return
        status = payload.get("status", "")
        if status != "ok":
            if status == "cache_full":
                self.clear_record_image(
                    f"Kelime görsel önbelleği {WORD_IMAGE_CACHE_LIMIT_BYTES // (1024 * 1024)} MB sınırına ulaştı. Yeni görsel indirilmedi."
                )
            else:
                self.clear_record_image(repair_mojibake_text(payload.get("note", "Bu kayıt için uygun açık kaynak görsel bulunamadı.")))
            return

        image_path = str(payload.get("path", "")).strip()
        photo = self.load_record_image_photo(image_path)
        if photo is None:
            self.clear_record_image("Görsel indirildi fakat önizleme hazırlanamadı.")
            return

        description = normalize_whitespace(repair_mojibake_text(payload.get("description", "")))
        attribution = normalize_whitespace(repair_mojibake_text(payload.get("attribution", "")))
        license_text = normalize_whitespace(repair_mojibake_text(payload.get("license", "")))
        note_parts = []
        if description:
            note_parts.append(description)
        if attribution:
            note_parts.append(attribution)
        elif license_text:
            note_parts.append(license_text)

        self.current_record_image_path = image_path
        self.record_image_photo = photo
        self.record_image_label.configure(image=photo, cursor="hand2")
        self.compact_record_image_label.configure(image=photo, cursor="hand2")
        self.record_image_note_var.set(" · ".join(note_parts) if note_parts else "Açık kaynak çevrimdışı görsel.")
        self.sync_record_image_container_visibility()

    def cancel_window_layout_refresh(self) -> None:
        if self.window_layout_job:
            self.after_cancel(self.window_layout_job)
            self.window_layout_job = None

    def schedule_window_layout_refresh(self, delay_ms: int = 70) -> None:
        self.cancel_window_layout_refresh()
        self.window_layout_job = self.after(delay_ms, self.run_window_layout_refresh)

    def run_window_layout_refresh(self) -> None:
        self.window_layout_job = None
        self.update_tree_visibility()

    def on_window_configure(self, _event=None) -> None:
        self.schedule_window_layout_refresh()

    def load_image_for_slot(
        self,
        slot_key: str,
        option_key: str,
        target_size: tuple[int, int],
        horizontal_focus: str = "center",
        vertical_focus: str = "center",
    ):
        custom_slots = sanitize_custom_art_slots(self.settings.get("custom_art_slots", {}))
        custom_config = custom_slots.get(slot_key, {})
        custom_path = str(custom_config.get("path", "")).strip()
        if custom_path:
            image = load_custom_slot_photo_image(custom_path, target_size, custom_config)
            if image is not None:
                return image
        return load_slot_photo_image(
            option_key,
            slot_key,
            target_size=target_size,
            horizontal_focus=horizontal_focus,
            vertical_focus=vertical_focus,
        )

    def is_art_slot_expanded(self, slot_key: str) -> bool:
        return bool(self.settings.get(f"expand_art_{slot_key}", False))

    def get_active_art_layout_preset(self) -> dict:
        preset_key = self.settings.get("art_layout_preset", DEFAULT_SETTINGS["art_layout_preset"])
        return ART_LAYOUT_PRESETS.get(preset_key, ART_LAYOUT_PRESETS[DEFAULT_SETTINGS["art_layout_preset"]])

    def get_art_sidebar_base_width(self) -> int:
        if self.is_art_slot_expanded("right_main") or self.is_art_slot_expanded("right_accent"):
            return RIGHT_ART_SIDEBAR_WIDTH_EXPANDED
        return RIGHT_ART_SIDEBAR_WIDTH

    def get_max_art_sidebar_width(self, total_width: int | None = None) -> int:
        available_total = total_width or self.winfo_width() or self.outer_paned.winfo_width()
        if available_total <= 0:
            return self.get_art_sidebar_base_width()
        ratio_width = int(round(available_total * 0.25))
        remaining_limit = max(RIGHT_ART_SIDEBAR_MIN_WIDTH, available_total - MAIN_CONTENT_MIN_WIDTH - 36)
        return max(RIGHT_ART_SIDEBAR_MIN_WIDTH, min(ratio_width, remaining_limit))

    def get_art_target_size(self, slot_key: str) -> tuple[int, int]:
        if slot_key == "right_main":
            base_size = RIGHT_ART_MAIN_SIZE_EXPANDED if self.is_art_slot_expanded(slot_key) else RIGHT_ART_MAIN_SIZE
            card_width = self.get_art_inner_width()
            aspect_ratio = base_size[1] / max(1, base_size[0])
            return (
                max(160, card_width) - (RIGHT_ART_FRAME_BORDER * 2),
                max(160, int(round(card_width * aspect_ratio))) - (RIGHT_ART_FRAME_BORDER * 2),
            )
        if slot_key == "right_accent":
            base_size = RIGHT_ART_ACCENT_SIZE_EXPANDED if self.is_art_slot_expanded(slot_key) else RIGHT_ART_ACCENT_SIZE
            card_width = self.get_art_inner_width()
            aspect_ratio = base_size[1] / max(1, base_size[0])
            default_height = max(120, int(round(card_width * aspect_ratio))) - (RIGHT_ART_FRAME_BORDER * 2)
            dynamic_height = default_height
            if hasattr(self, "right_art_sidebar"):
                self.update_idletasks()
                sidebar, title, main_card, _main_label, _accent_card, _accent_label = self.get_art_sidebar_widgets("right")
                sidebar_height = sidebar.winfo_height()
                title_height = title.winfo_reqheight()
                available_height = max(0, sidebar_height - title_height - 28)
                main_height = safe_int(main_card.cget("height"), RIGHT_ART_MAIN_SIZE[1] + (RIGHT_ART_FRAME_BORDER * 2))
                remaining_height = available_height - main_height - 12 - (RIGHT_ART_FRAME_BORDER * 2)
                if remaining_height > default_height:
                    dynamic_height = remaining_height
            return (
                max(160, card_width) - (RIGHT_ART_FRAME_BORDER * 2),
                dynamic_height,
            )
        if self.is_art_slot_expanded(slot_key):
            return ART_SLOT_EXPANDED_LIMITS.get(slot_key, ART_SLOT_LIMITS.get(slot_key, (320, 220)))
        return ART_SLOT_LIMITS.get(slot_key, (320, 220))

    def get_preferred_art_sidebar_width(self, total_width: int | None = None) -> int:
        ratio_width = self.get_max_art_sidebar_width(total_width)
        if not self.settings.get("allow_art_sidebar_resize", DEFAULT_SETTINGS["allow_art_sidebar_resize"]):
            return ratio_width
        stored_width = safe_int(self.settings.get("art_sidebar_width"), ratio_width)
        return max(RIGHT_ART_SIDEBAR_MIN_WIDTH, min(stored_width, ratio_width))

    def get_art_inner_width(self, sidebar_width: int | None = None) -> int:
        effective_width = max(RIGHT_ART_SIDEBAR_MIN_WIDTH, safe_int(sidebar_width, self.get_preferred_art_sidebar_width()))
        return max(160, effective_width - RIGHT_ART_CARD_HORIZONTAL_GAP)

    def get_art_sidebar_widgets(self, side_key: str) -> tuple[ttk.Frame, ttk.Label, ttk.Frame, tk.Label, ttk.Frame, tk.Label]:
        return (
            getattr(self, f"{side_key}_art_sidebar"),
            getattr(self, f"{side_key}_art_title"),
            getattr(self, f"{side_key}_art_main_card"),
            getattr(self, f"{side_key}_art_main_label"),
            getattr(self, f"{side_key}_art_accent_card"),
            getattr(self, f"{side_key}_art_accent_label"),
        )

    def apply_art_container_sizes(self) -> None:
        total_width = self.winfo_width() or self.outer_paned.winfo_width()
        sidebar_width = self.get_preferred_art_sidebar_width(total_width)
        right_main_size = self.get_art_target_size("right_main")
        right_accent_size = self.get_art_target_size("right_accent")

        sidebar, _title, main_card, main_label, accent_card, accent_label = self.get_art_sidebar_widgets("right")
        sidebar.configure(width=sidebar_width)
        main_card.configure(
            width=right_main_size[0] + (RIGHT_ART_FRAME_BORDER * 2),
            height=right_main_size[1] + (RIGHT_ART_FRAME_BORDER * 2),
        )
        accent_card.configure(
            width=right_accent_size[0] + (RIGHT_ART_FRAME_BORDER * 2),
            height=right_accent_size[1] + (RIGHT_ART_FRAME_BORDER * 2),
        )
        self.grid_columnconfigure(1, minsize=sidebar_width + 18)

    def update_art_sidebar_layout(self, side_key: str) -> None:
        if not hasattr(self, f"{side_key}_art_sidebar"):
            return

        sidebar, title, main_card, _main_label, accent_card, _accent_label = self.get_art_sidebar_widgets(side_key)
        main_image = getattr(self, f"{side_key}_sidebar_main_image")
        accent_image = getattr(self, f"{side_key}_sidebar_accent_image")
        self.update_idletasks()
        sidebar_height = sidebar.winfo_height()
        title_height = title.winfo_reqheight() if hasattr(self, f"{side_key}_art_title") else 0
        available_height = max(0, sidebar_height - title_height - 28)
        main_height = safe_int(main_card.cget("height"), RIGHT_ART_MAIN_SIZE[1])
        accent_height = safe_int(accent_card.cget("height"), RIGHT_ART_ACCENT_SIZE[1])
        card_gap = 12

        show_main = main_image is not None
        show_accent = accent_image is not None

        if show_main and show_accent and available_height < (main_height + accent_height + card_gap):
            show_accent = False

        for row in range(6):
            sidebar.rowconfigure(row, weight=0)

        if show_main:
            main_card.grid()
        else:
            main_card.grid_remove()

        if show_accent:
            accent_card.grid()
        else:
            accent_card.grid_remove()

        visible_count = int(show_main) + int(show_accent)
        if visible_count <= 1:
            sidebar.rowconfigure(1, weight=1)
            sidebar.rowconfigure(5, weight=1)
            if show_main:
                main_card.grid_configure(row=2, sticky="")
            if show_accent:
                accent_card.grid_configure(row=2, sticky="")
        else:
            sidebar.rowconfigure(5, weight=1)
            main_card.grid_configure(row=2, sticky="")
            accent_card.grid_configure(row=4, sticky="")

    def update_all_art_sidebar_layouts(self) -> None:
        self.update_art_sidebar_layout("right")

    def is_art_sidebar_visible(self, side_key: str) -> bool:
        sidebar, _title, _main_card, _main_label, _accent_card, _accent_label = self.get_art_sidebar_widgets(side_key)
        return bool(sidebar.winfo_manager())

    def are_art_sidebars_visible(self) -> bool:
        return self.is_art_sidebar_visible("right")

    def set_art_sidebars_visibility(self, visible: bool) -> None:
        if self._updating_art_visibility:
            return
        if not hasattr(self, "right_art_sidebar"):
            return
        self._updating_art_visibility = True
        try:
            if visible:
                if not self.right_art_sidebar.winfo_manager():
                    self.right_art_sidebar.grid(row=0, column=1, sticky="nsew", padx=(0, 18), pady=(18, 20))
            else:
                if self.right_art_sidebar.winfo_manager():
                    self.right_art_sidebar.grid_remove()
                self.grid_columnconfigure(1, minsize=0)
        finally:
            self._updating_art_visibility = False

    def apply_art_sidebar_width(self, preferred_width: int | None = None, force: bool = False) -> None:
        if not hasattr(self, "right_art_sidebar") or not self.is_art_sidebar_visible("right"):
            return
        desired_width = max(RIGHT_ART_SIDEBAR_MIN_WIDTH, safe_int(preferred_width, self.get_preferred_art_sidebar_width()))
        self.right_art_sidebar.configure(width=desired_width)
        self.grid_columnconfigure(1, minsize=desired_width + 18)

    def store_art_sidebar_width(self) -> None:
        if not self.settings.get("allow_art_sidebar_resize", DEFAULT_SETTINGS["allow_art_sidebar_resize"]):
            return
        if not self.is_art_sidebar_visible("right"):
            return
        width = round(self.right_art_sidebar.winfo_width())
        if width >= RIGHT_ART_SIDEBAR_MIN_WIDTH:
            self.settings["art_sidebar_width"] = min(width, self.get_max_art_sidebar_width())

    def cancel_art_reload(self) -> None:
        if self.art_reload_job:
            self.after_cancel(self.art_reload_job)
            self.art_reload_job = None

    def schedule_art_reload(self, delay_ms: int = 90) -> None:
        self.cancel_art_reload()
        self.art_reload_job = self.after(delay_ms, self.run_art_reload)

    def run_art_reload(self) -> None:
        self.art_reload_job = None
        self.load_tree_images()

    def on_art_sidebar_configure(self, _event=None) -> None:
        return

    def on_outer_paned_release(self, _event=None) -> None:
        return

    def load_tree_images(self) -> None:
        self.left_sidebar_main_image = None
        self.left_sidebar_accent_image = None
        self.right_sidebar_main_image = None
        self.right_sidebar_accent_image = None
        self.hero_bg_image = None
        self.search_bg_image = None
        self.results_bg_image = None
        self.leaves_bg_image = None
        self.apply_art_container_sizes()

        if self.settings.get("show_background_art", True):
            if self.settings.get("show_art_right_main", False):
                self.right_sidebar_main_image = self.load_image_for_slot(
                    "right_main",
                    self.settings.get("hero_background_art", DEFAULT_SETTINGS["hero_background_art"]),
                    target_size=self.get_art_target_size("right_main"),
                    horizontal_focus="right",
                )
            if self.settings.get("show_art_right_accent", False):
                self.right_sidebar_accent_image = self.load_image_for_slot(
                    "right_accent",
                    self.settings.get("detail_background_art", DEFAULT_SETTINGS["detail_background_art"]),
                    target_size=self.get_art_target_size("right_accent"),
                    horizontal_focus="right",
                )
            if self.settings.get("show_art_hero", False):
                self.hero_bg_image = self.load_image_for_slot(
                    "hero",
                    self.settings.get("hero_banner_art", DEFAULT_SETTINGS["hero_banner_art"]),
                    target_size=self.get_art_target_size("hero"),
                    horizontal_focus="right",
                )
            if self.settings.get("show_art_search", False):
                self.search_bg_image = self.load_image_for_slot(
                    "search",
                    self.settings.get("search_background_art", DEFAULT_SETTINGS["search_background_art"]),
                    target_size=self.get_art_target_size("search"),
                    horizontal_focus="right",
                )
            if self.settings.get("show_art_results", False):
                self.results_bg_image = self.load_image_for_slot(
                    "results",
                    self.settings.get("results_background_art", DEFAULT_SETTINGS["results_background_art"]),
                    target_size=self.get_art_target_size("results"),
                    horizontal_focus="right",
                )
            if self.settings.get("show_art_detail", False):
                self.leaves_bg_image = self.load_image_for_slot(
                    "detail",
                    self.settings.get("compact_background_art", DEFAULT_SETTINGS["compact_background_art"]),
                    target_size=self.get_art_target_size("detail"),
                    horizontal_focus="right",
                )

        self.hero_bg_label.configure(image="")
        self.search_bg_label.configure(image="")
        self.results_empty_bg_label.configure(image="")
        self.detail_empty_bg_label.configure(image="")
        self.compact_bg_label.configure(image="")

        self.left_art_main_label.configure(image=self.left_sidebar_main_image or "")
        self.left_art_accent_label.configure(image=self.left_sidebar_accent_image or "")
        self.right_art_main_label.configure(image=self.right_sidebar_main_image or "")
        self.right_art_accent_label.configure(image=self.right_sidebar_accent_image or "")
        if self.hero_bg_image is not None:
            self.hero_bg_label.configure(image=self.hero_bg_image)
        if self.search_bg_image is not None:
            self.search_bg_label.configure(image=self.search_bg_image)
        if self.results_bg_image is not None:
            self.results_empty_bg_label.configure(image=self.results_bg_image)
        if self.leaves_bg_image is not None:
            self.detail_empty_bg_label.configure(image=self.leaves_bg_image)
            self.compact_bg_label.configure(image=self.leaves_bg_image)
        self.update_all_art_sidebar_layouts()
        self.update_tree_visibility()

    def update_tree_visibility(self) -> None:
        if self._updating_art_visibility or self._applying_art_sidebar_width:
            return
        has_right_sidebar_art = bool(self.right_sidebar_main_image or self.right_sidebar_accent_image)
        total_width = self.winfo_width() or self.outer_paned.winfo_width()
        enough_room = total_width >= (MAIN_CONTENT_MIN_WIDTH + RIGHT_ART_SIDEBAR_MIN_WIDTH + 36)
        show_right_sidebar = bool(self.settings.get("show_background_art", True) and has_right_sidebar_art and enough_room)
        self.set_art_sidebars_visibility(show_right_sidebar)
        if show_right_sidebar:
            self.apply_art_container_sizes()
            self.update_all_art_sidebar_layouts()

    def apply_layout_preferences(self) -> None:
        self.update_shortcuts_hint_visibility()

        self.stats_row.grid_remove()

        self.quick_frame.grid_remove()

        panes = set(self.body_paned.panes())
        right_name = str(self.right_panel)
        left_name = str(self.left_panel)
        show_results_panel = True
        if show_results_panel:
            if left_name not in panes or right_name not in panes:
                if left_name in panes:
                    self.body_paned.forget(self.left_panel)
                if right_name in panes:
                    self.body_paned.forget(self.right_panel)
                self.body_paned.add(self.left_panel, weight=1)
                self.body_paned.add(self.right_panel, weight=1)
        else:
            if left_name in panes:
                self.body_paned.forget(self.left_panel)
            if right_name not in set(self.body_paned.panes()):
                self.body_paned.add(self.right_panel, weight=1)

        if self.settings.get("show_detail_actions", False):
            self.detail_actions_frame.grid()
        else:
            self.detail_actions_frame.grid_remove()

        if self.settings.get("show_extended_details", False):
            self.summary_strip.grid()
            self.detail_info_separator.grid()
            self.meta_label.grid()
        else:
            self.summary_strip.grid_remove()
            self.detail_info_separator.grid_remove()
            self.meta_label.grid_remove()
        self.sync_record_image_container_visibility()

    def format_search_suggestion(self, record: dict) -> str:
        parts = [self.get_record_display_word(record)]
        part_of_speech = str(record.get("tur", "")).strip()
        if part_of_speech:
            parts.append(part_of_speech)
        translation = str(record.get("turkce", "")).strip()
        if translation and translation != "-":
            parts.append(translation)
        return "  •  ".join(parts)

    def hide_search_suggestions(self) -> None:
        self.search_suggestion_records = []
        self.search_suggest_listbox.selection_clear(0, "end")
        self.search_suggest_listbox.delete(0, "end")
        self.search_suggest_frame.grid_remove()

    def update_search_suggestions(self, raw_search: str, records: list[dict]) -> None:
        focus_widget = self.focus_get()
        if self.search_suggestions_paused or not raw_search or focus_widget not in {self.search_entry, self.search_suggest_listbox}:
            self.hide_search_suggestions()
            return

        suggestions: list[dict] = []
        seen_keys: set[tuple[str, str, str]] = set()
        for record in records:
            dedupe_key = (
                normalize_text(self.get_record_display_word(record)),
                normalize_text(record.get("tur", "")),
                normalize_text(record.get("turkce", "")),
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            suggestions.append(record)
            if len(suggestions) >= 8:
                break

        if not suggestions:
            self.hide_search_suggestions()
            return

        previous_selection = self.search_suggest_listbox.curselection()
        previous_index = previous_selection[0] if previous_selection else 0
        self.search_suggestion_records = suggestions
        self.search_suggest_listbox.delete(0, "end")
        for record in suggestions:
            self.search_suggest_listbox.insert("end", self.format_search_suggestion(record))
        self.search_suggest_listbox.configure(height=min(len(suggestions), 8))
        self.search_suggest_frame.grid()

        target_index = min(previous_index, len(suggestions) - 1)
        if target_index >= 0:
            self.search_suggest_listbox.selection_clear(0, "end")
            self.search_suggest_listbox.selection_set(target_index)
            self.search_suggest_listbox.activate(target_index)
            self.search_suggest_listbox.see(target_index)

    def move_search_suggestion_selection(self, step: int):
        if not self.search_suggestion_records:
            return None
        current = self.search_suggest_listbox.curselection()
        if current:
            target_index = max(0, min(len(self.search_suggestion_records) - 1, current[0] + step))
        else:
            target_index = 0 if step >= 0 else len(self.search_suggestion_records) - 1
        self.search_suggest_listbox.selection_clear(0, "end")
        self.search_suggest_listbox.selection_set(target_index)
        self.search_suggest_listbox.activate(target_index)
        self.search_suggest_listbox.see(target_index)
        return "break"

    def apply_search_suggestion(self, index: int | None = None) -> str | None:
        if not self.search_suggestion_records:
            return None
        if index is None:
            selection = self.search_suggest_listbox.curselection()
            index = selection[0] if selection else 0
        if index < 0 or index >= len(self.search_suggestion_records):
            return None

        record = self.search_suggestion_records[index]
        self.search_suggestions_paused = True
        self.search_var.set(self.get_record_display_word(record))
        self.refresh_records(select_key=record_key(record))
        self.commit_current_search()
        self.search_suggestions_paused = False
        self.hide_search_suggestions()
        self.replace_search_on_next_key = True
        self.focus_search_entry(select_all=True)
        return "break"

    def on_search_entry_focus_in(self, _event=None):
        if self.search_var.get().strip() and self.search_suggestion_records:
            self.after(20, lambda: self.update_search_suggestions(self.search_var.get().strip(), self.filtered_records))

    def on_search_entry_focus_out(self, _event=None):
        self.after(120, self.hide_search_suggestions_if_needed)

    def hide_search_suggestions_if_needed(self) -> None:
        focus_widget = self.focus_get()
        if focus_widget in {self.search_entry, self.search_suggest_listbox}:
            return
        self.hide_search_suggestions()

    def on_search_suggestion_down(self, _event=None):
        return self.move_search_suggestion_selection(1)

    def on_search_suggestion_up(self, _event=None):
        return self.move_search_suggestion_selection(-1)

    def on_search_suggestion_submit(self, _event=None):
        return self.apply_search_suggestion()

    def on_search_suggestion_click(self, event=None):
        if event is not None and self.search_suggestion_records:
            target_index = self.search_suggest_listbox.nearest(event.y)
            self.search_suggest_listbox.selection_clear(0, "end")
            self.search_suggest_listbox.selection_set(target_index)
            self.search_suggest_listbox.activate(target_index)
        return self.apply_search_suggestion()

    def on_search_changed(self, *_args) -> None:
        self.schedule_search_refresh()
        self.queue_local_translation(self.search_var.get())

    def on_search_submit(self, _event=None):
        if self.search_suggestion_records:
            return self.apply_search_suggestion()
        self.refresh_search_now()
        self.commit_current_search()
        self.hide_search_suggestions()
        self.replace_search_on_next_key = True
        self.after(20, lambda: self.focus_search_entry(select_all=True))
        return "break"

    def on_search_keypress(self, event):
        if event.keysym in {"Return", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"}:
            return None
        if not self.replace_search_on_next_key:
            return None

        if event.keysym in {"BackSpace", "Delete"}:
            self.search_var.set("")
            self.replace_search_on_next_key = False
            return "break"

        if event.char and event.char.isprintable():
            self.search_var.set("")
            self.search_entry.icursor("end")
            self.replace_search_on_next_key = False
            return None

        self.replace_search_on_next_key = False
        return None

    def clear_search(self) -> None:
        if self.search_var.get():
            self.search_var.set("")
            self.refresh_search_now()
            self.hide_search_suggestions()
            self.search_entry.selection_clear()
            self.search_entry.icursor("end")
            self.replace_search_on_next_key = False
        else:
            self.hide_search_suggestions()
            self.focus_search_entry()

    def on_search_clear_shortcut(self, _event=None):
        self.clear_search()
        return "break"

    def commit_current_search(self) -> None:
        search = self.search_var.get().strip()
        if len(search) >= 2:
            recent = [search]
            recent.extend(item for item in self.settings.get("recent_searches", []) if normalize_text(item) != normalize_text(search))
            self.settings["recent_searches"] = recent[:MAX_RECENT_SEARCHES]
            self.update_quick_access()

    def update_quick_access(self) -> None:
        for frame in [self.recent_buttons_frame, self.pinned_buttons_frame]:
            for child in frame.winfo_children():
                child.destroy()

        recent_searches = self.settings.get("recent_searches", [])
        if recent_searches:
            for index, term in enumerate(recent_searches[:MAX_RECENT_SEARCHES]):
                ttk.Button(
                    self.recent_buttons_frame,
                    text=term,
                    style="Chip.TButton",
                    command=lambda value=term: self.apply_search_term(value),
                ).grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 6), pady=(0, 6))
        else:
            ttk.Label(
                self.recent_buttons_frame,
                text="Henüz son arama yok. Üstte arama yapınca burada görünür.",
                style="Muted.TLabel",
                wraplength=280,
                justify="left",
            ).grid(row=0, column=0, sticky="w")

        pinned_keys = self.settings.get("pinned_records", [])
        valid_pins = []
        if pinned_keys:
            for index, key_text in enumerate(pinned_keys[:MAX_PINNED_RECORDS]):
                record = self.find_record_by_serialized_key(key_text)
                if not record:
                    continue
                valid_pins.append(key_text)
                ttk.Button(
                    self.pinned_buttons_frame,
                    text=self.get_record_display_word(record),
                    style="Chip.TButton",
                    command=lambda value=record.get("almanca", ""): self.apply_search_term(value),
                ).grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 6), pady=(0, 6))

        self.settings["pinned_records"] = valid_pins[:MAX_PINNED_RECORDS]
        if not valid_pins:
            ttk.Label(
                self.pinned_buttons_frame,
                text="Sık kullanacağınız kelimeleri detay alanındaki düğmeyle favorilere ekleyebilirsiniz.",
                style="Muted.TLabel",
                wraplength=280,
                justify="left",
            ).grid(row=0, column=0, sticky="w")

        self.quick_stat_var.set(f"{len(recent_searches[:MAX_RECENT_SEARCHES])} arama • {len(valid_pins)} favori")

    def apply_search_term(self, term: str) -> None:
        self.search_var.set(term)
        self.refresh_search_now()
        self.commit_current_search()
        self.hide_search_suggestions()
        self.replace_search_on_next_key = True
        self.focus_search_entry(select_all=True)

    def build_search_aliases(self, raw_search: str) -> set[str]:
        normalized_search = normalize_text(raw_search)
        aliases = {normalized_search} if normalized_search else set()
        stripped = normalize_text(strip_known_article(raw_search))
        if stripped:
            aliases.add(stripped)
            aliases.add(normalize_text(f"der {stripped}"))
            aliases.add(normalize_text(f"die {stripped}"))
            title_term = stripped[:1].upper() + stripped[1:] if stripped else ""
            sourced_terms = self.fetch_wiktionary_gender_terms(title_term, allow_online=False) if title_term else {}
            for article, counterpart in sourced_terms.items():
                clean_counterpart = normalize_text(counterpart)
                if not clean_counterpart:
                    continue
                aliases.add(clean_counterpart)
                aliases.add(normalize_text(f"{article} {clean_counterpart}"))
            aliases.update(self.build_local_gender_aliases(stripped))
        return {item for item in aliases if item}

    def build_local_gender_aliases(self, stripped: str) -> set[str]:
        aliases: set[str] = set()
        if not stripped:
            return aliases

        if stripped.endswith("in") and len(stripped) > 4:
            base = stripped[:-2]
            if base:
                aliases.add(base)
                aliases.add(normalize_text(f"der {base}"))
                direct_match = self.find_record_by_term_and_article(base, "der")
                if direct_match:
                    candidate = normalize_text(direct_match.get("almanca", ""))
                    if candidate:
                        aliases.add(candidate)
                        aliases.add(normalize_text(f"der {candidate}"))
        else:
            feminine = f"{stripped}in"
            direct_match = self.find_record_by_term_and_article(feminine, "die")
            if direct_match:
                candidate = normalize_text(direct_match.get("almanca", ""))
                if candidate:
                    aliases.add(candidate)
                    aliases.add(normalize_text(f"die {candidate}"))
        return aliases

    def get_record_display_word(self, record: dict, allow_background: bool = False) -> str:
        forms = self.resolve_gender_forms(record, allow_background=allow_background)
        if forms and forms.get("eril") and forms.get("disil"):
            base_word = str(strip_known_article(forms["eril"])).strip()
            if base_word:
                return base_word
        return record.get("_word") or record.get("almanca", "-")

    def filter_records(self, search: str, search_aliases: set[str] | None = None) -> list[dict]:
        aliases = search_aliases or ({search} if search else set())
        preferred_sources = set(self.settings.get("preferred_sources", []))
        # Wildcard search: convert * patterns to regex (e.g. fahr* → ^fahr.*$)
        wildcard_pattern = None
        if search and "*" in search:
            import re as _re
            pat = _re.escape(search).replace(r"\*", ".*")
            try:
                wildcard_pattern = _re.compile(f"^{pat}$", _re.IGNORECASE)
            except Exception:
                wildcard_pattern = None
        filtered = []
        for item in self.records:
            if wildcard_pattern:
                word = normalize_text(item.get("almanca", ""))
                if not wildcard_pattern.match(word):
                    continue
            elif search:
                search_blob = item.get("_search_blob", "")
                if search not in search_blob:
                    word = normalize_text(item.get("almanca", ""))
                    word_with_article = normalize_text(item.get("_word", ""))
                    if not ({word, word_with_article} & aliases):
                        continue
            if self.settings.get("pos_filter") and item.get("tur") != self.settings["pos_filter"]:
                continue
            if self.settings.get("seviye_filter") and item.get("seviye") != self.settings["seviye_filter"]:
                continue
            if self.settings.get("category_filter") and self.settings["category_filter"] not in item.get("kategoriler", []):
                continue
            if self.settings.get("source_filter") and self.settings["source_filter"] not in item.get("_source_names", []):
                continue
            if self.settings.get("note_only") and not item.get("not", "").strip():
                continue
            if self.settings.get("source_mode") == "preferred_only" and preferred_sources:
                if not preferred_sources.intersection(item.get("_source_names", [])):
                    continue
            filtered.append(item)
        return filtered

    def rank_record_for_search(self, record: dict, search: str, search_aliases: set[str] | None = None) -> tuple:
        word = normalize_text(record.get("almanca", ""))
        word_with_article = normalize_text(record.get("_word", ""))
        translation = normalize_text(record.get("turkce", ""))
        description = normalize_text(record.get("aciklama_turkce", ""))
        related = normalize_text(" ".join(record.get("ilgili_kayitlar", [])))
        aliases = search_aliases or ({search} if search else set())

        if not search:
            return (10, word, translation)
        if search == word or search == word_with_article:
            return (0, word, translation)
        if aliases.intersection({word, word_with_article}):
            return (1, word, translation)
        if word.startswith(search) or word_with_article.startswith(search):
            return (2, word, translation)
        if translation.startswith(search):
            return (3, word, translation)
        if search in word or search in word_with_article:
            return (4, word, translation)
        if search in translation:
            return (5, word, translation)
        if search in description:
            return (6, word, translation)
        if search in related:
            return (7, word, translation)
        return (8, word, translation)

    def sort_records(self, records: list[dict], search: str, search_aliases: set[str] | None = None) -> list[dict]:
        sort_mode = self.settings.get("sort_mode", DEFAULT_SETTINGS["sort_mode"])
        # Arama yapılıyorsa her zaman önce alaka puanı kullan; seçilen sıralama
        # sadece aynı alaka puanına sahip kayıtlar arasında ikincil kriter olur.
        if search:
            def relevance_key(row: dict) -> tuple:
                rank = self.rank_record_for_search(row, search, search_aliases)
                word = normalize_text(row.get("almanca", ""))
                tr   = normalize_text(row.get("turkce", ""))
                if sort_mode == "turkce":
                    secondary = (tr, word)
                elif sort_mode == "almanca":
                    secondary = (word, tr)
                elif sort_mode == "kaynak":
                    secondary = (-len(row.get("_source_names", [])), word)
                elif sort_mode == "seviye":
                    secondary = (CEFR_ORDER.get(str(row.get("seviye") or "").strip(), 99), word)
                elif sort_mode == "frekans":
                    secondary = (-int(row.get("frekans") or 0), word)
                else:
                    secondary = (word, tr)
                return (rank[0],) + secondary
            return sorted(records, key=relevance_key)
        # Boş arama: kullanıcının seçtiği sıralama modu
        if sort_mode == "turkce":
            return sorted(records, key=lambda row: (normalize_text(row.get("turkce", "")), normalize_text(row.get("almanca", ""))))
        if sort_mode == "kaynak":
            return sorted(
                records,
                key=lambda row: (-len(row.get("_source_names", [])), normalize_text(row.get("almanca", "")), normalize_text(row.get("turkce", ""))),
            )
        if sort_mode == "almanca":
            return sorted(records, key=lambda row: (normalize_text(row.get("almanca", "")), normalize_text(row.get("turkce", ""))))
        if sort_mode == "seviye":
            return sorted(records, key=lambda row: (
                CEFR_ORDER.get(str(row.get("seviye") or "").strip(), 99),
                normalize_text(row.get("almanca", "")),
            ))
        if sort_mode == "frekans":
            return sorted(records, key=lambda row: (
                -int(row.get("frekans") or 0),
                normalize_text(row.get("almanca", "")),
            ))
        return sorted(records, key=lambda row: self.rank_record_for_search(row, search, search_aliases))

    def get_gender_family_key(self, record: dict) -> tuple[str, str] | None:
        forms = self.resolve_gender_forms(record, allow_background=False)
        if not forms or not forms.get("eril") or not forms.get("disil"):
            return None
        masculine_term = normalize_text(strip_known_article(forms["eril"]))
        if not masculine_term:
            return None
        return (masculine_term, normalize_text(record.get("tur", "")))

    def prefer_gender_family_record(self, current: dict, candidate: dict) -> dict:
        current_article = normalize_text(current.get("artikel", ""))
        candidate_article = normalize_text(candidate.get("artikel", ""))
        if current_article == "der":
            return current
        if candidate_article == "der":
            return candidate
        return current

    def dedupe_gender_family_records(self, records: list[dict], search: str) -> list[dict]:
        if not search:
            return records
        deduped: list[dict] = []
        family_positions: dict[tuple[str, str], int] = {}
        for record in records:
            family_key = self.get_gender_family_key(record)
            if family_key is None:
                deduped.append(record)
                continue
            if family_key in family_positions:
                existing_index = family_positions[family_key]
                deduped[existing_index] = self.prefer_gender_family_record(deduped[existing_index], record)
                continue
            family_positions[family_key] = len(deduped)
            deduped.append(record)
        return deduped

    def refresh_records(self, select_key: tuple[str, str, str] | None = None) -> None:
        raw_search = self.search_var.get().strip()
        search = normalize_text(raw_search)
        search_aliases = self.build_search_aliases(raw_search) if search else set()
        filtered = self.sort_records(self.filter_records(search, search_aliases), search, search_aliases)
        filtered = self.dedupe_gender_family_records(filtered, search)
        self.update_search_suggestions(raw_search, filtered)
        limit = max(50, safe_int(self.settings.get("result_limit"), DEFAULT_SETTINGS["result_limit"]))
        self.filtered_records = filtered[:limit]

        self.result_tree.delete(*self.result_tree.get_children())
        self.tree_keys.clear()
        for index, record in enumerate(self.filtered_records):
            item_id = f"row-{index}"
            self.result_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    self.get_record_display_word(record),
                    record.get("turkce", ""),
                    record.get("_meta_line", ""),
                ),
            )
            self.tree_keys[item_id] = record_key(record)

        self.total_stat_var.set(str(len(self.records)))
        self.visible_stat_var.set(str(len(self.filtered_records)))
        effective_results_panel = self.should_show_results_panel()
        self.apply_layout_preferences()

        if search:
            if self.filtered_records:
                if effective_results_panel:
                    self.search_status_var.set(
                        f'"{self.search_var.get().strip()}" için {len(self.filtered_records)} sonuç var. Soldan seçtiğinizde ayrıntılar sağda açılır.'
                    )
                else:
                    self.search_status_var.set(
                        f'"{self.search_var.get().strip()}" için {len(self.filtered_records)} eşleşme var. En uygun kayıt aşağıda gösteriliyor.'
                    )
            else:
                self.search_status_var.set(
                    f'"{self.search_var.get().strip()}" için sonuç bulunamadı. Kök biçimi, Türkçe karşılığı veya daha kısa bir arama deneyin. Cümle ise alttaki LibreTranslate kartında karşılığını görebilirsiniz.'
                )
        else:
            self.search_status_var.set(
                "Arama kutusu üstte sabit. Almanca kelime, Türkçe karşılık, açıklama veya kaynak adı yazarak başlayabilirsiniz."
            )

        if self.filtered_records:
            shown_count = min(len(filtered), limit)
            if len(filtered) > limit:
                self.result_summary_var.set(f"{shown_count} sonuç gösteriliyor. Daha fazlası için sonuç sayısını Ayarlar'dan artırın.")
            else:
                self.result_summary_var.set(f"{shown_count} sonuç listeleniyor.")
        else:
            self.result_summary_var.set("Sonuç listesi hazır.")

        filter_bits = []
        if self.settings.get("pos_filter"):
            filter_bits.append(f"Tür: {self.settings['pos_filter']}")
        if self.settings.get("category_filter"):
            filter_bits.append(f"Kategori: {self.settings['category_filter']}")
        if self.settings.get("source_filter"):
            filter_bits.append(f"Kaynak: {self.settings['source_filter']}")
        if self.settings.get("note_only"):
            filter_bits.append("Sadece notlu kayıtlar")
        if self.settings.get("source_mode") == "preferred_only" and self.settings.get("preferred_sources"):
            filter_bits.append(f"Kaynak grubu: {len(self.settings['preferred_sources'])} seçim")
        self.filter_summary_var.set(
            " • ".join(filter_bits) if filter_bits else "Ek filtre yok. Görünüm ve kaynak tercihleri Ayarlar bölümünde."
        )

        if not self.filtered_records:
            self.show_results_empty_state(search_active=bool(search))
            self.display_record(None)
            return

        self.hide_results_empty_state()
        target_key = select_key
        if target_key is None and self.current_record and effective_results_panel:
            target_key = record_key(self.current_record)

        selected_item = None
        if target_key is not None:
            for item_id, item_key in self.tree_keys.items():
                if item_key == target_key:
                    selected_item = item_id
                    break

        if selected_item is None and search:
            selected_item = next(iter(self.tree_keys))

        if selected_item is None:
            current_selection = self.result_tree.selection()
            if current_selection:
                self.result_tree.selection_remove(*current_selection)
            self.display_record(None)
            return

        self.result_tree.selection_set(selected_item)
        self.result_tree.focus(selected_item)
        self.result_tree.see(selected_item)
        self.display_record(self.find_record_by_key(self.tree_keys[selected_item]))

    def show_results_empty_state(self, search_active: bool) -> None:
        self.tree_frame.grid_remove()
        self.results_empty.grid(row=0, column=0, sticky="nsew")
        if search_active:
            self.result_empty_title_var.set("Uygun kayıt bulunamadı")
            self.result_empty_body_var.set(
                "Aramayı biraz kısaltın, Türkçe karşılığı deneyin veya Ayarlar bölümündeki filtreleri gevşetin."
            )
        else:
            self.result_empty_title_var.set("Sözlük hazır")
            self.result_empty_body_var.set("Soldaki sonuç alanı burada görünür. Üstte arama yapınca liste anında güncellenir.")

    def hide_results_empty_state(self) -> None:
        self.results_empty.grid_remove()
        self.tree_frame.grid(row=0, column=0, sticky="nsew")

    def find_record_by_key(self, key: tuple[str, str, str]) -> dict | None:
        for item in self.filtered_records:
            if record_key(item) == key:
                return item
        for item in self.records:
            if record_key(item) == key:
                return item
        return None

    def find_record_by_serialized_key(self, key_text: str) -> dict | None:
        bits = tuple(str(key_text).split("||", 2))
        if len(bits) != 3:
            return None
        return self.find_record_by_key((bits[0], bits[1], bits[2]))

    def is_current_record_favorite(self) -> bool:
        if not self.current_record:
            return False
        key_text = serialize_record_key(record_key(self.current_record))
        return key_text in self.settings.get("pinned_records", [])

    def refresh_favorite_button(self) -> None:
        self.favorite_button_var.set("Favorilere Ekle" if not self.is_current_record_favorite() else "Favoriden Kaldır")

    def get_existing_german_terms(self) -> set[str]:
        return {
            normalized
            for item in self.records
            for normalized in [normalize_import_term(item.get("almanca", ""))]
            if normalized
        }

    def on_tree_select(self, _event=None) -> None:
        selection = self.result_tree.selection()
        if not selection:
            return
        record = self.find_record_by_key(self.tree_keys[selection[0]])
        if record:
            self.commit_current_search()
        self.hide_search_suggestions()
        self.display_record(record)

    def _block_text_edit_keys(self, widget: tk.Text) -> None:
        """Bind a key handler that blocks editing but allows selection/copy/navigation."""
        if getattr(widget, "_readonly_bound", False):
            return
        _allowed_keys = {
            "ctrl+c", "ctrl+a", "ctrl+Insert",
            "Up", "Down", "Left", "Right", "Home", "End", "Prior", "Next",
            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
        }

        def _on_key(event: tk.Event) -> str | None:
            key = event.keysym
            state = event.state
            # Allow Ctrl+C, Ctrl+A, Ctrl+Insert
            ctrl = (state & 0x4) != 0
            if ctrl and key in ("c", "C", "a", "A", "Insert"):
                return None
            # Allow navigation and modifier keys
            if key in ("Up", "Down", "Left", "Right", "Home", "End", "Prior", "Next",
                       "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"):
                return None
            return "break"

        widget.bind("<Key>", _on_key, add=True)
        widget._readonly_bound = True  # type: ignore[attr-defined]

    def set_text_widget(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", format_display_text(value))
        widget.yview_moveto(0.0)
        self._block_text_edit_keys(widget)

    def clear_compact_meanings(self) -> None:
        self.compact_meaning_overviews = []
        self.compact_meanings_listbox.delete(0, "end")
        self.compact_meanings_listbox.selection_clear(0, "end")
        self.compact_meanings_label.grid_remove()
        self.compact_meanings_wrap.grid_remove()
        self.compact_definition_text.configure(state="normal")
        self.compact_definition_text.tag_delete("meaning_current")

    def summarize_compact_meaning(self, value: str, limit: int = 120) -> str:
        text = normalize_whitespace(value)
        if len(text) <= limit:
            return text
        trimmed = text[: limit - 1].rsplit(" ", 1)[0].strip()
        return f"{trimmed or text[: limit - 1]}…"

    def update_compact_meanings(self, definitions: list[str]) -> None:
        self.compact_meaning_overviews = definitions[:]
        self.compact_meanings_listbox.delete(0, "end")
        self.compact_meanings_listbox.selection_clear(0, "end")
        self.compact_meanings_label.grid_remove()
        self.compact_meanings_wrap.grid_remove()

    def render_compact_definition_text(self, definitions: list[str], fallback_text: str) -> None:
        self.compact_definition_text.configure(state="normal")
        self.compact_definition_text.delete("1.0", "end")
        for tag_name in self.compact_definition_text.tag_names():
            if tag_name.startswith("meaning_") or tag_name == "meaning_current":
                self.compact_definition_text.tag_delete(tag_name)

        if definitions:
            for index, definition in enumerate(definitions, start=1):
                tag_name = f"meaning_{index - 1}"
                start_index = self.compact_definition_text.index("end-1c")
                if start_index == "1.0" and not self.compact_definition_text.get("1.0", "end-1c"):
                    start_index = "1.0"
                self.compact_definition_text.insert("end", f"{index}. {definition}")
                end_index = self.compact_definition_text.index("end-1c")
                self.compact_definition_text.tag_add(tag_name, start_index, end_index)
                if index < len(definitions):
                    self.compact_definition_text.insert("end", "\n\n")
        else:
            self.compact_definition_text.insert("1.0", format_display_text(fallback_text))

        self.compact_definition_text.tag_configure("meaning_current", background=self.active_palette["accent_soft"])
        self.compact_definition_text.yview_moveto(0.0)
        self._block_text_edit_keys(self.compact_definition_text)

    def jump_to_compact_meaning(self, index: int) -> None:
        if index < 0 or index >= len(self.compact_meaning_overviews):
            return
        tag_name = f"meaning_{index}"
        ranges = self.compact_definition_text.tag_ranges(tag_name)
        if not ranges:
            return
        self.compact_definition_text.configure(state="normal")
        self.compact_definition_text.tag_remove("meaning_current", "1.0", "end")
        self.compact_definition_text.tag_add("meaning_current", ranges[0], ranges[1])
        self.compact_definition_text.see(ranges[0])

    def on_compact_meaning_select(self, _event=None):
        selection = self.compact_meanings_listbox.curselection()
        if not selection:
            return
        self.jump_to_compact_meaning(selection[0])

    def on_compact_meaning_activate(self, _event=None):
        selection = self.compact_meanings_listbox.curselection()
        if not selection:
            return "break"
        self.jump_to_compact_meaning(selection[0])
        return "break"

    def display_record(self, record: dict | None) -> None:
        self.current_record = record
        if not record:
            self.refresh_favorite_button()
            self.show_detail_empty_state()
            self.word_var.set("Kelime seçin")
            self.translation_var.set("Seçili kaydın kısa özeti burada görünür.")
            self.meta_var.set("")
            self.cogul_var.set("")
            self.cogul_label.grid_remove()
            self.partizip_var.set("")
            self.partizip_label.grid_remove()
            self.trennbar_var.set("")
            self.trennbar_label.grid_remove()
            self.verb_typ_var.set("")
            self.verb_typ_label.grid_remove()
            self._kelime_ailesi_frame.grid_remove()
            self._sinonim_frame.grid_remove()
            self._antonim_frame.grid_remove()
            self.seviye_var.set("")
            self.seviye_label.grid_remove()
            self.summary_caption_var.set("Kısa bilgi")
            self.compact_caption_var.set("Tanım")
            self.source_status_var.set("Kaynak bilgisi seçili kayıtla birlikte görünür.")
            self.translation_status_var.set("Çeviri doğrulama bilgisi seçili kayıtla birlikte görünür.")
            self.definition_hint_var.set("Çevrimiçi tanımları görmek için önce bir kayıt seçin.")
            self.set_text_widget(self.compact_detail_text, "")
            self.set_text_widget(self.compact_definition_text, "")
            self.clear_compact_meanings()
            self.set_text_widget(self.detail_text, "")
            self.set_text_widget(self.translation_note, "")
            self.set_text_widget(self.definition_de_text, "")
            self.set_text_widget(self.definition_tr_text, "")
            self.set_text_widget(self.examples_text, "")
            self.set_text_widget(self.conjugations_text, "")
            self.related_listbox.delete(0, "end")
            self.source_url_listbox.delete(0, "end")
            self.translation_source_listbox.delete(0, "end")
            self._update_ref_buttons(None)
            self.queue_record_image(None)
            self.compact_scroll_canvas.yview_moveto(0)
            return

        self.hide_detail_empty_state()
        self.refresh_favorite_button()
        self.word_var.set(self.get_record_display_word(record))
        self.translation_var.set(record.get("turkce", "-"))
        self.meta_var.set(record.get("_meta_line", ""))
        self.summary_caption_var.set("Kısa bilgi. Ayrıntılar sekmelerde.")
        self.compact_caption_var.set("Kısa bilgi")

        cogul = str(record.get("cogul", "") or "").strip()
        if cogul:
            self.cogul_var.set(f"Çoğul: die {cogul}")
            self.cogul_label.grid()
        else:
            self.cogul_var.set("")
            self.cogul_label.grid_remove()

        partizip2 = str(record.get("partizip2", "") or "").strip()
        perfekt_yardimci = str(record.get("perfekt_yardimci", "") or "").strip()
        if partizip2 or perfekt_yardimci:
            parts = []
            if partizip2:
                parts.append(f"Partizip II: {partizip2}")
            if perfekt_yardimci and partizip2:
                parts.append(f"Perfekt: {perfekt_yardimci} + {partizip2}")
            elif perfekt_yardimci:
                parts.append(f"Perfekt yardımcı: {perfekt_yardimci}")
            self.partizip_var.set("  •  ".join(parts))
            self.partizip_label.grid()
        else:
            self.partizip_var.set("")
            self.partizip_label.grid_remove()

        trennbar = record.get("trennbar")
        prefix = record.get("trennbar_prefix", "")
        if trennbar is True and prefix:
            self.trennbar_var.set(f"Ayrılabilir (trennbar): {prefix}- öneki ayrılır")
            self.trennbar_label.grid()
        elif trennbar is False and prefix:
            self.trennbar_var.set(f"Ayrılmaz (untrennbar): {prefix}- öneki kalır")
            self.trennbar_label.grid()
        else:
            self.trennbar_var.set("")
            self.trennbar_label.grid_remove()

        # Verb tipi (stark/schwach) ve geçişlilik
        verb_typ = str(record.get("verb_typ") or "").strip()
        gecisli = str(record.get("gecisli") or "").strip()
        verb_info_parts = []
        if verb_typ == "stark":
            verb_info_parts.append("Güçlü fiil (stark — düzensiz)")
        elif verb_typ == "schwach":
            verb_info_parts.append("Zayıf fiil (schwach — düzenli)")
        if gecisli == "transitiv":
            verb_info_parts.append("Geçişli (transitiv)")
        elif gecisli == "intransitiv":
            verb_info_parts.append("Geçişsiz (intransitiv)")
        elif gecisli == "reflexiv":
            verb_info_parts.append("Dönüşlü (reflexiv)")
        if verb_info_parts and record.get("tur") == "fiil":
            self.verb_typ_var.set("  •  ".join(verb_info_parts))
            self.verb_typ_label.grid()
        else:
            self.verb_typ_var.set("")
            self.verb_typ_label.grid_remove()

        # Kelime ailesi (word family links)
        kelime_ailesi = record.get("kelime_ailesi") or []
        if kelime_ailesi and isinstance(kelime_ailesi, list):
            self._populate_wrap_chip_frame(self._kelime_ailesi_frame, "Kelime ailesi:", kelime_ailesi[:6], "Chip.TButton")
            self._kelime_ailesi_frame.grid()
        else:
            self._kelime_ailesi_frame.grid_remove()

        # Sinonimler (synonyms)
        sinonimler = record.get("sinonim") or []
        if sinonimler and isinstance(sinonimler, list):
            self._populate_wrap_chip_frame(self._sinonim_frame, "Eş anlamlılar:", sinonimler[:8], "Chip.TButton")
            self._sinonim_frame.grid()
        else:
            self._sinonim_frame.grid_remove()

        # Antonimler (antonyms)
        antonimler = record.get("antonim") or []
        if antonimler and isinstance(antonimler, list):
            self._populate_wrap_chip_frame(self._antonim_frame, "Zıt anlamlılar:", antonimler[:8], "ChipAlt.TButton")
            self._antonim_frame.grid()
        else:
            self._antonim_frame.grid_remove()

        seviye = str(record.get("seviye", "") or "").strip()
        if seviye:
            self.seviye_var.set(f"Seviye: {seviye}")
            self.seviye_label.grid()
        else:
            self.seviye_var.set("")
            self.seviye_label.grid_remove()

        detail_parts = []
        if record.get("aciklama_turkce"):
            detail_parts.append(f"Açıklama\n{record['aciklama_turkce']}")
        gender_forms_text = self.build_gender_forms_text(record)
        if gender_forms_text:
            detail_parts.append(gender_forms_text)
        if self.settings.get("show_notes") and record.get("not"):
            detail_parts.append(f"Not\n{record['not']}")
        if not detail_parts:
            detail_parts.append("Bu kayıt için kısa açıklama bulunmuyor. Gerekirse kaynak veya tanım sekmelerine geçin.")
        self.set_text_widget(self.detail_text, "\n\n".join(detail_parts))

        self.related_listbox.delete(0, "end")
        related_terms = list(record.get("ilgili_kayitlar", []))
        gender_forms = self.resolve_gender_forms(record)
        if gender_forms:
            for label in [gender_forms.get("eril", ""), gender_forms.get("disil", "")]:
                clean_label = str(label).strip()
                if not clean_label:
                    continue
                if normalize_text(clean_label) == normalize_text(record.get("_word") or record.get("almanca", "")):
                    continue
                if all(normalize_text(clean_label) != normalize_text(existing) for existing in related_terms):
                    related_terms.insert(0, clean_label)
        if related_terms:
            for item in related_terms:
                self.related_listbox.insert("end", item)
        else:
            self.related_listbox.insert("end", "İlgili kayıt eklenmemiş.")

        source_names = record.get("_source_names", [])
        if source_names:
            self.source_status_var.set(f"Bu kayıt {', '.join(source_names)} kaynağıyla ilişkilendirildi.")
        else:
            self.source_status_var.set("Bu kayıt için kaynak adı yazılmamış.")

        self.current_source_urls = record.get("_source_urls", [])
        self.source_url_listbox.delete(0, "end")
        if self.current_source_urls:
            for url in self.current_source_urls:
                self.source_url_listbox.insert("end", url)
        else:
            self.source_url_listbox.insert("end", "Bu kayıt için bağlantı eklenmemiş.")

        self._update_ref_buttons(record)

        # Eş/Zıt Anlamlılar (Kaynak İncele tab)
        sinonim_src = record.get("sinonim") or []
        if sinonim_src and isinstance(sinonim_src, list):
            self._populate_wrap_chip_frame(self._sources_sinonim_frame, "Eş anlamlılar:", sinonim_src[:10], "Chip.TButton")
        else:
            for widget in self._sources_sinonim_frame.winfo_children():
                widget.destroy()
            ttk.Label(self._sources_sinonim_frame, text="Eş anlamlı yok.", style="Muted.TLabel").pack(side="left")

        antonim_src = record.get("antonim") or []
        if antonim_src and isinstance(antonim_src, list):
            self._populate_wrap_chip_frame(self._sources_antonim_frame, "Zıt anlamlılar:", antonim_src[:10], "ChipAlt.TButton")
        else:
            for widget in self._sources_antonim_frame.winfo_children():
                widget.destroy()
            ttk.Label(self._sources_antonim_frame, text="Zıt anlamlı yok.", style="Muted.TLabel").pack(side="left")

        review_status = REVIEW_STATUS_LABELS.get(record.get("ceviri_durumu", ""), record.get("ceviri_durumu", "Belirsiz"))
        self.translation_status_var.set(f"Çeviri durumu: {review_status}")
        translation_note_parts = []
        if record.get("ceviri_inceleme_notu"):
            translation_note_parts.append(record["ceviri_inceleme_notu"])
        else:
            translation_note_parts.append("Bu kayıt için ayrı çeviri inceleme notu bulunmuyor.")
        if self.settings.get("show_notes") and record.get("not"):
            translation_note_parts.append(f"Not: {record['not']}")
        self.set_text_widget(self.translation_note, "\n\n".join(translation_note_parts))

        self.current_translation_sources = record.get("_translation_sources", [])
        self.translation_source_listbox.delete(0, "end")
        if self.current_translation_sources:
            for item in self.current_translation_sources:
                self.translation_source_listbox.insert("end", format_source_item(item))
        else:
            self.translation_source_listbox.insert("end", "Ayrı çeviri doğrulama kaynağı eklenmemiş.")

        self.populate_definitions(record)
        self.populate_examples(record)
        self.populate_conjugations(record)
        self.queue_record_image(record)
        self.compact_scroll_canvas.yview_moveto(0)
        self.update_quick_access()

    def _search_for_word(self, word: str) -> None:
        """Verilen kelimeyi arama kutusuna yaz ve ara."""
        clean = strip_known_article(word)
        self.search_var.set(clean)
        self.search_entry.focus_set()

    def show_detail_empty_state(self) -> None:
        self.detail_content.grid_remove()
        self.compact_detail.grid_remove()
        self.detail_empty.grid(row=0, column=0, sticky="nsew")
        if self.search_var.get().strip():
            self.detail_empty_title_var.set("Sonuç seçin")
            self.detail_empty_body_var.set(
                "Aramanız hazır. En iyi eşleşme burada gösterilir. İsterseniz sonuç listesini Ayarlar bölümünden açabilirsiniz."
            )
        else:
            self.detail_empty_title_var.set("Aramaya başlayın")
            self.detail_empty_body_var.set(
                "Üstteki arama alanına kelime yazın. Varsayılan görünüm yalnızca arama ve kelime kartını gösterir."
            )

    def hide_detail_empty_state(self) -> None:
        self.detail_empty.grid_remove()
        if self.settings.get("show_extended_details", False):
            self.compact_detail.grid_remove()
            self.detail_content.grid(row=0, column=0, sticky="nsew")
        else:
            self.detail_content.grid_remove()
            self.compact_detail.grid(row=0, column=0, sticky="nsew")

    def populate_definitions(self, record: dict) -> None:
        de_key = ("de", record.get("almanca", ""))
        tr_key = ("tr", record.get("turkce", ""))
        if de_key not in self.definition_cache:
            self.definition_cache[de_key] = lookup_german_definition(record.get("almanca", ""))
        if tr_key not in self.definition_cache:
            self.definition_cache[tr_key] = lookup_turkish_definition(record.get("turkce", ""))
        de_payload = self.definition_cache[de_key]
        tr_payload = self.definition_cache[tr_key]
        self.refresh_online_definition_placeholders(record)
        compact_info_text, compact_definitions, compact_definition_text = self.build_compact_detail_text(record, de_payload, tr_payload)
        self.set_text_widget(self.compact_detail_text, compact_info_text)
        self.update_compact_meanings(compact_definitions)
        self.render_compact_definition_text(compact_definitions, compact_definition_text)
        if compact_definitions:
            self.jump_to_compact_meaning(0)

    def refresh_online_definition_placeholders(self, record: dict | None) -> None:
        if not record:
            self.set_text_widget(self.definition_de_text, "")
            self.set_text_widget(self.definition_tr_text, "")
            self.definition_hint_var.set("Tanımları görmek için kayıt seçin.")
            return

        self.definition_hint_var.set("Çevrimiçi tanımlar yalnızca + düğmelerine basınca yüklenir.")
        de_key = ("dwds", record.get("almanca", ""))
        tr_key = ("tdk", record.get("turkce", ""))
        de_payload = self.online_definition_cache.get(de_key)
        tr_payload = self.online_definition_cache.get(tr_key)
        self.set_text_widget(
            self.definition_de_text,
            self.format_definition_payload(de_payload)
            if de_payload
            else "DWDS tanımını görmek için + DWDS düğmesine basın.",
        )
        self.set_text_widget(
            self.definition_tr_text,
            self.format_definition_payload(tr_payload)
            if tr_payload
            else "TDK tanımını görmek için + TDK düğmesine basın.",
        )

    def load_dwds_definition_on_demand(self) -> None:
        if not self.current_record:
            return
        term = self.current_record.get("almanca", "")
        cache_key = ("dwds", term)
        payload = self.online_definition_cache.get(cache_key)
        if payload is None:
            payload = fetch_dwds_definition(term)
            self.online_definition_cache[cache_key] = payload
        self.set_text_widget(self.definition_de_text, self.format_definition_payload(payload))
        self.definition_hint_var.set("Çevrimiçi tanımlar yalnızca + düğmelerine basınca yüklenir.")

    def load_tdk_definition_on_demand(self) -> None:
        if not self.current_record:
            return
        term = self.current_record.get("turkce", "")
        cache_key = ("tdk", term)
        payload = self.online_definition_cache.get(cache_key)
        if payload is None:
            payload = lookup_turkish_definition_online(term)
            self.online_definition_cache[cache_key] = payload
        self.set_text_widget(self.definition_tr_text, self.format_definition_payload(payload))
        self.definition_hint_var.set("Çevrimiçi tanımlar yalnızca + düğmelerine basınca yüklenir.")

    def format_definition_payload(self, payload: dict) -> str:
        if payload.get("status") != "ok":
            return payload.get("note", "Tanım bulunamadı.")
        parts = [
            f"Eşleşen terim: {payload.get('matched_term', payload.get('term', ''))}",
            f"Kaynak: {payload.get('source', '-')}",
        ]
        if payload.get("url"):
            parts.append(f"Bağlantı: {payload['url']}")
        definitions = payload.get("definitions", [])
        if definitions:
            parts.append("")
            parts.extend(f"{index}. {item}" for index, item in enumerate(definitions, start=1))
        if payload.get("note"):
            parts.append("")
            parts.append(payload["note"])
        return "\n".join(parts)

    def find_record_by_term_and_article(self, term: str, article: str) -> dict | None:
        target_term = normalize_text(term)
        target_article = normalize_text(article)
        if not target_term or target_article not in {"der", "die"}:
            return None
        return self.noun_record_index.get((target_term, target_article))

    def fetch_wiktionary_gender_terms(self, term: str, allow_online: bool = True) -> dict[str, str]:
        normalized_term = normalize_text(term)
        if not normalized_term:
            return {}
        cached = self.gender_form_cache.get(normalized_term)
        if cached is not None:
            return cached
        if not allow_online:
            return {}

        url = f"https://de.wiktionary.org/w/index.php?title={quote(term, safe='')}&action=raw"
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw_text = urlopen(request, timeout=WIKTIONARY_GENDER_TIMEOUT_SECONDS).read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError, OSError):
            self.gender_form_cache[normalized_term] = {}
            return {}

        collected: dict[str, str] = {}
        section_key: str | None = None
        for line in raw_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("{{Weibliche Wortformen"):
                section_key = "die"
                continue
            if stripped.startswith("{{Männliche Wortformen"):
                section_key = "der"
                continue
            if section_key is None:
                continue
            if stripped.startswith("{{"):
                section_key = None
                continue
            if not stripped.startswith(":"):
                continue
            for candidate in re.findall(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]", stripped):
                clean_candidate = str(candidate).strip()
                if clean_candidate:
                    collected.setdefault(section_key, clean_candidate)
                    break

        self.gender_form_cache[normalized_term] = collected
        return collected

    def queue_gender_form_fetch(self, term: str, record: dict | None = None) -> None:
        normalized_term = normalize_text(term)
        if not normalized_term or normalized_term in self.gender_form_cache or normalized_term in self.gender_form_pending_terms:
            return
        refresh_key = record_key(record) if record else None
        self.gender_form_pending_terms.add(normalized_term)
        worker = threading.Thread(
            target=self._gender_form_fetch_worker,
            args=(term, normalized_term, refresh_key),
            daemon=True,
        )
        worker.start()

    def _gender_form_fetch_worker(self, term: str, normalized_term: str, refresh_key: tuple[str, str, str] | None) -> None:
        self.fetch_wiktionary_gender_terms(term, allow_online=True)
        self.gender_form_result_queue.put((normalized_term, refresh_key))

    def process_gender_form_results(self) -> None:
        refresh_current_record = False
        refresh_search_results = False
        while True:
            try:
                normalized_term, refresh_key = self.gender_form_result_queue.get_nowait()
            except queue.Empty:
                break
            self.gender_form_pending_terms.discard(normalized_term)
            if refresh_key is not None and self.current_record and record_key(self.current_record) == refresh_key:
                refresh_current_record = True
            elif self.search_var.get().strip():
                refresh_search_results = True

        if refresh_current_record and self.current_record:
            self.display_record(self.current_record)
        elif refresh_search_results:
            self.refresh_records(select_key=record_key(self.current_record) if self.current_record else None)

        if self.winfo_exists():
            self.after(180, self.process_gender_form_results)

    def on_gender_form_fetch_complete(self, normalized_term: str, refresh_key: tuple[str, str, str] | None) -> None:
        self.gender_form_pending_terms.discard(normalized_term)
        if not self.winfo_exists():
            return
        if refresh_key is not None and self.current_record and record_key(self.current_record) == refresh_key:
            self.display_record(self.current_record)
        elif self.search_var.get().strip():
            self.refresh_records(select_key=record_key(self.current_record) if self.current_record else None)

    def resolve_local_gender_forms(self, record: dict) -> dict | None:
        word = str(record.get("almanca", "")).strip()
        article = normalize_text(record.get("artikel", ""))
        if record.get("tur") != "isim" or article not in {"der", "die"} or not word:
            return None

        if article == "der":
            direct_match = self.find_record_by_term_and_article(f"{word}in", "die")
            if direct_match:
                return {"eril": f"der {word}", "disil": f"die {direct_match['almanca']}"}
            return None

        if not word.endswith("in") or len(word) <= 3:
            return None
        base_word = word[:-2]
        direct_match = self.find_record_by_term_and_article(base_word, "der")
        if direct_match:
            return {"eril": f"der {direct_match['almanca']}", "disil": f"die {word}"}
        return None

    def resolve_gender_forms(self, record: dict, allow_background: bool = True) -> dict | None:
        word = str(record.get("almanca", "")).strip()
        article = normalize_text(record.get("artikel", ""))
        if record.get("tur") != "isim" or article not in {"der", "die"} or not word:
            return None

        local_forms = self.resolve_local_gender_forms(record)
        if local_forms:
            return local_forms

        sourced_terms = self.fetch_wiktionary_gender_terms(word, allow_online=False)
        if not sourced_terms:
            if not allow_background:
                return None
            self.queue_gender_form_fetch(word, record)
            return None
        masculine = f"der {word}" if article == "der" else None
        feminine = f"die {word}" if article == "die" else None

        if article == "der":
            counterpart = sourced_terms.get("die", "").strip()
            if not counterpart:
                return None
            feminine = f"die {counterpart}"
        else:
            counterpart = sourced_terms.get("der", "").strip()
            if not counterpart:
                return None
            masculine = f"der {counterpart}"

        if not masculine or not feminine:
            return None
        return {"eril": masculine, "disil": feminine}

    def build_gender_forms_text(self, record: dict) -> str:
        forms = self.resolve_gender_forms(record)
        if not forms or not forms.get("eril") or not forms.get("disil"):
            return ""
        lines = [
            "Cinsiyet biçimi",
            "Bu isim eril ve dişil olmak üzere iki biçimde kullanılır.",
            f"Eril: {forms['eril']}",
            f"Di\u015fil: {forms['disil']}",
        ]
        return "\n".join(lines)

    def _populate_wrap_chip_frame(self, frame: ttk.Frame, label_text: str, words: list[str], chip_style: str) -> None:
        """Chip butonlarını label altında, çok gelince alt satıra geçerek frame'e yerleştir."""
        for w in frame.winfo_children():
            w.destroy()
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text=label_text, style="Muted.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 3))

        chip_host = ttk.Frame(frame, style="Panel.TFrame")
        chip_host.grid(row=1, column=0, sticky="ew")
        chip_host.columnconfigure(0, weight=1)

        buttons: list[ttk.Button] = []
        for word in words:
            btn = ttk.Button(
                chip_host,
                text=word,
                style=chip_style,
                command=lambda w=word: self._search_for_word(w),
            )
            buttons.append(btn)

        def _relayout(event=None) -> None:
            chip_host.update_idletasks()
            available_w = chip_host.winfo_width()
            if available_w <= 1:
                chip_host.after(30, _relayout)
                return
            x = y = row_h = 0
            for btn in buttons:
                btn.update_idletasks()
                bw = btn.winfo_reqwidth()
                bh = btn.winfo_reqheight()
                if x + bw > available_w and x > 0:
                    x = 0
                    y += row_h + 4
                    row_h = 0
                btn.place(x=x, y=y)
                x += bw + 4
                row_h = max(row_h, bh)
            chip_host.configure(height=max(y + row_h + 2, 1))

        chip_host.bind("<Configure>", _relayout)
        frame.after(30, _relayout)

    def build_compact_detail_text(self, record: dict, de_payload: dict, tr_payload: dict) -> tuple[str, list[str], str]:
        info_blocks = []
        if record.get("aciklama_turkce"):
            info_blocks.append(record["aciklama_turkce"])

        turkish_definitions = tr_payload.get("definitions", []) if tr_payload.get("status") == "ok" else []
        german_definitions = de_payload.get("definitions", []) if de_payload.get("status") == "ok" else []
        definitions = turkish_definitions if len(turkish_definitions) > 1 else german_definitions
        if definitions:
            definition_text = "\n\n".join(f"{index}. {item}" for index, item in enumerate(definitions, start=1))
        elif tr_payload.get("note"):
            definition_text = tr_payload.get("note", "")
        else:
            definition_text = "Bu kayıt için Türkçe tanım bulunmuyor."

        gender_forms_text = self.build_gender_forms_text(record)
        if gender_forms_text:
            info_blocks.append(gender_forms_text)

        if self.settings.get("show_notes") and record.get("not"):
            info_blocks.append("Not\n" + record["not"])

        compact_info_text = "\n\n".join(block for block in info_blocks if block.strip())
        if not compact_info_text:
            compact_info_text = "Bu kayıt için kısa açıklama bulunmuyor."
        return compact_info_text, definitions, definition_text

    def _bind_text_tag_tooltip(self, widget: tk.Text, tag: str, tip_text: str) -> None:
        """Text widget'taki bir tag'e hover tooltip bağlar."""
        state: dict = {"tip": None, "after_id": None}

        def _show() -> None:
            if state["tip"]:
                return
            try:
                x = widget.winfo_pointerx() + 14
                y = widget.winfo_pointery() + 14
                w = tk.Toplevel(widget)
                w.wm_overrideredirect(True)
                w.attributes("-topmost", True)
                tk.Label(
                    w,
                    text=tip_text,
                    justify="left",
                    wraplength=300,
                    background="#fffde7",
                    foreground="#333333",
                    relief="solid",
                    borderwidth=1,
                    padx=7,
                    pady=5,
                    font=("Segoe UI", 9),
                ).pack()
                w.geometry(f"+{x}+{y}")
                state["tip"] = w
            except Exception:
                pass

        def on_enter(_event=None) -> None:
            if state["after_id"]:
                try:
                    widget.after_cancel(state["after_id"])
                except Exception:
                    pass
            state["after_id"] = widget.after(400, _show)

        def on_leave(_event=None) -> None:
            if state["after_id"]:
                try:
                    widget.after_cancel(state["after_id"])
                except Exception:
                    pass
                state["after_id"] = None
            if state["tip"]:
                try:
                    state["tip"].destroy()
                except Exception:
                    pass
                state["tip"] = None

        widget.tag_bind(tag, "<Enter>", on_enter)
        widget.tag_bind(tag, "<Leave>", on_leave)

    def populate_examples(self, record: dict) -> None:
        if not self.settings.get("show_examples", True):
            self.set_text_widget(self.examples_text, "Örnekler Ayarlar bölümünden kapatıldı.")
            return

        widget = self.examples_text
        widget.configure(state="normal")
        widget.delete("1.0", "end")

        # Önceki dinamik kaynak tag'lerini temizle
        for tag in widget.tag_names():
            if tag.startswith("_src_"):
                widget.tag_delete(tag)

        examples = record.get("ornekler") or []
        has_content = False

        for idx, example in enumerate(examples):
            if not isinstance(example, dict):
                continue
            de = format_display_text(example.get("almanca") or "")
            tr = format_display_text(example.get("turkce") or "")
            kaynak = (example.get("kaynak") or "").strip()
            etiket = (example.get("etiket_turkce") or "").strip()
            nott = (example.get("not") or "").strip()

            if not de:
                continue

            if has_content:
                widget.insert("end", "\n\n")

            if etiket:
                widget.insert("end", f"[{etiket}]\n")

            # Almanca cümle + kaynak badge
            widget.insert("end", f"DE: {de}")
            if kaynak:
                tag_name = f"_src_{idx}"
                widget.tag_configure(tag_name, foreground="#4a90d9", font=("Segoe UI", 9))
                widget.insert("end", "  ⓘ", (tag_name, "src_badge"))
                self._bind_text_tag_tooltip(widget, tag_name, kaynak)

            widget.insert("end", "\n")

            if tr:
                widget.insert("end", f"TR: {tr}\n")
            if nott:
                widget.insert("end", f"Not: {nott}\n")

            has_content = True

        if not has_content:
            de = format_display_text(record.get("ornek_almanca") or "")
            tr = format_display_text(record.get("ornek_turkce") or "")
            if de:
                widget.insert("end", f"DE: {de}\n")
                if tr:
                    widget.insert("end", f"TR: {tr}\n")
            else:
                widget.insert("end", "Bu kayıt için örnek bulunmuyor.")

        widget.yview_moveto(0.0)
        self._block_text_edit_keys(widget)

    def open_settings(self) -> None:
        if self.settings_dialog and self.settings_dialog.winfo_exists():
            self.settings_dialog.bring_to_front()
            return
        self.settings_dialog = SettingsDialog(self)

    def open_dataset_editor(self) -> None:
        if self.dataset_editor_dialog and self.dataset_editor_dialog.winfo_exists():
            self.dataset_editor_dialog.bring_to_front()
            return
        self.dataset_editor_dialog = DatasetEditorDialog(self)

    def open_entry_dialog(self) -> None:
        EntryDialog(self)

    def build_import_runtime(self) -> dict:
        return {
            "build_existing_meaning_index": build_existing_meaning_index,
            "collect_url_import_scan": collect_url_import_scan,
            "collect_parallel_text_import_scan": collect_parallel_text_import_scan_strict,
            "test_llm_connection": test_llm_connection,
            "default_llm_model": DEFAULT_SETTINGS["llm_model"],
            "default_llm_model_api_url": DEFAULT_SETTINGS["llm_api_url"],
            "import_pos_choices": IMPORT_POS_CHOICES,
            "record_key": record_key,
            "save_user_entry": save_user_entry,
            "validate_user_entry": validate_user_entry,
            "increment_frekans_for_seen_terms": increment_frekans_for_seen_terms,
        }

    def open_import_dialog(self, initial_url: str = "", initial_mode: str = "url") -> None:
        mode = str(initial_mode or "url").strip().lower()
        if self.import_dialog and self.import_dialog.winfo_exists():
            if initial_url.strip():
                self.import_dialog.set_initial_url(initial_url)
            self.import_dialog.set_initial_mode(mode)
            self.import_dialog.bring_to_front()
            return
        try:
            from url_ai_import_dialog import EnhancedUrlImportDialog
        except ModuleNotFoundError:
            from scripts.url_ai_import_dialog import EnhancedUrlImportDialog

        self.import_dialog = EnhancedUrlImportDialog(self, self.build_import_runtime(), initial_url=initial_url, initial_mode=mode)

    def open_parallel_text_import_dialog(self) -> None:
        if self.parallel_text_import_dialog and self.parallel_text_import_dialog.winfo_exists():
            self.parallel_text_import_dialog.bring_to_front()
            return
        try:
            from parallel_text_import_dialog import ParallelTextImportDialog
        except ModuleNotFoundError:
            from scripts.parallel_text_import_dialog import ParallelTextImportDialog

        self.parallel_text_import_dialog = ParallelTextImportDialog(self, self.build_import_runtime())

    def open_quiz_dialog(self) -> None:
        if self.quiz_dialog and self.quiz_dialog.winfo_exists():
            self.quiz_dialog.bring_to_front()
            return
        self.quiz_dialog = MiniQuizDialog(self)

    def open_google_translate_for_search(self) -> None:
        text = self.search_var.get().strip()
        if not text:
            messagebox.showinfo("Google Çeviri", "Önce arama kutusuna bir kelime ya da cümle yazın.", parent=self)
            return
        query = urlencode({"sl": "de", "tl": "tr", "text": text, "op": "translate"})
        webbrowser.open(f"https://translate.google.com/?{query}")

    def open_primary_source(self) -> None:
        if self.current_source_urls:
            webbrowser.open(self.current_source_urls[0])
            return
        if self.current_translation_sources and self.current_translation_sources[0].get("url"):
            webbrowser.open(self.current_translation_sources[0]["url"])

    def open_selected_source(self) -> None:
        if not self.current_source_urls:
            return
        selection = self.source_url_listbox.curselection()
        index = selection[0] if selection else 0
        webbrowser.open(self.current_source_urls[index])

    def _open_ref_link(self, key: str) -> None:
        url = self._ref_links.get(key, "")
        if url:
            webbrowser.open(url)

    # --- Referans panel: inline içerik gösterimi ---
    def _show_ref_inline(self, key: str) -> None:
        if key == "duden":
            self._open_ref_link(key)
            return
        url = self._ref_links.get(key, "")
        if not url:
            return
        self._ref_panel_current_key = key
        labels = {"dwds": "DWDS", "wiktionary_de": "Wiktionary DE", "tdk": "TDK"}
        self._ref_panel_title_var.set(f"{labels.get(key, key)} — yükleniyor...")
        self._set_ref_panel_text("İçerik yükleniyor, lütfen bekleyin...")
        if not self._ref_result_panel_visible:
            self._ref_result_panel.grid(row=1, column=0, sticky="ew")
            self._ref_result_panel_visible = True
        threading.Thread(target=self._do_fetch_ref, args=(key, url), daemon=True).start()

    def _hide_ref_panel(self) -> None:
        self._ref_result_panel.grid_remove()
        self._ref_result_panel_visible = False

    def _set_ref_panel_text(self, text: str) -> None:
        self._ref_panel_text.configure(state="normal")
        self._ref_panel_text.delete("1.0", "end")
        self._ref_panel_text.insert("end", text)
        self._block_text_edit_keys(self._ref_panel_text)

    def _do_fetch_ref(self, key: str, url: str) -> None:
        try:
            title, content = self._fetch_ref_content(key, url)
        except Exception as exc:
            title = key.upper()
            content = f"Bağlantı hatası: {exc}"
        self.after(0, lambda t=title, c=content: self._apply_ref_panel_result(t, c))

    def _apply_ref_panel_result(self, title: str, content: str) -> None:
        if not self.winfo_exists():
            return
        self._ref_panel_title_var.set(title)
        self._set_ref_panel_text(content)

    def _fetch_ref_content(self, key: str, url: str) -> tuple[str, str]:
        import urllib.request as _ur
        import urllib.parse as _up
        headers = {"User-Agent": "AlmancaSozluk/1.0 (kisisel sozluk uygulamasi; yasal kullanim)"}

        if key == "tdk":
            tr_word = _up.unquote(url.split("=", 1)[-1])
            api = f"https://sozluk.gov.tr/gts?ara={_up.quote(tr_word)}"
            req = _ur.Request(api, headers=headers)
            with _ur.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            if not isinstance(data, list) or not data:
                return f"TDK — {tr_word}", "Sonuç bulunamadı."
            lines: list[str] = []
            for madde in data:
                anlamlar = madde.get("anlamlarListe") or madde.get("anlamlar") or []
                for i, anlam in enumerate(anlamlar, 1):
                    ozellik = anlam.get("ozelliklerListe") or []
                    etiket = ", ".join(o.get("tam_adi", "") for o in ozellik if o.get("tam_adi")) if ozellik else ""
                    metin = anlam.get("anlam", "").strip()
                    prefix = f"[{etiket}] " if etiket else ""
                    lines.append(f"{i}. {prefix}{metin}")
                    for ornek in (anlam.get("orneklerListe") or []):
                        lines.append(f'   "{ornek.get("ornek", "").strip()}"')
            return f"TDK — {tr_word}", "\n".join(lines) or "Sonuç bulunamadı."

        if key == "wiktionary_de":
            import urllib.error as _ue
            de_word = _up.unquote(url.split("/wiki/", 1)[-1])
            # Strip article prefix if present
            for article in ("der ", "die ", "das "):
                if de_word.lower().startswith(article):
                    de_word = de_word[len(article):]
                    break
            api = f"https://de.wiktionary.org/w/api.php?action=parse&page={_up.quote(de_word)}&format=json&prop=text"
            req = _ur.Request(api, headers=headers)
            try:
                with _ur.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode("utf-8"))
            except _ue.HTTPError as e:
                if e.code == 404:
                    return f"Wiktionary DE — {de_word}", "Bu kelime için Wiktionary DE sayfası bulunamadı."
                raise
            if "error" in data:
                return f"Wiktionary DE — {de_word}", "Bu kelime için Wiktionary DE sayfası bulunamadı."
            html_text = (data.get("parse") or {}).get("text") or {}
            html_content = html_text.get("*", "") if isinstance(html_text, dict) else ""
            dd_items = re.findall(r'<dd>(.*?)</dd>', html_content, re.DOTALL)
            lines = []
            for item in dd_items:
                cleaned = re.sub(r'<[^>]+>', '', item).strip()
                if cleaned and re.match(r'^\[\d+\]', cleaned):
                    lines.append(cleaned)
            return f"Wiktionary DE — {de_word}", "\n".join(lines) or "İçerik bulunamadı."

        if key == "dwds":
            de_word = _up.unquote(url.split("/wb/", 1)[-1])
            html_url = f"https://www.dwds.de/wb/{_up.quote(de_word)}"
            req = _ur.Request(html_url, headers=headers)
            with _ur.urlopen(req, timeout=10) as r:
                html = r.read().decode("utf-8")
            # Primary: <dd> elements with class="dwdswb-definition" (numbered as [1], [2] etc.)
            dd_defs = re.findall(r'<dd[^>]*class="[^"]*dwdswb-definition[^"]*"[^>]*>(.*?)</dd>', html, re.DOTALL)
            lines = []
            if dd_defs:
                for i, d in enumerate(dd_defs, 1):
                    cleaned = re.sub(r'<[^>]+>', '', d).strip()
                    if cleaned:
                        lines.append(f"[{i}] {cleaned}")
            if not lines:
                # Fallback: <span class="dwdswb-definition">
                span_defs = re.findall(r'<span class="dwdswb-definition">(.*?)</span>', html, re.DOTALL)
                for d in span_defs:
                    cleaned = re.sub(r'<[^>]+>', '', d).strip()
                    if cleaned:
                        lines.append(f"• {cleaned}")
            if not lines:
                # Last fallback: <div class="dwdswb-ft-sense-def">
                div_defs = re.findall(r'<div class="dwdswb-ft-sense-def">(.*?)</div>', html, re.DOTALL)
                for d in div_defs:
                    cleaned = re.sub(r'<[^>]+>', '', d).strip()
                    if cleaned:
                        lines.append(f"• {cleaned}")
            return f"DWDS — {de_word}", "\n".join(lines) or "İçerik bulunamadı."

        return key.upper(), "Desteklenmiyor."

    def _update_ref_buttons(self, record: dict | None) -> None:
        links = (record or {}).get("referans_linkler") or {}
        self._ref_links = links
        word = (record or {}).get("almanca", "") or ""
        is_phrase = (
            word.count(" ") >= 2
            or ", " in word
            or " und " in word
            or " oder " in word
        )
        _single_word_keys = {"dwds", "wiktionary_de", "tdk"}
        all_btn_dicts = [
            getattr(self, "_ref_buttons", {}),
            getattr(self, "_ref_buttons_head", {}),
        ]
        for btn_dict in all_btn_dicts:
            for key, btn in btn_dict.items():
                try:
                    if is_phrase and key in _single_word_keys:
                        btn.configure(state="disabled")
                    else:
                        btn.configure(state="normal" if links.get(key) else "disabled")
                except Exception:
                    pass

    def open_selected_translation_source(self) -> None:
        if not self.current_translation_sources:
            return
        selection = self.translation_source_listbox.curselection()
        index = selection[0] if selection else 0
        url = self.current_translation_sources[index].get("url", "")
        if url:
            webbrowser.open(url)

    def search_related_term(self, _event=None) -> None:
        selection = self.related_listbox.curselection()
        if not selection:
            return
        term = self.related_listbox.get(selection[0])
        if term == "İlgili kayıt eklenmemiş.":
            return
        self.apply_search_term(term)

    def toggle_pin_current_record(self) -> None:
        if not self.current_record:
            return
        key_text = serialize_record_key(record_key(self.current_record))
        pinned = [item for item in self.settings.get("pinned_records", []) if item != key_text]
        if len(pinned) == len(self.settings.get("pinned_records", [])):
            pinned.insert(0, key_text)
        self.settings["pinned_records"] = pinned[:MAX_PINNED_RECORDS]
        self.update_quick_access()
        self.refresh_favorite_button()

    def on_close(self) -> None:
        if not messagebox.askyesno("Çıkış", "Uygulamadan çıkmak istediğinize emin misiniz?", parent=self):
            return
        for widget in self.winfo_children():
            if isinstance(widget, tk.Toplevel):
                try:
                    widget.destroy()
                except Exception:
                    pass
        payload = dict(self.settings)
        payload["window_state"] = self.state()
        if payload["window_state"] != "zoomed":
            payload["window_geometry"] = self.geometry()
        if self.are_art_sidebars_visible():
            payload["art_sidebar_width"] = max(
                RIGHT_ART_SIDEBAR_MIN_WIDTH,
                round((self.left_art_sidebar.winfo_width() + self.right_art_sidebar.winfo_width()) / 2),
            )
        payload["last_search"] = self.search_var.get().strip() if payload.get("remember_search", True) else ""
        payload["recent_searches"] = payload.get("recent_searches", [])[:MAX_RECENT_SEARCHES]
        payload["pinned_records"] = payload.get("pinned_records", [])[:MAX_PINNED_RECORDS]
        write_settings(payload)
        self.destroy()


def main() -> None:
    import traceback
    _log_path = PROJECT_ROOT / "desktop_error.log"
    try:
        app = DesktopDictionaryApp()
        app.mainloop()
    except Exception:
        try:
            _log_path.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
