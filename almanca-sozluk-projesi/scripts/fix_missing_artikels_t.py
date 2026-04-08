"""
T ile biten isimlerin eksik artikellerini düzeltir.
101 kelime tespit edildi, hepsi manuel olarak doğrulandı.
"""
import json
import shutil
from pathlib import Path

JSONL_PATH = Path("C:/Users/ozan/Desktop/almanca sözlük projesi/Playground-Yedek/almanca-sozluk-projesi/output/dictionary.jsonl")

# Manuel doğrulanmış artikel tablosu
ARTIKEL_MAP = {
    # -licht bileşimleri → das
    "Abblendlicht": "das",
    "Kurvenlicht":  "das",
    "Nordlicht":    "das",
    "Polarlicht":   "das",
    "Sonnenlicht":  "das",
    "Licht":        "das",

    # -gerät bileşimleri → das
    "ABS-Steuergerät":  "das",
    "Motorsteuergerät": "das",
    "Elektrogerät":     "das",
    "Gerät":            "das",

    # -konzept → das
    "Betriebskonzept":  "das",
    "Sicherheitskonzept": "das",

    # -gebiet → das
    "Betriebsgebiet": "das",
    "Gebiet":         "das",

    # -keit / -igkeit → die
    "Kühlflüssigkeit": "die",

    # -management → das
    "Verkehrsmanagement": "das",

    # -boot → das
    "Boot":        "das",
    "Motorboot":   "das",
    "Unterseeboot": "das",

    # -gebet / -gebot → das
    "Gebot":          "das",
    "Freitagsgebet":  "das",

    # Diğer bileşikler
    "Gefährt":              "das",
    "Baugerüst":            "das",
    "Sprichwort":           "das",
    "Fahrverbot":           "das",
    "Überholverbot":        "das",
    "Armaturenbrett":       "das",
    "Trägheitsmoment":      "das",
    "Verfahrensrecht":      "das",
    "Flächenbombardement":  "das",

    # -heit → die
    "Freiheit": "die",
    "Hoheit":   "die",

    # -at (Heimat) → die
    "Heimat": "die",

    # Tekil basit kelimeler
    "Insekt": "das",
    "Ticket": "das",
    "Bot":    "der",   # internet/yazılım botu
    "Abt":    "der",   # başrahip
    "Rot":    "das",   # renk
    "Rat":    "der",   # tavsiye / konsey
    "Amt":    "das",
    "Gut":    "das",
    "Bit":    "das",
    "Takt":   "der",
    "Hiat":   "der",   # dilbilim
    "Blut":   "das",
    "Fett":   "das",
    "Gift":   "das",
    "Gast":   "der",
    "Diät":   "die",
    "Nest":   "das",
    "Wort":   "das",
    "Bett":   "das",
    "Obst":   "das",
    "Fest":   "das",
    "Watt":   "das",   # birim
    "Volt":   "das",   # birim
    "Beet":   "das",   # çiçek tarhı
    "Argot":  "das",
    "Blatt":  "das",
    "Haupt":  "das",
    "Sucht":  "die",
    "Kraft":  "die",
    "Achat":  "der",   # taş
    "Sicht":  "die",
    "Flint":  "der",   # çakmaktaşı
    "Paket":  "das",
    "Quant":  "das",   # kuantum (fizik)
    "Zitat":  "das",
    "Kraut":  "das",
    "Astat":  "das",   # kimyasal element (astatin)
    "Brett":  "das",
    "Limit":  "das",
    "Depot":  "das",
    "Filet":  "das",
    "Bidet":  "das",
    "Karat":  "das",
    "Opiat":  "das",
    "Gilet":  "das",   # yelek
    "Qubit":  "das",
    "Ablaut": "der",   # dilbilim
    "Aorist": "der",   # dilbilim
    "Sonant": "der",   # dilbilim
    "Aktant": "der",   # dilbilim
    "Anlaut": "der",   # dilbilim (kelime başı ses)
    "Aspekt": "der",
    "Inlaut": "der",   # dilbilim (kelime içi ses)
    "Talent": "das",
    "Jogurt": "der",
    "Oberst": "der",   # albay
    "Moment": "der",   # an (zaman); fizik → das, ama genel kullanım der
    "Plakat": "das",
    "Jetset": "der",
    "Fagott": "das",   # fagot (müzik aleti)
    "Kuvert": "das",   # zarf
    "Skript": "das",
    "Objekt": "das",
    "Kobalt": "das",   # kobalt elementi
}


def main():
    # Yedek al
    backup = JSONL_PATH.with_suffix(".jsonl.bak_artikel")
    shutil.copy2(JSONL_PATH, backup)
    print(f"Yedek: {backup}")

    lines_out = []
    fixed = 0
    skipped = []

    with open(JSONL_PATH, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            word = entry.get("almanca", "")
            tur  = entry.get("tur", "")
            art  = entry.get("artikel", "")

            if word.endswith("t") and tur == "isim" and not art:
                if word in ARTIKEL_MAP:
                    entry["artikel"] = ARTIKEL_MAP[word]
                    fixed += 1
                else:
                    skipped.append(word)

            lines_out.append(json.dumps(entry, ensure_ascii=False))

    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines_out) + "\n")

    print(f"\nDüzeltilen: {fixed}")
    if skipped:
        print(f"Atlanılan (lookup'ta yok): {skipped}")
    else:
        print("Tüm eksikler giderildi.")


if __name__ == "__main__":
    main()
