#!/usr/bin/env python3
"""
kelime_ailesi'nden yanlış substring eşleşmelerini temizler.
Kural: bir üye, ana kelimeyle MORFOLOJİK bağlantısı olmayan
ama tesadüfen substring olarak geçen kelimeleri çıkar.
Örnek: Verbrennungsmotor → das Verb  (VERBrennung'un ilk 4 harfi)
        Scheibenbremse   → die Eibe  (schEIBEbremse)
        Zylinder         → die Linde (zyLINDEr)
"""
import json, re, sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace')

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"

with open(DICT_PATH, encoding="utf-8") as f:
    data = json.load(f)

# Sözlükteki tüm Almanca kelimeler (küçük harf)
all_words = {e["almanca"].lower() for e in data if e.get("almanca")}


def shared_prefix_len(a, b):
    """İki kelimenin ortak başlangıç uzunluğu"""
    a, b = a.lower(), b.lower()
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return i
    return min(len(a), len(b))


def is_valid_family_member(main_word, member):
    """
    Üye gerçekten kelime ailesiyle ilgili mi?
    Geçerli: ana kelimeden türetilmiş (prefix/suffix paylaşımı), bileşik parçası
    Geçersiz: sadece substring denk düşme (Eibe in Scheibenbremse)
    """
    mw = main_word.lower()
    mem = member.lower()
    # Artikeli çıkar
    mem_bare = re.sub(r'^(der|die|das|den|dem|des)\s+', '', mem).strip()

    if not mem_bare:
        return False

    # 1. Ana kelime üyeyi içeriyorsa ve üye en az 5 harf ise → geçerli (bileşik parça)
    if mem_bare in mw and len(mem_bare) >= 5:
        return True

    # 2. Üye ana kelimeyi içeriyorsa → geçerli (türev)
    if mw in mem_bare:
        return True

    # 3. Ortak prefix en az 5 karakter → geçerli
    if shared_prefix_len(mw, mem_bare) >= 5:
        return True

    # 4. Ana kelime, üyenin çekimli/türev hali olabilir (Wortbildung)
    #    Üyenin kökü ana kelimenin başında/sonunda görünüyorsa → geçerli
    # Örnek: Kupplung → Sattelkupplung (kupplung mevcut)
    if len(mem_bare) > len(mw) and mw in mem_bare:
        return True

    # 5. Üye sözlükte bağımsız kelime olarak geçiyor VE ortak prefix < 4 → şüpheli
    prefix_len = shared_prefix_len(mw, mem_bare)
    if prefix_len < 4 and mem_bare in all_words:
        return False  # Tesadüfi substring

    # 6. Üye çok kısa (3 harf) → genellikle gürültü
    if len(mem_bare) <= 3:
        return False

    return True  # Emin değilsek tut


removed_total = 0
entries_fixed = 0

for entry in data:
    ailesi = entry.get("kelime_ailesi", [])
    if not ailesi:
        continue
    main = entry.get("almanca", "")
    clean = [m for m in ailesi if is_valid_family_member(main, m)]
    removed = len(ailesi) - len(clean)
    if removed > 0:
        entry["kelime_ailesi"] = clean
        removed_total += removed
        entries_fixed += 1

print(f"Çıkarılan gürültülü üye : {removed_total}")
print(f"Etkilenen kayıt         : {entries_fixed}")

with open(DICT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
with open(JSONL_PATH, "w", encoding="utf-8") as f:
    for entry in data:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("Kaydedildi.")
