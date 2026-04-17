#!/usr/bin/env python3
"""
Groq ile otomatik Almanca->Turkce ceviri ve zenginlestirme.
Fazlar:
  1. Bos turkce alanli fiilleri cevir
  2. Ornek cumlelerin Turkcelerini cevir
  3. Kalan bos turkce (isim, sifat vb.)
"""

import json, time, sys, urllib.request, urllib.error
from datetime import datetime

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"
LOG_PATH   = "groq_enrichment.log"

API_KEYS = [
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
    "YOUR_GROQ_API_KEY",
]

MODEL      = "llama-3.1-8b-instant"
SAVE_EVERY = 10
MAX_HOURS  = 5

key_idx    = 0
key_errors = [0] * len(API_KEYS)
START_TIME = time.time()


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def next_key():
    global key_idx
    for _ in range(len(API_KEYS)):
        key_idx = (key_idx + 1) % len(API_KEYS)
        if key_errors[key_idx] < 5:
            return API_KEYS[key_idx]
    return API_KEYS[0]


def groq_chat(messages, max_tokens=1024):
    key = next_key()
    body = json.dumps({
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
            return resp["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        key_errors[key_idx] += 1
        if e.code == 429:
            time.sleep(30)
        raise RuntimeError(f"HTTP {e.code}: {err_body[:200]}")


def extract_json(text):
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for p in parts:
            p = p.strip().lstrip("json").strip()
            if p.startswith("{") or p.startswith("["):
                text = p
                break
    for i, c in enumerate(text):
        if c in "{[":
            try:
                return json.loads(text[i:])
            except Exception:
                pass
    return None


def save(data):
    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    elapsed = (time.time() - START_TIME) / 60
    log(f"[KAYIT] {len(data)} giris yazildi. Sure: {elapsed:.1f} dk")


def time_ok():
    return (time.time() - START_TIME) < MAX_HOURS * 3600


# ─── FAZA 1: Fiil anlamlari ──────────────────────────────────────────────────
def translate_verbs(data):
    log("=== FAZA 1: Fiil anlam cevirisi ===")
    targets = [(i, e) for i, e in enumerate(data)
               if e.get("tur") == "fiil" and not e.get("turkce")]
    log(f"  Hedef: {len(targets)} fiil")
    BATCH = 10
    done = 0
    batch_no = 0
    for start in range(0, len(targets), BATCH):
        if not time_ok():
            log("Zaman siniri! Faza 1 durduruluyor."); break
        chunk = targets[start:start + BATCH]
        verbs = [e["almanca"] for _, e in chunk]
        verb_list = "\n".join(f'- "{v}"' for v in verbs)
        prompt = (
            "Translate the following German verbs to Turkish. "
            "Return a SINGLE valid JSON object with ALL verbs as keys and Turkish meanings as values. "
            "1-3 short meanings per verb, comma-separated. "
            "Output ONLY the JSON object, nothing else.\n\n"
            "Example: {\"aufbauen\": \"insaa etmek, kurmak\", \"verstehen\": \"anlamak\"}\n\n"
            "Verbs to translate:\n" + verb_list
        )
        try:
            raw = groq_chat([{"role": "user", "content": prompt}], max_tokens=700)
            result = extract_json(raw)
            if isinstance(result, dict):
                for idx, entry in chunk:
                    verb = entry["almanca"]
                    if verb in result and result[verb]:
                        data[idx]["turkce"] = result[verb]
                        data[idx]["ceviri_durumu"] = "otomatik-ceviri"
                        data[idx]["kaynak"] = "groq-llama3"
                        done += 1
            batch_no += 1
            if batch_no % 20 == 0:
                log(f"  Fiil: {done} cevrildi ({batch_no} batch)")
            if batch_no % SAVE_EVERY == 0:
                save(data)
            time.sleep(2.5)
        except Exception as ex:
            log(f"  HATA fiil batch {batch_no}: {ex}")
            time.sleep(4)
    log(f"  Faza 1 tamamlandi: {done} fiil cevrildi")
    save(data)


# ─── FAZA 2: Ornek cumle cevirileri ──────────────────────────────────────────
def translate_examples(data):
    log("=== FAZA 2: Ornek cumle cevirisi ===")
    targets = []
    for i, entry in enumerate(data):
        for j, orn in enumerate(entry.get("ornekler", [])):
            if orn.get("almanca") and not orn.get("turkce"):
                targets.append((i, j, orn["almanca"]))
    log(f"  Hedef: {len(targets)} cumle")
    BATCH = 8
    done = 0
    batch_no = 0
    for start in range(0, len(targets), BATCH):
        if not time_ok():
            log("Zaman siniri! Faza 2 durduruluyor."); break
        chunk = targets[start:start + BATCH]
        sentences = [c[2] for c in chunk]
        numbered = "\n".join(f"{k+1}. {s}" for k, s in enumerate(sentences))
        prompt = (
            "Translate the following German sentences to natural Turkish. "
            "Return a SINGLE valid JSON array with translations in the same order. "
            "Output ONLY the JSON array, nothing else.\n\n"
            f"Example: [\"Birinci cumle.\", \"Ikinci cumle.\"]\n\n"
            + numbered
        )
        try:
            raw = groq_chat([{"role": "user", "content": prompt}], max_tokens=900)
            result = extract_json(raw)
            if isinstance(result, list):
                for k, (di, ji, _) in enumerate(chunk):
                    if k < len(result) and result[k]:
                        data[di]["ornekler"][ji]["turkce"] = result[k]
                        if ji == 0:
                            data[di]["ornek_turkce"] = result[k]
                        done += 1
            batch_no += 1
            if batch_no % 20 == 0:
                log(f"  Cumle: {done} cevrildi ({batch_no} batch)")
            if batch_no % SAVE_EVERY == 0:
                save(data)
            time.sleep(2.5)
        except Exception as ex:
            log(f"  HATA cumle batch {batch_no}: {ex}")
            time.sleep(4)
    log(f"  Faza 2 tamamlandi: {done} cumle cevrildi")
    save(data)


# ─── FAZA 3: Diger bos turkce (isim, sifat vb.) ──────────────────────────────
def translate_nouns(data):
    log("=== FAZA 3: Diger bos turkce ===")
    targets = [(i, e) for i, e in enumerate(data)
               if not e.get("turkce") and e.get("almanca") and e.get("tur") != "fiil"]
    log(f"  Hedef: {len(targets)} kelime")
    BATCH = 10
    done = 0
    batch_no = 0
    for start in range(0, len(targets), BATCH):
        if not time_ok():
            log("Zaman siniri! Faza 3 durduruluyor."); break
        chunk = targets[start:start + BATCH]
        words = []
        for _, e in chunk:
            art = e.get("artikel", "")
            w = f"{art} {e['almanca']}".strip() if art else e["almanca"]
            words.append(w)
        word_list = "\n".join(f'- "{w}"' for w in words)
        prompt = (
            "Translate the following German words to Turkish. "
            "Return a SINGLE valid JSON object. Keys are the German words (without article), values are Turkish meanings (1-3, comma-separated). "
            "Output ONLY the JSON object, nothing else.\n\n"
            "Words:\n" + word_list
        )
        try:
            raw = groq_chat([{"role": "user", "content": prompt}], max_tokens=600)
            result = extract_json(raw)
            if isinstance(result, dict):
                for idx, entry in chunk:
                    key = entry["almanca"]
                    art = entry.get("artikel", "")
                    val = result.get(key) or result.get(f"{art} {key}".strip())
                    if val:
                        data[idx]["turkce"] = val
                        data[idx]["ceviri_durumu"] = "otomatik-ceviri"
                        data[idx]["kaynak"] = "groq-llama3"
                        done += 1
            batch_no += 1
            if batch_no % SAVE_EVERY == 0:
                save(data)
            time.sleep(2.5)
        except Exception as ex:
            log(f"  HATA isim batch {batch_no}: {ex}")
            time.sleep(4)
    log(f"  Faza 3 tamamlandi: {done} kelime cevrildi")
    save(data)


def main():
    log("=" * 50)
    log("Groq Enrichment Script basliyor")
    log("=" * 50)
    with open(DICT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    log(f"Sozluk yuklendi: {len(data)} giris")

    translate_verbs(data)
    translate_examples(data)
    translate_nouns(data)

    elapsed = (time.time() - START_TIME) / 60
    log(f"=== TAMAMLANDI === Toplam sure: {elapsed:.1f} dakika")

    # Final istatistik
    bos = sum(1 for e in data if not e.get("turkce"))
    ornek_bos = sum(
        1 for e in data
        for o in e.get("ornekler", [])
        if o.get("almanca") and not o.get("turkce")
    )
    log(f"Hala bos turkce: {bos}")
    log(f"Hala bos ornek ceviri: {ornek_bos}")


if __name__ == "__main__":
    main()
