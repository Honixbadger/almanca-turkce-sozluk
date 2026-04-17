#!/usr/bin/env python3
"""
import_xlsx_sozluk.py
=====================
sozluk.xlsx dosyasındaki üç sayfayı sözlüğe aktarır:
  - Kalip_Listesi   → fiil_kaliplari, ornekler, valenz, çekim formları
  - Kalip_Adaylari  → fiil_kaliplari (ek kalıplar)
  - Semantik_Destek → sinonim
"""
from __future__ import annotations
import json, re, sys, unicodedata
import openpyxl
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATH = PROJECT_ROOT / "output" / "dictionary.json"
XLSX_PATH = Path(r"C:\Users\ozan\Documents\Playground\sozluk.xlsx")
SOURCE = "sozluk.xlsx (manuel kurulmuş, DWDS destekli)"
MAX_ORNEKLER = 7
MAX_SYN = 20


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().casefold()


def strip_art(w: str) -> str:
    p = w.strip().split(" ", 1)
    return p[1] if len(p) == 2 and norm(p[0]) in {"der", "die", "das"} else w.strip()


def clean(v) -> str:
    return str(v).strip() if v is not None else ""


def parse_cekim(ozet: str) -> dict:
    result = {}
    if not ozet:
        return result
    for part in ozet.split("|"):
        part = part.strip()
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        k, v = k.strip().casefold(), v.strip()
        if "prät" in k or "pret" in k:
            result["prateritum"] = v
        elif "partizip" in k:
            result["partizip2"] = v
        elif "perfekt" in k:
            vl = v.casefold()
            result["perfekt_yardimci"] = "sein" if "sein" in vl else "haben"
        elif "tür" in k or "type" in k:
            vl = v.casefold()
            for t in ("stark", "schwach", "gemischt", "modal"):
                if t in vl:
                    result["verb_typ"] = t
                    break
    return result


def read_rows(ws) -> tuple[list[str], list[dict]]:
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], []
    header = [clean(c) for c in rows[0]]
    data = []
    for row in rows[1:]:
        r = {header[i]: clean(row[i]) for i in range(min(len(header), len(row)))}
        data.append(r)
    return header, data


