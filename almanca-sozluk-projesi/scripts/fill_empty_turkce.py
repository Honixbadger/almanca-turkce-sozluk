#!/usr/bin/env python3
"""
fill_empty_turkce.py
====================
turkce alani bos olan kayitlara ceviri doldurur.
Oncelik sirasi:
  1. Bilinen manuel eslemeler (hizli)
  2. Kadinlik eki (-in/-erin) olan isimler -> erkek formdan turet
  3. Groq API ile kalan bosluklar
"""

import json, re, sys, time
from pathlib import Path

try:
    import requests as _req; _USE_REQ = True
except ImportError:
    import urllib.request, urllib.error; _USE_REQ = False

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DICT_PATH = Path(__file__).resolve().parents[1] / "output" / "dictionary.json"
GROQ_URL  = "https://api.groq.com/openai/v1/chat/completions"
MODEL     = "llama-3.3-70b-versatile"
# API key'leri ortam degiskeninden veya ayri dosyadan oku
import os as _os
_keys_env = _os.environ.get("GROQ_API_KEYS", "")
API_KEYS = [k.strip() for k in _keys_env.split(",") if k.strip()] or []
BATCH = 15

# ── 1. Manuel eslemeler ───────────────────────────────────────────────────────
MANUAL = {
    "(sich) ausziehen":    "giysileri çıkarmak; taşınmak",
    "(sich) duschen":      "duş almak",
    "(sich) freuen":       "sevinmek; memnun olmak",
    "(sich) umsehen":      "etrafına bakmak; gezinmek",
    "(sich) verabschieden":"veda etmek; uğurlamak",
    "(sich) vorstellen":   "kendini tanıtmak; hayal etmek",
    "(sich) waschen":      "yıkanmak",
    "anklicken":           "tıklamak",
    "Antwortbogen":        "cevap kağıdı",
    "Auszubildende":       "stajyer; çırak (kadın)",
    "Auszubildender":      "stajyer; çırak (erkek)",
    "Babysitter":          "bebek bakıcısı",
    "Bäckerin":            "fırıncı kadın",
    "Busfahrerin":         "otobüs şoförü kadın",
    "CD":                  "CD; kompakt disk",
    "Chefin":              "şef kadın; patron kadın",
    "Comic":               "çizgi roman",
    "deinem":              "senin (yönelme hâli)",
    "Disko":               "disko; gece kulübü",
    "Doppelzimmer":        "çift kişilik oda",
    "dritten":             "üçüncü",
    "DVD":                 "DVD",
    "Elektriker":          "elektrikçi",
    "Elektrikerin":        "elektrikçi kadın",
    "Europäerin":          "Avrupalı kadın",
    "Flohmarkt":           "bit pazarı",
    "Fundsachen":          "kayıp eşya",
    "Halbpension":         "yarım pansiyon",
    "Handwerkerin":        "zanaatkâr kadın; esnaf kadın",
    "Hausmann":            "ev erkeği; ev işleriyle ilgilenen erkek",
    "Homepage":            "ana sayfa; web sitesi",
    "Journalistin":        "gazeteci kadın",
    "Kantonalen":          "kanton (İsviçre idari birimi)",
    "Kauffrau":            "iş kadını; tüccar kadın",
    "Kellnerin":           "garson kadın",
    "Krankenpflegerin":    "hemşire",
    "Lehrerin":            "öğretmen kadın",
    "Malerin":             "ressam kadın; boyacı kadın",
    "Mechanikerin":        "mekanikçi kadın",
    "Musikerin":           "müzisyen kadın",
    "Niveaustufen":        "seviye basamakları; düzey kademeleri",
    "Pizzeria":            "pizzeria",
    "Politikerin":         "siyasetçi kadın",
    "Professorin":         "profesör kadın",
    "Programmiererin":     "programcı kadın",
    "Rechtsanwältin":      "avukat kadın",
    "Schneiderin":         "terzi kadın",
    "Schriftstellerin":    "yazar kadın",
    "Sekretärin":          "sekreter kadın",
    "Sportlerin":          "sporcu kadın",
    "Studentin":           "öğrenci kadın; üniversite öğrencisi kadın",
    "Tierärztin":          "veteriner kadın",
    "Verkäuferin":         "satış görevlisi kadın; tezgâhtar kadın",
    "Wiederhören":         "tekrar duyma; (auf Wiederhören: telefonda görüşürüz)",
    "Wortbildung":         "sözcük yapımı; sözcük oluşturma",
    "zweiten":             "ikinci",
    "Ärztin":              "doktor kadın; hekim kadın",
    "Architektin":         "mimar kadın",
    "Friseurin":           "kuaför kadın; berber kadın",
    "Informatikerin":      "bilgisayar bilimcisi kadın",
    "Ingenieurin":         "mühendis kadın",
    "Köchin":              "aşçı kadın",
    "Managerin":           "müdür kadın; yönetici kadın",
    "Nachbarin":           "komşu kadın",
    "Polizistin":          "polis kadın",
    "Psychologin":         "psikolog kadın",
    "Regisseurin":         "yönetmen kadın",
    "Sängerin":            "şarkıcı kadın",
    "Sozialarbeiterin":    "sosyal hizmetler görevlisi kadın",
    "Unternehmerin":       "girişimci kadın; iş insanı kadın",
    "Wissenschaftlerin":   "bilim insanı kadın",
    "Zahnärztin":          "dişçi kadın; diş hekimi kadın",
}

