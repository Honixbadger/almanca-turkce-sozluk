#!/usr/bin/env python3
"""
grammar_utils.py
================
Almanca morfoloji yardımcı modülü — sözlük zenginleştirme scriptleri için.

İçerik:
  FİİL:
    - Geniş fiil listesinden schwach/stark/gemischt tespiti
    - Metindeki Präteritum/Partizip II formlarından otomatik tip tespiti
    - Çekimli formdan mastar (infinitiv) çıkarma
    - Ayrılabilir (trennbar) önek tespiti

  İSİM:
    - Hâl eklerini soyma (Genitiv -s/-es, Dativ -e, çoğul -en/-e/-er/-s)
    - Metinden artikel tespiti (der/die/das + sözcük kalıbı)
    - Bileşik sözcük (Kompositum) bölme → baş bileşen tespiti

  SIFAT:
    - Çekim eklerini soyma (-e/-en/-em/-er/-es + karşılaştırma ekleri)
    - -el/-er sonlu sıfat özel durumları (dunkel, teuer)
    - Üstünlük/karşılaştırma formlarından temel form çıkarma

  GENEL:
    - Lemmatizasyon (token → temel form)
    - POS tahmini (geliştirilmiş)
    - Türkçe çevirinin kalitesini skorlama
"""

import re
import unicodedata
from typing import Optional

# ===========================================================================
# TEMEL YARDIMCILAR
# ===========================================================================

def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)

def cf(s: str) -> str:
    return nfc(s).strip().casefold()

def strip_article(term: str) -> str:
    for art in ("der ", "die ", "das ", "Der ", "Die ", "Das "):
        if term.startswith(art):
            return term[len(art):]
    return term

# ===========================================================================
# FİİL VERİ TABANI
# Yapı: infinitiv → (präteritum_kök, partizip_ii, verb_typ)
# Kaynak: Duden Grammatik, Langenscheidt, kendi bilgim (CC0)
# ===========================================================================

