#!/usr/bin/env python3
"""
Eksik temel sıfat ve isimleri Wiktionary'den çekip sözlüğe ekler.
Bilinen çeviriler için hardcoded tablo, geri kalanlar için Google Translate.
"""
import json, re, time, urllib.request, urllib.parse, sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace')

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"

# ── Bilinen çeviriler tablosu ─────────────────────────────────────────────────
KNOWN_TR = {
    # Boyut
    "groß": "büyük; kocaman",
    "klein": "küçük; ufak",
    "lang": "uzun",
    "kurz": "kısa",
    "breit": "geniş; enli",
    "schmal": "dar; ince",
    "hoch": "yüksek",
    "tief": "derin; alçak",
    "dick": "kalın; şişman",
    "dünn": "ince; zayıf",
    "weit": "uzak; geniş",
    "eng": "dar; sıkı",
    "flach": "düz; yassı",
    "spitz": "sivri; keskin uçlu",
    "rund": "yuvarlak",
    "schief": "eğri; çarpık",
    "gerade": "düz; doğru",
    # Miktar
    "viel": "çok; fazla",
    "wenig": "az; yetersiz",
    "einige": "birkaç; bazı",
    "mehrere": "birçok; çeşitli",
    "beide": "her ikisi; ikisi de",
    # Nitelik
    "gut": "iyi; güzel",
    "schlecht": "kötü; berbat",
    "schön": "güzel; hoş",
    "toll": "harika; müthiş",
    "super": "süper; harika",
    "wunderbar": "harika; muhteşem",
    "herrlich": "muhteşem; güzel",
    "prima": "birinci sınıf; harika",
    "richtig": "doğru; gerçek",
    "falsch": "yanlış; hatalı",
    "wahr": "doğru; gerçek",
    "wichtig": "önemli",
    "nötig": "gerekli; zorunlu",
    "nützlich": "yararlı; faydalı",
    "nutzlos": "yararsız; işe yaramaz",
    "möglich": "mümkün; olası",
    "unmöglich": "imkânsız",
    "normal": "normal; olağan",
    "üblich": "olağan; alışılagelen",
    "typisch": "tipik; karakteristik",
    "besonder": "özel; farklı",
    # Zorluk
    "leicht": "hafif; kolay",
    "schwer": "ağır; zor",
    "einfach": "basit; kolay",
    "schwierig": "zor; güç",
    "kompliziert": "karmaşık; çetrefilli",
    # Hız / ses
    "schnell": "hızlı; çabuk",
    "langsam": "yavaş",
    "laut": "gürültülü; sesli",
    "leise": "sessiz; alçak sesle",
    # Doluluk
    "leer": "boş",
    "voll": "dolu",
    "offen": "açık",
    "geschlossen": "kapalı",
    "frei": "özgür; serbest; boş",
    "besetzt": "meşgul; dolu",
    # Temizlik
    "sauber": "temiz",
    "schmutzig": "kirli",
    "ordentlich": "düzenli; tertipli",
    "unordentlich": "dağınık; düzensiz",
    # Sıcaklık
    "kalt": "soğuk",
    "warm": "sıcak; ılık",
    "heiß": "sıcak; yakıcı",
    "kühl": "serin; soğukça",
    "frisch": "taze; serin",
    # Işık / renk
    "hell": "aydınlık; açık renkli",
    "dunkel": "karanlık; koyu renkli",
    "bunt": "renkli; çok renkli",
    "farbig": "renkli",
    # Renkler
    "rot": "kırmızı",
    "blau": "mavi",
    "grün": "yeşil",
    "gelb": "sarı",
    "schwarz": "siyah",
    "weiß": "beyaz",
    "grau": "gri",
    "braun": "kahverengi; esmer",
    "orange": "turuncu",
    "lila": "mor; eflatun",
    "rosa": "pembe",
    "pink": "pembe; açık pembe",
    "beige": "bej",
    "golden": "altın renkli; altın sarısı",
    "silbern": "gümüş renkli",
    "violett": "mor; eflatun",
    "türkis": "turkuaz",
    # Durum / his
    "müde": "yorgun; uykulu",
    "wach": "uyanık; uyanmış",
    "hungrig": "aç; açlıktan kıvranan",
    "durstig": "susuz; susamış",
    "krank": "hasta; rahatsız",
    "gesund": "sağlıklı",
    "glücklich": "mutlu; bahtiyar",
    "traurig": "üzgün; kederli",
    "fröhlich": "neşeli; şen",
    "wütend": "öfkeli; sinirli",
    "ärgerlich": "sinir bozucu; kızgın",
    "aufgeregt": "heyecanlı; sinirli",
    "nervös": "gergin; sinirli",
    "ruhig": "sakin; sessiz",
    "entspannt": "rahatlamış; sakin",
    "gestresst": "stresli",
    "lustig": "komik; eğlenceli",
    "witzig": "esprili; komik",
    "langweilig": "sıkıcı; can sıkıcı",
    "interessant": "ilginç; ilgi çekici",
    "spannend": "heyecanlı; merak uyandıran",
    "aufregend": "heyecan verici",
    "komisch": "komik; tuhaf",
    # Karakter
    "nett": "nazik; sevimli",
    "freundlich": "dostane; güler yüzlü",
    "höflich": "nazik; kibar",
    "unhöflich": "kaba; nezaketsiz",
    "böse": "kötü; kızgın; sinirli",
    "lieb": "sevgili; nazik",
    "süß": "tatlı; şirin",
    "fleißig": "çalışkan",
    "faul": "tembel",
    "klug": "zeki; akıllı",
    "dumm": "aptal; akılsız",
    "intelligent": "zeki; akıllı",
    "kreativ": "yaratıcı",
    "ehrlich": "dürüst; namuslu",
    "mutig": "cesur; yiğit",
    "beliebt": "sevilen; popüler",
    "bekannt": "tanınmış; bilinen",
    "berühmt": "ünlü; meşhur",
    # İlişki
    "allein": "yalnız; tek başına",
    "zusammen": "birlikte; beraber",
    "ähnlich": "benzer",
    "verschieden": "farklı; çeşitli",
    "gleich": "aynı; eşit",
    "anders": "farklı; başka türlü",
    "selber": "kendisi; bizzat",
    # Güvenlik / konfor
    "sicher": "güvenli; emin",
    "gefährlich": "tehlikeli",
    "bequem": "rahat; konforlu",
    "unbequem": "rahatsız; konforsuz",
    # Para
    "billig": "ucuz",
    "teuer": "pahalı",
    "kostenlos": "ücretsiz; parasız",
    "gratis": "bedava; ücretsiz",
    "günstig": "uygun fiyatlı; avantajlı",
    "preiswert": "değerinde; hesaplı",
    # Zaman
    "früh": "erken",
    "spät": "geç",
    "pünktlich": "dakik; zamanında",
    "neu": "yeni",
    "antik": "antik; eski",
    "modern": "modern; çağdaş",
    # Diğer
    "recht": "sağ; oldukça; hakkı olan",
    "links": "sol",
    "eigen": "kendi; öz",
    "öffentlich": "kamuya açık; halka açık",
    "privat": "özel; kişisel",
    "national": "ulusal; milli",
    "international": "uluslararası",
    "stark": "güçlü; kuvvetli",
    "schwach": "zayıf; güçsüz",
    "hart": "sert; katı",
    "weich": "yumuşak",
    "fest": "sağlam; katı",
    "locker": "gevşek; rahat",
    "froh": "sevinçli; mutlu",
    "zufrieden": "memnun; tatmin olmuş",
    "unzufrieden": "memnuniyetsiz",
    "fertig": "hazır; bitmiş",
    "bereit": "hazır; istekli",
    "kaputt": "bozuk; kırık",
    # İsimler
    "Samstag": "Cumartesi",
    "Sonntag": "Pazar",
}