# ── 2. -in/-erin/-frau ekli kadın formlar için lookup ──────────────────────────
def try_feminine_derivation(almanca: str, lookup: dict) -> str | None:
    """Erkek formunu bul, 'kadın' ekle."""
    w = almanca.strip()
    # -erin -> -er
    if w.endswith("erin"):
        base = w[:-2]  # -erin -> -er
        if base in lookup:
            return lookup[base].split(";")[0].strip() + " (kadın)"
        base2 = w[:-4]  # -erin -> kök
        if base2 in lookup:
            return lookup[base2].split(";")[0].strip() + " (kadın)"
    # -in -> kök
    if w.endswith("in") and len(w) > 4:
        base = w[:-2]
        if base in lookup:
            return lookup[base].split(";")[0].strip() + " (kadın)"
    # -frau -> -mann
    if w.endswith("frau"):
        base = w[:-4] + "mann"
        if base in lookup:
            return lookup[base].split(";")[0].strip() + " (kadın)"
    return None


# ── Groq ──────────────────────────────────────────────────────────────────────
_key_idx = 0

def groq_translate_batch(items: list[tuple[str, str, str]]) -> dict[int, str]:
    """[(almanca, tur, tanim_de), ...] -> {i: turkce}"""
    global _key_idx
    numbered = "\n".join(
        f"{i+1}. [{w}] ({pos}){': ' + d[:120] if d else ''}"
        for i, (w, pos, d) in enumerate(items)
    )
    messages = [
        {"role": "system", "content": (
            "Sen Almanca-Türkçe sözlük çevirmenisín. "
            "Her Almanca kelimeye kısa, doğal Türkçe karşılık ver. "
            "Sadece numaralı çevirileri yaz, başka açıklama ekleme."
        )},
        {"role": "user", "content": f"Şu kelimelerin Türkçe karşılığını ver:\n\n{numbered}"},
    ]
    payload = {"model": MODEL, "messages": messages, "max_tokens": len(items)*30+50, "temperature": 0.1}
    for attempt in range(len(API_KEYS)):
        key = API_KEYS[_key_idx % len(API_KEYS)]
        _key_idx += 1
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        try:
            if _USE_REQ:
                r = _req.post(GROQ_URL, headers=headers, json=payload, timeout=25)
                if r.status_code == 429:
                    time.sleep(5); continue
                if r.status_code != 200:
                    print(f"  HTTP {r.status_code}"); return {}
                text = r.json()["choices"][0]["message"]["content"].strip()
            else:
                import urllib.request
                data = json.dumps(payload).encode()
                req = urllib.request.Request(GROQ_URL, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=25) as resp:
                    text = json.loads(resp.read())["choices"][0]["message"]["content"].strip()
            result = {}
            for line in text.splitlines():
                m = re.match(r"^(\d+)[.)]\s*(.+)$", line.strip())
                if m:
                    i = int(m.group(1)) - 1
                    if 0 <= i < len(items):
                        result[i] = m.group(2).strip()
            return result
        except Exception as e:
            print(f"  Hata: {e}")
    return {}


# ── Ana ───────────────────────────────────────────────────────────────────────
def main():
    print("Sozluk yukleniyor...", flush=True)
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))

    # Almanca -> turkce lookup (dolu olanlar)
    lookup = {}
    for r in data:
        t = r.get("turkce", "").strip()
        if t:
            lookup[r.get("almanca", "").strip()] = t

    # Bos turkce kayitlari bul
    targets = [r for r in data if not r.get("turkce", "").strip()]
    print(f"Bos turkce: {len(targets)}", flush=True)

    filled_manual = 0
    filled_derive = 0
    filled_groq   = 0
    groq_queue    = []

    # 1+2: Manuel ve turetime
    for rec in targets:
        almanca = rec.get("almanca", "").strip()
        # Manuel
        if almanca in MANUAL:
            rec["turkce"] = MANUAL[almanca]
            rec["ceviri_durumu"] = "manuel-dogrulandi"
            print(f"  [MANUEL] [{almanca}] -> {MANUAL[almanca]}", flush=True)
            filled_manual += 1
            continue
        # Turetime
        derived = try_feminine_derivation(almanca, lookup)
        if derived:
            rec["turkce"] = derived
            rec["ceviri_durumu"] = "turetildi"
            print(f"  [TURET]  [{almanca}] -> {derived}", flush=True)
            filled_derive += 1
            continue
        # Groq kuyruğu
        groq_queue.append(rec)

    print(f"\nGroq kuyrugu: {len(groq_queue)}", flush=True)

    # 3: Groq
    batches = [groq_queue[i:i+BATCH] for i in range(0, len(groq_queue), BATCH)]
    for b_i, batch in enumerate(batches):
        items = [(r.get("almanca",""), r.get("tur",""), r.get("tanim_almanca","")) for r in batch]
        print(f"[Batch {b_i+1}/{len(batches)}] {', '.join(w for w,_,_ in items[:4])}{'...' if len(items)>4 else ''}", flush=True)
        translations = groq_translate_batch(items)
        for local_i, tr in translations.items():
            rec = batch[local_i]
            rec["turkce"] = tr
            rec["ceviri_durumu"] = "groq-cevirdi"
            print(f"  [GROQ]   [{rec['almanca']}] -> {tr}", flush=True)
            filled_groq += 1
        time.sleep(2)

    print(f"\n{'='*55}", flush=True)
    print(f"Manuel     : {filled_manual}", flush=True)
    print(f"Turetilen  : {filled_derive}", flush=True)
    print(f"Groq       : {filled_groq}", flush=True)
    print(f"Toplam     : {filled_manual + filled_derive + filled_groq}", flush=True)
    print(f"{'='*55}", flush=True)

    DICT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Kaydedildi.", flush=True)


if __name__ == "__main__":
    main()
