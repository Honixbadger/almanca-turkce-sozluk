#!/usr/bin/env python3
"""
Google Translate (ücretsiz, API key yok) ile örnek cümleleri çevirir.
Sadece temiz Almanca cümleleri çevirir, kirli/yabancı olanları atlar.
"""

import json, urllib.request, urllib.parse, re, time, sys
from datetime import datetime

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"
LOG_PATH   = "google_translate_ornekler.log"
START_TIME = time.time()
DELAY      = 0.8   # saniye — block riskini azaltır
SAVE_EVERY = 100   # batch sayısı

EN_WORDS = {
    'the','of','and','to','in','a','is','that','for','it','was','on','are','with',
    'as','at','from','this','have','an','by','not','or','but','had','his','they',
    'she','he','been','which','their','were','also','would','built','placed',
}
FR_WORDS = {
    'les','des','une','est','dans','par','sur','pour','qui','que','avec','son',
    'pas','nous','vous','ils','elle','leur','au','du','et','ou','mais',
}
DE_VERB_INDICATORS = {
    'ist','sind','hat','haben','wird','werden','war','waren','kann','soll',
    'muss','darf','wurde','ein','eine','der','die','das','ich','er','sie','es',
    'wir','ihr','man','sich','nicht','auch','aber','wenn','dass','als','und',
}

def is_clean_german(s):
    """Çevrilmeye değer temiz Almanca cümle mi?"""
    if not s or len(s) < 10 or len(s) > 4000:
        return False
    # Kaynak artığı
    if '\u2191' in s or 'ISBN' in s or re.search(r'https?://', s):
        return False
    words = re.findall(r'[a-zA-ZäöüÄÖÜß]+', s)
    if len(words) < 4:
        return False
    words_lower = [w.lower() for w in words]
    # Yabancı dil kontrolü
    en_hit = sum(1 for w in words_lower if w in EN_WORDS)
    fr_hit = sum(1 for w in words_lower if w in FR_WORDS)
    if en_hit / len(words_lower) > 0.35 or fr_hit / len(words_lower) > 0.30:
        return False
    # Fragment: kısa + Almanca fiil yok
    if len(words_lower) < 8 and not any(w in DE_VERB_INDICATORS for w in words_lower):
        return False
    return True

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def google_translate(text, src="de", dest="tr", retries=3):
    url = (
        "https://translate.googleapis.com/translate_a/single"
        "?client=gtx&sl=" + src + "&tl=" + dest + "&dt=t&q="
        + urllib.parse.quote(text)
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            return "".join(part[0] for part in data[0] if part[0])
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3 + attempt * 2)
            else:
                raise e

def save(data):
    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    elapsed = (time.time() - START_TIME) / 60
    log(f"[KAYIT] {elapsed:.0f} dk geçti")

def main():
    log("=== Google Translate Örnek Cümle Çevirisi ===")

    with open(DICT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    log(f"Sözlük: {len(data)} giriş")

    # Hedefleri topla
    targets = []
    for i, entry in enumerate(data):
        for j, orn in enumerate(entry.get("ornekler", [])):
            if orn.get("almanca") and not orn.get("turkce"):
                targets.append((i, j, orn["almanca"]))

    log(f"Çevrilecek: {len(targets)} cümle")

    done = 0
    errors = 0
    batch_no = 0

    for idx, (di, ji, sentence) in enumerate(targets):
        if not is_clean_german(sentence):
            continue

        try:
            tr = google_translate(sentence)
            data[di]["ornekler"][ji]["turkce"] = tr
            # İlk örnek ise üst alanı da güncelle
            if ji == 0:
                data[di]["ornek_turkce"] = tr
            done += 1
            time.sleep(DELAY)
        except Exception as e:
            errors += 1
            log(f"  HATA ({errors}): {str(e)[:80]}")
            time.sleep(5)
            # 429 / rate limit benzeri hata — biraz daha bekle
            if "429" in str(e) or "403" in str(e):
                log("  Rate limit! 60 sn bekleniyor...")
                time.sleep(60)
            continue

        batch_no += 1
        if batch_no % 500 == 0:
            log(f"  {done} cümle çevrildi ({errors} hata)")
        if batch_no % SAVE_EVERY == 0:
            save(data)

    save(data)
    elapsed = (time.time() - START_TIME) / 60
    log(f"=== TAMAMLANDI === {done} çevrildi, {errors} hata, {elapsed:.0f} dk")

if __name__ == "__main__":
    main()
