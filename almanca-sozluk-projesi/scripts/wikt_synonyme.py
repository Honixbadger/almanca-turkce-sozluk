#!/usr/bin/env python3
"""
Wiktionary'den esanlamlilar (Synonyme) ve kelime ailesi (Wortbildungen) ceker.
Mevcut noun cache'i kullanir, eksik olanlar icin yeni istek atar.
"""

import json, urllib.request, urllib.parse, re, time, sys
from datetime import datetime

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"
LOG_PATH   = "wikt_synonyme.log"
CACHE_PATH = "wikt_synonyme_cache.json"
MAX_HOURS  = 5
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
    req = urllib.request.Request(url, headers={"User-Agent": "AlmancaSozluk/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def parse_synonyme(wikitext):
    """Synonyme bolumunden ilk 5 esanlamlii cek"""
    syns = []
    in_syn = False
    for line in wikitext.splitlines():
        if "{{Synonyme}}" in line or "=== Synonyme ===" in line:
            in_syn = True
            continue
        if in_syn:
            if line.startswith("{{") and "Synonyme" not in line and not line.startswith(":"):
                break
            if line.startswith(":"):
                # [[wort]] veya [[wort|gosterim]] formatindan kelimeleri cek
                found = re.findall(r'\[\[([^\|\]]+?)(?:\|[^\]]+)?\]\]', line)
                for w in found:
                    w = w.strip()
                    if w and not w.startswith("Datei:") and len(w) < 30:
                        syns.append(w)
    return list(dict.fromkeys(syns))[:6]


def parse_wortbildungen(wikitext):
    """Wortbildungen bolumunden akraba kelimeleri cek"""
    words = []
    in_wb = False
    for line in wikitext.splitlines():
        if "{{Wortbildungen}}" in line or "=== Wortbildungen ===" in line:
            in_wb = True
            continue
        if in_wb:
            if line.startswith("==") and "Wortbildungen" not in line:
                break
            found = re.findall(r'\[\[([^\|\]]+?)(?:\|[^\]]+)?\]\]', line)
            for w in found:
                w = w.strip()
                if w and not w.startswith("Datei:") and len(w) < 35:
                    words.append(w)
            if len(words) >= 8:
                break
    return list(dict.fromkeys(words))[:8]


def parse_oberbegriffe(wikitext):
    """Oberbegriffe (ust kavramlar) - kelime ailesi icin yardimci"""
    words = []
    in_ob = False
    for line in wikitext.splitlines():
        if "{{Oberbegriffe}}" in line:
            in_ob = True
            continue
        if in_ob:
            if line.startswith("{{") and not line.startswith(":"):
                break
            found = re.findall(r'\[\[([^\|\]]+?)(?:\|[^\]]+)?\]\]', line)
            for w in found:
                w = w.strip()
                if w and len(w) < 25:
                    words.append(w)
    return list(dict.fromkeys(words))[:4]


def save(data):
    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    log("=== Wiktionary Synonyme/Wortbildungen ===")

    with open(DICT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    log(f"Sozluk: {len(data)} giris")

    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)
        log(f"Cache: {len(cache)} kayit")
    except Exception:
        cache = {}

    # Hedefler: esanlamlisi veya kelime ailesi bos olanlar (yuksek zipf = onemli)
    targets = [
        (i, e) for i, e in enumerate(data)
        if (not e.get("esanlamlilar") or not e.get("kelime_ailesi"))
        and e.get("almanca", "") not in cache
        and e.get("zipf_skoru", 0) >= 3.0  # Sadece onemlileri
    ]
    # Zipf'e gore sirala - en onemliyi once isle
    targets.sort(key=lambda x: -x[1].get("zipf_skoru", 0))

    log(f"Hedef: {len(targets)} giris")

    BATCH = 50
    batch_no = 0
    for start in range(0, len(targets), BATCH):
        if (time.time() - START_TIME) > MAX_HOURS * 3600:
            log("Zaman siniri!"); break

        chunk = targets[start:start + BATCH]
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
                # Sadece Deutsch bolumu
                de_m = re.search(
                    r'== .+? \(\{\{Sprache\|Deutsch\}\}\) ==(.+?)(?:== .+? \(\{\{Sprache\||\Z)',
                    wt, re.DOTALL
                )
                wt_de = de_m.group(1) if de_m else wt

                cache[title] = {
                    "synonyme": parse_synonyme(wt_de),
                    "wortbildungen": parse_wortbildungen(wt_de),
                    "oberbegriffe": parse_oberbegriffe(wt_de),
                }

            batch_no += 1
            if batch_no % 10 == 0:
                with open(CACHE_PATH, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False)
                log(f"  Batch {batch_no}: {len(cache)} cache")
            time.sleep(1.5)
        except Exception as ex:
            err = str(ex)
            if "429" in err:
                time.sleep(12)
            else:
                log(f"  HATA batch {batch_no}: {ex}")
                time.sleep(3)

    # Cache kaydet
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    log(f"Cache tamamlandi: {len(cache)}")

    # Sozluge isle
    log("Sozluge isleniyor...")
    syn_ek = wb_ek = 0
    for i, entry in enumerate(data):
        word = entry.get("almanca", "")
        cd = cache.get(word)
        if not cd:
            continue
        if cd.get("synonyme") and not entry.get("esanlamlilar"):
            entry["esanlamlilar"] = cd["synonyme"]
            syn_ek += 1
        wb = list(dict.fromkeys(
            cd.get("wortbildungen", []) + cd.get("oberbegriffe", [])
        ))[:6]
        if wb and not entry.get("kelime_ailesi"):
            entry["kelime_ailesi"] = wb
            wb_ek += 1

    log(f"Esanlamli eklendi: {syn_ek}, Kelime ailesi eklendi: {wb_ek}")
    save(data)

    bos_syn = sum(1 for e in data if not e.get("esanlamlilar"))
    bos_wb  = sum(1 for e in data if not e.get("kelime_ailesi"))
    log(f"Hala bos esanlamli: {bos_syn}, kelime_ailesi: {bos_wb}")
    log("=== TAMAMLANDI ===")


if __name__ == "__main__":
    main()