def main() -> None:
    print("=" * 60)
    print("import_xlsx_sozluk.py — sozluk.xlsx → dictionary.json")
    print("=" * 60)

    wb = openpyxl.load_workbook(str(XLSX_PATH), data_only=True)

    # ── Kalip_Listesi ─────────────────────────────────────────
    print("\n[1/4] Kalip_Listesi okunuyor...")
    _, kl_rows = read_rows(wb["Kalip_Listesi"])
    kalip_data: dict[str, dict] = {}
    for r in kl_rows:
        lemma = r.get("Lemma", "").strip()
        if not lemma:
            continue
        key = norm(strip_art(lemma))
        entry = kalip_data.setdefault(key, {
            "lemma": lemma, "kaliplar": [], "ornekler": [], "valenz": "", "cekim": {}
        })
        for n in ["1", "2", "3"]:
            kde = r.get(f"Kalıp {n} (DE)", "")
            ktr = r.get(f"Kalıp {n} (TR)", "")
            ode = r.get(f"Kalıp {n} Örnek (DE)", "")
            otr = r.get(f"Kalıp {n} Örnek (TR)", "")
            if kde:
                entry["kaliplar"].append({
                    "kalip_de": kde, "kalip_tr": ktr,
                    "ornek_de": ode, "ornek_tr": otr
                })
        for n in ["1", "2"]:
            ode = r.get(f"Genel Örnek {n} (DE)", "")
            otr = r.get(f"Genel Örnek {n} (TR)", "")
            if ode:
                entry["ornekler"].append((ode, otr))
        if r.get("Valenz", ""):
            entry["valenz"] = r["Valenz"]
        if r.get("Çekim Özeti", ""):
            entry["cekim"] = parse_cekim(r["Çekim Özeti"])
    print(f"  {len(kalip_data)} benzersiz fiil.")

    # ── Kalip_Adaylari ────────────────────────────────────────
    print("\n[2/4] Kalip_Adaylari okunuyor...")
    _, ka_rows = read_rows(wb["Kalip_Adaylari"])
    extra_kalip: dict[str, list] = {}
    for r in ka_rows:
        lemma = r.get("Lemma", "").strip()
        kde = r.get("Kalıp (DE)", "")
        if not lemma or not kde:
            continue
        key = norm(strip_art(lemma))
        extra_kalip.setdefault(key, []).append({
            "kalip_de": kde,
            "kalip_tr": r.get("Kalıp (TR)", ""),
            "ornek_de": r.get("Örnek (DE)", ""),
            "ornek_tr": r.get("Örnek (TR)", ""),
        })
    print(f"  {len(extra_kalip)} fiil için ek kalıp.")

    # ── Semantik_Destek ───────────────────────────────────────
    print("\n[3/4] Semantik_Destek okunuyor...")
    _, sd_rows = read_rows(wb["Semantik_Destek"])
    sem_data: dict[str, list] = {}
    for r in sd_rows:
        lemma = r.get("Lemma", "").strip()
        syns_raw = r.get("OpenThesaurus Eş Anlamlılar", "")
        if not lemma or not syns_raw:
            continue
        syns = [s.strip() for s in re.split(r"[;,]", syns_raw)
                if s.strip() and len(s.strip()) <= 60]
        sem_data[norm(strip_art(lemma))] = syns
    print(f"  {len(sem_data)} fiil için eş anlamlı.")

    # ── Sözlüğe uygula ────────────────────────────────────────
    print("\n[4/4] Sözlük güncelleniyor...")
    dictionary: list[dict] = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(dictionary):,} kayıt yüklendi.")

    idx_map: dict[str, int] = {}
    for i, rec in enumerate(dictionary):
        w = (rec.get("almanca") or "").strip()
        if w:
            idx_map[norm(w)] = i
            idx_map[norm(strip_art(w))] = i

    c_updated = c_kalip = c_ornek = c_valenz = c_cekim = c_syn = 0

    # Kalip_Listesi + Kalip_Adaylari → fiil_kaliplari, ornekler, valenz, çekim
    for key, data in kalip_data.items():
        i = idx_map.get(key)
        if i is None:
            continue
        rec = dictionary[i]
        changed = False

        # fiil_kaliplari
        existing_k: list[dict] = list(rec.get("fiil_kaliplari") or [])
        existing_kn = {norm(k.get("kalip_de", "")) for k in existing_k}
        all_kaliplar = list(data["kaliplar"])
        for ek in extra_kalip.get(key, []):
            en = norm(ek["kalip_de"])
            if en and en not in {norm(k["kalip_de"]) for k in all_kaliplar}:
                all_kaliplar.append(ek)
        for k in all_kaliplar:
            kn = norm(k["kalip_de"])
            if kn and kn not in existing_kn:
                existing_k.append({
                    "kalip": k["kalip_de"], "turkce": k["kalip_tr"],
                    "ornek_almanca": k["ornek_de"], "ornek_turkce": k["ornek_tr"],
                    "kaynak": SOURCE,
                })
                existing_kn.add(kn)
                c_kalip += 1
                changed = True
        if changed:
            rec["fiil_kaliplari"] = existing_k

        # ornekler (genel örnekler)
        existing_ex: list[dict] = list(rec.get("ornekler") or [])
        existing_en = {o.get("almanca", "").strip() for o in existing_ex}
        for ode, otr in data["ornekler"]:
            if ode and ode not in existing_en and len(existing_ex) < MAX_ORNEKLER:
                existing_ex.append({"almanca": ode, "turkce": otr, "kaynak": SOURCE})
                existing_en.add(ode)
                c_ornek += 1
                changed = True
                if not rec.get("ornek_almanca", "").strip():
                    rec["ornek_almanca"] = ode
                if not rec.get("ornek_turkce", "").strip() and otr:
                    rec["ornek_turkce"] = otr
        if c_ornek:
            rec["ornekler"] = existing_ex

        # valenz
        if data["valenz"] and not rec.get("valenz"):
            rec["valenz"] = [data["valenz"]]
            c_valenz += 1
            changed = True

        # çekim formları
        ck = data["cekim"]
        if ck.get("prateritum") and not rec.get("prateritum", "").strip():
            rec["prateritum"] = ck["prateritum"]
            c_cekim += 1
            changed = True
        if ck.get("partizip2") and not rec.get("partizip2", "").strip():
            rec["partizip2"] = ck["partizip2"]
            changed = True
        if ck.get("perfekt_yardimci") and not rec.get("perfekt_yardimci", "").strip():
            rec["perfekt_yardimci"] = ck["perfekt_yardimci"]
            changed = True
        if ck.get("verb_typ") and not rec.get("verb_typ", "").strip():
            rec["verb_typ"] = ck["verb_typ"]
            changed = True

        if changed:
            src = rec.get("kaynak") or ""
            if "sozluk.xlsx" not in src:
                rec["kaynak"] = (src + "; " + SOURCE).lstrip("; ")
            c_updated += 1

    # Semantik_Destek → sinonim
    for key, syns in sem_data.items():
        i = idx_map.get(key)
        if i is None:
            continue
        rec = dictionary[i]
        existing_s: list[str] = list(rec.get("sinonim") or [])
        en = {norm(x) for x in existing_s}
        added = 0
        for s in syns:
            ns = norm(s)
            if ns and ns not in en and len(existing_s) < MAX_SYN:
                existing_s.append(s)
                en.add(ns)
                added += 1
        if added:
            rec["sinonim"] = existing_s
            c_syn += added

    DICT_PATH.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Özet
    verbs = [r for r in dictionary if (r.get("tur") or "").casefold() in {"fiil", "verb"}]
    tv = len(verbs)
    has_kalip  = sum(1 for r in verbs if r.get("fiil_kaliplari"))
    has_valenz = sum(1 for r in verbs if r.get("valenz"))

    print(f"\n{'='*60}")
    print("SONUÇ")
    print(f"  Güncellenen kayıt        : {c_updated:,}")
    print(f"  Eklenen kalıp            : {c_kalip:,}")
    print(f"  Eklenen örnek cümle      : {c_ornek:,}")
    print(f"  Eklenen valenz           : {c_valenz:,}")
    print(f"  Eklenen çekim formu      : {c_cekim:,}")
    print(f"  Eklenen eş anlamlı       : {c_syn:,}")
    print()
    print(f"  fiil_kaliplari dolu      : {has_kalip:,} / {tv:,}  (%{100*has_kalip//max(tv,1)})")
    print(f"  valenz dolu              : {has_valenz:,} / {tv:,}  (%{100*has_valenz//max(tv,1)})")
    print(f"{'='*60}")
    print(f"\nKaydedildi: {DICT_PATH}")


if __name__ == "__main__":
    main()
