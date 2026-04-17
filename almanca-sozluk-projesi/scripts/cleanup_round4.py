#!/usr/bin/env python3
"""
4. tur temizlik:
  1. aciklama_turkce: "TR1; ALMANCA: ... -> TR2" formatından TR1+TR2 çıkar
  2. Kalan yabancı dil örnekler: daha sıkı kelime seti ile
  3. Türkçe örneklerde İngilizce artık: güvenli eşik
  4. Anlam karışması: otomotiv bağlamında yanlış sense'leri temizle
  5. Tekil çeviri düzeltmeleri (Feder, Blinker, Getriebe, Kolben, Katalysator)
"""
import json, re, sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace')

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"

with open(DICT_PATH, encoding="utf-8") as f:
    data = json.load(f)

# Almanca alan göstergeleri (alan adı: ile başlayan bloğu tanır)
DE_DOMAIN = re.compile(
    r'\b(Informatik|Informationstechnologie|Botanik|Biologie|Chemie|Physik|Mathematik|'
    r'Medizin|Technik|Architektur|Linguistik|Musik|Sport|Recht|Wirtschaft|'
    r'umgangssprachlich|veraltend|veraltet|regional|ugs\.|Plural|verkürzt|'
    r'übertragen|figurativ|fig\.|Jägersprache|Seemannssprache)\b'
)
TR_LETTERS = set('abcçdefgğhıijklmnoöprsştuüvyz')

def looks_turkish(s):
    """Kısa kontrolle Türkçe mi yoksa Almanca mı?"""
    if not s: return False
    s_low = s.lower()
    # Türkçeye özgü karakterler varsa kesinlikle Türkçe
    if any(c in s_low for c in 'çğışöü'): return True
    # Almancaya özgü karakterler varsa değil
    if any(c in s_low for c in 'äöüß'): return False
    # Kısa ve bilinen Türkçe kalıp
    if re.search(r'\b(bir|ve|ile|bu|için|den|da|de|ta|te|ya|ki|ne|mi|mu|mü|mı)\b', s_low):
        return True
    return False

def extract_turkish_from_aciklama(val):
    """
    Formatlar:
      a) "TR1; ALAN: ALMANCA_DEF -> TR2"  → "TR1; TR2"
      b) "TR1; ALMANCA_DEF -> TR2"         → "TR1; TR2"
      c) "ALMANCA_DEF -> TR"               → "TR"
    """
    if '->' not in val:
        return val

    # Tüm -> bölümlerini işle
    parts = re.split(r'\s*->\s*', val)
    turkish_parts = []

    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        # Alan adı ile biten kısmı temizle: "TR1; ALAN:" → "TR1"
        # Ayrıca segment içindeki Almanca tanım bloğunu çıkar
        # Semicolon ile ayrılmış alt parçaları kontrol et
        sub_parts = [p.strip() for p in re.split(r';\s*', part)]
        for sp in sub_parts:
            # Almanca alan göstergesi içeren alt parçaları atla
            if DE_DOMAIN.search(sp):
                continue
            # Büyük harf ile başlayan uzun Almanca cümle ise atla
            if re.match(r'^[A-ZÄÖÜ][a-zäöüß]', sp) and len(sp) > 40 and not looks_turkish(sp):
                continue
            # Kısa ve anlamlı görünen Türkçe kısım
            clean = re.sub(r':\s*$', '', sp).strip()
            if clean and len(clean) > 1:
                turkish_parts.append(clean)

    if not turkish_parts:
        return val  # Düzeltemedik, olduğu gibi bırak

    result = '; '.join(dict.fromkeys(turkish_parts))  # Tekrarları kaldır, sırayı koru
    return result


# ─── 1. ACIKLAMA_TURKCE DÜZELTMESİ ───────────────────────────────────────────
aciklama_fixed = 0
for entry in data:
    val = entry.get('aciklama_turkce', '')
    if not val or '->' not in val:
        continue
    new_val = extract_turkish_from_aciklama(val)
    if new_val != val:
        entry['aciklama_turkce'] = new_val
        aciklama_fixed += 1