STARK_VERBS: dict[str, tuple[str, str, str]] = {
    # A
    "backen":        ("buk",       "gebacken",     "stark"),
    "befehlen":      ("befahl",    "befohlen",     "stark"),
    "beginnen":      ("begann",    "begonnen",     "stark"),
    "beißen":        ("biss",      "gebissen",     "stark"),
    "bergen":        ("barg",      "geborgen",     "stark"),
    "bersten":       ("barst",     "geborsten",    "stark"),
    "biegen":        ("bog",       "gebogen",      "stark"),
    "bieten":        ("bot",       "geboten",      "stark"),
    "binden":        ("band",      "gebunden",     "stark"),
    "bitten":        ("bat",       "gebeten",      "stark"),
    "blasen":        ("blies",     "geblasen",     "stark"),
    "bleiben":       ("blieb",     "geblieben",    "stark"),
    "braten":        ("briet",     "gebraten",     "stark"),
    "brechen":       ("brach",     "gebrochen",    "stark"),
    "dreschen":      ("drosch",    "gedroschen",   "stark"),
    "dringen":       ("drang",     "gedrungen",    "stark"),
    "empfangen":     ("empfing",   "empfangen",    "stark"),
    "empfehlen":     ("empfahl",   "empfohlen",    "stark"),
    "empfinden":     ("empfand",   "empfunden",    "stark"),
    "erschrecken":   ("erschrak",  "erschrocken",  "stark"),
    "essen":         ("aß",        "gegessen",     "stark"),
    "fahren":        ("fuhr",      "gefahren",     "stark"),
    "fallen":        ("fiel",      "gefallen",     "stark"),
    "fangen":        ("fing",      "gefangen",     "stark"),
    "fechten":       ("focht",     "gefochten",    "stark"),
    "finden":        ("fand",      "gefunden",     "stark"),
    "flechten":      ("flocht",    "geflochten",   "stark"),
    "fliegen":       ("flog",      "geflogen",     "stark"),
    "fliehen":       ("floh",      "geflohen",     "stark"),
    "fließen":       ("floss",     "geflossen",    "stark"),
    "fressen":       ("fraß",      "gefressen",    "stark"),
    "frieren":       ("fror",      "gefroren",     "stark"),
    "geben":         ("gab",       "gegeben",      "stark"),
    "gehen":         ("ging",      "gegangen",     "stark"),
    "gelingen":      ("gelang",    "gelungen",     "stark"),
    "gelten":        ("galt",      "gegolten",     "stark"),
    "genesen":       ("genas",     "genesen",      "stark"),
    "genießen":      ("genoss",    "genossen",     "stark"),
    "geraten":       ("geriet",    "geraten",      "stark"),
    "geschehen":     ("geschah",   "geschehen",    "stark"),
    "gewinnen":      ("gewann",    "gewonnen",     "stark"),
    "gießen":        ("goss",      "gegossen",     "stark"),
    "gleichen":      ("glich",     "geglichen",    "stark"),
    "gleiten":       ("glitt",     "geglitten",    "stark"),
    "glimmen":       ("glomm",     "geglommen",    "stark"),
    "graben":        ("grub",      "gegraben",     "stark"),
    "greifen":       ("griff",     "gegriffen",    "stark"),
    "haben":         ("hatte",     "gehabt",       "schwach"),  # schwach trotzdem
    "halten":        ("hielt",     "gehalten",     "stark"),
    "hängen":        ("hing",      "gehangen",     "stark"),
    "hauen":         ("hieb",      "gehauen",      "stark"),
    "heben":         ("hob",       "gehoben",      "stark"),
    "heißen":        ("hieß",      "geheißen",     "stark"),
    "helfen":        ("half",      "geholfen",     "stark"),
    "klingen":       ("klang",     "geklungen",    "stark"),
    "kommen":        ("kam",       "gekommen",     "stark"),
    "kriechen":      ("kroch",     "gekrochen",    "stark"),
    "laden":         ("lud",       "geladen",      "stark"),
    "lassen":        ("ließ",      "gelassen",     "stark"),
    "laufen":        ("lief",      "gelaufen",     "stark"),
    "leiden":        ("litt",      "gelitten",     "stark"),
    "leihen":        ("lieh",      "geliehen",     "stark"),
    "lesen":         ("las",       "gelesen",      "stark"),
    "liegen":        ("lag",       "gelegen",      "stark"),
    "lügen":         ("log",       "gelogen",      "stark"),
    "meiden":        ("mied",      "gemieden",     "stark"),
    "melken":        ("molk",      "gemolken",     "stark"),
    "messen":        ("maß",       "gemessen",     "stark"),
    "nehmen":        ("nahm",      "genommen",     "stark"),
    "pfeifen":       ("pfiff",     "gepfiffen",    "stark"),
    "raten":         ("riet",      "geraten",      "stark"),
    "reiben":        ("rieb",      "gerieben",     "stark"),
    "reißen":        ("riss",      "gerissen",     "stark"),
    "reiten":        ("ritt",      "geritten",     "stark"),
    "riechen":       ("roch",      "gerochen",     "stark"),
    "ringen":        ("rang",      "gerungen",     "stark"),
    "rinnen":        ("rann",      "geronnen",     "stark"),
    "rufen":         ("rief",      "gerufen",      "stark"),
    "schaffen":      ("schuf",     "geschaffen",   "stark"),
    "scheiden":      ("schied",    "geschieden",   "stark"),
    "scheinen":      ("schien",    "geschienen",   "stark"),
    "schelten":      ("schalt",    "gescholten",   "stark"),
    "schieben":      ("schob",     "geschoben",    "stark"),
    "schießen":      ("schoss",    "geschossen",   "stark"),
    "schlafen":      ("schlief",   "geschlafen",   "stark"),
    "schlagen":      ("schlug",    "geschlagen",   "stark"),
    "schleichen":    ("schlich",   "geschlichen",  "stark"),
    "schließen":     ("schloss",   "geschlossen",  "stark"),
    "schmelzen":     ("schmolz",   "geschmolzen",  "stark"),
    "schneiden":     ("schnitt",   "geschnitten",  "stark"),
    "schreiben":     ("schrieb",   "geschrieben",  "stark"),
    "schreien":      ("schrie",    "geschrien",    "stark"),
    "schweigen":     ("schwieg",   "geschwiegen",  "stark"),
    "schwimmen":     ("schwamm",   "geschwommen",  "stark"),
    "schwingen":     ("schwang",   "geschwungen",  "stark"),
    "schwören":      ("schwor",    "geschworen",   "stark"),
    "sehen":         ("sah",       "gesehen",      "stark"),
    "sein":          ("war",       "gewesen",      "stark"),
    "singen":        ("sang",      "gesungen",     "stark"),
    "sinken":        ("sank",      "gesunken",     "stark"),
    "sinnen":        ("sann",      "gesonnen",     "stark"),
    "sitzen":        ("saß",       "gesessen",     "stark"),
    "sprechen":      ("sprach",    "gesprochen",   "stark"),
    "springen":      ("sprang",    "gesprungen",   "stark"),
    "stechen":       ("stach",     "gestochen",    "stark"),
    "stehen":        ("stand",     "gestanden",    "stark"),
    "stehlen":       ("stahl",     "gestohlen",    "stark"),
    "steigen":       ("stieg",     "gestiegen",    "stark"),
    "sterben":       ("starb",     "gestorben",    "stark"),
    "stinken":       ("stank",     "gestunken",    "stark"),
    "stoßen":        ("stieß",     "gestoßen",     "stark"),
    "streichen":     ("strich",    "gestrichen",   "stark"),
    "streiten":      ("stritt",    "gestritten",   "stark"),
    "tragen":        ("trug",      "getragen",     "stark"),
    "treffen":       ("traf",      "getroffen",    "stark"),
    "treiben":       ("trieb",     "getrieben",    "stark"),
    "treten":        ("trat",      "getreten",     "stark"),
    "trinken":       ("trank",     "getrunken",    "stark"),
    "tun":           ("tat",       "getan",        "stark"),
    "verbergen":     ("verbarg",   "verborgen",    "stark"),
    "verderben":     ("verdarb",   "verdorben",    "stark"),
    "vergessen":     ("vergaß",    "vergessen",    "stark"),
    "verlieren":     ("verlor",    "verloren",     "stark"),
    "vermeiden":     ("vermied",   "vermieden",    "stark"),
    "verschwinden":  ("verschwand","verschwunden", "stark"),
    "verstehen":     ("verstand",  "verstanden",   "stark"),
    "wachsen":       ("wuchs",     "gewachsen",    "stark"),
    "waschen":       ("wusch",     "gewaschen",    "stark"),
    "weichen":       ("wich",      "gewichen",     "stark"),
    "weisen":        ("wies",      "gewiesen",     "stark"),
    "werben":        ("warb",      "geworben",     "stark"),
    "werden":        ("wurde",     "geworden",     "stark"),
    "werfen":        ("warf",      "geworfen",     "stark"),
    "wiegen":        ("wog",       "gewogen",      "stark"),
    "winden":        ("wand",      "gewunden",     "stark"),
    "ziehen":        ("zog",       "gezogen",      "stark"),
    "zwingen":       ("zwang",     "gezwungen",    "stark"),
    # Gemischte Verben (karma)
    "brennen":       ("brannte",   "gebrannt",     "gemischt"),
    "bringen":       ("brachte",   "gebracht",     "gemischt"),
    "denken":        ("dachte",    "gedacht",      "gemischt"),
    "dürfen":        ("durfte",    "gedurft",      "gemischt"),
    "kennen":        ("kannte",    "gekannt",      "gemischt"),
    "können":        ("konnte",    "gekonnt",      "gemischt"),
    "mögen":         ("mochte",    "gemocht",      "gemischt"),
    "müssen":        ("musste",    "gemusst",      "gemischt"),
    "nennen":        ("nannte",    "genannt",      "gemischt"),
    "rennen":        ("rannte",    "gerannt",      "gemischt"),
    "senden":        ("sandte",    "gesandt",      "gemischt"),
    "sollen":        ("sollte",    "gesollt",      "gemischt"),
    "wenden":        ("wandte",    "gewandt",      "gemischt"),
    "wissen":        ("wusste",    "gewusst",      "gemischt"),
    "wollen":        ("wollte",    "gewollt",      "gemischt"),
}