MISSING_ADJ = [
    'allein','anders','antik','aufgeregt','beide','beige','bekannt','beliebt',
    'bequem','bereit','berühmt','besonder','blau','braun','breit','böse',
    'dick','durstig','dünn','ehrlich','einfach','einige','eng','entspannt',
    'falsch','fertig','fest','flach','frei','frisch','fröhlich','früh',
    'gelb','gerade','gestresst','gleich','golden','grau','gut','hart',
    'heiß','hell','herrlich','hoch','intelligent','interessant','international',
    'kalt','kompliziert','krank','kurz','kühl','lang','laut','leer','leicht',
    'leise','lieb','lila','links','locker','mehrere','modern','national','nett',
    'neu','orange','pink','preiswert','privat','recht','rosa','rot','rund',
    'sauber','schief','schlecht','schmal','schnell','schwach','schön','selber',
    'spannend','spitz','stark','super','teuer','tief','toll','türkis','unbequem',
    'violett','wach','wahr','warm','weich','weit','weiß','wütend',
]
MISSING_NOUN = ['Samstag', 'Sonntag']

# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────

def google_translate(text, src='de', dest='tr'):
    url = ('https://translate.googleapis.com/translate_a/single?client=gtx&sl='
           + src + '&tl=' + dest + '&dt=t&q=' + urllib.parse.quote(text))
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as r:
        result = json.loads(r.read())
    return ''.join(p[0] for p in result[0] if p[0])