# ─── 2. KALAN YABANCI DİL ÖRNEKLERİ (GÜÇLÜ EŞIK) ────────────────────────────
EN_STRONG = {
    'the','and','that','this','with','from','have','been','which','their',
    'were','would','there','when','what','could','should','about','after',
    'before','during','those','these','other','still','never','because',
    'although','however','therefore','information','system','management',
    'development','process','analysis','research','data','network','service',
    'application','technology','environment','performance','structure',
}
NL_STRONG = {
    'worden','wordt','heeft','werd','werden','kunnen','moeten','mogen',
    'willen','zullen','zijn','hebben','voor','naar','door','bij','ook',
    'maar','niet','meer','deze','deze','over','haar','hem','dan','dat','het',
}

def is_clearly_non_german(s):
    words = re.findall(r'[a-zA-Z]{4,}', s.lower())  # 4+ harf — kısa kelime false positive önler
    if len(words) < 3: return False
    en_r = sum(1 for w in words if w in EN_STRONG) / len(words)
    nl_r = sum(1 for w in words if w in NL_STRONG) / len(words)
    return en_r > 0.33 or nl_r > 0.33

DE_VERBS = {'ist','sind','hat','haben','wird','werden','war','waren','kann',
            'soll','muss','darf','wurde','ein','eine','der','die','das',
            'ich','er','sie','es','wir','man','sich','nicht','auch','aber',
            'wenn','dass','als','und','oder','mit','von','zu'}
ENDINGS = ('.','!','?','"',"'",')',']')

def is_fragment(s):
    words = s.split()
    if len(words) < 5 and not any(s.endswith(p) for p in ENDINGS): return True
    if len(words) < 8:
        wset = set(re.findall(r'[a-zA-ZäöüÄÖÜß]+', s.lower()))
        if not (wset & DE_VERBS): return True
    return False

removed_orn = 0
for entry in data:
    orn = entry.get('ornekler', [])
    if not orn: continue
    clean = []
    for o in orn:
        de = o.get('almanca', '')
        if not de: continue
        if is_clearly_non_german(de) or is_fragment(de):
            removed_orn += 1
            continue
        clean.append(o)
    if len(clean) != len(orn):
        entry['ornekler'] = clean

# ─── 3. TÜRKÇE ÖRNEKLERDE İNGİLİZCE ARTIK ────────────────────────────────────
# Güvenli: sadece 4+ harfli kelimelere bak, yüksek eşik
EN_IN_TR_STRONG = re.compile(
    r'\b(already|information|system|development|management|process|research|'
    r'because|although|however|therefore|environment|performance|structure|'
    r'application|technology|network|service|analysis)\b',
    re.IGNORECASE
)
cleared_tr = 0
for entry in data:
    for o in entry.get('ornekler', []):
        tr = o.get('turkce', '')
        if tr and EN_IN_TR_STRONG.search(tr):
            o['turkce'] = ''
            cleared_tr += 1

# ─── 4. ANLAM KARISMASINI TEMIZLE (OTOMOTİV BAĞLAMI) ─────────────────────────
# Bu girişler otomotiv kategorisinde ama başka alandan sense sızmış
AUTOMOTIVE_FIXES = {
    'Getriebe':      ('şanzıman', ['şanzıman; diferansiyel', 'şanzıman;diferansiyel']),
    'Kolben':        ('piston', ['piston; koçan', 'piston;koçan']),
    'Katalysator':   ('katalizör', ['katalizör; ivdirgen', 'katalizör;ivdirgen']),
    'Kühlflüssigkeit': ('soğutma sıvısı', ['soğutma sıvısı; soğutucu', 'soğutucu; soğutma sıvısı']),
}

