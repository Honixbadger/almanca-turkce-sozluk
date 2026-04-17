#!/usr/bin/env python3
"""
Boşluk doldurma - 4 alan:
  1. genitiv_endung: tam kelime → suffix'e çevir + boşları tahmin et
  2. cogul: suffix kurallarıyla tahmin et
  3. partizip2: prefix kurallarıyla tahmin et + verb_typ doldur
  4. kategoriler: keyword tabanlı kategori ataması genişlet
"""
import json, re, sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace')

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"

with open(DICT_PATH, encoding='utf-8') as f:
    data = json.load(f)

c = {k: 0 for k in ['gen_norm','gen_fill','cogul_fill','part2_fill','vtyp_fill','kat_fill']}

# ── 1. GENİTİV ────────────────────────────────────────────────────────────────

# Eğer genitiv_endung tam kelimeye eşitse → suffix'e çevir
def normalize_genitiv(word, val):
    if not val: return val
    if val == word:
        # Feminine: -ung/-heit/-keit/-schaft/-tion/-tät/-ie → genitiv = same (suffix '')
        return ''
    if val.startswith(word) and len(val) > len(word):
        suffix = val[len(word):]
        return suffix  # örn. "-es", "-s", "-en"
    return val

# Tahmin kuralları
def predict_genitiv(word, artikel):
    w = word.lower()
    art = (artikel or '').lower()
    # Dişil → genitiv = nominative (suffix yok)
    if art == 'die':
        return ''
    # Feminine sonekler (artikel bilinmese de)
    for suf in ['ung','heit','keit','schaft','tion','sion','tät','ät','ie','ur','ei']:
        if w.endswith(suf): return ''
    # Nötr küçülme
    for suf in ['chen','lein']:
        if w.endswith(suf): return 's'
    # Zayıf erkek isimler (-e soneki + der)
    if art == 'der' and w.endswith('e'): return 'n'
    # -nis → -ses (das/die Ergebnis)
    if w.endswith('nis'): return 'ses'
    # -us → '' (latince)
    if w.endswith('us'): return ''
    # -ismus → ''
    if w.endswith('ismus'): return ''
    # -or/-eur → 's'
    for suf in ['or','eur','är','ier']:
        if w.endswith(suf): return 's'
    # Erkek/nötr default: -s
    if art in ('der','das'): return 's'
    return 's'

for e in data:
    if e.get('tur') != 'isim': continue
    word = e.get('almanca','')
    # Normalize
    gen = e.get('genitiv_endung','')
    new_gen = normalize_genitiv(word, gen)
    if new_gen != gen:
        e['genitiv_endung'] = new_gen
        c['gen_norm'] += 1
    # Doldur
    if not e.get('genitiv_endung') and e.get('genitiv_endung') != '':
        pred = predict_genitiv(word, e.get('artikel',''))
        e['genitiv_endung'] = pred
        e.setdefault('genitiv_kaynak','tahmin')
        c['gen_fill'] += 1

# ── 2. ÇOĞUL ──────────────────────────────────────────────────────────────────
def predict_plural(word, artikel):
    w = word.lower()
    art = (artikel or '').lower()
    # Kesin kurallar
    rules = [
        ('ung',   word + 'en'),
        ('heit',  word + 'en'),
        ('keit',  word + 'en'),
        ('schaft',word + 'en'),
        ('tion',  word[:-4] + 'tionen'),
        ('sion',  word[:-4] + 'sionen'),
        ('tät',   word + 'en'),
        ('ät',    word + 'en'),
        ('ie',    word + 'n'),
        ('ur',    word + 'en'),
        ('ei',    word + 'en'),
        ('nis',   word + 'se'),
        ('ismus', word[:-2] + 'en'),   # Marxismus→Marxismen (nadir ama kabul)
        ('ist',   word + 'en'),
        ('ent',   word + 'en'),
        ('ant',   word + 'en'),
        ('at',    word + 'en'),
        ('chen',  word),               # Küçülme → değişmez
        ('lein',  word),
        ('ium',   word[:-2] + 'ien'),  # Stadium→Stadien
        ('um',    word[:-2] + 'en'),   # Datum→Daten
        ('ma',    word + 'ta'),        # Thema→Themata
        ('us',    word[:-2] + 'en'),   # Virus→Viren (genel kural)
    ]
    for suf, plural in rules:
        if w.endswith(suf): return plural
    # -er, -el — genellikle değişmez (Umlaut olabilir ama tahmin zor)
    for suf in ['er','el']:
        if w.endswith(suf): return word  # same
    # Sonu -e ile biten: +n
    if w.endswith('e'): return word + 'n'
    # Default
    return word + 'e'  # yaygın erkek/nötr çoğul