def fetch_wiktionary(word):
    """Wiktionary'den temel bilgi çek."""
    url = ('https://de.wiktionary.org/w/api.php?action=query&prop=revisions'
           '&rvprop=content&format=json&titles=' + urllib.parse.quote(word))
    req = urllib.request.Request(url, headers={'User-Agent': 'AlmancaSozluk/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        pages = data.get('query', {}).get('pages', {})
        page = next(iter(pages.values()))
        if 'missing' in page:
            return None
        return page['revisions'][0]['*']
    except Exception:
        return None


def parse_bedeutungen(wikitext):
    """Wikitext'ten Almanca tanım çek."""
    m = re.search(r'\{\{Bedeutungen\}\}(.*?)(?=\{\{[A-Z]|\Z)', wikitext, re.S)
    if not m:
        return ''
    lines = [re.sub(r'\{\{[^}]+\}\}|\[\[(?:[^|\]]+\|)?([^\]]+)\]\]|<[^>]+>|\'\'\'?|:{1,3}', r'\1', l).strip()
             for l in m.group(1).split('\n') if l.strip().startswith(':')]
    return '; '.join(l.lstrip(':').strip() for l in lines[:2] if l.lstrip(':').strip())


def parse_komparativ(wikitext):
    """Karşılaştırma formlarını çek."""
    forms = {}
    m = re.search(r'Komparativ[^=]+=\s*([^\|}\n]+)', wikitext)
    if m:
        forms['komparativ'] = m.group(1).strip()
    m = re.search(r'Superlativ[^=]+=\s*([^\|}\n]+)', wikitext)
    if m:
        forms['superlativ'] = 'am ' + m.group(1).strip()
    return forms


def zipf_to_seviye(zipf):
    if zipf >= 5.0: return 'A1'
    if zipf >= 4.5: return 'A2'
    if zipf >= 4.0: return 'B1'
    if zipf >= 3.5: return 'B2'
    if zipf >= 3.0: return 'C1'
    return 'C2'


# ── Ana mantık ────────────────────────────────────────────────────────────────

with open(DICT_PATH, encoding='utf-8') as f:
    data = json.load(f)

existing = {e['almanca'] for e in data}
added = 0
errors = []

all_targets = [(w, 'sıfat') for w in MISSING_ADJ] + [(w, 'isim') for w in MISSING_NOUN]

for word, tur in all_targets:
    if word in existing:
        print(f'  ATLA (zaten var): {word}')
        continue

    # Türkçe çeviri
    turkce = KNOWN_TR.get(word)
    if not turkce:
        try:
            turkce = google_translate(word)
            time.sleep(0.5)
        except Exception as e:
            turkce = ''
            errors.append(word)

    # Wiktionary
    wikitext = fetch_wiktionary(word)
    time.sleep(0.4)

    tanim_almanca = ''
    extra = {}
    if wikitext:
        tanim_almanca = parse_bedeutungen(wikitext)
        if tur == 'sıfat':
            extra = parse_komparativ(wikitext)

    # Seviye tahmini — temel kelimeler çoğunlukla A1/A2
    basic_a1 = {'gut','schlecht','groß','klein','alt','neu','jung','lang','kurz',
                'gut','rot','blau','grün','gelb','schwarz','weiß','kalt','warm',
                'heiß','schnell','langsam','laut','leise','billig','teuer',
                'richtig','falsch','krank','gesund','müde','hungrig','Samstag','Sonntag'}
    seviye = 'A1' if word in basic_a1 else 'A2'

    entry = {
        'almanca': word,
        'turkce': turkce,
        'tur': tur,
        'artikel': '' if tur == 'sıfat' else '',
        'seviye': seviye,
        'kategoriler': [],
        'ornekler': [],
        'kelime_ailesi': [],
        'esanlamlilar': [],
        'kaynak': 'wiktionary-de',
        'ceviri_durumu': 'otomatik',
    }
    if tanim_almanca:
        entry['tanim_almanca'] = tanim_almanca
    if extra.get('komparativ'):
        entry['komparativ'] = extra['komparativ']
    if extra.get('superlativ'):
        entry['superlativ'] = extra['superlativ']
    if tur == 'isim':
        entry['artikel'] = ''  # Wiktionary'den çekilmedi, doldurulabilir
    else:
        entry.pop('artikel', None)

    data.append(entry)
    existing.add(word)
    added += 1
    print(f'  Eklendi [{seviye}] {word}: {turkce}')

# Kaydet
with open(DICT_PATH, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
with open(JSONL_PATH, 'w', encoding='utf-8') as f:
    for e in data:
        f.write(json.dumps(e, ensure_ascii=False) + '\n')

print(f'\nToplam eklenen: {added}')
print(f'Toplam kayıt  : {len(data)}')
if errors:
    print(f'Hata (çeviri yapılamadı): {errors}')
