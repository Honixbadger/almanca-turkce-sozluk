#!/usr/bin/env python3
"""
Groq token limiti sifirlaninca ornek cumle cevirilerine devam eder.
Gunluk limit UTC 00:00'da sifirlaniyor = Turkiye 03:00.
Bu script limiti bekler, sonra ornekleri cevirir.
"""

import json, time, sys, urllib.request, urllib.error
from datetime import datetime

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"
LOG_PATH   = "groq_resume.log"

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
START_TIME = time.time()
MAX_HOURS  = 8
key_idx    = 0
key_daily_limit = set()  # gunluk limiti dolan keyler


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def next_key():
    global key_idx
    available = [k for i, k in enumerate(API_KEYS) if k not in key_daily_limit]
    if not available:
        return None
    key_idx = (key_idx + 1) % len(available)
    return available[key_idx % len(available)]


def groq_chat(messages, max_tokens=900):
    key = next_key()
    if not key:
        return "DAILY_LIMIT"
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
        err = e.read().decode("utf-8", errors="ignore")
        if e.code == 429:
            if "per day" in err or "TPD" in err:
                log(f"  Gunluk limit doldu: {key[:20]}...")
                key_daily_limit.add(key)
                if len(key_daily_limit) >= len(API_KEYS):
                    return "DAILY_LIMIT"
                return None
            time.sleep(30)
        raise RuntimeError(f"HTTP {e.code}: {err[:150]}")


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
    log(f"[KAYIT] {len(data)} giris. Sure: {elapsed:.0f} dk")


def wait_for_reset():
    """UTC 00:05'i bekle (Turkiye 03:05)"""
    now = datetime.utcnow()
    if now.hour == 0 and now.minute < 10:
        return  # zaten sifirlandi
    # Kac dakika kaldi?
    minutes_left = (60 - now.minute) + (23 - now.hour) * 60
    log(f"Gunluk limit bitti. UTC {now.hour}:{now.minute:02d}. Reset icin ~{minutes_left} dk bekliyorum...")
    time.sleep(minutes_left * 60 + 300)  # +5 dk tampon
    log("Bekleme bitti, devam ediyorum.")
    key_daily_limit.clear()


def translate_examples(data):
    log("=== Ornek cumle cevirisi basliyor ===")
    targets = []
    for i, entry in enumerate(data):
        for j, orn in enumerate(entry.get("ornekler", [])):
            if orn.get("almanca") and not orn.get("turkce"):
                targets.append((i, j, orn["almanca"]))

    log(f"  Hedef: {len(targets)} cumle")
    if not targets:
        log("  Cevirilecek cumle yok, cikiyorum.")
        return

    BATCH = 8
    done = 0
    batch_no = 0
    save_counter = 0

    for start in range(0, len(targets), BATCH):
        if (time.time() - START_TIME) > MAX_HOURS * 3600:
            log("Zaman siniri! Duruyorum."); break

        chunk = targets[start:start + BATCH]
        sentences = [c[2] for c in chunk]
        numbered = "\n".join(f"{k+1}. {s}" for k, s in enumerate(sentences))
        prompt = (
            "Translate the following German sentences to natural Turkish. "
            "Return a SINGLE valid JSON array with translations in the same order. "
            "Output ONLY the JSON array, nothing else.\n\n"
            f"[\"ceviri1\", \"ceviri2\"]\n\n"
            + numbered
        )
        try:
            raw = groq_chat([{"role": "user", "content": prompt}], max_tokens=900)
            if raw == "DAILY_LIMIT":
                log("Tum keyler gunluk limiti doldu!")
                wait_for_reset()
                continue
            if raw is None:
                time.sleep(30)
                continue
            result = extract_json(raw)
            if isinstance(result, list):
                for k, (di, ji, _) in enumerate(chunk):
                    if k < len(result) and result[k]:
                        data[di]["ornekler"][ji]["turkce"] = result[k]
                        if ji == 0:
                            data[di]["ornek_turkce"] = result[k]
                        done += 1
            batch_no += 1
            save_counter += 1
            if batch_no % 20 == 0:
                log(f"  {done} cumle cevrildi ({batch_no} batch)")
            if save_counter >= 15:
                save(data)
                save_counter = 0
            time.sleep(2.5)
        except RuntimeError as ex:
            err_str = str(ex)
            if "429" in err_str and ("per day" in err_str or "TPD" in err_str):
                wait_for_reset()
            else:
                log(f"  HATA: {ex}")
                time.sleep(5)
        except Exception as ex:
            log(f"  HATA: {ex}")
            time.sleep(5)

    log(f"  Ornek ceviri bitti: {done} cumle")
    save(data)


def translate_verbs(data):
    """Hala bos turkce alani olan fiilleri cevir"""
    log("=== Kalan fiil cevirisi ===")
    targets = [(i, e) for i, e in enumerate(data)
               if e.get("tur") == "fiil" and not e.get("turkce")]
    if not targets:
        log("  Bos fiil yok."); return
    log(f"  Hedef: {len(targets)} fiil")
    BATCH = 10
    done = 0
    for start in range(0, len(targets), BATCH):
        if (time.time() - START_TIME) > MAX_HOURS * 3600:
            break
        chunk = targets[start:start + BATCH]
        verbs = [e["almanca"] for _, e in chunk]
        verb_list = "\n".join(f'- "{v}"' for v in verbs)
        prompt = (
            "Translate the following German verbs to Turkish. "
            "Return a SINGLE valid JSON object. Keys=German verbs, values=Turkish meanings (1-3, comma-separated). "
            "Output ONLY the JSON object.\n\nVerbs:\n" + verb_list
        )
        try:
            raw = groq_chat([{"role": "user", "content": prompt}], max_tokens=400)
            if raw in (None, "DAILY_LIMIT"):
                time.sleep(30); continue
            result = extract_json(raw)
            if isinstance(result, dict):
                for idx, entry in chunk:
                    verb = entry["almanca"]
                    if verb in result and result[verb]:
                        data[idx]["turkce"] = result[verb]
                        data[idx]["ceviri_durumu"] = "otomatik-ceviri"
                        data[idx]["kaynak"] = "groq-llama3"
                        done += 1
            time.sleep(2.5)
        except Exception as ex:
            log(f"  HATA: {ex}"); time.sleep(5)
    log(f"  {done} fiil cevrildi")
    save(data)


def main():
    log("=" * 50)
    log("Groq Resume Script")
    log("=" * 50)

    with open(DICT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    log(f"Sozluk: {len(data)} giris")

    bos_turkce = sum(1 for e in data if not e.get("turkce"))
    bos_ornek  = sum(1 for e in data for o in e.get("ornekler", [])
                     if o.get("almanca") and not o.get("turkce"))
    log(f"Bos turkce: {bos_turkce}, Bos ornek: {bos_ornek}")

    # Once kalan fiilleri bitir
    translate_verbs(data)
    # Sonra ornekleri cevir
    translate_examples(data)

    elapsed = (time.time() - START_TIME) / 60
    log(f"=== TAMAMLANDI === {elapsed:.0f} dk")

    bos_kalan = sum(1 for e in data if not e.get("turkce"))
    bos_ornek_kalan = sum(1 for e in data for o in e.get("ornekler", [])
                          if o.get("almanca") and not o.get("turkce"))
    log(f"Son durum: bos turkce={bos_kalan}, bos ornek={bos_ornek_kalan}")


if __name__ == "__main__":
    main()