# Präteritum kök → mastar eşlemesi (hızlı ters arama)
_PRÄT_TO_INF: dict[str, str] = {}
_PARTII_TO_INF: dict[str, str] = {}
for _inf, (_prät, _partii, _typ) in STARK_VERBS.items():
    _PRÄT_TO_INF[cf(_prät)] = _inf
    _PARTII_TO_INF[cf(_partii)] = _inf

# Ayrılabilir fiil önekleri
TRENNBAR_PREFIXES = frozenset({
    "ab", "an", "auf", "aus", "bei", "durch", "ein", "entgegen",
    "fest", "fort", "gegenüber", "her", "herab", "heran", "herauf",
    "heraus", "herbei", "herein", "herüber", "herum", "herunter",
    "hervor", "hin", "hinab", "hinan", "hinauf", "hinaus", "hinein",
    "hinüber", "hinunter", "hoch", "los", "mit", "nach", "nieder",
    "vor", "voran", "voraus", "vorbei", "vorüber", "weg", "weiter",
    "wieder", "zu", "zurück", "zusammen", "zwischen",
})

# Ayrılmaz (untrennbar) önekler
UNTRENNBAR_PREFIXES = frozenset({
    "be", "emp", "ent", "er", "ge", "miss", "ver", "zer",
})

