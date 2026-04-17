#!/usr/bin/env python3
"""
enrich_verben_mit_praepositionen.py
=====================================
Almanca "Verben mit Präpositionen" kalıplarını sözlüğe ekler.

Kaynaklar:
  1. PONS Praxis-Grammatik PDF (111 kalıp, örnek cümleli)
  2. Genel dilbilgisi bilgi tabanı (ek kalıplar)

Her kalıp için:
  kalip       : "auf etw. (A) achten"
  turkce      : Türkçe açıklama
  ornek_almanca: Almanca örnek cümle
  ornek_turkce : boş (isteğe bağlı sonradan doldurulabilir)
  kaynak      : "PONS Praxis-Grammatik / VmP-Veritabanı"
"""

from __future__ import annotations
import json, re, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICT_PATH    = PROJECT_ROOT / "output" / "dictionary.json"
SOURCE_PONS  = "PONS Praxis-Grammatik (Verben mit Präpositionen)"
SOURCE_DB    = "VmP-Veritabanı (Verben mit Präpositionen)"

# ─────────────────────────────────────────────────────────────────────────────
# VERİ: (verb, reflexiv, präposition, kasus, kalip_str, turkce, ornek_almanca)
# reflexiv = True  → "sich XXX"
# ─────────────────────────────────────────────────────────────────────────────