for e in data:
    if e.get('tur') != 'isim': continue
    if not e.get('cogul'):
        pred = predict_plural(e.get('almanca',''), e.get('artikel',''))
        e['cogul'] = pred
        e.setdefault('cogul_kaynak','tahmin')
        c['cogul_fill'] += 1

# ── 3. PARTİZİP2 + VERB_TYP ───────────────────────────────────────────────────
UNTRENNBAR = {'be','emp','ent','er','ge','miss','ver','zer','wider'}
TRENNBAR   = {'ab','an','auf','aus','bei','durch','ein','fest','her','hin',
              'mit','nach','vor','weg','zu','zurück','über','um','unter','los',
              'zusammen','weiter','voran','entgegen','gegenüber'}

def get_verb_typ(inf):
    w = inf.lower().rstrip('n').rstrip('e')  # rough stem
    # Uzun önekler önce
    for pre in sorted(TRENNBAR | UNTRENNBAR, key=len, reverse=True):
        if inf.lower().startswith(pre):
            if pre in UNTRENNBAR:
                return 'untrennbar'
            else:
                return 'trennbar'
    return 'temel'

def predict_partizip2(inf, vtyp):
    w = inf
    # sich kaldır
    w = re.sub(r'^\(sich\)\s*', '', w).strip()
    w = re.sub(r'^sich\s+', '', w).strip()
    stem_inf = w.lower()

    # Güçlü fiiller (irregular) — çok sayıda var, sadece en yaygınları
    IRREGULAR = {
        'sein':'gewesen','haben':'gehabt','werden':'geworden',
        'gehen':'gegangen','kommen':'gekommen','stehen':'gestanden',
        'geben':'gegeben','nehmen':'genommen','fahren':'gefahren',
        'laufen':'gelaufen','halten':'gehalten','fallen':'gefallen',
        'schreiben':'geschrieben','sprechen':'gesprochen','sehen':'gesehen',
        'lesen':'gelesen','essen':'gegessen','trinken':'getrunken',
        'singen':'gesungen','springen':'gesprungen','finden':'gefunden',
        'binden':'gebunden','bringen':'gebracht','denken':'gedacht',
        'kennen':'gekannt','nennen':'genannt','rennen':'gerannt','senden':'gesandt',
        'wissen':'gewusst','müssen':'gemusst','können':'gekonnt',
        'sollen':'gesollt','wollen':'gewollt','dürfen':'gedurft','mögen':'gemocht',
    }
    if stem_inf in IRREGULAR:
        return IRREGULAR[stem_inf]

    # Untrennbar (kein ge-)
    if vtyp == 'untrennbar':
        # Stem: öneki çıkar
        for pre in sorted(UNTRENNBAR, key=len, reverse=True):
            if stem_inf.startswith(pre):
                root = w[len(pre):]
                root_stem = root[:-2] if root.endswith('en') else root[:-1] if root.endswith('n') else root
                if root.endswith('ieren'):
                    return pre + root[:-2] + 't'
                if root_stem.endswith('t') or root_stem.endswith('d'):
                    return pre + root_stem + 'et'
                return pre + root_stem + 't'
        return stem_inf  # fallback

    # Trennbar: ge- ortaya girer
    if vtyp == 'trennbar':
        for pre in sorted(TRENNBAR, key=len, reverse=True):
            if stem_inf.startswith(pre):
                root = w[len(pre):]
                root_stem = root[:-2] if root.endswith('en') else root[:-1] if root.endswith('n') else root
                if root_stem.endswith('t') or root_stem.endswith('d'):
                    return pre + 'ge' + root_stem + 'et'
                return pre + 'ge' + root_stem + 't'
        return stem_inf

    # Temel fiil: ge- başa
    stem = w[:-2] if w.endswith('en') else w[:-1] if w.endswith('n') else w
    stem_lower = stem.lower()
    # -ieren → -iert (kein ge-)
    if stem_inf.endswith('ieren'):
        return stem[:-3] + 't'
    # dt/tt sonu
    if stem_lower.endswith(('t','d')):
        return 'ge' + stem + 'et'
    return 'ge' + stem + 't'