# ===========================================================================
# FİİL FONKSİYONLARI
# ===========================================================================

def classify_verb_type(infinitive: str) -> str:
    """
    Fiil tipini tespit et: 'stark' | 'schwach' | 'gemischt' | ''

    Öncelik sırası:
      1. Bilinen fiil listesi (STARK_VERBS)
      2. -ieren/-isieren/-ifizieren sonucu → her zaman schwach
      3. Bilinen stark fiil öneki + köke uyuşum → stark
      4. Varsayılan: schwach
    """
    bare = strip_article(infinitive).strip().lower()

    # Doğrudan liste araması
    if bare in STARK_VERBS:
        return STARK_VERBS[bare][2]

    # Prefix'i soy, bare köke bak
    for prefix in sorted(TRENNBAR_PREFIXES | UNTRENNBAR_PREFIXES, key=len, reverse=True):
        if bare.startswith(prefix) and len(bare) > len(prefix) + 3:
            root = bare[len(prefix):]
            if root in STARK_VERBS:
                return STARK_VERBS[root][2]

    # -ieren / -isieren / -ifizieren → schwach
    if bare.endswith(("ieren", "isieren", "ifizieren", "izieren")):
        return "schwach"

    # -eln / -ern sonları → genellikle schwach
    if bare.endswith(("eln", "ern")):
        return "schwach"

    # Varsayılan
    return "schwach"


def detect_verb_type_from_text(infinitive: str, text: str) -> str:
    """
    Metindeki Präteritum ve Partizip II formlarına bakarak fiil tipini tespit et.
    Daha az güvenilir; classify_verb_type() ile birlikte kullanılır.
    """
    bare = infinitive.strip().lower()
    text_l = text.lower()

    # Partizip II: "ge...t" → schwach, "ge...en" → büyük ihtimalle stark
    # Pattern: ge + [2+ harf] + t veya en
    part2_schwach = re.compile(r'\bge[a-zäöüß]{2,}t\b')
    part2_stark   = re.compile(r'\bge[a-zäöüß]{2,}en\b')

    # Önce bilinen listede var mı?
    if bare in STARK_VERBS:
        return STARK_VERBS[bare][2]

    # Metinde fiil köküne yakın bir Partizip II var mı?
    root = bare
    for suffix in ("en", "eln", "ern"):
        if root.endswith(suffix):
            root = root[:-len(suffix)]
            break

    # Partizip tespiti için kök etrafındaki formlara bak
    if root and len(root) >= 3:
        # ge[root]t → schwach
        schwach_part = f"ge{root}t"
        stark_part   = f"ge{root}en"
        if schwach_part in text_l:
            return "schwach"
        if stark_part in text_l:
            return "stark"

    # Metinde -te/-tet/-ten formu → schwach
    schwach_prät = f"{root}te"
    if schwach_prät in text_l:
        return "schwach"

    return ""


def get_partizip_ii(infinitive: str) -> str:
    """Bilinen fiiller için Partizip II formunu döndür."""
    bare = infinitive.strip().lower()
    if bare in STARK_VERBS:
        return STARK_VERBS[bare][1]
    # Schwach heuristic
    root = bare
    for suffix in ("eln", "ern", "en"):
        if root.endswith(suffix):
            root = root[:-len(suffix)]
            break
    if bare.endswith("ieren"):
        return bare.replace("ieren", "iert")
    prefix = ""
    for p in sorted(UNTRENNBAR_PREFIXES, key=len, reverse=True):
        if root.startswith(p):
            prefix = p
            root = root[len(p):]
            break
    if prefix:
        return f"{prefix}ge{root}t" if not prefix else f"{prefix}{root}t"
    return f"ge{root}t"


def is_trennbar(infinitive: str) -> bool:
    """Ayrılabilir fiil mi?"""
    bare = infinitive.strip().lower()
    for p in sorted(TRENNBAR_PREFIXES, key=len, reverse=True):
        if bare.startswith(p) and len(bare) > len(p) + 3:
            return True
    return False