PATTERNS: list[tuple] = [
    # Verb, sich?, Prep, Kasus, Kalıp metni, Türkçe, Örnek (Almanca), Kaynak
    # ── PONS PDF (111 kalıp) ─────────────────────────────────────────────────
    ("abhängen",     False, "von",   "D", "von etw./jdm. (D) abhängen",     "-e bağlı olmak",                          "Ob wir fahren, hängt vom Wetter ab.",                       SOURCE_PONS),
    ("achten",       False, "auf",   "A", "auf etw./jdn. (A) achten",        "-e dikkat etmek",                         "Bitte achte auf den neuen Mantel.",                          SOURCE_PONS),
    ("anfangen",     False, "mit",   "D", "mit etw. (D) anfangen",           "-e başlamak",                             "Ich fange mit der Übung an.",                                SOURCE_PONS),
    ("ankommen",     False, "auf",   "A", "auf etw. (A) ankommen",           "-e bağlı olmak, -den ibaret olmak",       "Es kommt auf den richtigen Preis an.",                       SOURCE_PONS),
    ("antworten",    False, "auf",   "A", "auf etw. (A) antworten",          "-e cevap vermek",                         "Bitte antworten Sie heute auf den Brief.",                   SOURCE_PONS),
    ("ärgern",       True,  "über",  "A", "sich über etw./jdn. (A) ärgern",  "-e kızmak, sinirlenm",                    "Wir ärgern uns über den Regen.",                             SOURCE_PONS),
    ("aufhören",     False, "mit",   "D", "mit etw. (D) aufhören",           "-i bırakmak, durmak",                     "Er hört um 17 Uhr mit der Arbeit auf.",                      SOURCE_PONS),
    ("aufpassen",    False, "auf",   "A", "auf etw./jdn. (A) aufpassen",     "-e dikkat etmek, bakmak",                 "Ein Babysitter passt auf kleine Kinder auf.",                SOURCE_PONS),
    ("aufregen",     True,  "über",  "A", "sich über etw./jdn. (A) aufregen","sinirlenm, heyecanlanm",                  "Deutsche regen sich über Unpünktlichkeit auf.",              SOURCE_PONS),
    ("ausgeben",     False, "für",   "A", "etw. für etw. (A) ausgeben",      "-e harcamak",                             "Manche geben viel Geld für Schuhe aus.",                     SOURCE_PONS),
    ("bedanken",     True,  "bei",   "D", "sich bei jdm. (D) bedanken",      "birine teşekkür etmek",                   "Ich bedanke mich herzlich bei dir.",                         SOURCE_PONS),
    ("bedanken",     True,  "für",   "A", "sich für etw. (A) bedanken",      "-den dolayı teşekkür etmek",              "Martin bedankt sich für das Geschenk.",                      SOURCE_PONS),
    ("beginnen",     False, "mit",   "D", "mit etw. (D) beginnen",           "-e başlamak",                             "Wir beginnen pünktlich mit dem Deutschkurs.",                SOURCE_PONS),
    ("bemühen",      True,  "um",    "A", "sich um etw. (A) bemühen",        "için çaba göstermek, uğraşmak",           "Karla bemüht sich um eine Arbeit.",                          SOURCE_PONS),
    ("berichten",    False, "über",  "A", "über etw. (A) berichten",         "hakkında haber yapmak, rapor vermek",     "Der Reporter berichtet über die Wahlen.",                    SOURCE_PONS),
    ("beschäftigen", True,  "mit",   "D", "sich mit etw./jdm. (D) beschäftigen","ile ilgilenmek",                      "Ich beschäftige mich gern mit Pflanzen.",                    SOURCE_PONS),
    ("beschweren",   True,  "bei",   "D", "sich bei jdm. (D) beschweren",    "birine şikayet etmek",                    "Der Gast beschwert sich beim Kellner.",                      SOURCE_PONS),
    ("bestehen",     False, "aus",   "D", "aus etw. (D) bestehen",           "-den oluşmak",                            "Eheringe bestehen aus Gold.",                                SOURCE_PONS),
    ("bestehen",     False, "auf",   "D", "auf etw. (D) bestehen",           "-de ısrar etmek",                         "Ich bestehe auf sofortiger Bezahlung.",                      SOURCE_PONS),
    ("beteiligen",   True,  "an",    "D", "sich an etw. (D) beteiligen",     "-e katılmak",                             "Viele Studenten beteiligen sich an den Streiks.",             SOURCE_PONS),
    ("bewerben",     True,  "bei",   "D", "sich bei jdm./etw. (D) bewerben", "bir yere başvurmak",                      "Er bewirbt sich bei einer Bäckerei.",                        SOURCE_PONS),
    ("bewerben",     True,  "um",    "A", "sich um etw. (A) bewerben",       "bir pozisyon için başvurmak",             "Sie bewirbt sich um eine Stelle als Sekretärin.",             SOURCE_PONS),
    ("beziehen",     True,  "auf",   "A", "sich auf etw. (A) beziehen",      "-e atıfta bulunmak, -i kastetmek",        "Meine Frage bezieht sich auf Ihr Angebot.",                  SOURCE_PONS),
    ("bitten",       False, "um",    "A", "jdn. um etw. (A) bitten",         "birinden bir şey istemek, rica etmek",    "Der Redner bittet um Aufmerksamkeit.",                       SOURCE_PONS),
    ("danken",       False, "für",   "A", "jdm. für etw. (A) danken",        "-den dolayı teşekkür etmek",              "Sam dankt für Ritas Hilfe.",                                  SOURCE_PONS),
    ("denken",       False, "an",    "A", "an etw./jdn. (A) denken",         "-i düşünmek, -i hatırlamak",              "Maria denkt oft an den Urlaub.",                             SOURCE_PONS),
    ("diskutieren",  False, "über",  "A", "über etw. (A) diskutieren",       "hakkında tartışmak",                      "Das Kabinett diskutiert über eine neue Steuer.",              SOURCE_PONS),
    ("einladen",     False, "zu",    "D", "jdn. zu etw. (D) einladen",       "-e davet etmek",                          "Ich lade dich zu meinem Geburtstag ein.",                    SOURCE_PONS),
    ("entscheiden",  True,  "für",   "A", "sich für etw./jdn. (A) entscheiden","seçmek, karar kılmak",                 "Kinder entscheiden sich gern für Schokolade.",               SOURCE_PONS),
    ("entschließen", True,  "zu",    "D", "sich zu etw. (D) entschließen",   "-e karar vermek",                         "Karl entschließt sich zu einem Studium.",                    SOURCE_PONS),
    ("entschuldigen",True,  "bei",   "D", "sich bei jdm. (D) entschuldigen", "birine özür dilemek",                     "Tom entschuldigt sich bei ihrem Mann.",                      SOURCE_PONS),
    ("entschuldigen",True,  "für",   "A", "sich für etw. (A) entschuldigen", "-den dolayı özür dilemek",                "Ich entschuldige mich für das Verhalten meiner Katze.",      SOURCE_PONS),
    ("erholen",      True,  "von",   "D", "sich von etw./jdm. (D) erholen",  "-den dinlenmek, iyileşmek",               "Von dem Schock muss ich mich erst erholen.",                 SOURCE_PONS),
    ("erinnern",     True,  "an",    "A", "sich an etw./jdn. (A) erinnern",  "-i hatırlamak",                           "Wir erinnern uns gern an unser erstes Ehejahr.",             SOURCE_PONS),
    ("erkennen",     False, "an",    "D", "jdn./etw. an etw. (D) erkennen",  "-den tanımak",                            "Man erkennt Pinocchio an seiner langen Nase.",               SOURCE_PONS),
    ("erkundigen",   True,  "nach",  "D", "sich nach etw./jdm. (D) erkundigen","hakkında bilgi edinmek, sormak",        "Oma erkundigt sich oft nach meinen Plänen.",                SOURCE_PONS),
    ("erschrecken",  False, "über",  "A", "über etw./jdn. (A) erschrecken",  "-den korkmak, irkilmek",                  "Der Koch erschrickt über eine Maus.",                        SOURCE_PONS),
    ("erzählen",     False, "über",  "A", "über etw. (A) erzählen",          "hakkında anlatmak",                       "Ein Ostberliner erzählt über sein Leben in der ehemaligen DDR.", SOURCE_PONS),
    ("erzählen",     False, "von",   "D", "von etw. (D) erzählen",           "-i anlatmak, -den bahsetmek",             "Der Bischoff erzählt von der Reise nach Rom.",               SOURCE_PONS),
    ("fragen",       False, "nach",  "D", "nach etw. (D) fragen",            "-i sormak",                               "Die Journalistin fragt nach den Konsequenzen.",               SOURCE_PONS),
    ("freuen",       True,  "auf",   "A", "sich auf etw./jdn. (A) freuen",   "-i dört gözle beklemek",                  "Kinder freuen sich auf die Ferien.",                         SOURCE_PONS),
    ("freuen",       True,  "über",  "A", "sich über etw./jdn. (A) freuen",  "-den sevinmek, memnun olmak",             "Jeder freut sich über eine Gehaltserhöhung.",                SOURCE_PONS),
    ("gehen",        False, "um",    "A", "um etw. (A) gehen",               "söz konusu olmak, -e bağlı olmak",        "Immer geht es um Geld.",                                     SOURCE_PONS),
    ("gehören",      False, "zu",    "D", "zu etw./jdm. (D) gehören",        "-e ait olmak, -e mensup olmak",           "Das Elsass gehört zu Frankreich.",                           SOURCE_PONS),
    ("gewöhnen",     True,  "an",    "A", "sich an etw./jdn. (A) gewöhnen",  "-e alışmak",                              "Ich kann mich nicht an die Zeitumstellung gewöhnen.",        SOURCE_PONS),
    ("glauben",      False, "an",    "A", "an etw./jdn. (A) glauben",        "-e inanmak",                              "Teenager glauben an die große Liebe.",                       SOURCE_PONS),
    ("gratulieren",  False, "zu",    "D", "jdm. zu etw. (D) gratulieren",    "-den dolayı tebrik etmek",                "Wir gratulieren dir zum 18. Geburtstag.",                   SOURCE_PONS),
    ("halten",       False, "für",   "A", "etw./jdn. für etw. (A) halten",   "-i olarak kabul etmek, saymak",           "Ich halte das für keine gute Idee.",                         SOURCE_PONS),
    ("halten",       False, "von",   "D", "von etw./jdm. (D) halten",        "-e değer vermek; -den hoşlanmak",         "Kinder halten nicht viel von Ordnung.",                      SOURCE_PONS),
    ("handeln",      True,  "um",    "A", "sich um etw. (A) handeln",        "söz konusu olmak",                        "Es handelt sich nicht um Originalsoftware.",                 SOURCE_PONS),
    ("handeln",      False, "von",   "D", "von etw. (D) handeln",            "hakkında olmak (kitap/film)",             "Märchen handeln von Gut und Böse.",                          SOURCE_PONS),
    ("helfen",       False, "bei",   "D", "jdm. bei etw. (D) helfen",        "-de yardım etmek",                        "Kann ich dir beim Tischdecken helfen?",                      SOURCE_PONS),
    ("hindern",      False, "an",    "D", "jdn. an etw. (D) hindern",        "-den alıkoymak, engel olmak",             "Ein langsamer Fahrer hindert Greta am Überholen.",           SOURCE_PONS),
    ("hoffen",       False, "auf",   "A", "auf etw. (A) hoffen",             "-i ummak, beklemek",                      "Im März hoffen alle auf warme Frühlingstage.",               SOURCE_PONS),
    ("hören",        False, "von",   "D", "von jdm./etw. (D) hören",         "-den haber almak, duymak",                "Ich habe seit Sonntag nichts von Piet gehört.",              SOURCE_PONS),
    ("informieren",  True,  "über",  "A", "sich über etw. (A) informieren",  "hakkında bilgi edinmek",                  "Auf der Messe kann man sich über die neue Technologie informieren.", SOURCE_PONS),
    ("interessieren",True,  "für",   "A", "sich für etw./jdn. (A) interessieren","ile ilgilenmek",                     "Monika interessiert sich für ein Smartphone.",               SOURCE_PONS),
    ("klagen",       False, "über",  "A", "über etw./jdn. (A) klagen",       "-den yakınmak, şikayet etmek",            "Tim klagt häufig über Kopfschmerzen.",                       SOURCE_PONS),
    ("kämpfen",      False, "für",   "A", "für etw. (A) kämpfen",            "için mücadele etmek",                     "Die Gewerkschaft kämpft für höhere Löhne.",                  SOURCE_PONS),
    ("kommen",       False, "zu",    "D", "zu etw. (D) kommen",              "-e gelmek, yaşanmak",                     "In der Besprechung kam es zu einem Streit.",                 SOURCE_PONS),
    ("konzentrieren",True,  "auf",   "A", "sich auf etw. (A) konzentrieren", "-e yoğunlaşmak, odaklanmak",              "Karl konzentriert sich auf seine Hausaufgaben.",             SOURCE_PONS),
    ("kümmern",      True,  "um",    "A", "sich um etw./jdn. (A) kümmern",   "ile ilgilenmek, bakmak",                  "Im Pflegeheim kümmert man sich um alte Leute.",              SOURCE_PONS),
    ("lachen",       False, "über",  "A", "über etw./jdn. (A) lachen",       "-e gülmek",                               "Über einen guten Witz muss man laut lachen.",                SOURCE_PONS),
    ("leiden",       False, "an",    "D", "an etw. (D) leiden",              "-den muzdarip olmak (hastalık)",           "Jeder fünfte Manager leidet an Burn-out.",                  SOURCE_PONS),
    ("leiden",       False, "unter", "D", "unter etw. (D) leiden",           "-den acı çekmek",                         "Kaffeetrinker leiden unter Schlafproblemen.",                SOURCE_PONS),
    ("nachdenken",   False, "über",  "A", "über etw. (A) nachdenken",        "hakkında düşünmek",                       "Beamte müssen nicht über ihre Rente nachdenken.",            SOURCE_PONS),
    ("protestieren", False, "gegen", "A", "gegen etw./jdn. (A) protestieren","karşı protesto etmek",                    "Viele Menschen protestieren gegen Atomkraft.",               SOURCE_PONS),
    ("rechnen",      False, "mit",   "D", "mit etw./jdm. (D) rechnen",       "-i hesaba katmak, beklemek",              "Im Januar muss man mit Schnee rechnen.",                     SOURCE_PONS),
    ("reden",        False, "über",  "A", "über etw. (A) reden",             "hakkında konuşmak",                       "Deine Mutter redet gern über Krankheiten.",                  SOURCE_PONS),
    ("reden",        False, "von",   "D", "von etw. (D) reden",              "-den bahsetmek",                          "Großvater redet von den guten alten Zeiten.",                SOURCE_PONS),
    ("riechen",      False, "nach",  "D", "nach etw. (D) riechen",           "-in kokusu gelmek",                       "Hier riecht es nach Kuchen.",                                SOURCE_PONS),
    ("sagen",        False, "über",  "A", "über etw./jdn. (A) sagen",        "hakkında söylemek",                       "Brigitte sagt über Dietmar, dass er oft lügt.",              SOURCE_PONS),
    ("sagen",        False, "zu",    "D", "zu etw. (D) sagen",               "hakkında ne düşünmek",                    "Was sagst du zu meinem neuen Haarschnitt?",                  SOURCE_PONS),
    ("schicken",     False, "an",    "A", "etw. an jdn. (A) schicken",       "-e göndermek",                            "Die E-Mail schicke ich dir morgen.",                         SOURCE_PONS),
    ("schicken",     False, "zu",    "D", "jdn. zu jdm. (D) schicken",       "birine göndermek",                        "Der Arzt schickt den Patienten zu einem Spezialisten.",      SOURCE_PONS),
    ("schimpfen",    False, "über",  "A", "über etw./jdn. (A) schimpfen",    "-i yermek, şikayet etmek",                "Alle schimpfen über den Regen.",                             SOURCE_PONS),
    ("schmecken",    False, "nach",  "D", "nach etw. (D) schmecken",         "-in tadını vermek",                       "Muscheln schmecken nach Meerwasser.",                        SOURCE_PONS),
    ("schreiben",    False, "an",    "A", "an jdn. (A) schreiben",           "-e yazmak",                               "Bitte schreibe noch heute an deine Mutter.",                 SOURCE_PONS),
    ("schützen",     True,  "vor",   "D", "sich/etw. vor etw. (D) schützen", "-den korunmak",                           "Den Computer muss man vor Hackern schützen.",                SOURCE_PONS),
    ("sein",         False, "für",   "A", "für etw. (A) sein",               "-den yana olmak",                         "Ich bin für die Abschaffung der Kinderarbeit.",              SOURCE_PONS),
    ("sein",         False, "gegen", "A", "gegen etw. (A) sein",             "-e karşı olmak",                          "Viele sind gegen Steuererhöhungen.",                         SOURCE_PONS),
    ("sorgen",       False, "für",   "A", "für etw./jdn. (A) sorgen",        "-e bakmak, sağlamak",                     "Kinder müssen im Alter für ihre Eltern sorgen.",             SOURCE_PONS),
    ("sprechen",     False, "mit",   "D", "mit jdm. (D) sprechen",           "biriyle konuşmak",                        "Ich spreche noch einmal mit deinem Vater.",                  SOURCE_PONS),
    ("sprechen",     False, "über",  "A", "über etw. (A) sprechen",          "hakkında konuşmak",                       "Lass uns über deine Zukunft sprechen.",                      SOURCE_PONS),
    ("sterben",      False, "an",    "D", "an etw. (D) sterben",             "-den ölmek",                              "Zwei Deutsche sind an der Grippe gestorben.",                SOURCE_PONS),
    ("streiten",     False, "mit",   "D", "mit jdm. (D) streiten",           "biriyle kavga etmek",                     "Ich möchte nicht mit dir streiten.",                         SOURCE_PONS),
    ("streiten",     False, "über",  "A", "über etw. (A) streiten",          "hakkında kavga etmek",                    "Die USA und Deutschland streiten über eine neue Strategie.", SOURCE_PONS),
    ("teilnehmen",   False, "an",    "D", "an etw. (D) teilnehmen",          "-e katılmak",                             "Nordkorea nimmt an der Fußball-WM teil.",                    SOURCE_PONS),
    ("telefonieren", False, "mit",   "D", "mit jdm. (D) telefonieren",       "biriyle telefon görüşmesi yapmak",        "Hast du schon mit dem Arzt telefoniert?",                    SOURCE_PONS),
    ("treffen",      True,  "mit",   "D", "sich mit jdm. (D) treffen",       "biriyle buluşmak",                        "Die Kanzlerin trifft sich täglich mit ihrem Pressesprecher.", SOURCE_PONS),
    ("treffen",      True,  "zu",    "D", "sich zu etw. (D) treffen",        "bir amaçla bir araya gelmek",             "Sie treffen sich nur zu einem kurzen Gespräch.",             SOURCE_PONS),
    ("überreden",    False, "zu",    "D", "jdn. zu etw. (D) überreden",      "-e ikna etmek",                           "Kann ich dich zu einem Glas Wein überreden?",               SOURCE_PONS),
    ("unterhalten",  True,  "mit",   "D", "sich mit jdm. (D) unterhalten",   "biriyle sohbet etmek",                    "Der Sänger unterhält sich mit dem Bassisten.",               SOURCE_PONS),
    ("unterhalten",  True,  "über",  "A", "sich über etw. (A) unterhalten",  "hakkında sohbet etmek",                   "Die Modedesigner unterhalten sich über die neuesten Trends.", SOURCE_PONS),
    ("verabreden",   True,  "mit",   "D", "sich mit jdm. (D) verabreden",    "biriyle randevulaşmak",                   "Heute verabrede ich mich mit einer Freundin.",               SOURCE_PONS),
    ("verabschieden",True,  "von",   "D", "sich von jdm. (D) verabschieden", "-den veda etmek",                         "Nun wollen wir uns von euch verabschieden.",                 SOURCE_PONS),
    ("vergleichen",  False, "mit",   "D", "etw./jdn. mit etw./jdm. (D) vergleichen","ile karşılaştırmak",              "Vergleichen Sie München mit Berlin.",                        SOURCE_PONS),
    ("verlassen",    True,  "auf",   "A", "sich auf etw./jdn. (A) verlassen","güvenmek, itimat etmek",                  "Auf mich kann man sich verlassen.",                          SOURCE_PONS),
    ("verlieben",    True,  "in",    "A", "sich in jdn./etw. (A) verlieben", "-e aşık olmak",                           "Britta hat sich in das alte Bauernhaus verliebt.",           SOURCE_PONS),
    ("verstehen",    True,  "mit",   "D", "sich mit jdm. (D) verstehen",     "biriyle iyi geçinmek",                    "Daniel versteht sich gut mit seinem Chef.",                  SOURCE_PONS),
    ("verstehen",    False, "von",   "D", "von etw. (D) verstehen",          "-den anlamak, -den bilmek",               "Verstehst du etwas von Elektrik?",                           SOURCE_PONS),
    ("vorbereiten",  True,  "auf",   "A", "sich auf etw. (A) vorbereiten",   "-e hazırlanmak",                          "Karl bereitet sich auf eine Präsentation vor.",              SOURCE_PONS),
    ("warnen",       False, "vor",   "D", "jdn. vor etw./jdm. (D) warnen",   "-den uyarmak",                            "Man hatte ihn vor den hohen Kosten gewarnt.",                SOURCE_PONS),
    ("warten",       False, "auf",   "A", "auf etw./jdn. (A) warten",        "beklemek",                                "Hier wartet man lange auf einen Bus.",                       SOURCE_PONS),
    ("wenden",       True,  "an",    "A", "sich an jdn. (A) wenden",         "birine başvurmak, müracaat etmek",        "Bitte wenden Sie sich an die Buchhaltung.",                 SOURCE_PONS),
    ("werden",       False, "zu",    "D", "zu etw. (D) werden",              "-e dönüşmek",                             "Unter null Grad wird Wasser zu Eis.",                        SOURCE_PONS),
    ("wissen",       False, "von",   "D", "von etw. (D) wissen",             "-den haberdar olmak",                     "Ich weiß nichts von neuen Computern für unser Team.",        SOURCE_PONS),
    ("wundern",      True,  "über",  "A", "sich über etw./jdn. (A) wundern", "-e şaşırmak",                             "Viele wundern sich über die plötzlich hohen Stromkosten.",  SOURCE_PONS),
    ("zuschauen",    False, "bei",   "D", "jdm. bei etw. (D) zuschauen",     "-i izlemek",                              "Kann ich dir bei der Reparatur zuschauen?",                  SOURCE_PONS),
    ("zusehen",      False, "bei",   "D", "jdm. bei etw. (D) zusehen",       "-i izlemek",                              "Willst du mir beim Kochen zusehen?",                         SOURCE_PONS),
    ("zweifeln",     False, "an",    "D", "an etw./jdm. (D) zweifeln",       "-den şüphe etmek, kuşku duymak",          "John zweifelt daran, dass sein Sohn die Wahrheit gesagt hat.", SOURCE_PONS),

    # ── EK KALIPLAR (dilbilgisi veritabanı) ──────────────────────────────────
    ("abraten",         False, "von",   "D", "von etw. (D) abraten",           "-i tavsiye etmemek, vazgeçirm",           "Er rät mir von diesem Plan ab.",                             SOURCE_DB),
    ("abstimmen",       False, "über",  "A", "über etw. (A) abstimmen",        "hakkında oy kullanmak",                   "Das Parlament stimmt über das Gesetz ab.",                   SOURCE_DB),
    ("absehen",         False, "von",   "D", "von etw. (D) absehen",           "-den vazgeçmek, görmezden gelmek",        "Wir sehen von einer Strafe ab.",                             SOURCE_DB),
    ("anknüpfen",       False, "an",    "A", "an etw. (A) anknüpfen",          "-e bağlamak, devam ettirmek",             "Der Redner knüpft an das vorherige Thema an.",               SOURCE_DB),
    ("anpassen",        True,  "an",    "A", "sich an etw. (A) anpassen",      "-e uyum sağlamak",                        "Man muss sich an neue Situationen anpassen.",                SOURCE_DB),
    ("anspielen",       False, "auf",   "A", "auf etw. (A) anspielen",         "-e ima etmek, işaret etmek",              "Worauf spielt er mit dieser Bemerkung an?",                  SOURCE_DB),
    ("auffordern",      False, "zu",    "D", "jdn. zu etw. (D) auffordern",    "-e davet etmek, çağırmak",                "Die Polizei forderte ihn zum Anhalten auf.",                 SOURCE_DB),
    ("ausgehen",        False, "von",   "D", "von etw. (D) ausgehen",          "-den yola çıkmak, saymak",                "Wir gehen davon aus, dass er kommt.",                        SOURCE_DB),
    ("auseinandersetzen",True, "mit",   "D", "sich mit etw./jdm. (D) auseinandersetzen","ile derinlemesine ilgilenmek",  "Wir setzen uns mit dem Problem auseinander.",                SOURCE_DB),
    ("beitragen",       False, "zu",    "D", "zu etw. (D) beitragen",          "-e katkıda bulunmak",                     "Jeder kann zum Umweltschutz beitragen.",                     SOURCE_DB),
    ("beklagen",        True,  "über",  "A", "sich über etw. (A) beklagen",    "-den yakınmak",                           "Er beklagt sich ständig über seinen Chef.",                  SOURCE_DB),
    ("beschränken",     True,  "auf",   "A", "sich auf etw. (A) beschränken",  "-le sınırlı kalmak",                      "Ich beschränke mich auf das Wesentliche.",                   SOURCE_DB),
    ("beurteilen",      False, "nach",  "D", "etw./jdn. nach etw. (D) beurteilen","-e göre değerlendirmek",              "Man sollte Menschen nicht nach dem Äußeren beurteilen.",     SOURCE_DB),
    ("einsetzen",       True,  "für",   "A", "sich für etw./jdn. (A) einsetzen","için çaba göstermek, savunmak",         "Sie setzt sich für Menschenrechte ein.",                     SOURCE_DB),
    ("einigen",         True,  "auf",   "A", "sich auf etw. (A) einigen",      "üzerinde uzlaşmak, anlaşmak",             "Wir haben uns auf einen Kompromiss geeinigt.",               SOURCE_DB),
    ("entwickeln",      True,  "zu",    "D", "sich zu etw. (D) entwickeln",    "-e dönüşmek, gelişmek",                  "Das Kind entwickelt sich zu einem selbstständigen Menschen.",SOURCE_DB),
    ("ergeben",         True,  "aus",   "D", "sich aus etw. (D) ergeben",      "-den kaynaklanmak",                       "Daraus ergibt sich ein Problem.",                            SOURCE_DB),
    ("ermutigen",       False, "zu",    "D", "jdn. zu etw. (D) ermutigen",     "-e cesaretlendirmek, teşvik etmek",       "Der Lehrer ermutigt die Schüler zur Teilnahme.",             SOURCE_DB),
    ("fürchten",        True,  "vor",   "D", "sich vor etw./jdm. (D) fürchten","korkmak",                                "Das Kind fürchtet sich vor der Dunkelheit.",                 SOURCE_DB),
    ("hinweisen",       False, "auf",   "A", "auf etw. (A) hinweisen",         "-e dikkat çekmek, işaret etmek",          "Der Arzt weist auf mögliche Nebenwirkungen hin.",            SOURCE_DB),
    ("identifizieren",  True,  "mit",   "D", "sich mit etw./jdm. (D) identifizieren","ile özdeşleştirmek",              "Ich identifiziere mich sehr mit dieser Figur.",              SOURCE_DB),
    ("investieren",     False, "in",    "A", "in etw. (A) investieren",        "-e yatırım yapmak",                       "Das Unternehmen investiert in neue Technologien.",           SOURCE_DB),
    ("jammern",         False, "über",  "A", "über etw. (A) jammern",          "-den yakınmak, sızlanmak",                "Er jammert immer über das Wetter.",                          SOURCE_DB),
    ("jubeln",          False, "über",  "A", "über etw. (A) jubeln",           "-den sevinmek, alkışlamak",               "Die Fans jubeln über den Sieg.",                             SOURCE_DB),
    ("kämpfen",         False, "gegen", "A", "gegen etw./jdn. (A) kämpfen",    "-e karşı savaşmak",                       "Sie kämpften gegen die Ungerechtigkeit.",                    SOURCE_DB),
    ("kämpfen",         False, "um",    "A", "um etw. (A) kämpfen",            "için mücadele etmek",                     "Die Mannschaft kämpft um den Titel.",                        SOURCE_DB),
    ("kommunizieren",   False, "mit",   "D", "mit jdm. (D) kommunizieren",     "biriyle iletişim kurmak",                 "Es ist wichtig, offen miteinander zu kommunizieren.",        SOURCE_DB),
    ("konkurrieren",    False, "mit",   "D", "mit jdm. (D) konkurrieren",      "biriyle rekabet etmek",                   "Die Firmen konkurrieren miteinander.",                       SOURCE_DB),
    ("lustig machen",   True,  "über",  "A", "sich über jdn./etw. (A) lustig machen","ile alay etmek",                  "Man sollte sich nicht über andere lustig machen.",           SOURCE_DB),
    ("orientieren",     True,  "an",    "D", "sich an etw./jdm. (D) orientieren","-e göre yönlenmek",                    "Wir orientieren uns an bewährten Methoden.",                 SOURCE_DB),
    ("passen",          False, "zu",    "D", "zu etw./jdm. (D) passen",        "-e uymak, yakışmak",                     "Diese Krawatte passt nicht zu deinem Hemd.",                 SOURCE_DB),
    ("profitieren",     False, "von",   "D", "von etw. (D) profitieren",       "-den faydalanmak",                        "Alle profitieren von der neuen Regelung.",                   SOURCE_DB),
    ("richten",         False, "an",    "A", "etw. an jdn. (A) richten",       "-e yöneltmek, yönelik olmak",             "Diese Frage richtet sich an alle Teilnehmer.",               SOURCE_DB),
    ("schwärmen",       False, "von",   "D", "von jdm./etw. (D) schwärmen",    "-i çok beğenmek, hayran olmak",           "Alle schwärmen von diesem Restaurant.",                      SOURCE_DB),
    ("sehnen",          True,  "nach",  "D", "sich nach etw./jdm. (D) sehnen", "özlemek, hasret çekmek",                 "Er sehnt sich nach seiner Heimat.",                          SOURCE_DB),
    ("stammen",         False, "aus",   "D", "aus etw. (D) stammen",           "-den gelmek, köken almak",                "Dieses Wort stammt aus dem Lateinischen.",                   SOURCE_DB),
    ("stoßen",          False, "auf",   "A", "auf etw. (A) stoßen",            "-le karşılaşmak",                         "Wir sind auf ein unerwartetes Problem gestoßen.",            SOURCE_DB),
    ("suchen",          False, "nach",  "D", "nach etw./jdm. (D) suchen",      "-i aramak",                               "Die Polizei sucht nach dem Täter.",                          SOURCE_DB),
    ("täuschen",        True,  "über",  "A", "sich über etw. (A) täuschen",    "-de yanılmak",                            "Da hast du dich getäuscht.",                                 SOURCE_DB),
    ("tendieren",       False, "zu",    "D", "zu etw. (D) tendieren",          "-e eğilimli olmak",                       "Er tendiert zu übertriebenen Aussagen.",                     SOURCE_DB),
    ("träumen",         False, "von",   "D", "von etw./jdm. (D) träumen",      "-i hayal etmek, rüyasını görmek",         "Sie träumt von einer besseren Welt.",                        SOURCE_DB),
    ("übereinstimmen",  False, "mit",   "D", "mit etw./jdm. (D) übereinstimmen","ile örtüşmek, uyuşmak",               "Seine Aussage stimmt mit den Fakten überein.",               SOURCE_DB),
    ("überzeugen",      False, "von",   "D", "jdn. von etw. (D) überzeugen",   "ikna etmek",                              "Er hat mich von seiner Idee überzeugt.",                     SOURCE_DB),
    ("urteilen",        False, "über",  "A", "über jdn./etw. (A) urteilen",    "hakkında hüküm vermek",                   "Man sollte nicht vorschnell über andere urteilen.",          SOURCE_DB),
    ("vertrauen",       False, "auf",   "A", "auf etw./jdn. (A) vertrauen",    "-e güvenmek",                             "Du kannst auf mich vertrauen.",                              SOURCE_DB),
    ("verweisen",       False, "auf",   "A", "auf etw./jdn. (A) verweisen",    "-e yönlendirmek, işaret etmek",           "Der Autor verweist auf frühere Studien.",                    SOURCE_DB),
    ("verzichten",      False, "auf",   "A", "auf etw. (A) verzichten",        "-den vazgeçmek",                          "Ich verzichte auf Zucker in meinem Kaffee.",                 SOURCE_DB),
    ("wechseln",        False, "zu",    "D", "zu etw. (D) wechseln",           "-e geçmek",                               "Er ist zur Konkurrenz gewechselt.",                          SOURCE_DB),
    ("wenden",          True,  "gegen", "A", "sich gegen etw./jdn. (A) wenden","karşı çıkmak",                           "Die Bevölkerung wandte sich gegen die Reform.",              SOURCE_DB),
    ("zusammenarbeiten",False, "mit",   "D", "mit jdm. (D) zusammenarbeiten",  "biriyle işbirliği yapmak",                "Wir arbeiten eng mit dem Partner zusammen.",                 SOURCE_DB),
    ("zurückgreifen",   False, "auf",   "A", "auf etw. (A) zurückgreifen",     "-e başvurmak, -den yararlanmak",          "Im Notfall können wir auf unsere Ersparnisse zurückgreifen.", SOURCE_DB),
    ("zurückkehren",    False, "zu",    "D", "zu etw./jdm. (D) zurückkehren",  "-e geri dönmek",                          "Nach dem Urlaub kehrt er zu seiner Routine zurück.",         SOURCE_DB),
    ("zählen",          False, "zu",    "D", "zu etw. (D) zählen",             "-e dahil olmak, arasında sayılmak",       "Berlin zählt zu den größten Städten Europas.",              SOURCE_DB),
    ("äußern",          True,  "zu",    "D", "sich zu etw. (D) äußern",        "hakkında görüş bildirmek",                "Der Minister äußerte sich zu den Vorwürfen.",               SOURCE_DB),
    ("äußern",          True,  "über",  "A", "sich über etw. (A) äußern",      "hakkında yorum yapmak",                   "Er äußerte sich kritisch über die Situation.",              SOURCE_DB),
    ("begeistern",      True,  "für",   "A", "sich für etw. (A) begeistern",   "-e heyecanlanmak, tutku duymak",          "Die Kinder begeistern sich für Sport.",                     SOURCE_DB),
    ("entscheiden",     False, "über",  "A", "über etw. (A) entscheiden",      "hakkında karar vermek",                   "Das Gericht entscheidet über den Fall.",                    SOURCE_DB),
    ("forschen",        False, "nach",  "D", "nach etw. (D) forschen",         "-i araştırmak",                           "Wissenschaftler forschen nach einem Impfstoff.",             SOURCE_DB),
    ("kritisieren",     False, "an",    "D", "etw. an jdm./etw. (D) kritisieren","-i eleştirmek",                        "Was kritisierst du an seiner Arbeit?",                       SOURCE_DB),
    ("mahnen",          False, "zu",    "D", "jdn. zu etw. (D) mahnen",        "-e uyarmak, hatırlatmak",                 "Der Chef mahnte die Mitarbeiter zur Pünktlichkeit.",         SOURCE_DB),
    ("melden",          True,  "bei",   "D", "sich bei jdm. (D) melden",       "birine başvurmak, bildirmek",             "Bitte melden Sie sich beim Empfang.",                       SOURCE_DB),
    ("stützen",         True,  "auf",   "A", "sich auf etw. (A) stützen",      "-e dayanmak",                             "Seine Argumentation stützt sich auf Fakten.",               SOURCE_DB),
    ("verzweifeln",     False, "an",    "D", "an etw. (D) verzweifeln",        "-den umutsuzluğa düşmek",                 "Er verzweifelt an dieser Aufgabe.",                         SOURCE_DB),
    ("verpflichten",    True,  "zu",    "D", "sich zu etw. (D) verpflichten",  "-i taahhüt etmek, söz vermek",            "Das Unternehmen verpflichtet sich zu Nachhaltigkeit.",      SOURCE_DB),
    ("vorstellen",      True,  "bei",   "D", "sich bei jdm. (D) vorstellen",   "birine tanıtmak kendini",                 "Er stellt sich morgen beim Chef vor.",                      SOURCE_DB),
    ("zweifeln",        False, "an",    "D", "an etw./jdm. (D) zweifeln",      "-den şüphe etmek",                        "Ich zweifle an seiner Ehrlichkeit.",                        SOURCE_DB),  # dup intentional (different example)
    ("leiden",          False, "unter", "D", "unter etw./jdm. (D) leiden",     "-den acı çekmek",                         "Die Wirtschaft leidet unter der Inflation.",                 SOURCE_DB),
    ("bewerben",        True,  "für",   "A", "sich für etw. (A) bewerben",     "için başvurmak",                          "Ich bewerbe mich für diesen Job.",                          SOURCE_DB),
    ("hängen",          False, "an",    "D", "an etw./jdm. (D) hängen",        "-e bağlı olmak, düşkün olmak",            "Er hängt sehr an seiner Heimatstadt.",                      SOURCE_DB),
    ("klagen",          False, "gegen", "A", "gegen jdn. (A) klagen",          "birine dava açmak",                       "Er klagte gegen die Entscheidung.",                         SOURCE_DB),
    ("passen",          False, "auf",   "A", "auf etw./jdn. (A) passen",       "-e dikkat etmek, bakmak",                 "Kannst du auf meinen Hund aufpassen?",                      SOURCE_DB),
    ("nachfragen",      False, "nach",  "D", "nach etw. (D) nachfragen",       "-i sormak, öğrenmek istemek",             "Ich frage morgen noch einmal nach dem Termin nach.",        SOURCE_DB),
    ("anmelden",        True,  "bei",   "D", "sich bei etw. (D) anmelden",     "bir yere kayıt yaptırmak",                "Ich habe mich beim Kurs angemeldet.",                       SOURCE_DB),
    ("anmelden",        True,  "für",   "A", "sich für etw. (A) anmelden",     "için kayıt olmak",                        "Sie meldete sich für den Marathon an.",                     SOURCE_DB),
    ("abmelden",        True,  "von",   "D", "sich von etw. (D) abmelden",     "-den çıkış yapmak, kaydını sildirmek",    "Ich melde mich vom Newsletter ab.",                         SOURCE_DB),
    ("verlassen",       True,  "auf",   "A", "sich auf jdn. (A) verlassen",    "güvenmek, bel bağlamak",                  "Ich verlasse mich auf dich.",                               SOURCE_DB),
    ("eingehen",        False, "auf",   "A", "auf etw. (A) eingehen",          "-i ele almak, -e değinmek",               "Der Lehrer geht auf alle Fragen ein.",                      SOURCE_DB),
    ("verzichten",      False, "auf",   "A", "auf etw. (A) verzichten",        "-den vazgeçmek, feragat etmek",           "Er verzichtet auf Fleisch.",                                SOURCE_DB),
    ("angewiesen sein", False, "auf",   "A", "auf etw./jdn. (A) angewiesen sein","muhtaç olmak, bağımlı olmak",           "Er ist auf Hilfe angewiesen.",                              SOURCE_DB),
    ("beruhen",         False, "auf",   "D", "auf etw. (D) beruhen",           "-e dayanmak",                             "Diese Geschichte beruht auf wahren Begebenheiten.",         SOURCE_DB),
    ("verständigen",    True,  "mit",   "D", "sich mit jdm. (D) verständigen", "biriyle anlaşmak, haberleşmek",           "Wir haben uns telefonisch mit ihm verständigt.",            SOURCE_DB),
    ("einwilligen",     False, "in",    "A", "in etw. (A) einwilligen",        "-e razı olmak, onaylamak",                "Der Patient willigt in die Operation ein.",                  SOURCE_DB),
    ("zustimmen",       False, "zu",    "D", "etw./jdm. zustimmen",            "-i onaylamak, katılmak",                  "Ich stimme deiner Meinung zu.",                             SOURCE_DB),
    ("widersprechen",   False, "zu",    "D", "jdm./etw. widersprechen",        "itiraz etmek, karşı çıkmak",              "Er widersprach dem Vorschlag.",                             SOURCE_DB),
    ("ablehnen",        False, "von",   "", "etw. ablehnen",                   "reddetmek",                               "Er lehnte das Angebot ab.",                                  SOURCE_DB),
    ("neigen",          False, "zu",    "D", "zu etw. (D) neigen",             "-e meyletmek, eğiliminde olmak",          "Sie neigt dazu, zu übertreiben.",                           SOURCE_DB),
    ("verfügen",        False, "über",  "A", "über etw. (A) verfügen",         "sahip olmak, kullanmak",                  "Er verfügt über große Erfahrung.",                          SOURCE_DB),
    ("verstoßen",       False, "gegen", "A", "gegen etw. (A) verstoßen",       "-e aykırı davranmak, ihlal etmek",        "Er hat gegen die Regeln verstoßen.",                        SOURCE_DB),
    ("sich weigern",    True,  "zu",    "", "sich weigern, etw. zu tun",       "reddetmek, karşı koymak",                 "Sie weigert sich, das zu tun.",                             SOURCE_DB),
    ("anfragen",        False, "bei",   "D", "bei jdm. (D) anfragen",          "birine sormak, talep etmek",              "Ich frage morgen beim Verlag an.",                          SOURCE_DB),
    ("aufrufen",        False, "zu",    "D", "zu etw. (D) aufrufen",           "-e çağırmak",                             "Der Präsident rief zur Solidarität auf.",                   SOURCE_DB),
    ("bestimmen",       False, "über",  "A", "über etw. (A) bestimmen",        "hakkında karar vermek, yönetmek",         "Er bestimmt über sein eigenes Leben.",                      SOURCE_DB),
    ("drängen",         False, "auf",   "A", "auf etw. (A) drängen",           "-de ısrar etmek, zorlamak",               "Die Partei drängt auf schnelle Reformen.",                  SOURCE_DB),
    ("eintreten",       False, "für",   "A", "für etw./jdn. (A) eintreten",    "için savunmak, desteklemek",              "Er tritt für Gerechtigkeit ein.",                           SOURCE_DB),
    ("sich einigen",    True,  "über",  "A", "sich über etw. (A) einigen",     "hakkında anlaşmak",                       "Sie einigten sich über die Bedingungen.",                   SOURCE_DB),
]