for e in data:
    if e.get('tur') != 'fiil': continue
    inf = e.get('almanca','')
    # verb_typ
    if not e.get('verb_typ'):
        vt = get_verb_typ(inf)
        e['verb_typ'] = vt
        c['vtyp_fill'] += 1
    else:
        vt = e['verb_typ']
    # partizip2
    if not e.get('partizip2'):
        # Sözlük girişi gerçekten fiil mi? (adj/pronoun formları geçmiş olabilir)
        if ' ' in inf or not re.search(r'[a-zA-ZäöüÄÖÜß]en$|[a-zA-ZäöüÄÖÜß]n$', inf):
            continue  # Çok kelimeli veya fiil gibi görünmeyen → atla
        p2 = predict_partizip2(inf, vt)
        if p2:
            e['partizip2'] = p2
            e.setdefault('partizip2_kaynak','tahmin')
            c['part2_fill'] += 1

# ── 4. KATEGORİLER ────────────────────────────────────────────────────────────
KAT_RULES = [
    ('otomotiv',        r'auto|motor|fahrzeug|reifen|bremse|lenkung|getriebe|kupplung|zylinder|'
                        r'kolben|ventil|auspuff|abgas|kraftstoff|benzin|diesel|öl|kühlwasser|'
                        r'achse|fahrwerk|karosserie|scheibe|wischer|scheinwerfer|blinker|'
                        r'araba|otomotiv|araç|motor|fren|debriyaj|şanzıman|lastik'),
    ('bilişim',         r'computer|software|hardware|internet|daten|programm|app|digital|'
                        r'netzwerk|server|code|algorithm|datenbank|datei|system|byte|pixel|'
                        r'bilgisayar|yazılım|donanım|internet|veri|program|dijital|ağ'),
    ('sağlık-tıp',      r'medizin|arzt|krank|gesund|therapie|diagnose|symptom|behandlung|'
                        r'krankenhaus|apotheke|impf|virus|bakterie|blut|herz|lunge|hirn|'
                        r'doktor|hasta|sağlık|tedavi|ilaç|hastane|eczane|kalp|akciğer'),
    ('hukuk',           r'recht|gesetz|gericht|strafe|vertrag|klage|anwalt|richter|urteil|'
                        r'paragraph|gesetzlich|hukuk|kanun|mahkeme|ceza|sözleşme|avukat|hakim'),
    ('müzik',           r'musik|lied|melodie|rhythmus|instrument|gitarre|klavier|geige|'
                        r'singen|sänger|konzert|band|album|müzik|şarkı|melodi|enstrüman|gitar'),
    ('spor',            r'sport|fußball|tennis|schwimmen|laufen|rennen|wettkampf|mannschaft|'
                        r'spieler|trainer|tor|punkt|spor|futbol|koşu|yarış|takım|oyuncu'),
    ('eğitim-bilim',    r'schule|universität|lernen|lehren|prüfung|wissenschaft|forschung|'
                        r'studie|theorie|experiment|lehrer|schüler|okul|üniversite|öğrenme|bilim'),
    ('ekonomi',         r'wirtschaft|markt|preis|geld|bank|finanz|aktie|handel|unternehmen|'
                        r'produktion|inflation|steuer|ekonomi|piyasa|fiyat|para|banka|finans'),
    ('gıda-mutfak',     r'essen|trinken|kochen|rezept|mahlzeit|küche|restaurant|brot|fleisch|'
                        r'gemüse|obst|milch|käse|yemek|içmek|pişirme|tarif|ekmek|et|sebze|meyve'),
    ('giyim',           r'kleidung|hemd|hose|jacke|kleid|schuh|mütze|mode|stoff|'
                        r'giyim|gömlek|pantolon|ceket|elbise|ayakkabı|şapka|moda|kumaş'),
    ('doğa-çevre',      r'natur|tier|pflanze|baum|wald|berg|see|fluss|luft|wasser|erde|'
                        r'umwelt|klima|doğa|hayvan|bitki|ağaç|orman|dağ|göl|nehir|çevre'),
    ('aile-sosyal',     r'familie|mutter|vater|kind|bruder|schwester|freund|beziehung|ehe|'
                        r'aile|anne|baba|çocuk|kardeş|arkadaş|ilişki|evlilik'),
    ('coğrafya',        r'land|stadt|dorf|straße|platz|gebäude|gebiet|region|ülke|şehir|köy|'
                        r'sokak|alan|bina|bölge'),
    ('sanat-kültür',    r'kunst|malerei|skulptur|literatur|theater|film|foto|architektur|'
                        r'kultur|sanat|resim|heykel|edebiyat|tiyatro|film|fotoğraf|mimari'),
    ('din-felsefe',     r'religion|kirche|gott|gebet|glaube|philosophie|ethik|moral|'
                        r'din|kilise|tanrı|dua|inanç|felsefe|etik|ahlak'),
    ('ulaşım',          r'zug|bus|flugzeug|schiff|straße|bahnhof|flughafen|hafen|fahren|reise|'
                        r'tren|otobüs|uçak|gemi|yol|istasyon|havalimanı|liman|seyahat'),
    ('elektrik-elektronik', r'elektrik|strom|spannung|widerstand|kondensator|transistor|'
                        r'schaltung|elektronik|sensor|akku|batterie|laden|'
                        r'elektrik|akım|gerilim|direnç|kondansatör|elektronik|sensör'),
    ('inşaat-mimari',   r'bau|gebäude|haus|wand|boden|decke|fenster|tür|treppe|fundament|'
                        r'zement|beton|inşaat|bina|ev|duvar|zemin|tavan|pencere|kapı|merdiven'),
    ('enerji',          r'energie|kraftwerk|solar|wind|atom|kohle|gas|öl|strom|erneuerbar|'
                        r'enerji|santral|güneş|rüzgar|nükleer|kömür|gaz|yenilenebilir'),
    ('tarih',           r'geschichte|krieg|kaiser|könig|reich|revolution|antike|mittelalter|'
                        r'tarih|savaş|imparator|kral|devrim|antik|ortaçağ'),
]

