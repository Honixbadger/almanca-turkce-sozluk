#!/usr/bin/env python3
"""
enrich_add_missing_basic.py
============================
Sözlükte olması gereken ama eksik olan temel kelimeleri ekler.

Kaynak 1 : Hardcoded veritabanı (bilgi tabanı + VmP listesinden eksikler)
Kaynak 2 : Wiktionary DE API (Türkçe çeviri + Almanca tanım için)

Her kelime için şu alanlar doldurulur:
  almanca, turkce, tur, artikel (isimler için),
  prateritum, partizip2, perfekt_yardimci, trennbar, trennbar_prefix (fiiller),
  fiil_kaliplari (varsa), kaynak, ceviri_durumu
"""

from __future__ import annotations
import json, re, sys, time, urllib.request, urllib.parse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATH    = PROJECT_ROOT / "output" / "dictionary.json"

SOURCE_BASIC = "temel-kelime-veritabani"
SOURCE_WIKI  = "dewiktionary-api"

# ─────────────────────────────────────────────────────────────────────────────
# VERİ: Eklenecek kelimeler
# Format: {almanca, turkce, tur, artikel?, prateritum?, partizip2?,
#          perfekt_yardimci?, trennbar?, trennbar_prefix?,
#          verb_typ?, fiil_kaliplari?[], ornek_almanca?, ornek_turkce?}
# ─────────────────────────────────────────────────────────────────────────────

SOURCE_PONS = "PONS Praxis-Grammatik (Verben mit Präpositionen)"
SOURCE_DB   = "VmP-Veritabanı (Verben mit Präpositionen)"