# ─────────────────────────────────────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").casefold()).strip()


def build_lookup(dictionary: list[dict]) -> dict[str, list[int]]:
    """almanca alanı → kayıt index listesi."""
    idx: dict[str, list[int]] = {}
    for i, rec in enumerate(dictionary):
        key = normalize(rec.get("almanca", ""))
        if key:
            idx.setdefault(key, []).append(i)
    return idx


def find_record_indices(lookup: dict[str, list[int]], verb: str, reflexiv: bool) -> list[int]:
    """
    Sözlükte verbi arar.
    Önce "sich <verb>" veya "<verb>" olarak tam eşleşme dener,
    sonra eksiz kök olarak dener.
    """
    candidates: list[str] = []
    if reflexiv:
        candidates.append(normalize(f"sich {verb}"))
    candidates.append(normalize(verb))
    for cand in candidates:
        if cand in lookup:
            return lookup[cand]
    # Kısa eşleşme: sözlükte "anrufen" → "anruf" gibi prefix eşleşmesi
    for key, indices in lookup.items():
        if key == normalize(verb) or key.startswith(normalize(verb)):
            return indices
    return []


def kalip_already_exists(existing: list[dict], kalip_str: str) -> bool:
    kn = normalize(kalip_str)
    for item in existing:
        if normalize(item.get("kalip") or item.get("kalip_de") or "") == kn:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# ANA İŞLEM
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 65)
    print("enrich_verben_mit_praepositionen.py")
    print("=" * 65)

    dictionary: list[dict] = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    print(f"  {len(dictionary):,} kayıt yüklendi.")

    lookup = build_lookup(dictionary)

    added_total   = 0
    matched_verbs = set()
    missing_verbs: list[str] = []
    skipped_dup   = 0

    # Grup: aynı fiil → birden fazla kalıp
    from collections import defaultdict
    verb_to_patterns: dict[str, list[tuple]] = defaultdict(list)
    for row in PATTERNS:
        verb_to_patterns[row[0]].append(row)

    for verb, rows in verb_to_patterns.items():
        row0 = rows[0]
        reflexiv = row0[1]
        indices = find_record_indices(lookup, verb, reflexiv)
        if not indices:
            missing_verbs.append(f"{'sich ' if reflexiv else ''}{verb}")
            continue

        for idx in indices:
            rec = dictionary[idx]
            existing_k: list[dict] = list(rec.get("fiil_kaliplari") or [])

            added_here = 0
            for row in rows:
                _, _, prep, kasus, kalip_str, turkce, ornek_de, kaynak = row
                if kalip_already_exists(existing_k, kalip_str):
                    skipped_dup += 1
                    continue
                existing_k.append({
                    "kalip":         kalip_str,
                    "turkce":        turkce,
                    "ornek_almanca": ornek_de,
                    "ornek_turkce":  "",
                    "kaynak":        kaynak,
                })
                added_here += 1

            if added_here:
                dictionary[idx]["fiil_kaliplari"] = existing_k
                added_total += added_here
                matched_verbs.add(verb)
                print(f"  ✓ {rec['almanca']:30} → {added_here} kalıp eklendi")

    # Kaydet
    DICT_PATH.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Özet
    verbs_all  = [r for r in dictionary if (r.get("tur") or "").casefold() in {"fiil", "verb"}]
    has_kalip  = sum(1 for r in verbs_all if r.get("fiil_kaliplari"))
    tv         = len(verbs_all)

    print(f"\n{'=' * 65}")
    print("SONUÇ")
    print(f"  Kaynak kalıp sayısı     : {len(PATTERNS)}")
    print(f"  Sözlükte bulunan fiil   : {len(matched_verbs)}")
    print(f"  Eklenen kalıp           : {added_total}")
    print(f"  Zaten var (atlandı)     : {skipped_dup}")
    print(f"  Sözlükte bulunamayan    : {len(missing_verbs)}")
    if missing_verbs:
        print("  Eksik fiiller:")
        for v in sorted(missing_verbs):
            print(f"    - {v}")
    print()
    print(f"  fiil_kaliplari dolu     : {has_kalip:,} / {tv:,}  (%{100*has_kalip//max(tv,1)})")
    print(f"{'=' * 65}")
    print(f"\nKaydedildi: {DICT_PATH}")


if __name__ == "__main__":
    main()
