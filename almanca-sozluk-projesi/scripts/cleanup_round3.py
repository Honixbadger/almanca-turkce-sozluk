#!/usr/bin/env python3
"""
3. tur kapsamlı temizlik:
  1. aciklama_turkce -> formatını düzelt
  2. Non-German/Dutch ornekleri sil (ratio tabanlı + kelime seti genişletildi)
  3. Bozuk Türkçe (İngilizce kelime karışmış) ornekleri sil
  4. Çince karakter içeren ornekleri sil
  5. kelime_ailesi — endswith/substring eşleşmesi yerine prefix-only kural
  6. ceviri_durumu normalizasyonu
  7. Leitungsnetz turkce ve senkron düzeltmesi
  8. ornek_almanca/turkce senkronu son kez yenile
"""
import json, re, sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace')

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"

with open(DICT_PATH, encoding="utf-8") as f:
    data = json.load(f)

counts = {}

# ─── 1. aciklama_turkce -> FORMAT ─────────────────────────────────────────────
fixed_aciklama = 0
for e in data:
    val = e.get("aciklama_turkce", "")
    if val and "->" in val:
        parts = val.split("->", 1)
        tr = parts[1].strip() if len(parts) > 1 else ""
        if tr and len(tr) > 2:
            e["aciklama_turkce"] = tr
            fixed_aciklama += 1
        else:
            e.pop("aciklama_turkce", None)
            fixed_aciklama += 1
counts["aciklama_fix"] = fixed_aciklama

# ─── 2. NON-GERMAN (EN/NL/FR) ÖRNEK FİLTRESİ ─────────────────────────────────
EN = {'the','of','and','to','in','a','is','that','for','it','was','on','are',
      'with','as','at','from','this','have','an','by','not','or','but','had',
      'his','they','she','he','been','which','their','were','also','would',
      'there','when','who','what','how','all','any','may','him','her','do',
      'did','has','its','said','been','some','more','will','can','been',
      'about','after','before','during','such','both','each','these','those',
      'could','should','would','been','very','much','many','most','only',
      'just','also','still','never','well','back','here','then','than','now',
      'even','too','yet','again','where','while','though','through','own',
      'same','last','next','long','high','own','keep','come','give','think',
      'seem','take','make','know','see','get','go','say','look','use','find'}
NL = {'de','het','een','van','in','en','is','dat','op','te','voor','met',
      'zijn','aan','ook','maar','bij','wordt','naar','door','heeft','werd',
      'deze','om','als','kan','wel','wordt','nog','worden','hij','ze','dit',
      'die','niet','hun','dan','tot','was','zich','meer','zo','hier','been',
      'over','wat','hoe','wie','waar','had','zou','worden','moeten','kunnen'}
FR = {'les','des','une','est','dans','par','sur','pour','qui','que','avec',
      'son','pas','nous','vous','ils','elle','leur','au','du','et','ou',
      'mais','ce','se','lui','je','tu','il','le','la','mon','sa','ses',
      'dont','comme','plus','tout','bien','aussi','même','très','déjà'}

DE_VERBS = {'ist','sind','hat','haben','wird','werden','war','waren','kann',
            'soll','muss','darf','wurde','ein','eine','der','die','das','ich',
            'er','sie','es','wir','ihr','man','sich','nicht','auch','aber',
            'wenn','dass','als','und','oder','mit','von','zu','auf','an','in',
            'bei','nach','vor','unter','über','durch','für','gegen','ohne',
            'um','bis','seit','während','weil','obwohl','damit','jedoch'}

ENDINGS = ('.', '!', '?', '"', "'", ']', ')')

def classify_language(s):
    words = re.findall(r'[a-zA-Z]+', s.lower())
    if len(words) < 4:
        return 'ok'
    en_r = sum(1 for w in words if w in EN) / len(words)
    nl_r = sum(1 for w in words if w in NL) / len(words)
    fr_r = sum(1 for w in words if w in FR) / len(words)
    if en_r > 0.30: return 'en'
    if nl_r > 0.28: return 'nl'
    if fr_r > 0.28: return 'fr'
    return 'ok'

def is_fragment(s):
    words = s.split()
    if len(words) < 5 and not any(s.endswith(p) for p in ENDINGS):
        return True
    if len(words) < 8:
        wset = set(re.findall(r'[a-zA-ZäöüÄÖÜß]+', s.lower()))
        if not (wset & DE_VERBS):
            return True
    return False

def has_citation(s):
    return bool('\u2191' in s or 'ISBN' in s or re.search(r'https?://', s))

def has_chinese(s):
    return any('\u4e00' <= c <= '\u9fff' for c in s)

# İngilizce kelimelerin Türkçe çeviride geçmesi
EN_IN_TR = re.compile(
    r'\b(already|the|and|that|with|this|have|from|they|been|which|were|also|would|there|when|who|what|can|its|said|some|more|will|just|still|never|well|back|then|than|even|too|yet|again|where|while|through|same|last|next|high|keep|come|give|think|seem|take|make|know|see|get|go|say|look|use|find)\b',
    re.IGNORECASE
)

removed_orn = 0
for entry in data:
    ornekler = entry.get("ornekler", [])
    if not ornekler:
        continue
    clean = []
    for o in ornekler:
        de = o.get("almanca", "")
        tr = o.get("turkce", "")
        # Almanca taraf kontrolleri
        if not de:
            continue
        if classify_language(de) != 'ok':
            removed_orn += 1
            continue
        if is_fragment(de):
            removed_orn += 1
            continue
        if has_citation(de):
            removed_orn += 1
            continue
        if has_chinese(de):
            removed_orn += 1
            continue
        # Türkçe taraf kontrolleri
        if tr and EN_IN_TR.search(tr):
            o["turkce"] = ""  # Türkçeyi sil, yeniden çevrilsin
        if tr and has_chinese(tr):
            o["turkce"] = ""
        clean.append(o)
    if len(clean) != len(ornekler):
        entry["ornekler"] = clean

