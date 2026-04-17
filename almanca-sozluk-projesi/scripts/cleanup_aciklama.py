#!/usr/bin/env python3
"""
aciklama_turkce alanındaki "Almanca tanım -> Türkçe karşılık" formatını düzeltir.
-> işaretinden sonraki kısmı alır, boşsa alanı siler.
"""
import json, sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace')

DICT_PATH  = "almanca-sozluk-projesi/output/dictionary.json"
JSONL_PATH = "almanca-sozluk-projesi/output/dictionary.jsonl"

with open(DICT_PATH, encoding="utf-8") as f:
    data = json.load(f)

fixed = 0
cleared = 0

for entry in data:
    val = entry.get("aciklama_turkce", "")
    if not val or "->" not in val:
        continue

    # "Almanca tanım -> Türkçe karşılık" → Türkçe kısmı al
    parts = val.split("->", 1)
    tr_part = parts[1].strip() if len(parts) > 1 else ""

    if tr_part and len(tr_part) > 2:
        entry["aciklama_turkce"] = tr_part
        fixed += 1
    else:
        # -> sonrası boşsa alanı temizle
        del entry["aciklama_turkce"]
        cleared += 1

print(f"Düzeltilen (-> sonrası alındı) : {fixed}")
print(f"Temizlenen (boş içerik)        : {cleared}")

with open(DICT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
with open(JSONL_PATH, "w", encoding="utf-8") as f:
    for entry in data:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("Kaydedildi.")
