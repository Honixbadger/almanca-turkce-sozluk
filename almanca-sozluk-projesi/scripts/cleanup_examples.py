#!/usr/bin/env python3
import json, re, sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace')

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"

with open(DICT_PATH, encoding="utf-8") as f:
    data = json.load(f)

EN_WORDS = {
    'the','of','and','to','in','a','is','that','for','it','was','on','are','with',
    'as','at','from','this','have','an','by','not','or','but','had','his','they',
    'she','he','been','which','their','were','also','would','built','placed','hotel',
    'house','motor','car','about','feet','where','taken','sight','shed','text','draft',
    'into','out','up','down','through','over','under','between','after','before',
    'during','its','our','your','both','each','few','more','most','other','some',
    'such','no','only','same','than','too','very','just','can','will','there','when',
    'who','what','how','all','any','one','two','may','him','her','so','do','did',
    'has','should','could','many','much','since','still','these','those','own','if',
    'then','well','back','first','long','great','little','now','old','right','think',
    'come','here','know','place','take','year','good','away','go','see','even','give',
    'us','made','never','say','later','used','front','dark','building','stopped',
    'cathedral','moment','last','took','way','east','blocked','soruna','which',
}

FR_WORDS = {
    'les','des','une','est','dans','par','sur','pour','qui','que','avec','son',
    'pas','nous','vous','ils','elle','leur','au','du','en','et','ou','donc','mais',
    'car','batterie','francaise','nombreux','morts','entre','prisonniers','surprend',
    'dragons','pied','terre','chez','plus','tout','cette','ces','leurs','sans','sous',
    'vers','avant','dont','etre','avoir','faire','dit','tres','bien','quand','meme',
    'aussi','comme','ce','cet','se','lui','me','te','je','tu','il','le','la','mon',
    'ma','mes','ton','ta','tes','sa','ses','notre','votre','leur',
}

SENTENCE_ENDINGS = ('.', '!', '?', '"', "'", ']', ')')

DE_VERB_INDICATORS = {
    'ist','sind','hat','haben','wird','werden','war','waren','kann','soll','muss',
    'darf','mag','wurde','ein','eine','der','die','das','ich','er','sie','es',
    'wir','ihr','sie','man','sich','nicht','auch','aber','wenn','dass','als',
    'und','oder','mit','von','zu','auf','an','in','bei','nach','vor','unter',
    'über','durch','für','gegen','ohne','um','bis','seit','während','weil',
    'obwohl','damit','sodass','jedoch','dennoch','trotzdem','außerdem',
}


def is_non_german(s):
    if not s or len(s) < 15:
        return False
    words = re.findall(r'[a-zA-Z]+', s.lower())
    if len(words) < 4:
        return False
    en_hit = sum(1 for w in words if w in EN_WORDS)
    fr_hit = sum(1 for w in words if w in FR_WORDS)
    ratio_en = en_hit / len(words)
    ratio_fr = fr_hit / len(words)
    return ratio_en > 0.35 or ratio_fr > 0.30


def is_truncated(s):
    if not s:
        return True
    words = s.split()
    # Çok kısa ve cümle sonu yok
    if len(words) < 5 and not any(s.endswith(p) for p in SENTENCE_ENDINGS):
        return True
    # Wikipedia caption: kısa + Almanca fiil yok
    if len(words) < 8:
        word_set = set(re.findall(r'[a-zA-ZäöüÄÖÜß]+', s.lower()))
        if not (word_set & DE_VERB_INDICATORS):
            return True
    return False


def has_citation(s):
    return bool(
        '\u2191' in s or          # ↑
        'ISBN' in s or
        re.search(r'doi:', s, re.I) or
        re.search(r'https?://', s) or
        re.search(r'\(S\.\s*\d+\)', s) or
        re.search(r'^\s*[a-z]\s+[a-z]\s+[a-z]\b', s)
    )


removed = 0
kept = 0
entries_affected = 0

for entry in data:
    ornekler = entry.get("ornekler", [])
    if not ornekler:
        continue
    clean = []
    for o in ornekler:
        s = o.get("almanca", "")
        if is_non_german(s) or is_truncated(s) or has_citation(s):
            removed += 1
        else:
            clean.append(o)
            kept += 1
    if len(clean) != len(ornekler):
        entries_affected += 1
        entry["ornekler"] = clean
        if clean and clean[0].get("turkce"):
            entry["ornek_turkce"] = clean[0]["turkce"]
        elif not clean:
            entry.pop("ornek_turkce", None)

print(f"Silinen örnek   : {removed}")
print(f"Kalan örnek     : {kept}")
print(f"Etkilenen kayıt : {entries_affected}")

bos_tr = sum(1 for e in data for o in e.get("ornekler",[]) if o.get("almanca") and not o.get("turkce"))
print(f"Hala çevrilmemiş: {bos_tr}")

with open(DICT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
with open(JSONL_PATH, "w", encoding="utf-8") as f:
    for entry in data:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("Kaydedildi.")