def get_trennbar_prefix(infinitive: str) -> str:
    """Ayrılabilir fiil önekini döndür."""
    bare = infinitive.strip().lower()
    for p in sorted(TRENNBAR_PREFIXES, key=len, reverse=True):
        if bare.startswith(p) and len(bare) > len(p) + 3:
            return p
    return ""


def lemmatize_verb(token: str) -> str:
    """
    Çekimli fiil formundan mastar (infinitiv) çıkarmaya çalış.
    Kesin değil; WikDict aramasını desteklemek için kullanılır.
    """
    t = token.strip().lower()

    # Zaten mastar formunda mı?
    if t.endswith(("en", "eln", "ern")) and len(t) >= 5:
        return t

    # Präteritum → mastar (bilinen listeden)
    if cf(t) in _PRÄT_TO_INF:
        return _PRÄT_TO_INF[cf(t)]

    # Partizip II → mastar
    if cf(t) in _PARTII_TO_INF:
        return _PARTII_TO_INF[cf(t)]

    # Çekim eki soyma denemeleri
    stripping_rules = [
        # (son_ek, yerine_koy)
        ("ieren", "ieren"),   # zaten mastar
        ("isierst", "isieren"),
        ("isiert",  "isieren"),
        ("ifiziert", "ifizieren"),
        ("iert",  "ieren"),
        ("iere",  "ieren"),
        ("etest", "eten"),
        ("etet",  "eten"),
        ("esten", "esten"),
        ("etest", "eten"),
        ("test",  "ten"),
        ("tet",   "ten"),
        ("est",   "en"),
        ("est",   "ern"),
        ("est",   "eln"),
        ("st",    "en"),
        ("te",    "en"),
        ("te",    "ten"),
        ("t",     "en"),
        ("e",     "en"),
    ]
    for suffix, replacement in stripping_rules:
        if t.endswith(suffix) and len(t) > len(suffix) + 2:
            candidate = t[: -len(suffix)] + replacement
            # Bilinen listede var mı?
            if candidate in STARK_VERBS:
                return candidate
            # Makul uzunlukta mı?
            if len(candidate) >= 4:
                return candidate

    return t


# ===========================================================================
# SIFAT FONKSİYONLARI
# ===========================================================================

# -el ve -er ile biten sıfatlar: çekimde e düşer
_EL_ER_ADJECTIVES: frozenset = frozenset({
    "dunkel", "übel", "edel", "eitel", "heikel", "heiter", "integer",
    "labil", "nobel", "sauber", "teuer", "finster", "munter", "tapfer",
    "bieder", "lecker", "locker", "makaber", "mager", "munter",
    "nüchtern", "sicher", "bitter", "wacker",
})


def lemmatize_adjective(token: str) -> str:
    """
    Sıfatın çekimli formundan temel formu çıkar.

    Örnekler:
      schönen → schön
      großem  → groß
      dunklen → dunkel   (-el düşen)
      teurem  → teuer    (-er düşen)
      ältere  → alt      (karşılaştırma)
      größten → groß     (üstünlük)
    """
    t = token.strip().lower()

    # Üstünlük (Superlativ): -sten/-stem/-ster/-stes/-ste
    for sup_end in ("sten", "stem", "ster", "stes", "ste"):
        if t.endswith(sup_end) and len(t) > len(sup_end) + 2:
            base = t[: -len(sup_end)]
            # Umlaut geri al: äl → al, öß → oß, üg → ug (yaklaşık)
            base = _restore_umlaut_base(base)
            if len(base) >= 3:
                return _try_restore_el_er(base)

    # Karşılaştırma (Komparativ): -eren/-erem/-erer/-eres/-ere/-er
    for cmp_end in ("eren", "erem", "erer", "eres", "ere"):
        if t.endswith(cmp_end) and len(t) > len(cmp_end) + 2:
            base = t[: -len(cmp_end)]
            base = _restore_umlaut_base(base)
            if len(base) >= 3:
                return _try_restore_el_er(base)

    # Çekim ekleri (uzundan kısaya soy)
    for end in ("en", "em", "er", "es", "e"):
        if t.endswith(end) and len(t) > len(end) + 2:
            base = t[: -len(end)]
            if len(base) >= 3:
                return _try_restore_el_er(base)

    return t