counts["removed_orn"] = removed_orn

# ─── 3. ORNEK SENKRONU ────────────────────────────────────────────────────────
for entry in data:
    orn = entry.get("ornekler", [])
    if orn:
        entry["ornek_almanca"] = orn[0].get("almanca", "")
        entry["ornek_turkce"]  = orn[0].get("turkce", "")
    else:
        entry.pop("ornek_almanca", None)
        entry.pop("ornek_turkce", None)

# ─── 4. KELİME AİLESİ — SADECE PREFIX KURALI ─────────────────────────────────
# Geçerli bağlantı: bare member, mw'nin başında (prefix compound)
# VEYA mw, bare member'ın başında (türev)
# KALDIRILAN: endswith (Zebrastreifen←reifen, Elle←welle gibi false positive)

def is_valid_member_strict(main_word, member):
    mw = main_word.lower()
    # Artikeli + çoğul/edat eklerini çıkar
    bare = re.sub(r'^(der|die|das|den|dem|des|ein|eine|einen|einem|einer)\s+', '', member.lower()).strip()
    if not bare or len(bare) < 3:
        return False
    # Wikipedia bölüm başlığı
    if re.search(r'\b(Aspekte|Übersicht|Portal|Verwendung|Arten|Geschichte|Typen|Formen|Einsatz|kund|tut)\b', member):
        return False
    # Çok uzun ifade (büyük olasılıkla cümle/başlık)
    if len(bare.split()) > 4:
        return False
    first = bare.split()[0]

    # a) member, mw ile başlıyor (türev: Kupplung → Kupplungsdruck)
    if first.startswith(mw) and len(mw) >= 4:
        return True
    # b) mw, member ile başlıyor (bileşik baş: Verbrennungsmotor → Verbrennung)
    if mw.startswith(first) and len(first) >= 5:
        return True
    # c) Ortak prefix ≥ 5 harf BAŞTA
    plen = 0
    for a, b in zip(mw, first):
        if a == b: plen += 1
        else: break
    if plen >= 5:
        return True
    return False

ail_removed = 0
for entry in data:
    ailesi = entry.get("kelime_ailesi", [])
    if not ailesi:
        continue
    mw = entry.get("almanca", "")
    clean = [m for m in ailesi if is_valid_member_strict(mw, m)]
    removed = len(ailesi) - len(clean)
    if removed > 0:
        entry["kelime_ailesi"] = clean
        ail_removed += removed

counts["ail_removed"] = ail_removed

# ─── 5. CEVIRI_DURUMU NORMALİZASYONU ─────────────────────────────────────────
CD_MAP = {
    'çeviri-bekleniyor': 'ceviri-bekleniyor',
    'doğrulanmış':       'manuel-dogrulandi',
    'otomatik':          'otomatik-ceviri',
    'eksik':             'ceviri-bekleniyor',
}
cd_fixed = 0
for entry in data:
    cd = entry.get("ceviri_durumu", "")
    if cd in CD_MAP:
        entry["ceviri_durumu"] = CD_MAP[cd]
        cd_fixed += 1
counts["cd_fixed"] = cd_fixed

# ─── 6. SPESİFİK DÜZELTMELER ──────────────────────────────────────────────────
# Leitungsnetz turkce "hat agi" → doğru Türkçe
for e in data:
    if e.get("almanca") == "Leitungsnetz":
        if e.get("turkce", "").strip().lower() in ("hat agi", "hat ağı", "hat agı"):
            e["turkce"] = "elektrik şebekesi; dağıtım ağı"

# ─── 7. KAYDET ────────────────────────────────────────────────────────────────
with open(DICT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
with open(JSONL_PATH, "w", encoding="utf-8") as f:
    for entry in data:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# ─── RAPOR ────────────────────────────────────────────────────────────────────
print(f"[1] aciklama_turkce -> düzeltildi : {counts['aciklama_fix']}")
print(f"[2] Silinen yabancı dil örnek      : {counts['removed_orn']}")
print(f"[4] kelime_ailesi gürültü silindi  : {counts['ail_removed']}")
print(f"[5] ceviri_durumu normalize        : {counts['cd_fixed']}")
print(f"[6] Leitungsnetz turkce fix        : ✓")

# Kontroller
arrow_left = sum(1 for e in data if '->' in str(e.get('aciklama_turkce','')))
mismatch = sum(1 for e in data if e.get('ornek_almanca') and e.get('ornekler') and e['ornek_almanca'] != e['ornekler'][0].get('almanca',''))
bos_tr = sum(1 for e in data for o in e.get('ornekler',[]) if o.get('almanca') and not o.get('turkce'))
total_orn = sum(len(e.get('ornekler',[])) for e in data)
print(f"\nSon durum:")
print(f"  aciklama -> kalan    : {arrow_left}")
print(f"  ornek senkron hatasi : {mismatch}")
print(f"  Toplam ornek         : {total_orn}")
print(f"  Cevrilmemis          : {bos_tr}")
print(f"  Toplam kayit         : {len(data)}")

# Spesifik kontroller
for k in ['Reifen','Kurbelwelle','Kind','Leitungsnetz']:
    e = next((x for x in data if x.get('almanca')==k), None)
    if e:
        if k == 'Leitungsnetz':
            print(f"  Leitungsnetz turkce  : {e.get('turkce','')}")
        else:
            print(f"  {k} ailesi: {e.get('kelime_ailesi',[])[:4]}")
