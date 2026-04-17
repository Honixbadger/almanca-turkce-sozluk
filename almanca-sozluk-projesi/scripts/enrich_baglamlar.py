"""
enrich_baglamlar.py
-------------------
Groq API kullanarak sözlük kayitlarina baglamsal kullanim örnekleri ekler.

Her hedef kayit için ONE API çagrisi yapilir; yanit dogrudan JSON formatinda
istenir. Elde edilen "baglamlar" listesi kayda eklenir.

Kullanim:
    python enrich_baglamlar.py --api-key YOUR_GROQ_KEY [secenekler]

Seçenekler:
    --api-key       Zorunlu. Groq API anahtari.
    --model         Kullanilacak model (varsayilan: llama-3.1-8b-instant)
    --limit         Islenecek maksimum kayit sayisi (varsayilan: 100)
    --min-zipf      Minimum Zipf skoru filtreleme icin (varsayilan: 4.0)
    --dry-run       API çagrisi yapmadan simüle eder
    --overwrite     Zaten "baglamlar" alani olan kayitlari da yeniden isle
"""

from __future__ import annotations

import argparse
import json
import time
import sys
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Yollar
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DICT_PATH = BASE_DIR / "output" / "dictionary.json"
CHECKPOINT_PATH = BASE_DIR / "output" / "baglamlar_checkpoint.json"

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "llama-3.1-8b-instant"
DEFAULT_LIMIT = 100
DEFAULT_MIN_ZIPF = 4.0
RATE_LIMIT_PER_MIN = 20          # istek/dakika
SAVE_EVERY = 10                  # kayit araliginda kaydet
ALL_KATEGORILER = ["günlük", "iş", "sosyal", "eğitim", "seyahat"]

# ---------------------------------------------------------------------------
# Groq istemcisi
# ---------------------------------------------------------------------------

def get_groq_client(api_key: str):
    """groq paketini içe aktar ve istemci döndür."""
    try:
        from groq import Groq  # type: ignore
    except ImportError:
        print("[HATA] 'groq' paketi bulunamadi. Lütfen kurun: pip install groq")
        sys.exit(1)
    return Groq(api_key=api_key)


# ---------------------------------------------------------------------------
# Yardimci fonksiyonlar
# ---------------------------------------------------------------------------

