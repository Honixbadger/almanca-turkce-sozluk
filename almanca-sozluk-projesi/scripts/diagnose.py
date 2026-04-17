import json, sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace')

with open('almanca-sozluk-projesi/output/dictionary.json', encoding='utf-8') as f:
    data = json.load(f)

# 1. ornek_almanca / ornek_turkce senkron sorunu
mismatch = 0
both_filled = 0
for e in data:
    oa = e.get('ornek_almanca', '')
    ot = e.get('ornek_turkce', '')
    ornekler = e.get('ornekler', [])
    if oa and ot:
        both_filled += 1
        if ornekler:
            ilk_de = ornekler[0].get('almanca', '')
            ilk_tr = ornekler[0].get('turkce', '')
            if oa != ilk_de or (ilk_tr and ot != ilk_tr):
                mismatch += 1

print(f"Her ikisi dolu: {both_filled}")
print(f"Uyumsuz cift  : {mismatch}")

# Zylinder
e = next(x for x in data if x.get('almanca') == 'Zylinder')
print("\n=== Zylinder ===")
print(f"  ornek_almanca: {e.get('ornek_almanca', '')[:80]}")
print(f"  ornek_turkce : {e.get('ornek_turkce', '')[:60]}")
for i, o in enumerate(e.get('ornekler', [])[:3]):
    de = o.get('almanca', '')[:70]
    tr = o.get('turkce', '')[:50]
    print(f"  ornekler[{i}]: {de} | {tr}")

# Kalan kırpık örnekleri say
fragment = 0
citation = 0
for e in data:
    for o in e.get('ornekler', []):
        s = o.get('almanca', '')
        if not s:
            continue
        if '\u2191' in s or ('ISBN' in s):
            citation += 1
        words = s.split()
        if len(words) < 5 and not any(s.endswith(p) for p in ['.','!','?']):
            fragment += 1

print(f"\nKalan kırpık fragment : {fragment}")
print(f"Kalan citation artığı : {citation}")

# Verbrennungsmotor kelime_ailesi
e = next((x for x in data if x.get('almanca') == 'Verbrennungsmotor'), None)
if e:
    print(f"\nVerbrennungsmotor kelime_ailesi: {e.get('kelime_ailesi', [])}")

# Reifen kelime_ailesi
e = next((x for x in data if x.get('almanca') == 'Reifen'), None)
if e:
    print(f"Reifen kelime_ailesi: {e.get('kelime_ailesi', [])}")
