#!/usr/bin/env python3
"""
İkinci tur temizlik:
  1. ornek_almanca / ornek_turkce → ornekler[0] ile senkronize et
  2. kelime_ailesi: middle-substring false positive'leri çıkar
  3. Kalan fragment örnekleri sil
"""
import json, re, sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace')

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"

with open(DICT_PATH, encoding="utf-8") as f:
    data = json.load(f)

all_words_lower = {e["almanca"].lower() for e in data if e.get("almanca")}

# ─── 1. ORNEK SENKRONU ────────────────────────────────────────────────────────
sync_fixed = 0
sync_cleared = 0

for entry in data:
    ornekler = entry.get("ornekler", [])
    if ornekler:
        first = ornekler[0]
        de0 = first.get("almanca", "")
        tr0 = first.get("turkce", "")
        if de0:
            entry["ornek_almanca"] = de0
        if tr0:
            entry["ornek_turkce"] = tr0
        elif "ornek_turkce" in entry and not tr0:
            # ornekler[0] henüz çevrilmemiş — eski değeri temizle
            entry["ornek_turkce"] = ""
        sync_fixed += 1
    else:
        # Örnek kalmamışsa alanları temizle
        entry.pop("ornek_almanca", None)
        entry.pop("ornek_turkce", None)
        sync_cleared += 1

print(f"[1] Örnek senkronu: {sync_fixed} güncellendi, {sync_cleared} temizlendi")


# ─── 2. KELİME AİLESİ — DAHA SIKI FİLTRE ────────────────────────────────────
# Geçerli bağlantı:
#   a) Üye, ana kelimenin PREFIX'iyle başlıyor (en az 5 ortak karakter başta)
#   b) Ana kelime, üyenin PREFIX'iyle başlıyor (türev: Motor → Motorrad)
#   c) Üye, ana kelimeyle BİTİYOR (bileşik son: Reifen → Winterreifen)
#   d) Ana kelime, üyeyle BİTİYOR (kök: Kupplung → Sattelkupplung)
# Geçersiz: sadece ortada substring (reifen in übergreifende)

def is_valid_member(main_word, member):
    mw = main_word.lower()
    mem = member.lower()
    # Artikeli çıkar
    mem_bare = re.sub(r'^(der|die|das|den|dem|des|ein|eine)\s+', '', mem).strip()
    # Çok kısa veya boş
    if len(mem_bare) < 3:
        return False
    # Wikipedia section başlığı gibi görünüyor (büyük harf + boşluk)
    if re.search(r'\s+(Aspekte|Übersicht|Portal|Verwendung|Arten|Geschichte|Typen|Arten|Formen|Einsatz)', member):
        return False
    # Sadece ilk kelimeye bak (bileşik üyeler için)
    mem_first = mem_bare.split()[0] if ' ' in mem_bare else mem_bare

    # a) Ortak prefix ≥ 5
    plen = 0
    for a, b in zip(mw, mem_first):
        if a == b:
            plen += 1
        else:
            break
    if plen >= 5:
        return True

    # b) Ana kelime üyenin prefix'i (Motor → Motorrad: mw in mem_bare START)
    if mem_first.startswith(mw) and len(mw) >= 4:
        return True

    # c) Üye ana kelimeyle bitiyor (Reifen → Winterreifen: mem ends with mw)
    if mem_first.endswith(mw) and len(mw) >= 4:
        return True

    # d) Ana kelime üyeyle bitiyor (Kupplung → Sattelkupplung)
    if mw.endswith(mem_first) and len(mem_first) >= 4:
        return True

    # e) Üye ana kelimenin tam başında (prefix compound): Verbrennungsmotor → Verbrennung
    if mw.startswith(mem_first) and len(mem_first) >= 5:
        return True

    return False


ailesi_removed = 0
ailesi_entries = 0

for entry in data:
    ailesi = entry.get("kelime_ailesi", [])
    if not ailesi:
        continue
    main = entry.get("almanca", "")
    clean = [m for m in ailesi if is_valid_member(main, m)]
    removed = len(ailesi) - len(clean)
    if removed > 0:
        entry["kelime_ailesi"] = clean
        ailesi_removed += removed
        ailesi_entries += 1

print(f"[2] kelime_ailesi: {ailesi_removed} gürültülü üye silindi ({ailesi_entries} kayıt)")


# ─── 3. KALAN FRAGMENT ÖRNEKLERİ ─────────────────────────────────────────────
DE_VERBS = {
    'ist','sind','hat','haben','wird','werden','war','waren','kann','soll',
    'muss','darf','wurde','ein','eine','der','die','das','ich','er','sie','es',
    'wir','ihr','man','sich','nicht','auch','aber','wenn','dass','als','und',
}
ENDINGS = ('.', '!', '?', '"', "'", ']', ')')

def is_fragment(s):
    words = s.split()
    if len(words) < 5 and not any(s.endswith(p) for p in ENDINGS):
        return True
    if len(words) < 8:
        wset = set(re.findall(r'[a-zA-ZäöüÄÖÜß]+', s.lower()))
        if not (wset & DE_VERBS):
            return True
    return False

frag_removed = 0
for entry in data:
    ornekler = entry.get("ornekler", [])
    if not ornekler:
        continue
    clean = [o for o in ornekler if not is_fragment(o.get("almanca", ""))]
    if len(clean) != len(ornekler):
        frag_removed += len(ornekler) - len(clean)
        entry["ornekler"] = clean
        # Senkronu güncelle
        if clean and clean[0].get("almanca"):
            entry["ornek_almanca"] = clean[0]["almanca"]
            entry["ornek_turkce"] = clean[0].get("turkce", "")
        else:
            entry.pop("ornek_almanca", None)
            entry.pop("ornek_turkce", None)

print(f"[3] Kalan fragment silindi: {frag_removed}")


# ─── KAYDET ──────────────────────────────────────────────────────────────────
with open(DICT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
with open(JSONL_PATH, "w", encoding="utf-8") as f:
    for entry in data:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("Kaydedildi.")

# Son kontrol
mismatch = sum(
    1 for e in data
    if e.get("ornek_almanca") and e.get("ornekler")
    and e["ornek_almanca"] != e["ornekler"][0].get("almanca", "")
)
print(f"\nKalan uyumsuz ornek_almanca: {mismatch}")
print(f"Verbrennungsmotor kelime_ailesi: {next((e.get('kelime_ailesi',[]) for e in data if e.get('almanca')=='Verbrennungsmotor'), [])}")
print(f"Reifen kelime_ailesi: {next((e.get('kelime_ailesi',[]) for e in data if e.get('almanca')=='Reifen'), [])}")
