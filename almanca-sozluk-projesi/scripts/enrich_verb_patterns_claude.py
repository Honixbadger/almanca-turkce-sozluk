#!/usr/bin/env python3
"""
enrich_verb_patterns_claude.py
================================
Sözlükteki fiil_kaliplari eksik olan fiiller için Claude API üzerinden
Almanca valenz kalıpları (Valenzmuster) üretir ve ekler.

Her fiil için 3 tipik kullanım kalıbı + Türkçe açıklama alır.
Format: {"kalip": "auf etw. (A) achten", "turkce": "-e dikkat etmek", ...}

Kullanım:
  python scripts/enrich_verb_patterns_claude.py
  python scripts/enrich_verb_patterns_claude.py --limit 50   # test
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import anthropic
except ImportError:
    print("HATA: 'pip install anthropic' komutuyla paketi kurun.")
    sys.exit(1)

import argparse

PROJECT_ROOT  = Path(__file__).resolve().parents[1]
DICT_PATH     = PROJECT_ROOT / "output" / "dictionary.json"
CHECKPOINT    = PROJECT_ROOT / "output" / "verb_patterns_claude_checkpoint.json"
SETTINGS_PATH = PROJECT_ROOT / "data" / "manual" / "desktop_settings.json"

MODEL         = "claude-haiku-4-5-20251001"   # En ucuz, hızlı
MAX_PATTERNS  = 3
BATCH_SAVE    = 30
SOURCE        = "Claude Haiku (otomatik kalıp)"

SYSTEM_PROMPT = (
    "Sen Almanca dilbilgisi uzmanısın. "
    "Almanca fiillerin valenz yapılarını (Ergänzungsrahmen / Valenzmuster) biliyorsun. "
    "Sadece istenen formatta cevap ver, başlık veya açıklama ekleme."
)

USER_TEMPLATE = """\
Almanca fiil: "{verb}"{hint}

Bu fiilin en yaygın {n} kullanım kalıbını listele.
Her satırda: ALMANCA_KALIP | TÜRKÇE_AÇIKLAMA

Kısaltmalar:
  jd.  = jemand (biri, Nom)
  jdn. = jemanden (birini, Akk)
  jdm. = jemandem (birine, Dat)
  etw. (A) = etwas Akkusativ (bir şeyi)
  etw. (D) = etwas Dativ (bir şeye)
  irgendwo   = bir yerde (Dat)
  irgendwohin = bir yere (Akk)

Örnek format:
  etw. kaufen | bir şey satın almak
  jdm. etw. kaufen | birine bir şey satın almak

