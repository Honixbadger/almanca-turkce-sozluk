#!/usr/bin/env python3
"""Build a preview report for safer top-level Turkish translation reselection.

This script does not modify dictionary.json. It inspects records and proposes
better `turkce` values only when the current top-level translation looks weak
and a safer alternative can be inferred from existing structured data.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

DICT_PATH = Path("output/dictionary.json")
DEFAULT_OUTPUT = Path("output/top_translation_reselection_preview.json")

WEAK_TRANSLATIONS = {
    "etmek",
    "yapmak",
    "gitmek",
    "gelmek",
    "olmak",
    "durum",
    "olgu",
    "fenomen",
}

SAFE_NOMINAL_SUFFIXES = (
    "ung",
    "heit",
    "keit",
    "tion",
    "tät",
    "nis",
    "schaft",
    "anz",
    "enz",
)


@dataclass
class Candidate:
    almanca: str
    tur: str
    current: str
    suggested: str
    confidence: float
    reason: str
    explanation: str
    sample_definition: str


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def looks_generic(text: str) -> bool:
    norm = normalize_space(text).casefold()
    return norm in WEAK_TRANSLATIONS


def looks_infinitive(text: str) -> bool:
    norm = normalize_space(text).casefold()
    return norm.endswith("mak") or norm.endswith("mek")


def nounify_turkish_infinitive(text: str) -> str:
    parts = [normalize_space(part) for part in text.split(";") if normalize_space(part)]
    if len(parts) != 1:
        return ""
    part = parts[0]
    tokens = part.split(" ")
    if not tokens:
        return ""
    last = tokens[-1]
    if last.endswith("mak"):
        tokens[-1] = last[:-3] + "ma"
    elif last.endswith("mek"):
        tokens[-1] = last[:-3] + "me"
    else:
        return ""
    return " ".join(tokens)


def choose_sense_candidate(record: dict) -> tuple[str, str]:
    senses = record.get("anlamlar") or []
    for sense in senses:
        tr = normalize_space(sense.get("turkce") or "")
        de_def = normalize_space(sense.get("tanim_almanca") or "")
        if not tr:
            continue
        if looks_generic(tr):
            continue
        return tr, de_def
    return "", ""


def top_level_reselection_candidate(record: dict) -> Candidate | None:
    word = normalize_space(record.get("almanca") or "")
    pos = normalize_space(record.get("tur") or "")
    current = normalize_space(record.get("turkce") or "")
    de_def = normalize_space(record.get("tanim_almanca") or "")
    if not word or not current or pos != "isim":
        return None

    sense_tr, sense_def = choose_sense_candidate(record)
    if sense_tr and sense_tr != current and looks_generic(current):
        return Candidate(
            almanca=word,
            tur=pos,
            current=current,
            suggested=sense_tr,
            confidence=0.93,
            reason="generic_top_translation_with_better_sense",
            explanation="Üst çeviri çok genel, mevcut anlamlar içinde daha iyi Türkçe karşılık var.",
            sample_definition=sense_def or de_def,
        )

    nominalized = nounify_turkish_infinitive(current)
    if nominalized and nominalized != current:
        lowered = word.casefold()
        if lowered.endswith(SAFE_NOMINAL_SUFFIXES):
            return Candidate(
                almanca=word,
                tur=pos,
                current=current,
                suggested=nominalized,
                confidence=0.87,
                reason="noun_suffix_with_infinitive_top_translation",
                explanation="İsim kaydı fiil mastarıyla çevrilmiş görünüyor; güvenli isimleştirme önerildi.",
                sample_definition=de_def or sense_def,
            )
        if normalize_space(record.get("aciklama_turkce") or "") == current:
            return Candidate(
                almanca=word,
                tur=pos,
                current=current,
                suggested=nominalized,
                confidence=0.8,
                reason="infinitive_top_translation_repeated_in_description",
                explanation="Üst çeviri ve açıklama aynı fiil mastarı; isim kullanımına daha yakın kısa karşılık önerildi.",
                sample_definition=de_def or sense_def,
            )

    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--min-confidence", type=float, default=0.8)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))

    candidates: list[Candidate] = []
    for record in data:
        candidate = top_level_reselection_candidate(record)
        if candidate and candidate.confidence >= args.min_confidence:
            candidates.append(candidate)

    candidates.sort(key=lambda item: (-item.confidence, item.almanca.casefold()))
    if args.limit:
        candidates = candidates[: args.limit]

    payload = {
        "count": len(candidates),
        "min_confidence": args.min_confidence,
        "items": [
            {
                "almanca": item.almanca,
                "tur": item.tur,
                "current": item.current,
                "suggested": item.suggested,
                "confidence": item.confidence,
                "reason": item.reason,
                "explanation": item.explanation,
                "sample_definition": item.sample_definition,
            }
            for item in candidates
        ],
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"preview_count={len(candidates)}")
    print(f"output={output_path}")
    for item in candidates[:20]:
        print(
            f"{item.almanca}\t{item.current}\t=>\t{item.suggested}\t"
            f"[{item.reason}] conf={item.confidence:.2f}"
        )


if __name__ == "__main__":
    main()
