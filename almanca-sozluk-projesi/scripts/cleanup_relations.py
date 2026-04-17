#!/usr/bin/env python3
"""
İlişki alanları temizliği:
  1. Açık yanlış-sense esanlamlilar: 8 sorunlu giriş için el ile temizlik
  2. Çok kelimeli (multi-word) esanlamlilar/zit_anlamlilar sil — bunlar leksikal birim değil
  3. sinonim & esanlamlilar duplikat: sinonim'dekini esanlamlilar'dan çıkar
  4. esanlamlilar karşılıklı hale getir: A→B varsa ve B sözlükte ise B→A ekle
  5. zit_anlamlilar: yalnız çok kelimeli ve sözlükte hiç çözülemeyen gürültüyü sil
"""
import json, sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace')

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"

with open(DICT_PATH, encoding="utf-8") as f:
    data = json.load(f)

existing = {e["almanca"] for e in data}
entry_map = {e["almanca"]: e for e in data}

# ─── 1. AÇIK YANLIŞ-SENSE ESANLAMLILAR ────────────────────────────────────────
WRONG_SENSE_CLEANUP = {
    # Garage: müzik türleri (yanlış sense — "araç garajı" için)
    "Garage":      {"Garagenrock", "Garage Punk", "Sixties Punk", "Garage Rock"},
    # Getriebe: curcuna/koşturmaca sense (yanlış — "şanzıman" için)
    "Getriebe":    {"Treiben", "pralle Leben", "Hin und Her", "Geschehen", "Umformerelement"},
    # Klimaanlage: havalandırma/aspiratör (yanlış — "klima" için)
    "Klimaanlage": {"Abzug", "Entlüfter", "Dunstabzug"},
    # Kolben: burun jargonu (yanlış — "piston" için)
    "Kolben":      {"Zinken", "Nase", "Riecher", "Riechkolben", "Gesichtserker"},
    # Batterie: birikim/yığın sense (yanlış — "akü" için)
    "Batterie":    {"Ansammlung", "Konzentration"},
    # Zylinder: şekil benzerliği (yanlış — "motor silindiri" için)
    "Zylinder":    {"Laufrad", "Rolle", "Spule", "Trommel", "Walze"},
    # Wartung: eğlence/nafaka anlamı (yanlış — "teknik bakım" için)
    "Wartung":     {"Unterhaltung", "Unterhalt"},
    # Reifen: parça-bütün ilişkisi, eş anlam değil
    "Reifen":      {"Rad"},
}

wrong_removed = 0
for word, bad_set in WRONG_SENSE_CLEANUP.items():
    e = entry_map.get(word)
    if not e:
        continue
    before = list(e.get("esanlamlilar", []))
    after = [r for r in before if r not in bad_set]
    if len(after) != len(before):
        e["esanlamlilar"] = after
        wrong_removed += len(before) - len(after)

# ─── 2. ÇOKLU KELİME (MULTI-WORD) ESANLAMLILAR SİL ───────────────────────────
# Gerçek eş anlamlılar tek kelimedir; "absolut super", "pralle Leben" gibi ifadeler değil
multi_removed_es = 0
multi_removed_zit = 0
for e in data:
    # esanlamlilar
    es = e.get("esanlamlilar", [])
    clean = [r for r in es if " " not in r.strip()]
    if len(clean) != len(es):
        multi_removed_es += len(es) - len(clean)
        e["esanlamlilar"] = clean
    # zit_anlamlilar — multi-word + sözlükte çözülmeyen
    zit = e.get("zit_anlamlilar", [])
    clean_zit = [r for r in zit if " " not in r.strip() or r in existing]
    # Ayrıca yalnız sözlükte olmayan çok kelimeli zıt anlamları da sil
    clean_zit2 = [r for r in clean_zit if " " not in r.strip()]
    if len(clean_zit2) != len(zit):
        multi_removed_zit += len(zit) - len(clean_zit2)
        e["zit_anlamlilar"] = clean_zit2

# ─── 3. SİNONİM & ESANLAMLILAR DUPLIKAT ──────────────────────────────────────
dup_removed = 0
for e in data:
    sin = set(e.get("sinonim", []))
    es  = e.get("esanlamlilar", [])
    if sin and es:
        clean = [r for r in es if r not in sin]
        if len(clean) != len(es):
            dup_removed += len(es) - len(clean)
            e["esanlamlilar"] = clean

# ─── 4. ESANLAMLILAR KARŞILIKLI HALE GETİR ────────────────────────────────────
mutual_added = 0
for e in data:
    word = e.get("almanca", "")
    for r in list(e.get("esanlamlilar", [])):
        target = entry_map.get(r)
        if not target:
            continue
        target_es = target.get("esanlamlilar", [])
        if word not in target_es and word not in target.get("sinonim", []):
            target.setdefault("esanlamlilar", []).append(word)
            mutual_added += 1

# ─── 5. ZIT_ANLAMLILAR: YALNIZ SÖZLÜKTE ÇÖZÜLEN KALSIN ───────────────────────
# (Ölçülü: çözülemeyen kelimeler bilinen Almanca olabilir ama
#  zit_anlamlilar'ın kalitesi zaten düşük, çözülenlerle sınırla)
zit_filtered = 0
for e in data:
    zit = e.get("zit_anlamlilar", [])
    if not zit:
        continue
    clean = [r for r in zit if r in existing]
    if len(clean) != len(zit):
        zit_filtered += len(zit) - len(clean)
        e["zit_anlamlilar"] = clean

# ─── KAYDET ───────────────────────────────────────────────────────────────────
with open(DICT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
with open(JSONL_PATH, "w", encoding="utf-8") as f:
    for entry in data:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# ─── RAPOR ────────────────────────────────────────────────────────────────────
print(f"[1] Yanlış-sense esanlamlilar silindi : {wrong_removed}")
print(f"[2] Multi-word esanlamlilar silindi   : {multi_removed_es}")
print(f"[2] Multi-word zit_anlamlilar silindi : {multi_removed_zit}")
print(f"[3] Sinonim/esanlamlilar duplikat     : {dup_removed}")
print(f"[4] Karşılıklı esanlamlilar eklendi   : {mutual_added}")
print(f"[5] Çözümsüz zit_anlamlilar silindi   : {zit_filtered}")

# Son istatistikler
for field in ["esanlamlilar", "sinonim", "zit_anlamlilar", "antonim"]:
    entries = [e for e in data if e.get(field)]
    total = sum(len(e[field]) for e in entries)
    resolves = sum(1 for e in entries for r in e[field] if r in existing)
    mutual = 0
    for e in entries:
        for r in e[field]:
            t = entry_map.get(r)
            if t and e["almanca"] in t.get(field, []):
                mutual += 1
    pct_res = resolves*100//total if total else 0
    pct_mut = mutual*100//total if total else 0
    print(f"{field:15s}: kayit={len(entries):5d}, ilişki={total:6d}, çözülen={resolves:6d} (%{pct_res}), karşılıklı={mutual:5d} (%{pct_mut})")

# Kontrol
for k in ["Garage","Getriebe","Klimaanlage","Kolben","Batterie","Zylinder","Wartung"]:
    e = entry_map.get(k)
    if e:
        print(f"  {k}: esanlamlilar={e.get('esanlamlilar',[])}")
