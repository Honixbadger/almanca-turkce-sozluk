#!/usr/bin/env python3
"""Apply a manually curated, deep-research-based enrichment batch to the dictionary.

This script is intentionally conservative:
- does not delete existing data
- only appends curated examples, valency, and verb patterns
- writes a detailed report
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATHS = [
    PROJECT_ROOT / "output" / "dictionary.json",
    PROJECT_ROOT / "dist" / "AlmancaSozluk" / "_internal" / "output" / "dictionary.json",
]
REPORT_DIR = PROJECT_ROOT / "output"

SOURCE_NOTE = "deep-research-manual-curation"
SOURCE_BASIS = [
    "Kaikki / deWiktionary structured data",
    "Tatoeba bilingual examples",
    "DWDS valency/usage validation",
]

CURATED_UPDATES = {
    "abweichen": {
        "examples": [
            {
                "almanca": "Ich werde von meinem Weg nie abweichen.",
                "turkce": "Yolumdan asla sapmayacağım.",
            },
            {
                "almanca": "In Deutschland gibt es viele verschiedene Dialekte, die mehr oder weniger von dem geschriebenen Deutsch abweichen.",
                "turkce": "Almanya'da, yazı dilindeki Almancadan az ya da çok farklılaşan birçok lehçe vardır.",
            },
        ],
        "valenz": ["von + Dativ"],
        "patterns": [
            {"kalip": "von etwas abweichen", "turkce": "bir şeyden sapmak; bir şeyden farklılaşmak"},
        ],
    },
    "analysieren": {
        "examples": [
            {"almanca": "Er analysierte das Problem gründlich.", "turkce": "Sorunu ayrıntılı biçimde analiz etti."},
            {"almanca": "Er analysierte die Situation sorgfältig.", "turkce": "Durumu dikkatle analiz etti."},
        ],
        "valenz": ["etwas + Akkusativ"],
        "patterns": [
            {"kalip": "etwas analysieren", "turkce": "bir şeyi analiz etmek"},
        ],
    },
    "arbeiten": {
        "examples": [
            {"almanca": "Mein Bruder arbeitet in einer Bank.", "turkce": "Erkek kardeşim bir bankada çalışıyor."},
            {"almanca": "Ich habe es satt, hier zu arbeiten.", "turkce": "Burada çalışmaktan bıktım."},
        ],
    },
    "aufnehmen": {
        "examples": [
            {"almanca": "Könntest du zu ihm Kontakt aufnehmen?", "turkce": "Onunla iletişime geçebilir misin?"},
            {"almanca": "Könnten Sie zu ihm Kontakt aufnehmen?", "turkce": "Onunla iletişime geçebilir misiniz?"},
        ],
        "patterns": [
            {"kalip": "Kontakt zu jemandem aufnehmen", "turkce": "biriyle iletişime geçmek"},
        ],
    },
    "ausgehen": {
        "examples": [
            {"almanca": "Ich will heute Abend nicht ausgehen.", "turkce": "Bu akşam dışarı çıkmak istemiyorum."},
            {"almanca": "Ich würde heute lieber nicht ausgehen.", "turkce": "Bugün dışarı çıkmamayı tercih ederim."},
        ],
    },
    "beachten": {
        "examples": [
            {"almanca": "Wir müssen die rote Ampel beachten.", "turkce": "Kırmızı ışığa uymalıyız."},
            {"almanca": "Die Gesetze müssen beachtet werden.", "turkce": "Yasalara uyulmalıdır."},
        ],
        "valenz": ["etwas + Akkusativ"],
        "patterns": [
            {"kalip": "etwas beachten", "turkce": "bir şeyi dikkate almak; bir kurala uymak"},
        ],
    },
    "beantworten": {
        "examples": [
            {"almanca": "Ich konnte seine Frage beantworten.", "turkce": "Onun sorusunu cevaplayabildim."},
            {"almanca": "Wer möchte diese Frage beantworten?", "turkce": "Bu soruyu kim cevaplamak ister?"},
        ],
        "valenz": ["etwas + Akkusativ"],
        "patterns": [
            {"kalip": "eine Frage beantworten", "turkce": "bir soruyu cevaplamak"},
        ],
    },
    "bedeuten": {
        "examples": [
            {"almanca": "Weißt du, wie viel mir das bedeutet?", "turkce": "Bunun benim için ne kadar önemli olduğunu biliyor musun?"},
            {"almanca": "Das wird viel bedeuten für das Dorf.", "turkce": "Bu, köy için çok şey ifade edecek."},
        ],
        "patterns": [
            {"kalip": "jemandem viel bedeuten", "turkce": "birisi için çok şey ifade etmek"},
        ],
    },
    "bedienen": {
        "examples": [
            {"almanca": "Eine schöne Kellnerin bediente uns.", "turkce": "Güzel bir garson bize hizmet etti."},
            {"almanca": "Niemand kann diese Maschine bedienen.", "turkce": "Bu makineyi kimse kullanamıyor."},
        ],
        "valenz": ["jemanden + Akkusativ", "etwas + Akkusativ"],
        "patterns": [
            {"kalip": "eine Maschine bedienen", "turkce": "bir makineyi kullanmak"},
            {"kalip": "jemanden bedienen", "turkce": "birine hizmet etmek"},
        ],
    },
    "beeinflussen": {
        "examples": [
            {"almanca": "Sie hat sich von ihm beeinflussen lassen.", "turkce": "Kendisini onun etkilemesine izin verdi."},
            {"almanca": "Marias Vater kann man leicht beeinflussen.", "turkce": "Maria'nın babasını etkilemek kolaydır."},
        ],
    },
    "begegnen": {
        "examples": [
            {"almanca": "Ich hoffe, ihm nicht mehr zu begegnen.", "turkce": "Umarım onunla bir daha karşılaşmam."},
            {"almanca": "Es ist mir eine Ehre, Ihnen zu begegnen.", "turkce": "Sizinle karşılaşmak benim için bir onur."},
        ],
        "valenz": ["jemandem + Dativ"],
        "patterns": [
            {"kalip": "jemandem begegnen", "turkce": "biriyle karşılaşmak"},
        ],
    },
    "beinhalten": {
        "examples": [
            {"almanca": "Karotten beinhalten viel Vitamin A.", "turkce": "Havuç çok miktarda A vitamini içerir."},
            {"almanca": "Dieser Betrag beinhaltet die Steuer.", "turkce": "Bu tutar vergiyi içerir."},
        ],
        "valenz": ["etwas + Akkusativ"],
        "patterns": [
            {"kalip": "etwas beinhalten", "turkce": "bir şeyi içermek"},
        ],
    },
    "bestehen": {
        "examples": [
            {"almanca": "Lebewesen bestehen aus Kohlenstoff.", "turkce": "Canlılar karbondan oluşur."},
            {"almanca": "Sein Ziel ist, den Test zu bestehen.", "turkce": "Onun hedefi sınavı geçmektir."},
        ],
        "valenz": ["aus + Dativ"],
        "patterns": [
            {"kalip": "aus etwas bestehen", "turkce": "bir şeyden oluşmak"},
            {"kalip": "eine Prüfung bestehen", "turkce": "bir sınavı geçmek"},
        ],
    },
    "dauern": {
        "examples": [
            {"almanca": "Das kann Wochen oder Monate dauern.", "turkce": "Bu haftalar ya da aylar sürebilir."},
            {"almanca": "Wie lange wird der Sturm noch dauern?", "turkce": "Fırtına daha ne kadar sürecek?"},
        ],
    },
    "entlassen": {
        "examples": [
            {"almanca": "Du wurdest auf Bewährung entlassen.", "turkce": "Şartlı tahliye edildin."},
            {"almanca": "Er wurde wegen Diebstahls entlassen.", "turkce": "Hırsızlık nedeniyle işten çıkarıldı."},
        ],
    },
    "erinnern": {
        "examples": [
            {"almanca": "Deine Augen erinnern mich an Sterne.", "turkce": "Gözlerin bana yıldızları hatırlatıyor."},
            {"almanca": "Tom schien sich an mich zu erinnern.", "turkce": "Tom beni hatırlıyor gibi görünüyordu."},
        ],
        "valenz": ["an + Akkusativ"],
        "patterns": [
            {"kalip": "jemanden an etwas erinnern", "turkce": "birine bir şeyi hatırlatmak"},
            {"kalip": "sich an etwas erinnern", "turkce": "bir şeyi hatırlamak"},
        ],
    },
    "informieren": {
        "examples": [
            {"almanca": "Informieren Sie mich über die Einzelheiten.", "turkce": "Ayrıntılar hakkında beni bilgilendirin."},
            {"almanca": "Informieren Sie mich, sobald er wiederkommt.", "turkce": "O geri döner dönmez beni haberdar edin."},
        ],
        "valenz": ["über + Akkusativ"],
        "patterns": [
            {"kalip": "jemanden über etwas informieren", "turkce": "birini bir şey hakkında bilgilendirmek"},
        ],
    },
    "leisten": {
        "examples": [
            {"almanca": "Ich kann mir kein neues Auto leisten.", "turkce": "Yeni bir araba almaya gücüm yetmez."},
            {"almanca": "Können wir uns ein neues Auto leisten?", "turkce": "Yeni bir araba almaya gücümüz yeter mi?"},
        ],
        "patterns": [
            {"kalip": "sich etwas leisten", "turkce": "bir şeye maddi olarak gücü yetmek"},
        ],
    },
    "reagieren": {
        "examples": [
            {"almanca": "Sie reagierte nicht auf meine Frage.", "turkce": "Soruma tepki vermedi."},
            {"almanca": "Du reagierst zu empfindlich auf Kritik.", "turkce": "Eleştiriye fazla hassas tepki veriyorsun."},
        ],
        "valenz": ["auf + Akkusativ"],
        "patterns": [
            {"kalip": "auf etwas reagieren", "turkce": "bir şeye tepki vermek"},
        ],
    },
    "sorgen": {
        "examples": [
            {"almanca": "Sie sorgt sich um deine Sicherheit.", "turkce": "Senin güvenliğin için endişeleniyor."},
            {"almanca": "Ihr Vorschlag sorgte für rote Köpfe.", "turkce": "Onun önerisi ortalığı kızıştırdı."},
        ],
        "valenz": ["für + Akkusativ", "um + Akkusativ"],
        "patterns": [
            {"kalip": "für etwas sorgen", "turkce": "bir şeyi sağlamak"},
            {"kalip": "sich um etwas sorgen", "turkce": "bir şey için endişelenmek"},
        ],
    },
    "versorgen": {
        "examples": [
            {"almanca": "Kühe versorgen uns mit guter Milch.", "turkce": "İnekler bize kaliteli süt sağlar."},
            {"almanca": "Können Sie uns mit Getränken versorgen?", "turkce": "Bize içecek temin edebilir misiniz?"},
        ],
        "valenz": ["mit + Dativ"],
        "patterns": [
            {"kalip": "jemanden mit etwas versorgen", "turkce": "birini bir şeyle temin etmek"},
        ],
    },
    "vermeiden": {
        "examples": [
            {"almanca": "Mayuko vermied anstrengende Arbeit.", "turkce": "Mayuko yorucu işlerden kaçındı."},
            {"almanca": "Die Regierung will eine Panik vermeiden.", "turkce": "Hükümet bir paniği önlemek istiyor."},
        ],
        "valenz": ["etwas + Akkusativ"],
        "patterns": [
            {"kalip": "etwas vermeiden", "turkce": "bir şeyi önlemek; bir şeyden kaçınmak"},
        ],
    },
    "wissen": {
        "examples": [
            {"almanca": "Ich will wissen, wer mit uns kommt.", "turkce": "Bizimle kimin geleceğini bilmek istiyorum."},
            {"almanca": "Wissen Sie, wem dieses Auto gehört?", "turkce": "Bu arabanın kime ait olduğunu biliyor musunuz?"},
        ],
        "patterns": [
            {"kalip": "wissen, wer/wem ...", "turkce": "kim/kime ... olduğunu bilmek"},
        ],
    },
    "ziehen": {
        "examples": [
            {"almanca": "Was ziehen Sie vor, Reis oder Brot?", "turkce": "Hangisini tercih edersiniz, pirinci mi ekmeği mi?"},
            {"almanca": "Er zog sich das auffällige Hemd an.", "turkce": "Dikkat çekici gömleğini giydi."},
        ],
        "patterns": [
            {"kalip": "etwas vorziehen", "turkce": "bir şeyi tercih etmek"},
            {"kalip": "sich etwas anziehen", "turkce": "bir şeyi giymek"},
        ],
    },
}


def compact(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def normalize(text: str) -> str:
    return compact(text).casefold()


def merge_examples(record: dict, payload: list[dict]) -> tuple[int, int]:
    existing_examples = list(record.get("ornekler") or [])
    existing_keys = {
        normalize(item.get("almanca") or "")
        for item in existing_examples
        if isinstance(item, dict) and compact(item.get("almanca") or "")
    }
    added = 0
    top_level_filled = 0

    for item in payload:
        de_text = compact(item["almanca"])
        tr_text = compact(item["turkce"])
        key = normalize(de_text)
        if key in existing_keys:
            continue
        existing_examples.append(
            {
                "almanca": de_text,
                "turkce": tr_text,
                "kaynak": SOURCE_NOTE,
            }
        )
        existing_keys.add(key)
        added += 1

    if added:
        record["ornekler"] = existing_examples

    if payload:
        if not compact(record.get("ornek_almanca") or ""):
            record["ornek_almanca"] = compact(payload[0]["almanca"])
            top_level_filled += 1
        if not compact(record.get("ornek_turkce") or ""):
            record["ornek_turkce"] = compact(payload[0]["turkce"])
            top_level_filled += 1

    return added, top_level_filled


def merge_valenz(record: dict, values: list[str]) -> int:
    current = [compact(item) for item in (record.get("valenz") or []) if compact(item)]
    seen = {normalize(item) for item in current}
    added = 0
    for item in values or []:
        text = compact(item)
        if text and normalize(text) not in seen:
            current.append(text)
            seen.add(normalize(text))
            added += 1
    if added:
        record["valenz"] = current
    return added


def merge_patterns(record: dict, rows: list[dict]) -> int:
    current = [item for item in (record.get("fiil_kaliplari") or []) if isinstance(item, dict)]
    seen = {normalize(item.get("kalip") or "") for item in current if compact(item.get("kalip") or "")}
    added = 0
    for item in rows or []:
        kalip = compact(item.get("kalip") or "")
        if not kalip or normalize(kalip) in seen:
            continue
        current.append(
            {
                "kalip": kalip,
                "turkce": compact(item.get("turkce") or ""),
                "kaynak": SOURCE_NOTE,
            }
        )
        seen.add(normalize(kalip))
        added += 1
    if added:
        record["fiil_kaliplari"] = current
    return added


def apply_to_dictionary(path: Path, updates: dict[str, dict]) -> dict:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.stem}.backup.curated-deep-research-{timestamp}{path.suffix}")
    shutil.copy2(path, backup_path)

    data = json.loads(path.read_text(encoding="utf-8"))
    index = {normalize(item.get("almanca") or ""): item for item in data if isinstance(item, dict)}
    stats = Counter()
    samples = []

    for lemma, payload in updates.items():
        record = index.get(normalize(lemma))
        if record is None:
            stats["missing_records"] += 1
            continue
        stats["lemmas_updated"] += 1
        ex_added, top_filled = merge_examples(record, payload.get("examples") or [])
        val_added = merge_valenz(record, payload.get("valenz") or [])
        pat_added = merge_patterns(record, payload.get("patterns") or [])
        stats["examples_added"] += ex_added
        stats["top_level_example_fields_filled"] += top_filled
        stats["valenz_added"] += val_added
        stats["patterns_added"] += pat_added
        if ex_added or val_added or pat_added:
            if len(samples) < 40:
                samples.append(
                    {
                        "lemma": lemma,
                        "examples_added": ex_added,
                        "valenz_added": val_added,
                        "patterns_added": pat_added,
                    }
                )

    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {
        "file": str(path),
        "backup": str(backup_path),
        "stats": dict(stats),
        "sample": samples,
    }


def write_markdown_summary(path: Path, report: dict) -> None:
    lines = [
        "# Curated Deep Research Enrichment",
        "",
        f"- Updated at: `{report['updated_at']}`",
        f"- Lemmas targeted: `{report['lemmas_targeted']}`",
        f"- Examples added: `{report['totals']['examples_added']}`",
        f"- Valenz added: `{report['totals']['valenz_added']}`",
        f"- Patterns added: `{report['totals']['patterns_added']}`",
        "",
        "## Sources",
        "",
    ]
    for item in SOURCE_BASIS:
        lines.append(f"- {item}")
    lines.extend(["", "## Sample", ""])
    for row in report["sample"][:20]:
        lines.append(
            f"- `{row['lemma']}`: +{row['examples_added']} örnek, +{row['valenz_added']} valenz, +{row['patterns_added']} kalıp"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_reports = [apply_to_dictionary(path, CURATED_UPDATES) for path in DICT_PATHS if path.exists()]

    primary_stats = dict(file_reports[0]["stats"]) if file_reports else {}
    sync_totals = Counter()
    sample = []
    for item in file_reports:
        stats = item["stats"]
        for key, value in stats.items():
            if key != "lemmas_updated":
                sync_totals[key] += int(value)
        for row in item["sample"]:
            if len(sample) < 30:
                sample.append(row)

    report = {
        "updated_at": timestamp,
        "lemmas_targeted": len(CURATED_UPDATES),
        "sources": SOURCE_BASIS,
        "totals": primary_stats,
        "sync_totals": dict(sync_totals),
        "files": file_reports,
        "sample": sample,
        "lemmas": sorted(CURATED_UPDATES.keys()),
    }
    json_path = REPORT_DIR / f"curated_deep_research_enrichment_report_{timestamp}.json"
    md_path = REPORT_DIR / f"curated_deep_research_enrichment_report_{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_summary(md_path, report)
    print(json.dumps({"json_report": str(json_path), "md_report": str(md_path), "totals": report["totals"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