def load_dictionary() -> list[dict]:
    if not DICT_PATH.exists():
        print(f"[HATA] Sözlük dosyasi bulunamadi: {DICT_PATH}")
        sys.exit(1)
    with open(DICT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = list(data.values())
    print(f"[BİLGİ] Sözlük yüklendi: {len(data)} kayit")
    return data


def save_dictionary(data: list[dict]) -> None:
    """Disk'teki güncel dosyayı okuyup sadece baglamlar değişikliklerini uygular."""
    try:
        disk_data = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    except Exception:
        disk_data = data
    disk_idx = {str(e.get("almanca", "")): e for e in disk_data}
    for mem_entry in data:
        key = str(mem_entry.get("almanca", ""))
        disk_entry = disk_idx.get(key)
        if disk_entry is None:
            continue
        if mem_entry.get("baglamlar") and not disk_entry.get("baglamlar"):
            disk_entry["baglamlar"] = mem_entry["baglamlar"]
    DICT_PATH.write_text(json.dumps(disk_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def load_checkpoint() -> dict[str, Any]:
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_checkpoint(checkpoint: dict[str, Any]) -> None:
    CHECKPOINT_PATH.write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_target_entry(entry: dict, min_zipf: float, overwrite: bool) -> bool:
    """Kayitin hedef olup olmadigini belirle."""
    # Zaten baglamlar varsa ve --overwrite yoksa atla
    if not overwrite and entry.get("baglamlar"):
        return False

    # Yüksek frekanslilara öncelik ver
    zipf = entry.get("zipf_skoru")
    seviye = str(entry.get("seviye") or "").strip().upper()
    ornekler = entry.get("ornekler") or []

    if zipf is not None:
        try:
            if float(zipf) >= min_zipf:
                return True
        except (TypeError, ValueError):
            pass

    if seviye in ("A1", "A2", "B1"):
        return True

    # Zaten örnekleri olan kayitlar
    if ornekler:
        return True

    return False


def choose_kategoriler(entry: dict) -> list[str]:
    """Kelime türüne göre uygun baglamlar seç."""
    tur = str(entry.get("tur") or "").strip().lower()
    kategoriler = list(ALL_KATEGORILER)

    # Fiiller için seyahat, günlük, iş; isimler için tümü uygun
    if tur in ("fiil", "verb"):
        return ["günlük", "iş", "seyahat"]
    if tur in ("isim", "noun", "substantiv"):
        return ["günlük", "iş", "sosyal"]
    if tur in ("sifat", "adjektiv", "adjective"):
        return ["günlük", "sosyal", "eğitim"]
    return kategoriler[:3]


def build_prompt(entry: dict, kategoriler: list[str]) -> str:
    almanca = entry.get("almanca") or ""
    turkce = entry.get("turkce") or ""
    tur = entry.get("tur") or "kelime"
    kat_str = ", ".join(kategoriler)

    kat_json_example = json.dumps(
        [
            {
                "kategori": k,
                "cumleler": [
                    {"de": "...", "tr": "..."},
                    {"de": "...", "tr": "..."},
                ],
            }
            for k in kategoriler
        ],
        ensure_ascii=False,
        indent=2,
    )

    return f"""Almanca kelime: "{almanca}" ({tur}) - Türkçe: "{turkce}"

Bu kelime için {len(kategoriler)} farklı bağlamda ({kat_str}) kısa, doğal Almanca cümleler ve Türkçe çevirileri yaz.
Her bağlam için 2 cümle ekle. Cümleler günlük dilde kullanılan, orta zorlukta olsun.

SADECE aşağıdaki JSON formatında yanıt ver, başka hiçbir şey yazma:
{{
  "baglamlar": {kat_json_example}
}}"""


def parse_baglamlar_response(text: str) -> list[dict] | None:
    """API yanit metninden baglamlar listesini çikart."""
    # Önce direkt JSON parse dene
    try:
        obj = json.loads(text.strip())
        baglamlar = obj.get("baglamlar")
        if isinstance(baglamlar, list):
            return baglamlar
    except json.JSONDecodeError:
        pass

    # Markdown kod blogu içinde JSON aramayı dene
    code_block = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if code_block:
        try:
            obj = json.loads(code_block.group(1).strip())
            baglamlar = obj.get("baglamlar")
            if isinstance(baglamlar, list):
                return baglamlar
        except json.JSONDecodeError:
            pass

    # Ham JSON blogu bul
    brace_match = re.search(r'\{[\s\S]*"baglamlar"[\s\S]*\}', text)
    if brace_match:
        try:
            obj = json.loads(brace_match.group(0))
            baglamlar = obj.get("baglamlar")
            if isinstance(baglamlar, list):
                return baglamlar
        except json.JSONDecodeError:
            pass

    return None


def validate_baglamlar(baglamlar: list[dict]) -> list[dict]:
    """Beklenmedik yapilari temizle; sadece gecerli kategorileri sakla."""
    valid = []
    for item in baglamlar:
        if not isinstance(item, dict):
            continue
        kat = item.get("kategori")
        cumleler = item.get("cumleler")
        if not kat or not isinstance(cumleler, list):
            continue
        clean_cumleler = []
        for c in cumleler:
            if isinstance(c, dict) and c.get("de") and c.get("tr"):
                clean_cumleler.append({"de": c["de"], "tr": c["tr"]})
        if clean_cumleler:
            valid.append({"kategori": kat, "cumleler": clean_cumleler})
    return valid


# ---------------------------------------------------------------------------
# Ana islem döngüsü
# ---------------------------------------------------------------------------

def enrich(args: argparse.Namespace) -> None:
    data = load_dictionary()
    checkpoint = load_checkpoint()
    processed_keys: set[str] = set(checkpoint.get("processed_keys", []))

    # Hedef kayitlari filtrele
    targets: list[tuple[int, dict]] = []
    for idx, entry in enumerate(data):
        almanca = entry.get("almanca") or ""
        if not almanca:
            continue
        key = almanca.strip().lower()
        if key in processed_keys and not args.overwrite:
            continue
        if is_target_entry(entry, args.min_zipf, args.overwrite):
            targets.append((idx, entry))

    targets = targets[: args.limit]
    total = len(targets)
    print(f"[BİLGİ] İşlenecek kayit sayisi: {total}")

    if total == 0:
        print("[BİLGİ] İşlenecek kayit yok. Çikiliyor.")
        return

    if args.dry_run:
        print("[DRY-RUN] Örnek prompt:")
        _, sample = targets[0]
        kats = choose_kategoriler(sample)
        print(build_prompt(sample, kats))
        print(f"\n[DRY-RUN] {total} kayit işlenecekti, API çagrisi yapilmadi.")
        return

    client = get_groq_client(args.api_key)
    interval = 60.0 / RATE_LIMIT_PER_MIN  # saniye cinsinden bekleme

    ok_count = 0
    err_count = 0
    last_save = 0

    for batch_idx, (data_idx, entry) in enumerate(targets):
        almanca = entry.get("almanca", "")
        key = almanca.strip().lower()

        kategoriler = choose_kategoriler(entry)
        prompt = build_prompt(entry, kategoriler)

        print(f"[{batch_idx + 1}/{total}] İşleniyor: {almanca!r}  ({', '.join(kategoriler)})")

        try:
            response = client.chat.completions.create(
                model=args.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1024,
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            print(f"  [HATA] API hatasi: {exc}")
            err_count += 1
            time.sleep(interval)
            continue

        baglamlar = parse_baglamlar_response(raw)
        if baglamlar is None:
            print(f"  [UYARI] JSON parse basarisiz, kayit atlaniyor. Ham yanit: {raw[:120]!r}")
            err_count += 1
        else:
            baglamlar = validate_baglamlar(baglamlar)
            if not baglamlar:
                print("  [UYARI] Gecerli baglamlar bulunamadi, atlanıyor.")
                err_count += 1
            else:
                data[data_idx]["baglamlar"] = baglamlar
                processed_keys.add(key)
                ok_count += 1
                print(f"  [OK] {len(baglamlar)} baglamlar eklendi.")

        # Periyodik kayit
        if ok_count - last_save >= SAVE_EVERY:
            save_dictionary(data)
            save_checkpoint({"processed_keys": list(processed_keys)})
            last_save = ok_count
            print(f"  [KAYIT] {ok_count} kayit islendi, sözlük kaydedildi.")

        # Rate limitleme
        if batch_idx < total - 1:
            time.sleep(interval)

    # Son kayit
    save_dictionary(data)
    save_checkpoint({"processed_keys": list(processed_keys)})

    print(f"\n[BITTI] Basarili: {ok_count}, Hata: {err_count}, Toplam islem: {total}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sözlük kayitlarina Groq API ile baglamsal cümleler ekle.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--api-key", required=True, help="Groq API anahtari")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Kullanilacak Groq modeli")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Islenecek maksimum kayit sayisi",
    )
    parser.add_argument(
        "--min-zipf",
        type=float,
        default=DEFAULT_MIN_ZIPF,
        dest="min_zipf",
        help="Minimum Zipf skoru (bu deger ve üzeri islenir)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="API çagrisi yapmadan çalisti (simülasyon)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Zaten 'baglamlar' alani olan kayitlari da yeniden isle",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    enrich(args)