def assign_categories(entry):
    existing_kats = set(entry.get('kategoriler', []))
    text = ' '.join([
        entry.get('almanca',''), entry.get('turkce',''),
        entry.get('tanim_almanca',''), entry.get('aciklama_turkce','')
    ]).lower()
    new_kats = list(existing_kats - {'genel'})
    for kat, pattern in KAT_RULES:
        if kat not in new_kats and re.search(pattern, text):
            new_kats.append(kat)
        if len(new_kats) >= 3:
            break
    if not new_kats:
        new_kats = ['genel']
    return new_kats

for e in data:
    old_kats = e.get('kategoriler', [])
    new_kats = assign_categories(e)
    if set(new_kats) != set(old_kats):
        e['kategoriler'] = new_kats
        if not old_kats or old_kats == ['genel']:
            c['kat_fill'] += 1

# ── KAYDET ────────────────────────────────────────────────────────────────────
with open(DICT_PATH, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
with open(JSONL_PATH, 'w', encoding='utf-8') as f:
    for e in data:
        f.write(json.dumps(e, ensure_ascii=False) + '\n')

# ── RAPOR ─────────────────────────────────────────────────────────────────────
nouns = [e for e in data if e.get('tur')=='isim']
verbs = [e for e in data if e.get('tur')=='fiil']
print(f"[1] genitiv normalize : {c['gen_norm']}")
print(f"[1] genitiv tahmin    : {c['gen_fill']}")
print(f"[2] çoğul tahmin      : {c['cogul_fill']}")
print(f"[3] partizip2 tahmin  : {c['part2_fill']}")
print(f"[3] verb_typ doldurma : {c['vtyp_fill']}")
print(f"[4] kategori eklendi  : {c['kat_fill']}")
print()
print(f"Genitiv bos  : {sum(1 for e in nouns if e.get('genitiv_endung','') == '' and 'genitiv_kaynak' not in e and not e.get('artikel','').lower()=='die')}")
print(f"Cogul bos    : {sum(1 for e in nouns if not e.get('cogul'))}")
print(f"Partizip2 bos: {sum(1 for e in verbs if not e.get('partizip2'))}")
print(f"Verb_typ bos : {sum(1 for e in verbs if not e.get('verb_typ'))}")
print(f"Kategori bos : {sum(1 for e in data if not e.get('kategoriler'))}")
