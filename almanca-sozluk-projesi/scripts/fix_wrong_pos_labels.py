# -*- coding: utf-8 -*-
"""
fix_wrong_pos_labels.py
========================
Yanlış tur (POS) etiketli kayıtları düzeltir.

Sorun: Goethe-Institut kaynaklı bazı kelimeler tur=fiil olarak işaretlenmiş
ama gerçekte sıfat, zarf, edat, zamir vs.

Strateji:
  tur=fiil ama mastar değil (almanca -en/-n ile bitmiyor) → doğru tur'a ata.

Usage:
  python fix_wrong_pos_labels.py [--dry-run]
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent
DICT_PATH = SCRIPTS_DIR.parent / "output" / "dictionary.json"

# Kelime → doğru tur eşlemesi
# (küçük harf, Goethe listesinden tespit edilen yanlış etiketler)
WORD_TO_TUR: dict[str, str] = {
    # Sıfatlar
    "besetzt": "sıfat",
    "eilig": "sıfat",
    "groß": "sıfat",
    "herzlich": "sıfat",
    "jung": "sıfat",
    "kaputt": "sıfat",
    "ledig": "sıfat",
    "lustig": "sıfat",
    "müde": "sıfat",
    "schwer": "sıfat",
    "wunderbar": "sıfat",
    "aufregend": "sıfat",
    "blond": "sıfat",
    "bunt": "sıfat",
    "dumm": "sıfat",
    "echt": "sıfat",
    "fantastisch": "sıfat",
    "faul": "sıfat",
    "fleißig": "sıfat",
    "freundlich": "sıfat",
    "froh": "sıfat",
    "hässlich": "sıfat",
    "klug": "sıfat",
    "komisch": "sıfat",
    "neblig": "sıfat",
    "nervös": "sıfat",
    "praktisch": "sıfat",
    "sauer": "sıfat",
    "schlimm": "sıfat",
    "schmutzig": "sıfat",
    "schrecklich": "sıfat",
    "sonnig": "sıfat",
    "sportlich": "sıfat",
    "stressig": "sıfat",
    "sympathisch": "sıfat",
    "wahrscheinlich": "sıfat",
    "bequeme": "sıfat",
    "bewölkt": "sıfat",
    "eckig": "sıfat",
    "einsam": "sıfat",
    "entspannend": "sıfat",
    "erkältet": "sıfat",
    "fällig": "sıfat",
    "gemütlich": "sıfat",
    "haltbar": "sıfat",
    "hübsch": "sıfat",
    "interkulturell": "sıfat",
    "interkulturelles": "sıfat",
    "langweilig": "sıfat",
    "lecker": "sıfat",
    "merkwürdig": "sıfat",
    "möbliert": "sıfat",
    "neugierig": "sıfat",
    "offenbar": "sıfat",
    "ordentlich": "sıfat",
    "peinlich": "sıfat",
    "schwanger": "sıfat",
    "seltsam": "sıfat",
    "sinnlos": "sıfat",
    "statistisch": "sıfat",
    "unglaublich": "sıfat",
    "unheimlich": "sıfat",
    "vegetarisch": "sıfat",
    "verliebt": "sıfat",
    "verrückt": "sıfat",
    "wahnsinnig": "sıfat",
    "ängstlich": "sıfat",
    "ärgerlich": "sıfat",
    "prima": "sıfat",
    "befreit": "sıfat",
    "begeistert": "sıfat",
    "verpflichtet": "sıfat",
    "warm": "sıfat",
    # Zarflar
    "früher": "zarf",
    "geradeaus": "zarf",
    "immer": "zarf",
    "jetzt": "zarf",
    "lange": "zarf",
    "leider": "zarf",
    "sehr": "zarf",
    "sofort": "zarf",
    "später": "zarf",
    "weiter": "zarf",
    "hoffentlich": "zarf",
    "dabei": "zarf",
    "damals": "zarf",
    "danach": "zarf",
    "deshalb": "zarf",
    "fast": "zarf",
    "gegenüber": "zarf",
    "bereits": "zarf",
    "dafür": "zarf",
    "damit": "zarf",
    "eher": "zarf",
    "falls": "zarf",
    "halbtags": "zarf",
    "indem": "zarf",
    "insgesamt": "zarf",
    "jedoch": "zarf",
    "mittlerweile": "zarf",
    "nebenbei": "zarf",
    "neulich": "zarf",
    "nämlich": "zarf",
    "schließlich": "zarf",
    "seitdem": "zarf",
    "sodass": "zarf",
    "sonst": "zarf",
    "trotzdem": "zarf",
    "umsonst": "zarf",
    "unterwegs": "zarf",
    "voneinander": "zarf",
    "wieso": "zarf",
    "worum": "zarf",
    "während": "zarf",
    "zuerst": "zarf",
    "zuletzt": "zarf",
    "zwar": "zarf",
    "allerdings": "zarf",
    "andererseits": "zarf",
    "abwärts": "zarf",
    "satt": "zarf",
    # Edatlar
    "über": "edat",
    "außer": "edat",
    "hinter": "edat",
    "seit": "edat",
    "statt": "edat",
    # Edatlar (devam)
    "beim": "edat",
    # Yazım hatası / tanımsız
    "radeiser": None,   # tanımlanamayan kelime → sil
    # Bağlaçlar
    "dass": "bağlaç",
    "weil": "bağlaç",
    "wieder": "bağlaç",  # actually more of an adverb but mismapped
    "zwar": "bağlaç",
    # Zamirler
    "euer": "zamir",
    "eine": "zamir",
    "keine": "zamir",
    "meine": "zamir",
    "meiner": "zamir",
    "deinem": "zamir",
    "deiner": "zamir",
    "diesem": "zamir",
    "dieser": "zamir",
    "dieses": "zamir",
    "unsere": "zamir",
    "welchem": "zamir",
    # Selamlama / ünlem
    "hallo": "ünlem",
    "tschüs": "ünlem",
    # Çekimli fiil (sil veya düzelt) - bunlar çekimli, mastar değil
    "scheidt": None,   # scheiden'in çekimi → sil
    "fliegt": None,    # fliegen'in çekimi → sil
    "sollte": None,    # sollen'in çekimi → sil
    "möchte": None,    # mögen'in çekimi → sil
    "täuscht": None,   # täuschen'in çekimi → sil
    "wortet": None,    # worten'in çekimi? → sil
    "zieht": None,     # ziehen'in çekimi → sil
    "zeige": None,     # zeigen'in çekimi → sil
    # Belirsiz/karma - sıfat olabilir
    "viel": "sıfat",
    "wenig": "sıfat",
    "etwas": "zamir",
    "gebadet": "sıfat",
    "gesollt": "sıfat",
    "geehrt": "sıfat",
    "genäht": "sıfat",
    "geparkt": "sıfat",
    "befreit": "sıfat",
    # Kelime kombinasyonları (birden fazla biçim)
    "große": "sıfat",
    "großes": "sıfat",
    "gute": "sıfat",
    "klare": "sıfat",
    "warme": "sıfat",
    "trockenes": "sıfat",
    "starker": "sıfat",
    "letzter": "sıfat",
    "offenem": "sıfat",
    "genannte": "sıfat",
    "private": "sıfat",
}

# Zarf ayrı tekrar (duplicate key sorununu önlemek için)
WORD_TO_TUR.update({
    "wieder": "zarf",
})


def main(dry_run: bool = False) -> None:
    with open(DICT_PATH, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Toplam kayıt: {len(data)}")

    fixed = 0
    deleted = 0
    to_remove: set[int] = set()

    for r in data:
        tur = r.get("tur", "")
        if tur != "fiil":
            continue

        w = r.get("almanca", "").strip()
        w_lower = w.lower()

        # Mastar mı? → dokunma
        if w_lower.endswith(("en", "n")) or w.startswith("("):
            continue

        if w_lower in WORD_TO_TUR:
            new_tur = WORD_TO_TUR[w_lower]
            if new_tur is None:
                # Çekimli form → sil
                print(f"  [SİL] {w!r} → çekimli form, siliniyor")
                to_remove.add(id(r))
                deleted += 1
            else:
                print(f"  [DÜZELT] {w!r}: fiil → {new_tur}")
                if not dry_run:
                    r["tur"] = new_tur
                fixed += 1
        else:
            # Listeye eklenmemiş — ekrana yaz, ama dokunma
            print(f"  [ATLANDI] {w!r} (tur=fiil, mastar değil, listede yok)")

    new_data = [r for r in data if id(r) not in to_remove]

    print(f"\n{'='*60}")
    print(f"Düzeltilen tur etiketi: {fixed}")
    print(f"Silinen çekimli form:   {deleted}")
    print(f"Yeni kayıt sayısı:      {len(new_data)}")

    if not dry_run:
        with open(DICT_PATH, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        print(f"Kaydedildi: {DICT_PATH}")
    else:
        print("[DRY RUN — dosya değiştirilmedi]")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