for word, (correct, wrong_variants) in AUTOMOTIVE_FIXES.items():
    e = next((x for x in data if x.get('almanca') == word), None)
    if not e: continue
    current = e.get('turkce', '')
    for wrong in wrong_variants:
        if current.strip().lower() == wrong.lower():
            e['turkce'] = correct
            break

# ─── 5. TEKİL ÇEVİRİ DÜZELTMELERİ ───────────────────────────────────────────
targeted = 0

for entry in data:
    almanca = entry.get('almanca', '')

    # Feder: "tanımlayamaz mısın?" → "tanıyamaz mısın?"
    if almanca == 'Feder':
        for o in entry.get('ornekler', []):
            if 'Hahnenfeder' in o.get('almanca', '') and 'tanımlayamaz' in o.get('turkce', ''):
                o['turkce'] = 'Horoz tüyünü tanıyamaz mısın?'
                targeted += 1

    # Blinker: örneği daha doğal hale getir
    if almanca == 'Blinker':
        for o in entry.get('ornekler', []):
            tr = o.get('turkce', '')
            if 'Tom sinyal lambasını açtı' in tr:
                o['turkce'] = 'Tom sinyali yaktı.'
                targeted += 1

    # Getriebe: getrieben fiiline takılmış örneği temizle
    if almanca == 'Getriebe':
        orn = entry.get('ornekler', [])
        clean_orn = [o for o in orn if 'getrieben' not in o.get('almanca', '').lower().split()
                     or 'Getriebe' in o.get('almanca', '')]
        if len(clean_orn) != len(orn):
            entry['ornekler'] = clean_orn
            targeted += 1

    # Zylinder: turkce'den bilişim anlamını çıkar
    if almanca == 'Zylinder':
        tr = entry.get('turkce', '')
        # "harddisk üzeri sektör" veya "bilişim" ile ilgili parçaları sil
        cleaned = re.sub(r';\s*(harddisk[^;]*|bilişim[^;]*|veri\s+kayıt[^;]*)', '', tr, flags=re.I)
        if cleaned != tr:
            entry['turkce'] = cleaned.strip('; ')
            targeted += 1

# ─── 6. ORNEK SENKRONU ────────────────────────────────────────────────────────
for entry in data:
    orn = entry.get('ornekler', [])
    if orn:
        entry['ornek_almanca'] = orn[0].get('almanca', '')
        entry['ornek_turkce']  = orn[0].get('turkce', '')
    else:
        entry.pop('ornek_almanca', None)
        entry.pop('ornek_turkce', None)

# ─── KAYDET ───────────────────────────────────────────────────────────────────
with open(DICT_PATH, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
with open(JSONL_PATH, 'w', encoding='utf-8') as f:
    for entry in data:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')

# ─── RAPOR ────────────────────────────────────────────────────────────────────
arrow_left = sum(1 for e in data if '->' in str(e.get('aciklama_turkce', '')))
bos_tr = sum(1 for e in data for o in e.get('ornekler',[]) if o.get('almanca') and not o.get('turkce'))

print(f'[1] aciklama -> düzeltildi  : {aciklama_fixed}  (kalan: {arrow_left})')
print(f'[2] Yabancı dil örnek silindi: {removed_orn}')
print(f'[3] Bozuk TR örnek temizlendi: {cleared_tr}')
print(f'[4] Anlam karışması düzeltildi: automotive sense fix ✓')
print(f'[5] Tekil düzeltmeler        : {targeted}')
print(f'')
print(f'Toplam örnek    : {sum(len(e.get("ornekler",[])) for e in data)}')
print(f'Çevrilmemiş     : {bos_tr}')
print(f'Toplam kayıt    : {len(data)}')

# Spesifik kontrol
for k in ['Getriebe','Kolben','Katalysator','Zylinder','Feder']:
    e = next((x for x in data if x.get('almanca')==k), None)
    if e: print(f'  {k}: {e.get("turkce","")[:60]}')