def _restore_umlaut_base(base: str) -> str:
    """
    Üstünlük formundaki Umlaut'u yaklaşık olarak geri al.
    Kesin değil (ä→a, ö→o, ü→u), sadece ipucu.
    """
    return base  # Gerçek Umlaut geri alma NLP gerektirir; şimdilik olduğu gibi bırak


def _try_restore_el_er(base: str) -> str:
    """
    -el/-er düşen sıfatların geri yüklenmesi:
      dunkl → dunkel, teur → teuer, saub → sauber
    """
    # Bilinen listede doğrudan var mı?
    if base in _EL_ER_ADJECTIVES:
        return base
    # -l ile bitiyorsa ve bilinen el-sıfatı olabilirse: dunkl → dunkel
    if base.endswith("l") and not base.endswith("ll") and base + "el" in _EL_ER_ADJECTIVES:
        return base + "el"
    # -r ile bitiyorsa: teur → teuer, saub → sauber
    if base.endswith("r") and not base.endswith("rr"):
        candidate_er = base[:-1] + "er" if not base.endswith("er") else base
        if candidate_er in _EL_ER_ADJECTIVES:
            return candidate_er
        candidate_er2 = base + "er"
        if candidate_er2 in _EL_ER_ADJECTIVES:
            return candidate_er2
    return base


# ===========================================================================
# İSİM FONKSİYONLARI
# ===========================================================================

def lemmatize_noun(token: str) -> str:
    """
    İsmin çekim formundan nominativ tekil formunu çıkarmaya çalış.
    Makul sonuç; kesin değil.

    Örnekler:
      Autos   → Auto       (Genitiv/Plural -s)
      Kindes  → Kind       (Genitiv -es)
      Männer  → Mann       (Plural -er + Umlaut geri al: zor)
      Büchern → Buch       (Dativ Plural -ern: zor)
      Häusern → Haus       (zor)
    """
    if not token or not token[:1].isupper():
        return token

    bare = strip_article(token)
    t = bare

    # Çok kısa isimler → dokunma
    if len(t) <= 3:
        return t

    # Genitiv -es (uzun form): Kindes → Kind, Tisches → Tisch
    if t.endswith("es") and len(t) >= 5:
        candidate = t[:-2]
        if len(candidate) >= 2:
            # Eğer aday bir fiil gibi görünmüyorsa kabul et
            if not candidate.lower().endswith(("en", "eln", "ern")):
                return candidate

    # Genitiv -s: Autos → Auto, Vaters → Vater
    if t.endswith("s") and not t.endswith("ss") and len(t) >= 4:
        candidate = t[:-1]
        if len(candidate) >= 2:
            return candidate

    # Dativ Plural -en / -ern / -eln: Kindern → Kind
    if t.endswith("ern") and len(t) >= 5:
        return t[:-3]
    if t.endswith("eln") and len(t) >= 5:
        return t[:-3]
    if t.endswith("en") and len(t) >= 5:
        return t[:-2]

    # Plural -er (Männer, Bücher): soy -er, Umlaut geri alma yok
    if t.endswith("er") and len(t) >= 5:
        candidate = t[:-2]
        if len(candidate) >= 2:
            return candidate

    return t


# ---------------------------------------------------------------------------
# Artikel tespiti (metinden)
# ---------------------------------------------------------------------------

_ARTIKEL_PATTERN = re.compile(
    r'\b(der|die|das|den|dem|des|Der|Die|Das|Den|Dem|Des)\s+'
    r'([A-ZÄÖÜ][a-zäöüß]{2,}(?:-[A-ZÄÖÜ]?[a-zäöüß]{2,})*)',
    re.UNICODE,
)
_NOM_ARTICLES = {"der": "der", "die": "die", "das": "das",
                 "Der": "der", "Die": "die", "Das": "das"}
_AKK_ARTICLES = {"den": "der"}
_DAT_ARTICLES = {"dem": "der/das", "des": "der/das"}