Sadece kalıpları yaz:"""


def load_api_key() -> str:
    key = ""
    if SETTINGS_PATH.exists():
        try:
            s = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            key = str(s.get("claude_api_key") or "").strip()
        except Exception:
            pass
    if not key:
        import os
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    return key


def load_checkpoint() -> set[str]:
    if CHECKPOINT.exists():
        try:
            return set(json.loads(CHECKPOINT.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def save_checkpoint(done: set[str]) -> None:
    CHECKPOINT.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")


def generate_patterns(client: anthropic.Anthropic, verb: str, turkce: str) -> list[dict]:
    hint = f' (Türkçe: "{turkce}")' if turkce else ""
    prompt = USER_TEMPLATE.format(verb=verb, hint=hint, n=MAX_PATTERNS)

    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        response = msg.content[0].text.strip()
    except anthropic.RateLimitError:
        print("  Rate limit — 30s bekleniyor...", flush=True)
        time.sleep(30)
        return []
    except anthropic.APIError as e:
        print(f"  API hatası: {e}", flush=True)
        return []

    patterns: list[dict] = []
    seen: set[str] = set()
    for line in response.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        # Numaralı satır temizle: "1. etw. kaufen | ..." → "etw. kaufen | ..."
        line = re.sub(r"^\d+[.)]\s*", "", line)
        parts = line.split("|", 1)
        if len(parts) != 2:
            continue
        kalip_de = parts[0].strip()
        kalip_tr = parts[1].strip()
        if not kalip_de or not kalip_tr:
            continue
        if len(kalip_de) > 120 or len(kalip_tr) > 120:
            continue
        key = kalip_de.casefold()
        if key in seen:
            continue
        seen.add(key)
        patterns.append({
            "kalip": kalip_de,
            "turkce": kalip_tr,
            "ornek_almanca": "",
            "ornek_turkce": "",
            "kaynak": SOURCE,
        })
        if len(patterns) >= MAX_PATTERNS:
            break

    return patterns


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="İşlenecek max fiil sayısı (test için)")
    parser.add_argument("--min-existing", type=int, default=2,
                        help="Kaç kalıbı olanlara dokunma (varsayılan: 2)")
    args = parser.parse_args()

    print("=" * 65)
    print("enrich_verb_patterns_claude.py — Claude Haiku ile Fiil Kalıbı")
    print(f"Model: {MODEL}")
    print("=" * 65)

    api_key = load_api_key()
    if not api_key:
        print("HATA: Claude API anahtarı bulunamadı.")
        print("desktop_settings.json içine 'claude_api_key' ekleyin")
        print("veya ANTHROPIC_API_KEY ortam değişkenini ayarlayın.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    dictionary: list[dict] = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(dictionary):,} kayıt yüklendi.")

    done = load_checkpoint()
    print(f"  Checkpoint: {len(done)} fiil daha önce işlendi.")

    # Hedef: fiil_kaliplari eksik veya az olan fiiller
    targets: list[tuple[int, dict]] = []
    for i, rec in enumerate(dictionary):
        tur = (rec.get("tur") or "").strip().casefold()
        if tur not in {"fiil", "verb"}:
            continue
        almanca = (rec.get("almanca") or "").strip()
        if not almanca or almanca in done:
            continue
        kaliplar = rec.get("fiil_kaliplari") or []
        if len(kaliplar) >= args.min_existing:
            continue
        targets.append((i, rec))

    if args.limit:
        targets = targets[:args.limit]

    print(f"  İşlenecek fiil: {len(targets):,}")
    print()

    updated = 0
    skipped = 0

    for task_num, (dict_idx, rec) in enumerate(targets, start=1):
        almanca = (rec.get("almanca") or "").strip()
        turkce  = (rec.get("turkce") or "").strip()
        existing: list[dict] = list(rec.get("fiil_kaliplari") or [])
        existing_keys = {(k.get("kalip") or "").strip().casefold() for k in existing}

        print(f"[{task_num}/{len(targets)}] {almanca}", flush=True)

        patterns = generate_patterns(client, almanca, turkce)
        if not patterns:
            print("  Kalıp üretilemedi.", flush=True)
            skipped += 1
            done.add(almanca)
            continue

        added = 0
        for p in patterns:
            kn = p["kalip"].strip().casefold()
            if kn and kn not in existing_keys:
                existing.append(p)
                existing_keys.add(kn)
                added += 1
                print(f"  + {p['kalip']} | {p['turkce']}", flush=True)

        if added:
            dictionary[dict_idx]["fiil_kaliplari"] = existing
            updated += 1

        done.add(almanca)

        if task_num % BATCH_SAVE == 0:
            DICT_PATH.write_text(
                json.dumps(dictionary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            save_checkpoint(done)
            print(f"  [Checkpoint: {updated} fiil güncellendi]", flush=True)

    # Son kayıt
    DICT_PATH.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    save_checkpoint(done)

    verbs = [r for r in dictionary if (r.get("tur") or "").casefold() in {"fiil", "verb"}]
    has_kalip = sum(1 for r in verbs if r.get("fiil_kaliplari"))

    print(f"\n{'=' * 65}")
    print("SONUÇ")
    print(f"  İşlenen fiil          : {len(targets):,}")
    print(f"  Güncellenen           : {updated:,}")
    print(f"  Kalıp üretilemedi     : {skipped:,}")
    print(f"  fiil_kaliplari dolu   : {has_kalip:,} / {len(verbs):,}  (%{100*has_kalip//max(len(verbs),1)})")
    print(f"{'=' * 65}")
    print(f"\nKaydedildi: {DICT_PATH}")


if __name__ == "__main__":
    main()
