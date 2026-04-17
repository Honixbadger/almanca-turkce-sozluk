#!/usr/bin/env python3
"""
Wiktionary DE'den isimler icin:
  - artikel (der/die/das)
  - genitiv_endung
  - cogul
  - tanim_almanca
  - cekimler (Nominativ/Genitiv/Dativ/Akkusativ)
Her 200 kelimede bir kaydet. Cache kullan.
"""

import json, urllib.request, urllib.parse, re, time, sys
from datetime import datetime

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"
LOG_PATH   = "wikt_noun_enrichment.log"
CACHE_PATH = "wikt_noun_cache.json"
MAX_HOURS  = 6

START_TIME = time.time()


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def fetch_batch(words):
    titles = "|".join(words)
    url = (
        "https://de.wiktionary.org/w/api.php?action=query"
        "&prop=revisions&rvprop=content&format=json&formatversion=2"
        "&titles=" + urllib.parse.quote(titles)
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": "AlmancaSozluk/1.0 (enrichment)"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def parse_genus(wikitext):
    """der/die/das cikart"""
    # {{Deutsch Substantiv Ubersicht|Genus=n}} veya |Genus 1=m
    m = re.search(r'\|Genus\s*[12]?\s*=\s*([mfn])', wikitext)
    if m:
        g = m.group(1)
        return {"m": "der", "f": "die", "n": "das"}.get(g, "")
    # Alternatif: Worttrennung bolumundeki der/die/das
    m = re.search(r'\{\{([Dd]er|[Dd]ie|[Dd]as)\|', wikitext)
    if m:
        return m.group(1).lower()
    return ""


def parse_genitiv(wikitext):
    """Genitiv Singular cikart"""
    # Substantiv Ubersicht tablosunda
    m = re.search(r'\|Genitiv Singular\s*=\s*([^\n|]+)', wikitext)
    if not m:
        m = re.search(r'\|Genitiv Singular 1\s*=\s*([^\n|]+)', wikitext)
    if m:
        val = m.group(1).strip()
        val = re.sub(r'\{\{.*?\}\}', '', val).strip()
        if val and val not in ('—', '-', ''):
            # Endung: tam kelimeden son karakteri al, ya da s/es/en etc
            return val
    return ""


def parse_cogul(wikitext):
    """Nominativ Plural cikart"""
    m = re.search(r'\|Nominativ Plural\s*=\s*([^\n|]+)', wikitext)
    if not m:
        m = re.search(r'\|Nominativ Plural 1\s*=\s*([^\n|]+)', wikitext)
    if m:
        val = m.group(1).strip()
        val = re.sub(r'\{\{.*?\}\}', '', val).strip()
        if val and val not in ('—', '-', '', '–'):
            return val
    return ""


def parse_bedeutungen(wikitext):
    """Almanca tanim (ilk 2 anlam)"""
    lines = []
    in_bed = False
    for line in wikitext.splitlines():
        if "{{Bedeutungen}}" in line:
            in_bed = True
            continue
        if in_bed:
            if line.startswith("{{") and "Bedeutungen" not in line and not line.startswith(":"):
                break
            if line.startswith(":") and not line.startswith("::"):
                s = line.lstrip(":")
                s = re.sub(r'\[\[([^\|\]]+\|)?([^\]]+)\]\]', r'\2', s)
                s = re.sub(r'\{\{[Kk]\|[^}]+\}\}', '', s)
                s = re.sub(r'\{\{[^}]+\}\}', '', s)
                s = re.sub(r'^\[[\d,\s]+\]\s*', '', s)
                s = s.strip()
                if len(s) > 5:
                    lines.append(s)
            if len(lines) >= 2:
                break
    return "; ".join(lines)


def parse_cekimler(wikitext, artikel):
    """Temel halleri cikart"""
    cases = {}
    patterns = [
        ("Nominativ Singular", "nom_sg"),
        ("Genitiv Singular", "gen_sg"),
        ("Dativ Singular", "dat_sg"),
        ("Akkusativ Singular", "akk_sg"),
        ("Nominativ Plural", "nom_pl"),
    ]
    for pat, key in patterns:
        m = re.search(rf'\|{pat}\s*(?:1\s*)?=\s*([^\n|]+)', wikitext)
        if m:
            val = m.group(1).strip()
            val = re.sub(r'\{\{.*?\}\}', '', val).strip()
            if val and val not in ('—', '-', '–', ''):
                cases[key] = val
    return cases if cases else None


def save(data):
    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    log("=== Wiktionary Noun Enrichment basliyor ===")

    with open(DICT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    log(f"Sozluk: {len(data)} giris")

    # Cache yukle
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)
        log(f"Cache yuklendi: {len(cache)} kayit")
    except Exception:
        cache = {}
        log("Cache yok, sifirdan basliyor")

    # Hedefler: isimler + fiiller (partizip2 icin)
    noun_targets = [
        (i, e) for i, e in enumerate(data)
        if e.get("tur") == "isim" and (
            not e.get("artikel") or
            not e.get("genitiv_endung") or
            not e.get("cogul") or
            not e.get("tanim_almanca")
        )
    ]
    verb_targets = [
        (i, e) for i, e in enumerate(data)
        if e.get("tur") == "fiil" and not e.get("partizip2")
    ]

    log(f"Isim hedef: {len(noun_targets)}, Fiil (partizip2) hedef: {len(verb_targets)}")

    all_targets = noun_targets + verb_targets
    eksik = [(i, e) for i, e in all_targets if e.get("almanca", "") not in cache]
    log(f"Cache'de olmayan: {len(eksik)}")

    BATCH = 50
    batch_no = 0
    updated = 0

    for start in range(0, len(eksik), BATCH):
        if (time.time() - START_TIME) > MAX_HOURS * 3600:
            log("Zaman siniri! Duruyorum.")
            break

        chunk = eksik[start:start + BATCH]
        words = [e["almanca"] for _, e in chunk]

        try:
            resp = fetch_batch(words)
            pages = resp.get("query", {}).get("pages", [])
            for page in pages:
                title = page.get("title", "")
                revs = page.get("revisions", [])
                if not revs:
                    cache[title] = {}
                    continue
                wt = revs[0].get("content", "")
                # Sadece Deutsch bolumunu al
                de_match = re.search(r'== .+? \(\{\{Sprache\|Deutsch\}\}\) ==(.+?)(?:== .+? \(\{\{Sprache\|)', wt, re.DOTALL)
                wt_de = de_match.group(1) if de_match else wt

                entry_data = {
                    "artikel": parse_genus(wt_de),
                    "genitiv": parse_genitiv(wt_de),
                    "cogul": parse_cogul(wt_de),
                    "tanim": parse_bedeutungen(wt_de),
                    "cekimler": parse_cekimler(wt_de, ""),
                    "partizip2": "",
                    "prateritum": "",
                    "hilfsverb": "",
                }
                # Fiil bilgisi
                m = re.search(r'\|Partizip II=([^\n|]+)', wt_de)
                if m: entry_data["partizip2"] = m.group(1).strip()
                m = re.search(r'\|Präteritum_ich=([^\n|]+)', wt_de)
                if m: entry_data["prateritum"] = m.group(1).strip()
                m = re.search(r'\|Hilfsverb=([^\n|]+)', wt_de)
                if m: entry_data["hilfsverb"] = m.group(1).strip()

                cache[title] = entry_data

            batch_no += 1
            if batch_no % 10 == 0:
                # Cache kaydet
                with open(CACHE_PATH, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False)
                log(f"  Batch {batch_no}: cache {len(cache)} kayit")
            time.sleep(0.4)
        except Exception as ex:
            log(f"  HATA batch {batch_no}: {ex}")
            time.sleep(3)

    # Cache son kayit
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    log(f"Cache tamamlandi: {len(cache)} kayit")

    # Sozluge isle
    log("Sozluge isleniyor...")
    for i, entry in enumerate(data):
        word = entry.get("almanca", "")
        cd = cache.get(word)
        if not cd:
            continue
        changed = False
        if entry.get("tur") == "isim":
            if cd.get("artikel") and not entry.get("artikel"):
                entry["artikel"] = cd["artikel"]; changed = True
            if cd.get("genitiv") and not entry.get("genitiv_endung"):
                # Genitiv endung: son -s, -es, -en, -n vs.
                gen_full = cd["genitiv"]
                entry["genitiv_endung"] = gen_full; changed = True
            if cd.get("cogul") and not entry.get("cogul"):
                entry["cogul"] = cd["cogul"]; changed = True
            if cd.get("cekimler") and not entry.get("cekimler"):
                entry["cekimler"] = cd["cekimler"]; changed = True
        if not entry.get("tanim_almanca") and cd.get("tanim"):
            entry["tanim_almanca"] = cd["tanim"]; changed = True
        if entry.get("tur") == "fiil":
            if cd.get("partizip2") and not entry.get("partizip2"):
                entry["partizip2"] = cd["partizip2"]; changed = True
            if cd.get("prateritum") and not entry.get("prateritum"):
                entry["prateritum"] = cd["prateritum"]; changed = True
            if cd.get("hilfsverb") and not entry.get("perfekt_yardimci"):
                entry["perfekt_yardimci"] = cd["hilfsverb"]; changed = True
        if changed:
            updated += 1

    log(f"Sozluk guncellendi: {updated} giris degisti")
    save(data)

    # Sonuc istatistigi
    bos_artikel  = sum(1 for e in data if e.get("tur")=="isim" and not e.get("artikel"))
    bos_genitiv  = sum(1 for e in data if e.get("tur")=="isim" and not e.get("genitiv_endung"))
    bos_cogul    = sum(1 for e in data if e.get("tur")=="isim" and not e.get("cogul"))
    bos_tanim    = sum(1 for e in data if not e.get("tanim_almanca"))
    bos_partizip = sum(1 for e in data if e.get("tur")=="fiil" and not e.get("partizip2"))
    log(f"Sonuc: artikel bos={bos_artikel}, genitiv bos={bos_genitiv}, cogul bos={bos_cogul}, tanim bos={bos_tanim}, partizip2 bos={bos_partizip}")
    log("=== TAMAMLANDI ===")


if __name__ == "__main__":
    main()