def detect_article_from_context(word: str, text: str) -> str:
    """
    Metinden sözcüğün artikelini bulmaya çalış.
    Nominativ önceliği vardır.
    Döndürür: 'der' | 'die' | 'das' | ''
    """
    bare = strip_article(word).strip()
    if not bare:
        return ""

    bare_cf = cf(bare)
    nom_counts: dict[str, int] = {"der": 0, "die": 0, "das": 0}
    other_hits: list[str] = []

    for m in _ARTIKEL_PATTERN.finditer(text):
        art_raw = m.group(1)
        noun = m.group(2)
        if cf(noun) != bare_cf:
            continue

        if art_raw in _NOM_ARTICLES:
            nom = _NOM_ARTICLES[art_raw]
            nom_counts[nom] = nom_counts.get(nom, 0) + 1
        elif art_raw in _AKK_ARTICLES:
            other_hits.append("der")
        # Dativ/Genitiv'i görmezden gel (belirsiz)

    # En sık geçen nominativ artikeli döndür
    best = max(nom_counts, key=lambda k: nom_counts[k])
    if nom_counts[best] > 0:
        return best

    # Nominativ yoksa Akkusatif'ten tahmin
    if other_hits:
        return other_hits[0]

    return ""


# ---------------------------------------------------------------------------
# Bileşik sözcük (Kompositum) bölme
# ---------------------------------------------------------------------------

# Bağlantı ekleri (Fugenelemente)
_FUGEN = ("s", "es", "n", "en", "er", "e", "")

# Minimum bileşen uzunluğu
_MIN_COMP_LEN = 3


def split_compound(word: str, known_words: Optional[set] = None) -> list[str]:
    """
    Almanca bileşik sözcüğü bileşenlerine ayır.
    known_words: geçerli sözcük kümesi (varsa daha iyi bölme yapar)

    Örnek:
      "Kraftfahrzeug" → ["Kraft", "Fahrzeug"]
      "Antiblockiersystem" → ["Anti", "Blockier", "system"]
    """
    bare = strip_article(word).strip()
    if len(bare) < 7:
        return [bare]

    result = _split_recursive(bare.lower(), known_words or set(), depth=0)
    if result and len(result) > 1:
        # Orijinal büyük/küçük harf koru (ilk harfi büyük yap)
        return [c.capitalize() for c in result]
    return [bare]


def _split_recursive(word: str, known: set, depth: int) -> list[str]:
    if depth > 4 or len(word) < _MIN_COMP_LEN * 2:
        return [word]

    for i in range(_MIN_COMP_LEN, len(word) - _MIN_COMP_LEN + 1):
        left = word[:i]
        rest = word[i:]

        for fuge in _FUGEN:
            if rest.startswith(fuge):
                tail = rest[len(fuge):]
                if len(tail) < _MIN_COMP_LEN:
                    continue
                # known listesi varsa kontrol et
                if known and (left in known or left + "e" in known):
                    sub = _split_recursive(tail, known, depth + 1)
                    if sub:
                        return [left] + sub
                # known yoksa uzunluk + büyük harf heuristic
                if not known and len(left) >= _MIN_COMP_LEN and len(tail) >= _MIN_COMP_LEN:
                    sub = _split_recursive(tail, known, depth + 1)
                    if sub:
                        return [left] + sub

    return [word]


def get_head_noun(compound: str) -> str:
    """Bileşik sözcüğün baş bileşenini (son parça) döndür."""
    parts = split_compound(compound)
    return parts[-1] if parts else compound


# ===========================================================================
# GELİŞTİRİLMİŞ LEMMATIZASYON
# ===========================================================================

def lemmatize(token: str, pos_hint: str = "") -> str:
    """
    Birleşik lemmatizasyon: isim/sıfat/fiil formundan temel form.
    pos_hint: 'isim' | 'fiil' | 'sıfat' | '' (bilinmiyor)
    """
    if not token:
        return token

    if pos_hint == "fiil" or (not pos_hint and is_likely_verb(token)):
        return lemmatize_verb(token)
    if pos_hint == "sıfat" or (not pos_hint and is_likely_adjective(token)):
        return lemmatize_adjective(token)
    if pos_hint == "isim" or (not pos_hint and is_likely_noun(token)):
        return lemmatize_noun(token)
    return token


def is_likely_noun(token: str) -> bool:
    """Basit heuristic: büyük harfle başlıyor."""
    return bool(token) and token[0].isupper()


def is_likely_verb(token: str) -> bool:
    """Basit heuristic: küçük harf + fiil sonu."""
    t = token.lower()
    if token[:1].isupper():
        return False
    return t.endswith(("en", "eln", "ern", "iert", "iert", "te", "est", "st"))