ENTRIES: list[dict] = [

    # ── VmP eksik fiiller ─────────────────────────────────────────────────────

    {"almanca": "achten", "turkce": "dikkat etmek; saygı göstermek", "tur": "fiil",
     "prateritum": "achtete", "partizip2": "geachtet", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Bitte achte auf deine Gesundheit.",
     "ornek_turkce": "Lütfen sağlığına dikkat et.",
     "fiil_kaliplari": [{"kalip": "auf etw./jdn. (A) achten", "turkce": "-e dikkat etmek",
                         "ornek_almanca": "Bitte achte auf den neuen Mantel.",
                         "ornek_turkce": "", "kaynak": SOURCE_PONS}]},

    {"almanca": "antworten", "turkce": "cevap vermek, yanıtlamak", "tur": "fiil",
     "prateritum": "antwortete", "partizip2": "geantwortet", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie antwortete nicht auf seine Frage.",
     "ornek_turkce": "Onun sorusuna cevap vermedi.",
     "fiil_kaliplari": [{"kalip": "auf etw. (A) antworten", "turkce": "-e cevap vermek",
                         "ornek_almanca": "Bitte antworten Sie heute auf den Brief.",
                         "ornek_turkce": "", "kaynak": SOURCE_PONS}]},

    {"almanca": "berichten", "turkce": "haber vermek, rapor etmek, aktarmak", "tur": "fiil",
     "prateritum": "berichtete", "partizip2": "berichtet", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Der Journalist berichtete über den Unfall.",
     "ornek_turkce": "Gazeteci kazayı haber yaptı.",
     "fiil_kaliplari": [{"kalip": "über etw. (A) berichten", "turkce": "hakkında haber yapmak",
                         "ornek_almanca": "Der Reporter berichtet über die Wahlen.",
                         "ornek_turkce": "", "kaynak": SOURCE_PONS}]},

    {"almanca": "klagen", "turkce": "şikayet etmek; dava açmak; ağlamak", "tur": "fiil",
     "prateritum": "klagte", "partizip2": "geklagt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Er klagt ständig über Rückenschmerzen.",
     "ornek_turkce": "Sürekli sırt ağrısından şikayet ediyor.",
     "fiil_kaliplari": [
         {"kalip": "über etw. (A) klagen", "turkce": "-den yakınmak, şikayet etmek",
          "ornek_almanca": "Tim klagt häufig über Kopfschmerzen.", "ornek_turkce": "", "kaynak": SOURCE_PONS},
         {"kalip": "gegen jdn. (A) klagen", "turkce": "birine dava açmak",
          "ornek_almanca": "Er klagte gegen die Entscheidung.", "ornek_turkce": "", "kaynak": SOURCE_DB},
     ]},

    {"almanca": "protestieren", "turkce": "protesto etmek, karşı çıkmak", "tur": "fiil",
     "prateritum": "protestierte", "partizip2": "protestiert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Tausende protestierten gegen das Gesetz.",
     "ornek_turkce": "Binlerce kişi yasayı protesto etti.",
     "fiil_kaliplari": [{"kalip": "gegen etw./jdn. (A) protestieren", "turkce": "karşı protesto etmek",
                         "ornek_almanca": "Viele Menschen protestieren gegen Atomkraft.",
                         "ornek_turkce": "", "kaynak": SOURCE_PONS}]},

    {"almanca": "jubeln", "turkce": "sevinmek, coşmak, tezahürat yapmak", "tur": "fiil",
     "prateritum": "jubelte", "partizip2": "gejubelt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Die Fans jubelten nach dem Tor.",
     "ornek_turkce": "Taraftarlar golün ardından coştu.",
     "fiil_kaliplari": [{"kalip": "über etw. (A) jubeln", "turkce": "-den sevinmek",
                         "ornek_almanca": "Die Fans jubeln über den Sieg.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "jammern", "turkce": "yakınmak, sızlanmak, inlemek", "tur": "fiil",
     "prateritum": "jammerte", "partizip2": "gejammert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Hör auf zu jammern und tu etwas.",
     "ornek_turkce": "Sızlanmayı bırak ve bir şeyler yap.",
     "fiil_kaliplari": [{"kalip": "über etw. (A) jammern", "turkce": "-den yakınmak",
                         "ornek_almanca": "Er jammert immer über das Wetter.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "schwärmen", "turkce": "hayran olmak, çok beğenmek; uçuşmak (böcekler)", "tur": "fiil",
     "prateritum": "schwärmte", "partizip2": "geschwärmt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie schwärmt von Italien.",
     "ornek_turkce": "İtalya'ya hayran.",
     "fiil_kaliplari": [{"kalip": "von jdm./etw. (D) schwärmen", "turkce": "-i çok beğenmek, hayran olmak",
                         "ornek_almanca": "Alle schwärmen von diesem Restaurant.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "stammen", "turkce": "köken almak, gelmek, türemek", "tur": "fiil",
     "prateritum": "stammte", "partizip2": "gestammt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Dieses Wort stammt aus dem Arabischen.",
     "ornek_turkce": "Bu kelime Arapçadan gelmektedir.",
     "fiil_kaliplari": [{"kalip": "aus etw. (D) stammen", "turkce": "-den gelmek, köken almak",
                         "ornek_almanca": "Dieses Wort stammt aus dem Lateinischen.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "stoßen", "turkce": "itmek; çarpmak; -le karşılaşmak", "tur": "fiil",
     "prateritum": "stieß", "partizip2": "gestoßen", "perfekt_yardimci": "haben", "verb_typ": "stark",
     "ornek_almanca": "Er stieß die Tür auf.",
     "ornek_turkce": "Kapıyı açtı (itti).",
     "fiil_kaliplari": [{"kalip": "auf etw. (A) stoßen", "turkce": "-le karşılaşmak",
                         "ornek_almanca": "Wir sind auf ein unerwartetes Problem gestoßen.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "zurückgreifen", "turkce": "başvurmak, yararlanmak", "tur": "fiil",
     "prateritum": "griff zurück", "partizip2": "zurückgegriffen", "perfekt_yardimci": "haben",
     "verb_typ": "stark", "trennbar": True, "trennbar_prefix": "zurück",
     "ornek_almanca": "Im Notfall greifen wir auf unsere Ersparnisse zurück.",
     "ornek_turkce": "Acil durumda birikimlerimize başvururuz.",
     "fiil_kaliplari": [{"kalip": "auf etw. (A) zurückgreifen", "turkce": "-e başvurmak, -den yararlanmak",
                         "ornek_almanca": "Im Notfall können wir auf unsere Ersparnisse zurückgreifen.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "beitragen", "turkce": "katkıda bulunmak", "tur": "fiil",
     "prateritum": "trug bei", "partizip2": "beigetragen", "perfekt_yardimci": "haben",
     "verb_typ": "stark", "trennbar": True, "trennbar_prefix": "bei",
     "ornek_almanca": "Jeder kann zum Umweltschutz beitragen.",
     "ornek_turkce": "Herkes çevre korumasına katkıda bulunabilir.",
     "fiil_kaliplari": [{"kalip": "zu etw. (D) beitragen", "turkce": "-e katkıda bulunmak",
                         "ornek_almanca": "Jeder kann zum Umweltschutz beitragen.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "abraten", "turkce": "caydırmak, tavsiye etmemek", "tur": "fiil",
     "prateritum": "riet ab", "partizip2": "abgeraten", "perfekt_yardimci": "haben",
     "verb_typ": "stark", "trennbar": True, "trennbar_prefix": "ab",
     "ornek_almanca": "Der Arzt riet mir von Alkohol ab.",
     "ornek_turkce": "Doktor bana alkolü tavsiye etmedi.",
     "fiil_kaliplari": [{"kalip": "jdm. von etw. (D) abraten", "turkce": "-i tavsiye etmemek, caydırmak",
                         "ornek_almanca": "Er rät mir von diesem Plan ab.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "aufrufen", "turkce": "çağırmak; harekete geçirmek; açmak (dosya)", "tur": "fiil",
     "prateritum": "rief auf", "partizip2": "aufgerufen", "perfekt_yardimci": "haben",
     "verb_typ": "stark", "trennbar": True, "trennbar_prefix": "auf",
     "ornek_almanca": "Der Lehrer rief den nächsten Schüler auf.",
     "ornek_turkce": "Öğretmen bir sonraki öğrenciyi çağırdı.",
     "fiil_kaliplari": [{"kalip": "zu etw. (D) aufrufen", "turkce": "-e çağırmak",
                         "ornek_almanca": "Der Präsident rief zur Solidarität auf.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "tendieren", "turkce": "eğilimli olmak, -e yönelmek", "tur": "fiil",
     "prateritum": "tendierte", "partizip2": "tendiert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Er tendiert dazu, zu übertreiben.",
     "ornek_turkce": "Abartmaya eğilimli.",
     "fiil_kaliplari": [{"kalip": "zu etw. (D) tendieren", "turkce": "-e eğilimli olmak",
                         "ornek_almanca": "Er tendiert zu übertriebenen Aussagen.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "urteilen", "turkce": "yargılamak, hüküm vermek, değerlendirmek", "tur": "fiil",
     "prateritum": "urteilte", "partizip2": "geurteilt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Man sollte nicht vorschnell über andere urteilen.",
     "ornek_turkce": "Başkaları hakkında aceleyle yargıda bulunmamalı.",
     "fiil_kaliplari": [{"kalip": "über jdn./etw. (A) urteilen", "turkce": "hakkında hüküm vermek",
                         "ornek_almanca": "Man sollte nicht vorschnell über andere urteilen.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "verstoßen", "turkce": "ihlal etmek; reddetmek, dışlamak", "tur": "fiil",
     "prateritum": "verstieß", "partizip2": "verstoßen", "perfekt_yardimci": "haben", "verb_typ": "stark",
     "ornek_almanca": "Er hat gegen die Regeln verstoßen.",
     "ornek_turkce": "Kurallara uymadı.",
     "fiil_kaliplari": [{"kalip": "gegen etw. (A) verstoßen", "turkce": "-e aykırı davranmak, ihlal etmek",
                         "ornek_almanca": "Er hat gegen die Regeln verstoßen.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "anfragen", "turkce": "sormak, talep etmek, bilgi istemek", "tur": "fiil",
     "prateritum": "fragte an", "partizip2": "angefragt", "perfekt_yardimci": "haben",
     "verb_typ": "schwach", "trennbar": True, "trennbar_prefix": "an",
     "ornek_almanca": "Ich frage morgen beim Verlag an.",
     "ornek_turkce": "Yarın yayınevine soracağım.",
     "fiil_kaliplari": [{"kalip": "bei jdm. (D) anfragen", "turkce": "birine sormak, talep etmek",
                         "ornek_almanca": "Ich frage morgen beim Verlag an.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "anspielen", "turkce": "ima etmek, işaret etmek", "tur": "fiil",
     "prateritum": "spielte an", "partizip2": "angespielt", "perfekt_yardimci": "haben",
     "verb_typ": "schwach", "trennbar": True, "trennbar_prefix": "an",
     "ornek_almanca": "Worauf spielst du damit an?",
     "ornek_turkce": "Bununla neyi ima ediyorsun?",
     "fiil_kaliplari": [{"kalip": "auf etw. (A) anspielen", "turkce": "-e ima etmek, işaret etmek",
                         "ornek_almanca": "Worauf spielt er mit dieser Bemerkung an?",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "ermutigen", "turkce": "cesaretlendirmek, teşvik etmek", "tur": "fiil",
     "prateritum": "ermutigte", "partizip2": "ermutigt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Der Coach ermutigt seine Spieler.",
     "ornek_turkce": "Koç oyuncularını cesaretlendiriyor.",
     "fiil_kaliplari": [{"kalip": "jdn. zu etw. (D) ermutigen", "turkce": "-e cesaretlendirmek",
                         "ornek_almanca": "Der Lehrer ermutigt die Schüler zur Teilnahme.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "einwilligen", "turkce": "razı olmak, onaylamak, izin vermek", "tur": "fiil",
     "prateritum": "willigte ein", "partizip2": "eingewilligt", "perfekt_yardimci": "haben",
     "verb_typ": "schwach", "trennbar": True, "trennbar_prefix": "ein",
     "ornek_almanca": "Der Patient willigte in die Operation ein.",
     "ornek_turkce": "Hasta ameliyatı onayladı.",
     "fiil_kaliplari": [{"kalip": "in etw. (A) einwilligen", "turkce": "-e razı olmak, onaylamak",
                         "ornek_almanca": "Der Patient willigt in die Operation ein.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "nachfragen", "turkce": "tekrar sormak; öğrenmek istemek", "tur": "fiil",
     "prateritum": "fragte nach", "partizip2": "nachgefragt", "perfekt_yardimci": "haben",
     "verb_typ": "schwach", "trennbar": True, "trennbar_prefix": "nach",
     "ornek_almanca": "Ich frage morgen noch einmal nach.",
     "ornek_turkce": "Yarın tekrar soracağım.",
     "fiil_kaliplari": [{"kalip": "nach etw. (D) nachfragen", "turkce": "-i tekrar sormak",
                         "ornek_almanca": "Ich frage morgen noch einmal nach dem Termin nach.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "abmelden", "turkce": "kayıt silmek; çıkış yapmak; abonelikten çıkmak", "tur": "fiil",
     "prateritum": "meldete ab", "partizip2": "abgemeldet", "perfekt_yardimci": "haben",
     "verb_typ": "schwach", "trennbar": True, "trennbar_prefix": "ab",
     "ornek_almanca": "Ich habe mich vom Newsletter abgemeldet.",
     "ornek_turkce": "Bülten aboneliğimden çıktım.",
     "fiil_kaliplari": [{"kalip": "sich von etw. (D) abmelden", "turkce": "-den çıkış yapmak",
                         "ornek_almanca": "Ich melde mich vom Newsletter ab.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "sich weigern", "turkce": "reddetmek, yapmayı reddedmek", "tur": "fiil",
     "prateritum": "weigerte sich", "partizip2": "geweigert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie weigerte sich, das Dokument zu unterschreiben.",
     "ornek_turkce": "Belgeyi imzalamayı reddetti."},

    {"almanca": "sich äußern", "turkce": "görüş bildirmek, ifade etmek, yorum yapmak", "tur": "fiil",
     "prateritum": "äußerte sich", "partizip2": "geäußert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Der Politiker äußerte sich zu den Vorwürfen.",
     "ornek_turkce": "Politikacı suçlamalar hakkında görüş bildirdi.",
     "fiil_kaliplari": [
         {"kalip": "sich zu etw. (D) äußern", "turkce": "hakkında görüş bildirmek",
          "ornek_almanca": "Der Minister äußerte sich zu den Vorwürfen.",
          "ornek_turkce": "", "kaynak": SOURCE_DB},
         {"kalip": "sich über etw. (A) äußern", "turkce": "hakkında yorum yapmak",
          "ornek_almanca": "Er äußerte sich kritisch über die Situation.",
          "ornek_turkce": "", "kaynak": SOURCE_DB},
     ]},

    {"almanca": "sich begeistern", "turkce": "heyecanlanmak, tutku duymak, coşmak", "tur": "fiil",
     "prateritum": "begeisterte sich", "partizip2": "begeistert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Die Kinder begeistern sich für Sport.",
     "ornek_turkce": "Çocuklar spora tutku duyuyor.",
     "fiil_kaliplari": [{"kalip": "sich für etw. (A) begeistern", "turkce": "-e heyecanlanmak, tutku duymak",
                         "ornek_almanca": "Die Kinder begeistern sich für Sport.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "sich erkundigen", "turkce": "bilgi edinmek, araştırmak, sormak", "tur": "fiil",
     "prateritum": "erkundigte sich", "partizip2": "erkundigt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Ich erkundigte mich nach dem nächsten Zug.",
     "ornek_turkce": "Bir sonraki tren hakkında bilgi aldım.",
     "fiil_kaliplari": [{"kalip": "sich nach etw./jdm. (D) erkundigen", "turkce": "hakkında bilgi edinmek",
                         "ornek_almanca": "Oma erkundigt sich oft nach meinen Plänen.",
                         "ornek_turkce": "", "kaynak": SOURCE_PONS}]},

    {"almanca": "sich einigen", "turkce": "anlaşmak, uzlaşmak, mutabık kalmak", "tur": "fiil",
     "prateritum": "einigte sich", "partizip2": "geeinigt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Wir haben uns auf einen Kompromiss geeinigt.",
     "ornek_turkce": "Bir uzlaşı üzerinde anlaştık.",
     "fiil_kaliplari": [
         {"kalip": "sich auf etw. (A) einigen", "turkce": "üzerinde uzlaşmak",
          "ornek_almanca": "Wir haben uns auf einen Kompromiss geeinigt.",
          "ornek_turkce": "", "kaynak": SOURCE_DB},
         {"kalip": "sich über etw. (A) einigen", "turkce": "hakkında anlaşmak",
          "ornek_almanca": "Sie einigten sich über die Bedingungen.",
          "ornek_turkce": "", "kaynak": SOURCE_DB},
     ]},

    {"almanca": "sich verständigen", "turkce": "iletişim kurmak; anlaşmak, haberleşmek", "tur": "fiil",
     "prateritum": "verständigte sich", "partizip2": "verständigt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Wir haben uns telefonisch verständigt.",
     "ornek_turkce": "Telefonla haberleştik.",
     "fiil_kaliplari": [{"kalip": "sich mit jdm. (D) verständigen", "turkce": "biriyle anlaşmak",
                         "ornek_almanca": "Wir haben uns telefonisch mit ihm verständigt.",
                         "ornek_turkce": "", "kaynak": SOURCE_DB}]},

    {"almanca": "sich wundern", "turkce": "şaşırmak, hayret etmek", "tur": "fiil",
     "prateritum": "wunderte sich", "partizip2": "gewundert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Ich wundere mich über seine Reaktion.",
     "ornek_turkce": "Tepkisine şaştım.",
     "fiil_kaliplari": [{"kalip": "sich über etw./jdn. (A) wundern", "turkce": "-e şaşırmak",
                         "ornek_almanca": "Viele wundern sich über die hohen Stromkosten.",
                         "ornek_turkce": "", "kaynak": SOURCE_PONS}]},

    # ── Diğer eksik temel fiiller ─────────────────────────────────────────────

    {"almanca": "winken", "turkce": "el sallamak, işaret etmek", "tur": "fiil",
     "prateritum": "winkte", "partizip2": "gewinkt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie winkte ihm zum Abschied.",
     "ornek_turkce": "Veda ederken ona el salladı."},

    {"almanca": "fallen", "turkce": "düşmek; azalmak; devrilmek", "tur": "fiil",
     "prateritum": "fiel", "partizip2": "gefallen", "perfekt_yardimci": "sein", "verb_typ": "stark",
     "ornek_almanca": "Das Kind ist auf den Boden gefallen.",
     "ornek_turkce": "Çocuk yere düştü."},

    {"almanca": "steigen", "turkce": "tırmanmak; yükselmek; artmak", "tur": "fiil",
     "prateritum": "stieg", "partizip2": "gestiegen", "perfekt_yardimci": "sein", "verb_typ": "stark",
     "ornek_almanca": "Die Preise sind stark gestiegen.",
     "ornek_turkce": "Fiyatlar büyük ölçüde arttı."},

    {"almanca": "misslingen", "turkce": "başarısız olmak, tutmamak", "tur": "fiil",
     "prateritum": "misslang", "partizip2": "misslungen", "perfekt_yardimci": "sein", "verb_typ": "stark",
     "ornek_almanca": "Der Versuch ist misslungen.",
     "ornek_turkce": "Deneme başarısız oldu."},

    {"almanca": "enttäuschen", "turkce": "hayal kırıklığı yaratmak, düş kırmak", "tur": "fiil",
     "prateritum": "enttäuschte", "partizip2": "enttäuscht", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Das Ergebnis hat mich sehr enttäuscht.",
     "ornek_turkce": "Sonuç beni çok hayal kırıklığına uğrattı."},

    {"almanca": "unterrichten", "turkce": "ders vermek, öğretmek; bilgi vermek", "tur": "fiil",
     "prateritum": "unterrichtete", "partizip2": "unterrichtet", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie unterrichtet Mathematik an einer Schule.",
     "ornek_turkce": "Bir okulda matematik dersi veriyor."},

    {"almanca": "planen", "turkce": "planlamak, tasarlamak", "tur": "fiil",
     "prateritum": "plante", "partizip2": "geplant", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Wir planen eine Reise nach Deutschland.",
     "ornek_turkce": "Almanya'ya bir seyahat planlıyoruz."},

    {"almanca": "austauschen", "turkce": "değiş tokuş etmek; değiştirmek", "tur": "fiil",
     "prateritum": "tauschte aus", "partizip2": "ausgetauscht", "perfekt_yardimci": "haben",
     "verb_typ": "schwach", "trennbar": True, "trennbar_prefix": "aus",
     "ornek_almanca": "Wir haben unsere Erfahrungen ausgetauscht.",
     "ornek_turkce": "Deneyimlerimizi paylaştık."},

    {"almanca": "sparen", "turkce": "tasarruf etmek, biriktirmek", "tur": "fiil",
     "prateritum": "sparte", "partizip2": "gespart", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Ich spare Geld für den Urlaub.",
     "ornek_turkce": "Tatil için para biriktiriyorum."},

    {"almanca": "quittieren", "turkce": "makbuz/fiş vermek; bir işi bırakmak", "tur": "fiil",
     "prateritum": "quittierte", "partizip2": "quittiert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Bitte quittieren Sie den Empfang.",
     "ornek_turkce": "Lütfen teslim alındığını imzalayın."},

    {"almanca": "buchen", "turkce": "rezervasyon yapmak, kitap etmek", "tur": "fiil",
     "prateritum": "buchte", "partizip2": "gebucht", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Ich habe ein Hotelzimmer gebucht.",
     "ornek_turkce": "Bir otel odası rezervasyonu yaptım."},

    {"almanca": "servieren", "turkce": "servis yapmak, sunmak, ikram etmek", "tur": "fiil",
     "prateritum": "servierte", "partizip2": "serviert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Der Kellner servierte das Essen.",
     "ornek_turkce": "Garson yemeği servis yaptı."},

    {"almanca": "renovieren", "turkce": "tadilat yapmak, yenilemek, restore etmek", "tur": "fiil",
     "prateritum": "renovierte", "partizip2": "renoviert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie renovieren gerade die Küche.",
     "ornek_turkce": "Şu an mutfağı yeniliyorlar."},

    {"almanca": "streichen", "turkce": "boyamak; silmek; iptal etmek", "tur": "fiil",
     "prateritum": "strich", "partizip2": "gestrichen", "perfekt_yardimci": "haben", "verb_typ": "stark",
     "ornek_almanca": "Wir haben die Wände weiß gestrichen.",
     "ornek_turkce": "Duvarları beyaza boyadık."},

    # ── Ek faydalı temel kelimeler ────────────────────────────────────────────

    {"almanca": "sinken", "turkce": "batmak; düşmek, azalmak", "tur": "fiil",
     "prateritum": "sank", "partizip2": "gesunken", "perfekt_yardimci": "sein", "verb_typ": "stark",
     "ornek_almanca": "Die Temperaturen sind gesunken.",
     "ornek_turkce": "Sıcaklıklar düştü."},

    {"almanca": "wachsen", "turkce": "büyümek; artmak; yetişmek", "tur": "fiil",
     "prateritum": "wuchs", "partizip2": "gewachsen", "perfekt_yardimci": "sein", "verb_typ": "stark",
     "ornek_almanca": "Die Stadt wächst sehr schnell.",
     "ornek_turkce": "Şehir çok hızlı büyüyor."},

    {"almanca": "lächeln", "turkce": "gülümsemek", "tur": "fiil",
     "prateritum": "lächelte", "partizip2": "gelächelt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie lächelte freundlich.",
     "ornek_turkce": "Kibarca gülümsedi."},

    {"almanca": "weinen", "turkce": "ağlamak", "tur": "fiil",
     "prateritum": "weinte", "partizip2": "geweint", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Das Kind weinte laut.",
     "ornek_turkce": "Çocuk yüksek sesle ağladı."},

    {"almanca": "schreien", "turkce": "bağırmak, çığlık atmak", "tur": "fiil",
     "prateritum": "schrie", "partizip2": "geschrien", "perfekt_yardimci": "haben", "verb_typ": "stark",
     "ornek_almanca": "Er schrie vor Schmerzen.",
     "ornek_turkce": "Acıyla bağırdı."},

    {"almanca": "flüstern", "turkce": "fısıldamak", "tur": "fiil",
     "prateritum": "flüsterte", "partizip2": "geflüstert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie flüsterte ihm etwas ins Ohr.",
     "ornek_turkce": "Kulağına bir şeyler fısıldadı."},

    {"almanca": "nicken", "turkce": "başını sallamak (onay)", "tur": "fiil",
     "prateritum": "nickte", "partizip2": "genickt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Er nickte zustimmend.",
     "ornek_turkce": "Onaylarcasına başını salladı."},

    {"almanca": "zittern", "turkce": "titremek", "tur": "fiil",
     "prateritum": "zitterte", "partizip2": "gezittert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Ihre Hände zitterten vor Aufregung.",
     "ornek_turkce": "Elleri heyecandan titriyordu."},

    {"almanca": "staunen", "turkce": "şaşırmak, hayrete düşmek", "tur": "fiil",
     "prateritum": "staunte", "partizip2": "gestaunt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Ich staune immer wieder über die Natur.",
     "ornek_turkce": "Doğaya her seferinde hayret ediyorum."},

    {"almanca": "seufzen", "turkce": "iç çekmek, ah çekmek", "tur": "fiil",
     "prateritum": "seufzte", "partizip2": "geseufzt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie seufzte tief und legte das Buch weg.",
     "ornek_turkce": "Derin bir iç çekti ve kitabı bıraktı."},

    {"almanca": "gähnen", "turkce": "esnemek", "tur": "fiil",
     "prateritum": "gähnte", "partizip2": "gegähnt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Er gähnte laut im Unterricht.",
     "ornek_turkce": "Derste yüksek sesle esnedi."},

    {"almanca": "husten", "turkce": "öksürmek", "tur": "fiil",
     "prateritum": "hustete", "partizip2": "gehustet", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Er hustete die ganze Nacht.",
     "ornek_turkce": "Bütün gece öksürdü."},

    {"almanca": "niesen", "turkce": "hapşırmak", "tur": "fiil",
     "prateritum": "nieste", "partizip2": "geniest", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie musste plötzlich niesen.",
     "ornek_turkce": "Aniden hapşırmak zorunda kaldı."},

    {"almanca": "stolpern", "turkce": "tökezlemek, takılıp düşmek", "tur": "fiil",
     "prateritum": "stolperte", "partizip2": "gestolpert", "perfekt_yardimci": "sein", "verb_typ": "schwach",
     "ornek_almanca": "Er stolperte über den Stein.",
     "ornek_turkce": "Taşa takılıp düştü."},

    {"almanca": "klettern", "turkce": "tırmanmak", "tur": "fiil",
     "prateritum": "kletterte", "partizip2": "geklettert", "perfekt_yardimci": "sein", "verb_typ": "schwach",
     "ornek_almanca": "Das Kind klettert auf den Baum.",
     "ornek_turkce": "Çocuk ağaca tırmanıyor."},

    {"almanca": "tauchen", "turkce": "dalmak; batmak", "tur": "fiil",
     "prateritum": "tauchte", "partizip2": "getaucht", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Er taucht gerne im Meer.",
     "ornek_turkce": "Denizde dalmayı seviyor."},

    {"almanca": "siegen", "turkce": "galip gelmek, kazanmak", "tur": "fiil",
     "prateritum": "siegte", "partizip2": "gesiegt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Das Team siegte 3:1.",
     "ornek_turkce": "Takım 3:1 kazandı."},

    {"almanca": "scheitern", "turkce": "başarısız olmak, çökmek", "tur": "fiil",
     "prateritum": "scheiterte", "partizip2": "gescheitert", "perfekt_yardimci": "sein", "verb_typ": "schwach",
     "ornek_almanca": "Das Projekt ist gescheitert.",
     "ornek_turkce": "Proje başarısız oldu."},

    {"almanca": "gelingen", "turkce": "başarmak, sonuç vermek (kişisiz)", "tur": "fiil",
     "prateritum": "gelang", "partizip2": "gelungen", "perfekt_yardimci": "sein", "verb_typ": "stark",
     "ornek_almanca": "Es ist mir gelungen, ihn zu überzeugen.",
     "ornek_turkce": "Onu ikna etmeyi başardım."},

    {"almanca": "verbessern", "turkce": "iyileştirmek, düzeltmek", "tur": "fiil",
     "prateritum": "verbesserte", "partizip2": "verbessert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie möchte ihr Deutsch verbessern.",
     "ornek_turkce": "Almancasını geliştirmek istiyor."},

    {"almanca": "verschlechtern", "turkce": "kötüleşmek; kötüleştirmek", "tur": "fiil",
     "prateritum": "verschlechterte", "partizip2": "verschlechtert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Das Wetter hat sich verschlechtert.",
     "ornek_turkce": "Hava kötüleşti."},

    {"almanca": "beeindrucken", "turkce": "etkilemek, iz bırakmak", "tur": "fiil",
     "prateritum": "beeindruckte", "partizip2": "beeindruckt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Seine Rede hat mich sehr beeindruckt.",
     "ornek_turkce": "Konuşması beni çok etkiledi."},

    {"almanca": "beschreiben", "turkce": "tarif etmek, tanımlamak, betimlemek", "tur": "fiil",
     "prateritum": "beschrieb", "partizip2": "beschrieben", "perfekt_yardimci": "haben", "verb_typ": "stark",
     "ornek_almanca": "Kannst du das Problem genauer beschreiben?",
     "ornek_turkce": "Problemi daha ayrıntılı tarif edebilir misin?"},

    {"almanca": "definieren", "turkce": "tanımlamak, belirlemek", "tur": "fiil",
     "prateritum": "definierte", "partizip2": "definiert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Wie würdest du Glück definieren?",
     "ornek_turkce": "Mutluluğu nasıl tanımlarsın?"},

    {"almanca": "analysieren", "turkce": "analiz etmek, incelemek, çözümlemek", "tur": "fiil",
     "prateritum": "analysierte", "partizip2": "analysiert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Wir müssen die Situation genau analysieren.",
     "ornek_turkce": "Durumu dikkatli analiz etmeliyiz."},

    {"almanca": "organisieren", "turkce": "düzenlemek, organize etmek", "tur": "fiil",
     "prateritum": "organisierte", "partizip2": "organisiert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Wer organisiert das nächste Treffen?",
     "ornek_turkce": "Bir sonraki toplantıyı kim organize ediyor?"},

    {"almanca": "durchführen", "turkce": "gerçekleştirmek, uygulamak, yürütmek", "tur": "fiil",
     "prateritum": "führte durch", "partizip2": "durchgeführt", "perfekt_yardimci": "haben",
     "verb_typ": "schwach", "trennbar": True, "trennbar_prefix": "durch",
     "ornek_almanca": "Das Experiment wurde erfolgreich durchgeführt.",
     "ornek_turkce": "Deney başarıyla gerçekleştirildi."},

    {"almanca": "abschließen", "turkce": "bitirmek, tamamlamak; kilitlemek; anlaşmak", "tur": "fiil",
     "prateritum": "schloss ab", "partizip2": "abgeschlossen", "perfekt_yardimci": "haben",
     "verb_typ": "stark", "trennbar": True, "trennbar_prefix": "ab",
     "ornek_almanca": "Sie hat ihr Studium abgeschlossen.",
     "ornek_turkce": "Üniversitesini tamamladı."},

    {"almanca": "liefern", "turkce": "teslim etmek, göndermek, sağlamak", "tur": "fiil",
     "prateritum": "lieferte", "partizip2": "geliefert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Das Paket wird morgen geliefert.",
     "ornek_turkce": "Paket yarın teslim edilecek."},

    {"almanca": "empfangen", "turkce": "almak; karşılamak; misafir kabul etmek", "tur": "fiil",
     "prateritum": "empfing", "partizip2": "empfangen", "perfekt_yardimci": "haben", "verb_typ": "stark",
     "ornek_almanca": "Er empfing die Gäste herzlich.",
     "ornek_turkce": "Misafirleri sıcak bir şekilde karşıladı."},

    {"almanca": "ankommen", "turkce": "varmak, ulaşmak; karşılanmak", "tur": "fiil",
     "prateritum": "kam an", "partizip2": "angekommen", "perfekt_yardimci": "sein",
     "verb_typ": "stark", "trennbar": True, "trennbar_prefix": "an",
     "ornek_almanca": "Der Zug kam pünktlich an.",
     "ornek_turkce": "Tren zamanında geldi."},

    {"almanca": "abfahren", "turkce": "hareket etmek, yola çıkmak; kalkmak", "tur": "fiil",
     "prateritum": "fuhr ab", "partizip2": "abgefahren", "perfekt_yardimci": "sein",
     "verb_typ": "stark", "trennbar": True, "trennbar_prefix": "ab",
     "ornek_almanca": "Der Bus fährt in zehn Minuten ab.",
     "ornek_turkce": "Otobüs on dakika içinde kalkıyor."},

    {"almanca": "übernachten", "turkce": "geceyi geçirmek, gecelemek", "tur": "fiil",
     "prateritum": "übernachtete", "partizip2": "übernachtet", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Wir haben in einem Hotel übernachtet.",
     "ornek_turkce": "Bir otelde kaldık."},

    {"almanca": "backen", "turkce": "pişirmek (fırında); ekmek yapmak", "tur": "fiil",
     "prateritum": "backte", "partizip2": "gebacken", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie bäckt jeden Sonntag Kuchen.",
     "ornek_turkce": "Her pazar kek pişiriyor."},

    {"almanca": "braten", "turkce": "kızartmak, kavurmak, ızgara yapmak", "tur": "fiil",
     "prateritum": "briet", "partizip2": "gebraten", "perfekt_yardimci": "haben", "verb_typ": "stark",
     "ornek_almanca": "Er brät Fleisch in der Pfanne.",
     "ornek_turkce": "Tavada et kızartıyor."},

    {"almanca": "würzen", "turkce": "baharatlamak, çeşni katmak", "tur": "fiil",
     "prateritum": "würzte", "partizip2": "gewürzt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie würzt die Suppe mit Salz und Pfeffer.",
     "ornek_turkce": "Çorbayı tuz ve biberle baharatlıyor."},

    {"almanca": "aufräumen", "turkce": "toplamak, düzenlemek, temizlemek", "tur": "fiil",
     "prateritum": "räumte auf", "partizip2": "aufgeräumt", "perfekt_yardimci": "haben",
     "verb_typ": "schwach", "trennbar": True, "trennbar_prefix": "auf",
     "ornek_almanca": "Räum bitte dein Zimmer auf.",
     "ornek_turkce": "Lütfen odanı topla."},

    {"almanca": "putzen", "turkce": "temizlemek, silmek; diş fırçalamak", "tur": "fiil",
     "prateritum": "putzte", "partizip2": "geputzt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Er putzt jeden Morgen die Zähne.",
     "ornek_turkce": "Her sabah dişlerini fırçalar."},

    {"almanca": "bügeln", "turkce": "ütülemek", "tur": "fiil",
     "prateritum": "bügelte", "partizip2": "gebügelt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Ich bügle mein Hemd.",
     "ornek_turkce": "Gömleğimi ütülüyorum."},

    {"almanca": "nähen", "turkce": "dikmek, dikiş dikmek", "tur": "fiil",
     "prateritum": "nähte", "partizip2": "genäht", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie näht ein Kleid für ihre Tochter.",
     "ornek_turkce": "Kızı için bir elbise dikyor."},

    {"almanca": "reparieren", "turkce": "tamir etmek, onarmak", "tur": "fiil",
     "prateritum": "reparierte", "partizip2": "repariert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Der Mechaniker repariert das Auto.",
     "ornek_turkce": "Tamirci arabayı tamir ediyor."},

    {"almanca": "montieren", "turkce": "monte etmek, kurmak, yerleştirmek", "tur": "fiil",
     "prateritum": "montierte", "partizip2": "montiert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Die Arbeiter montieren die Maschine.",
     "ornek_turkce": "İşçiler makineyi monte ediyor."},

    {"almanca": "programmieren", "turkce": "programlamak, kod yazmak", "tur": "fiil",
     "prateritum": "programmierte", "partizip2": "programmiert", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Er programmiert eine neue App.",
     "ornek_turkce": "Yeni bir uygulama programlıyor."},

    {"almanca": "drucken", "turkce": "yazdırmak, basmak", "tur": "fiil",
     "prateritum": "druckte", "partizip2": "gedruckt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Ich drucke das Dokument aus.",
     "ornek_turkce": "Belgeyi yazdırıyorum."},

    {"almanca": "streicheln", "turkce": "okşamak, sıvazlamak", "tur": "fiil",
     "prateritum": "streichelte", "partizip2": "gestreichelt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie streichelte den Hund sanft.",
     "ornek_turkce": "Köpeği nazikçe okşadı."},

    {"almanca": "umarmen", "turkce": "sarılmak, kucaklamak", "tur": "fiil",
     "prateritum": "umarmte", "partizip2": "umarmt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Er umarmte seine Mutter herzlich.",
     "ornek_turkce": "Annesine sıkıca sarıldı."},

    {"almanca": "küssen", "turkce": "öpmek", "tur": "fiil",
     "prateritum": "küsste", "partizip2": "geküsst", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie küssten sich zum Abschied.",
     "ornek_turkce": "Veda ederken öpüştüler."},

    {"almanca": "versöhnen", "turkce": "barıştırmak; barışmak", "tur": "fiil",
     "prateritum": "versöhnte", "partizip2": "versöhnt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Sie haben sich nach dem Streit versöhnt.",
     "ornek_turkce": "Tartışmanın ardından barıştılar."},

    {"almanca": "erlauben", "turkce": "izin vermek, müsaade etmek", "tur": "fiil",
     "prateritum": "erlaubte", "partizip2": "erlaubt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Darf ich fragen? — Erlaubt sich jemand einen Witz?",
     "ornek_turkce": "Sorabilir miyim? — Biri şaka yapıyor mu?"},

    {"almanca": "schweben", "turkce": "süzülmek; askıda durmak; havada uçmak", "tur": "fiil",
     "prateritum": "schwebte", "partizip2": "geschwebt", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Der Adler schwebt über den Bergen.",
     "ornek_turkce": "Kartal dağların üzerinde süzülüyor."},

    {"almanca": "rutschen", "turkce": "kaymak; sürçmek", "tur": "fiil",
     "prateritum": "rutschte", "partizip2": "gerutscht", "perfekt_yardimci": "sein", "verb_typ": "schwach",
     "ornek_almanca": "Sie rutschte auf dem Eis aus.",
     "ornek_turkce": "Buzda kaydı."},

    {"almanca": "blühen", "turkce": "çiçek açmak; gelişmek, serpilmek", "tur": "fiil",
     "prateritum": "blühte", "partizip2": "geblüht", "perfekt_yardimci": "haben", "verb_typ": "schwach",
     "ornek_almanca": "Im Frühling blühen die Kirschbäume.",
     "ornek_turkce": "İlkbaharda kiraz ağaçları çiçek açar."},

    {"almanca": "reifen", "turkce": "olgunlaşmak; pişmek (meyve)", "tur": "fiil",
     "prateritum": "reifte", "partizip2": "gereift", "perfekt_yardimci": "sein", "verb_typ": "schwach",
     "ornek_almanca": "Die Tomaten reifen in der Sonne.",
     "ornek_turkce": "Domatesler güneşte olgunlaşıyor."},
]


# ─────────────────────────────────────────────────────────────────────────────
# YARDIMCI
# ─────────────────────────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").casefold()).strip()


def build_lookup(dictionary: list[dict]) -> dict[str, int]:
    result: dict[str, int] = {}
    for i, r in enumerate(dictionary):
        k = normalize(r.get("almanca", ""))
        if k and k not in result:
            result[k] = i
    return result


def wiktionary_fetch(word: str) -> dict:
    """Wiktionary DE API'den Türkçe çevirisi ve Almanca tanım çekmeye çalışır."""
    try:
        url = (
            "https://de.wiktionary.org/w/api.php?action=parse&page="
            + urllib.parse.quote(word)
            + "&format=json&prop=wikitext&redirects"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "AlmancaSozluk/1.0 (educational)"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        wikitext = (data.get("parse") or {}).get("wikitext", {}).get("*", "")
        return {"wikitext": wikitext}
    except Exception:
        return {}


def extract_tr_from_wikitext(wikitext: str) -> str:
    """Wiktionary wikitext'inden Türkçe çevirileri çeker."""
    lines = wikitext.splitlines()
    in_tr_section = False
    results: list[str] = []
    for line in lines:
        if "{{Übersetzungen}}" in line or "{{Ü-Tabelle" in line:
            in_tr_section = True
        if in_tr_section and ("{{Ü|tr|" in line or "{{Ü2|tr|" in line):
            matches = re.findall(r"\{\{Ü[12]?\|tr\|([^}|]+)", line)
            for m in matches:
                clean = m.strip().rstrip("|")
                if clean:
                    results.append(clean)
        if in_tr_section and line.startswith("==") and "Türkisch" not in line:
            if results:
                break
    return "; ".join(dict.fromkeys(results)) if results else ""


# ─────────────────────────────────────────────────────────────────────────────
# ANA İŞLEM
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 65)
    print("enrich_add_missing_basic.py")
    print(f"  {len(ENTRIES)} kelime eklenecek / güncellenecek")
    print("=" * 65)

    dictionary: list[dict] = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    lookup = build_lookup(dictionary)

    added_new   = 0
    updated     = 0
    wiki_hits   = 0

    for entry in ENTRIES:
        word = entry["almanca"]
        key  = normalize(word)

        if key in lookup:
            # Kayıt var — sadece boş alanları doldur
            idx = lookup[key]
            rec = dictionary[idx]
            changed = False

            for field in ("turkce","prateritum","partizip2","perfekt_yardimci",
                          "verb_typ","trennbar","trennbar_prefix","ornek_almanca","ornek_turkce"):
                if field in entry and not rec.get(field):
                    rec[field] = entry[field]
                    changed = True

            # fiil_kaliplari: yeni olanları ekle
            new_kp = entry.get("fiil_kaliplari") or []
            existing_kp: list[dict] = list(rec.get("fiil_kaliplari") or [])
            existing_keys = {normalize(k.get("kalip","")) for k in existing_kp}
            for kp in new_kp:
                kn = normalize(kp.get("kalip",""))
                if kn and kn not in existing_keys:
                    existing_kp.append(kp)
                    existing_keys.add(kn)
                    changed = True
            if new_kp:
                rec["fiil_kaliplari"] = existing_kp

            if changed:
                updated += 1
                print(f"  ~ güncellendi : {word}")
            else:
                print(f"  = zaten tam   : {word}")
            continue

        # Kayıt yok — Wiktionary'den ekstra bilgi almayı dene
        turkce = entry.get("turkce", "")
        if not turkce:
            time.sleep(0.3)
            wiki = wiktionary_fetch(word.replace("sich ", ""))
            wt   = wiki.get("wikitext", "")
            if wt:
                wiki_tr = extract_tr_from_wikitext(wt)
                if wiki_tr:
                    turkce = wiki_tr
                    wiki_hits += 1

        new_record: dict = {
            "almanca":              word,
            "artikel":              entry.get("artikel", ""),
            "turkce":               turkce,
            "aciklama_turkce":      "",
            "tur":                  entry.get("tur", "fiil"),
            "ornek_almanca":        entry.get("ornek_almanca", ""),
            "ornek_turkce":         entry.get("ornek_turkce", ""),
            "kaynak":               SOURCE_BASIC,
            "not":                  "",
            "kaynak_url":           "",
            "ceviri_durumu":        "kaynak-izli",
            "ornekler":             [],
            "sinonim":              [],
            "antonim":              [],
            "kelime_ailesi":        [],
            "ilgili_kayitlar":      [],
            "anlamlar":             [],
            "fiil_kaliplari":       entry.get("fiil_kaliplari", []),
            "prateritum":           entry.get("prateritum", ""),
            "partizip2":            entry.get("partizip2", ""),
            "perfekt_yardimci":     entry.get("perfekt_yardimci", ""),
            "verb_typ":             entry.get("verb_typ", ""),
            "trennbar":             entry.get("trennbar", False),
            "trennbar_prefix":      entry.get("trennbar_prefix", ""),
            "cekimler":             {},
            "ceviri_kaynaklari":    [],
            "ceviri_inceleme_notu": "",
        }
        dictionary.append(new_record)
        lookup[key] = len(dictionary) - 1
        added_new += 1
        print(f"  + eklendi     : {word}  ({turkce[:50]})")

    # Kaydet
    DICT_PATH.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n{'=' * 65}")
    print("SONUÇ")
    print(f"  Yeni eklenen  : {added_new}")
    print(f"  Güncellenen   : {updated}")
    print(f"  Wikidata hit  : {wiki_hits}")
    print(f"  Toplam kayıt  : {len(dictionary):,}")
    print(f"{'=' * 65}")
    print(f"\nKaydedildi: {DICT_PATH}")


if __name__ == "__main__":
    main()