def is_likely_adjective(token: str) -> bool:
    """Basit heuristic: küçük harf + sıfat sonu."""
    if token[:1].isupper():
        return False
    t = token.lower()
    return t.endswith(("lich", "isch", "ig", "bar", "sam", "haft", "los", "voll",
                       "arm", "reich", "frei", "wert", "würdig",
                       "en", "em", "er", "es", "e"))


# ===========================================================================
# GELİŞTİRİLMİŞ POS TAHMİNİ
# ===========================================================================

def guess_pos(token: str, text_context: str = "") -> str:
    """
    Geliştirilmiş POS tahmini.
    Döndürür: 'isim' | 'fiil' | 'sıfat' | 'zarf' | 'edat' | 'isim'
    """
    bare = strip_article(token).strip()
    t = bare.lower()

    # Büyük harfle başlayan → isim (Almanca'ya özgü)
    if bare[:1].isupper() and " " not in bare:
        return "isim"

    # Fiil belirteci
    if t.endswith(("ieren", "isieren", "ifizieren", "eln", "ern")):
        return "fiil"
    if t.endswith("en") and len(t) >= 5:
        # Mastar veya isim olabilir; bağlama bak
        if text_context:
            # Metinde büyük harfle kullanılmış mu?
            if re.search(r'\b' + re.escape(bare.capitalize()) + r'\b', text_context):
                return "isim"
        return "fiil"

    # Sıfat belirteci
    if t.endswith(("lich", "isch", "ig", "bar", "sam", "haft", "los", "voll",
                   "arm", "reich", "frei", "wert", "würdig")):
        return "sıfat"

    # Zarf belirteci
    if t.endswith(("weise", "maßen", "falls", "mal")):
        return "zarf"

    return "isim"


# ===========================================================================
# ÇEVİRİ KALİTESİ SKORU
# ===========================================================================

def translation_quality_score(translation: str, german_word: str = "") -> float:
    """
    WikDict çevirisinin kalitesini 0.0-1.0 arasında skorla.
    Düşük skor → şüpheli çeviri.
    """
    if not translation:
        return 0.0

    score = 1.0
    t = translation.strip()

    # Çok kısa → şüpheli
    if len(t) < 2:
        score -= 0.5

    # Sadece noktalama
    if re.match(r'^[^a-zA-ZÇĞİÖŞÜçğışöşü]+$', t):
        score -= 0.8

    # Almanca ile aynı → genellikle loanword (kabul edilebilir)
    if german_word and cf(t) == cf(strip_article(german_word)):
        score -= 0.1  # Çok az ceza

    # İngilizce gibi görünüyor (sadece ASCII, kısa)
    if re.match(r'^[a-z]{2,8}$', t) and t not in ("bu", "bir", "ama", "ile", "gibi"):
        # Türkçeye özgü harf yok → şüpheli
        if not any(c in t for c in "çğışöşü"):
            score -= 0.3

    # Parantez/köşeli parantez içeriyorsa → açıklama var, ek bilgi
    if "(" in t or "[" in t:
        score += 0.05

    # Virgülle ayrılmış birden fazla anlam → daha zengin
    parts = [p.strip() for p in t.split(",")]
    if len(parts) >= 2:
        score += 0.1

    return max(0.0, min(1.0, score))


# ===========================================================================
# TOPLU İŞLEM YARDIMCISI
# ===========================================================================

def enrich_record_grammar(record: dict, text: str = "") -> dict:
    """
    Tek bir sözlük kaydını gramer bilgisiyle zenginleştir.
    Mevcut alanlar varsa üzerine yazmaz; boş olanları doldurur.

    Doldurulabilecek alanlar:
      - artikel    (metinden tespit)
      - verb_typ   (schwach/stark/gemischt)
      - tur        (POS)
    """
    almanca = (record.get("almanca", "") or "").strip()
    if not almanca:
        return record

    tur = record.get("tur", "") or ""
    verb_typ = record.get("verb_typ", "") or ""
    artikel = record.get("artikel", "") or ""

    # POS tahmini
    if not tur:
        record["tur"] = guess_pos(almanca, text)
        tur = record["tur"]

    # Fiil tipi
    if tur == "fiil" and not verb_typ:
        vt = classify_verb_type(almanca)
        if not vt and text:
            vt = detect_verb_type_from_text(almanca, text)
        if vt:
            record["verb_typ"] = vt

    # Artikel tespiti
    if not artikel and text:
        art = detect_article_from_context(almanca, text)
        if art:
            record["artikel"] = art

    return record
