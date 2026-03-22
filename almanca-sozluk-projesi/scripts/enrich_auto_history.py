#!/usr/bin/env python3
"""
enrich_auto_history.py
======================
Otomotiv (ağırlıklı) + tarih Wikipedia sayfalarından sürekli zenginleştirme.
min_freq=1, encoding fix dahil.
"""
import json, re, sqlite3, sys, unicodedata
import urllib.parse as _up, urllib.request as _ur
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8","utf8"):
    try: sys.stdout.reconfigure(encoding="utf-8",errors="replace"); sys.stderr.reconfigure(encoding="utf-8",errors="replace")
    except: pass

_SCRIPTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPTS_DIR.parent
DICT_PATHS = [
    _PROJECT_ROOT / "output" / "dictionary.json",
]
WIKDICT_PATH = _PROJECT_ROOT / "data" / "raw" / "downloads" / "de-tr.sqlite3"

SOURCE_URLS = [
    # === Otomotiv — Elektronik & Steuerung ===
    "https://de.wikipedia.org/wiki/Fahrzeugelektronik",
    "https://de.wikipedia.org/wiki/Bordnetz",
    "https://de.wikipedia.org/wiki/LIN-Bus",
    "https://de.wikipedia.org/wiki/FlexRay",
    "https://de.wikipedia.org/wiki/Automotive_Ethernet",
    "https://de.wikipedia.org/wiki/Motormanagement",
    "https://de.wikipedia.org/wiki/Klopfregelung",
    "https://de.wikipedia.org/wiki/Getriebesteuerung",
    "https://de.wikipedia.org/wiki/Einspritzdüse",
    "https://de.wikipedia.org/wiki/Common-Rail",
    "https://de.wikipedia.org/wiki/Piezoaktor",
    "https://de.wikipedia.org/wiki/Kraftstoffdruckregler",
    "https://de.wikipedia.org/wiki/Lambdasonde",
    "https://de.wikipedia.org/wiki/Nockenwellenverstellung",
    "https://de.wikipedia.org/wiki/Zylinderabschaltung",
    "https://de.wikipedia.org/wiki/Start-Stopp-System",
    "https://de.wikipedia.org/wiki/Segelbetrieb_(Kraftfahrzeug)",
    "https://de.wikipedia.org/wiki/Rekuperationsbremse",
    "https://de.wikipedia.org/wiki/Batteriemanagementsystem",
    "https://de.wikipedia.org/wiki/Thermomanagement",
    "https://de.wikipedia.org/wiki/Festkörperbatterie",
    "https://de.wikipedia.org/wiki/Fahrzeugakustik",
    "https://de.wikipedia.org/wiki/Aktive_Geräuschunterdrückung",
    "https://de.wikipedia.org/wiki/Rückfahrkamera",
    "https://de.wikipedia.org/wiki/Parkassistent",
    "https://de.wikipedia.org/wiki/Nachtsichtassistent",
    "https://de.wikipedia.org/wiki/Totwinkel-Assistent",
    "https://de.wikipedia.org/wiki/Stauassistent",
    "https://de.wikipedia.org/wiki/Abstandsregeltempomat",

    # === Otomotiv — Abgas & Kraftstoff (detaylı) ===
    "https://de.wikipedia.org/wiki/SCR-Katalysator",
    "https://de.wikipedia.org/wiki/Harnstoffeinspritzung",
    "https://de.wikipedia.org/wiki/Benzindirekteinspritzung",
    "https://de.wikipedia.org/wiki/Magermotor",
    "https://de.wikipedia.org/wiki/Ottomotor_mit_Direkteinspritzung",
    "https://de.wikipedia.org/wiki/Homogene_Kompressionszündung",
    "https://de.wikipedia.org/wiki/Autogas",
    "https://de.wikipedia.org/wiki/Erdgasfahrzeug",
    "https://de.wikipedia.org/wiki/Biokraftstoff",
    "https://de.wikipedia.org/wiki/E-Fuel",
    "https://de.wikipedia.org/wiki/Wasserstoffauto",
    "https://de.wikipedia.org/wiki/Oktanzahl",
    "https://de.wikipedia.org/wiki/Cetanzahl",
    "https://de.wikipedia.org/wiki/AdBlue",

    # === Otomotiv — Aerodynamik & Karosserie ===
    "https://de.wikipedia.org/wiki/Fahrzeugaerodynamik",
    "https://de.wikipedia.org/wiki/Windkanal",
    "https://de.wikipedia.org/wiki/Luftwiderstand",
    "https://de.wikipedia.org/wiki/Abtrieb_(Aerodynamik)",
    "https://de.wikipedia.org/wiki/Fahrzeuglackierung",
    "https://de.wikipedia.org/wiki/Elektrotauchlackierung",
    "https://de.wikipedia.org/wiki/Unterbodenschutz",
    "https://de.wikipedia.org/wiki/Hohlraumversiegelung",
    "https://de.wikipedia.org/wiki/Leichtbau",
    "https://de.wikipedia.org/wiki/Space-Frame",
    "https://de.wikipedia.org/wiki/Stahl_(Werkstoff)",
    "https://de.wikipedia.org/wiki/Aluminiumlegierung",
    "https://de.wikipedia.org/wiki/Kohlenstofffaserverstärkter_Kunststoff",

    # === Otomotiv — Reifen & Fahrwerk (detaylı) ===
    "https://de.wikipedia.org/wiki/Reifendruckkontrollsystem",
    "https://de.wikipedia.org/wiki/Pannenschutz",
    "https://de.wikipedia.org/wiki/Run-Flat-Reifen",
    "https://de.wikipedia.org/wiki/Reifenkennzeichnung",
    "https://de.wikipedia.org/wiki/Reifenindex",
    "https://de.wikipedia.org/wiki/Fahrzeugdynamik",
    "https://de.wikipedia.org/wiki/Gierrate",
    "https://de.wikipedia.org/wiki/Untersteuern",
    "https://de.wikipedia.org/wiki/Übersteuern",
    "https://de.wikipedia.org/wiki/Schlupf_(Fahrzeugtechnik)",
    "https://de.wikipedia.org/wiki/Antriebsschlupfregelung",
    "https://de.wikipedia.org/wiki/Torque_Vectoring",
    "https://de.wikipedia.org/wiki/Wankausgleich",
    "https://de.wikipedia.org/wiki/Nickausgleich",
    "https://de.wikipedia.org/wiki/Aktives_Fahrwerk",

    # === Otomotiv — Bremse (detaylı) ===
    "https://de.wikipedia.org/wiki/Bremsweg",
    "https://de.wikipedia.org/wiki/Bremsverzögerung",
    "https://de.wikipedia.org/wiki/Bremsassistent",
    "https://de.wikipedia.org/wiki/Notbremsassistent",
    "https://de.wikipedia.org/wiki/Brake-by-Wire",
    "https://de.wikipedia.org/wiki/Elektrische_Feststellbremse",
    "https://de.wikipedia.org/wiki/Scheibenbremsbelag",

    # === Motorsport & Rennwagen ===
    "https://de.wikipedia.org/wiki/Motorsport",
    "https://de.wikipedia.org/wiki/Formel_1",
    "https://de.wikipedia.org/wiki/Rallye",
    "https://de.wikipedia.org/wiki/Le_Mans_(Rennen)",
    "https://de.wikipedia.org/wiki/Nürburgring",
    "https://de.wikipedia.org/wiki/DTM",
    "https://de.wikipedia.org/wiki/Rennwagen",
    "https://de.wikipedia.org/wiki/Rennstrecke",
    "https://de.wikipedia.org/wiki/Boxenstopp",
    "https://de.wikipedia.org/wiki/Slick_(Reifen)",
    "https://de.wikipedia.org/wiki/Aerodynamikpaket",
    "https://de.wikipedia.org/wiki/KERS",

    # === Otomotiv — Vernetzung & Zukunft ===
    "https://de.wikipedia.org/wiki/Vernetztes_Fahrzeug",
    "https://de.wikipedia.org/wiki/Vehicle-to-Everything",
    "https://de.wikipedia.org/wiki/Fahrzeugtelematik",
    "https://de.wikipedia.org/wiki/Flottenmanagement",
    "https://de.wikipedia.org/wiki/Carsharing",
    "https://de.wikipedia.org/wiki/Ridesharing",
    "https://de.wikipedia.org/wiki/Mikromobilität",
    "https://de.wikipedia.org/wiki/Elektroroller",
    "https://de.wikipedia.org/wiki/Pedelec",
    "https://de.wikipedia.org/wiki/Fahrtenschreiber",
    "https://de.wikipedia.org/wiki/Maut",
    "https://de.wikipedia.org/wiki/Parkraumbewirtschaftung",

    # === Otomotiv — Produktion & Industrie ===
    "https://de.wikipedia.org/wiki/Automobilindustrie",
    "https://de.wikipedia.org/wiki/Automobilproduktion",
    "https://de.wikipedia.org/wiki/Automobilzulieferer",
    "https://de.wikipedia.org/wiki/Karosseriebau",
    "https://de.wikipedia.org/wiki/Presswerk",
    "https://de.wikipedia.org/wiki/Rohbau_(Automobil)",
    "https://de.wikipedia.org/wiki/Lackiererei",
    "https://de.wikipedia.org/wiki/Montagewerk",
    "https://de.wikipedia.org/wiki/Just-in-time-Produktion",
    "https://de.wikipedia.org/wiki/Qualitätssicherung",
    "https://de.wikipedia.org/wiki/Fahrzeugprüfung",
    "https://de.wikipedia.org/wiki/Homologation",
    "https://de.wikipedia.org/wiki/Typgenehmigung",
    "https://de.wikipedia.org/wiki/WLTP",
    "https://de.wikipedia.org/wiki/NEFZ",
    "https://de.wikipedia.org/wiki/Crashtestverfahren",

    # === Geschichte des Automobils ===
    "https://de.wikipedia.org/wiki/Geschichte_des_Automobils",
    "https://de.wikipedia.org/wiki/Carl_Benz",
    "https://de.wikipedia.org/wiki/Gottlieb_Daimler",
    "https://de.wikipedia.org/wiki/Wilhelm_Maybach",
    "https://de.wikipedia.org/wiki/Rudolf_Diesel",
    "https://de.wikipedia.org/wiki/August_Horch",
    "https://de.wikipedia.org/wiki/Ferdinand_Porsche",
    "https://de.wikipedia.org/wiki/Henry_Ford",
    "https://de.wikipedia.org/wiki/Fließbandproduktion",
    "https://de.wikipedia.org/wiki/Dampfmaschine",
    "https://de.wikipedia.org/wiki/Industrialisierung",
    "https://de.wikipedia.org/wiki/Geschichte_der_Eisenbahn",
    "https://de.wikipedia.org/wiki/Geschichte_der_Luftfahrt",
    "https://de.wikipedia.org/wiki/Geschichte_der_Schifffahrt",

    # === Allgemeine Geschichte ===
    "https://de.wikipedia.org/wiki/Erster_Weltkrieg",
    "https://de.wikipedia.org/wiki/Zweiter_Weltkrieg",
    "https://de.wikipedia.org/wiki/Weimarer_Republik",
    "https://de.wikipedia.org/wiki/Nationalsozialismus",
    "https://de.wikipedia.org/wiki/Kalter_Krieg",
    "https://de.wikipedia.org/wiki/Deutsche_Wiedervereinigung",
    "https://de.wikipedia.org/wiki/Berliner_Mauer",
    "https://de.wikipedia.org/wiki/Kaiserreich_(Deutschland)",
    "https://de.wikipedia.org/wiki/Bismarck_(Staatsmann)",
    "https://de.wikipedia.org/wiki/Dreißigjähriger_Krieg",
    "https://de.wikipedia.org/wiki/Reformation",
    "https://de.wikipedia.org/wiki/Industrielle_Revolution",
    "https://de.wikipedia.org/wiki/Französische_Revolution",
    "https://de.wikipedia.org/wiki/Napoleonische_Kriege",
    "https://de.wikipedia.org/wiki/Russische_Revolution",
    "https://de.wikipedia.org/wiki/Kolonialismus",
    "https://de.wikipedia.org/wiki/Imperialismus",
    "https://de.wikipedia.org/wiki/Antike",
    "https://de.wikipedia.org/wiki/Mittelalter",
    "https://de.wikipedia.org/wiki/Renaissance",
    "https://de.wikipedia.org/wiki/Aufklärung_(Epoche)",
    "https://de.wikipedia.org/wiki/Römisches_Reich",
    "https://de.wikipedia.org/wiki/Griechische_Antike",
    "https://de.wikipedia.org/wiki/Byzantinisches_Reich",
    "https://de.wikipedia.org/wiki/Osmanisches_Reich",
    "https://de.wikipedia.org/wiki/Kreuzzüge",
    "https://de.wikipedia.org/wiki/Pest_(Krankheit)",
    "https://de.wikipedia.org/wiki/Absolutismus",
    "https://de.wikipedia.org/wiki/Preußen",
    "https://de.wikipedia.org/wiki/Habsburg",
    "https://de.wikipedia.org/wiki/Völkerwanderung",
    "https://de.wikipedia.org/wiki/Wikinger",
    "https://de.wikipedia.org/wiki/Feudalismus",
    "https://de.wikipedia.org/wiki/Sklaverei",
    "https://de.wikipedia.org/wiki/Kolonisation",
    "https://de.wikipedia.org/wiki/Entkolonialisierung",
    "https://de.wikipedia.org/wiki/Kalter_Krieg",
    "https://de.wikipedia.org/wiki/Kuba-Krise",
    "https://de.wikipedia.org/wiki/Vietnamkrieg",
    "https://de.wikipedia.org/wiki/Koreakrieg",
    "https://de.wikipedia.org/wiki/Apartheid",
    "https://de.wikipedia.org/wiki/Bürgerrechtsbewegung",
    "https://de.wikipedia.org/wiki/Globalisierung",
    "https://de.wikipedia.org/wiki/Geschichte_der_Demokratie",
    "https://de.wikipedia.org/wiki/Geschichte_des_Geldes",
    "https://de.wikipedia.org/wiki/Geschichte_der_Wissenschaft",
    "https://de.wikipedia.org/wiki/Geschichte_der_Medizin",
    "https://de.wikipedia.org/wiki/Geschichte_der_Kunst",
    "https://de.wikipedia.org/wiki/Geschichte_der_Musik",
    "https://de.wikipedia.org/wiki/Geschichte_des_Sports",

    # === Teknik & Mühendislik (tamamlayıcı) ===
    "https://de.wikipedia.org/wiki/Werkzeugmaschine",
    "https://de.wikipedia.org/wiki/Zerspanung",
    "https://de.wikipedia.org/wiki/Gießen_(Urformen)",
    "https://de.wikipedia.org/wiki/Umformen",
    "https://de.wikipedia.org/wiki/Fügen_(Fertigungsverfahren)",
    "https://de.wikipedia.org/wiki/Löten",
    "https://de.wikipedia.org/wiki/Kleben_(Fügen)",
    "https://de.wikipedia.org/wiki/Oberflächenbehandlung",
    "https://de.wikipedia.org/wiki/Wärmebehandlung",
    "https://de.wikipedia.org/wiki/Härten_(Metall)",
    "https://de.wikipedia.org/wiki/Galvanik",
    "https://de.wikipedia.org/wiki/Pulverbeschichtung",
    "https://de.wikipedia.org/wiki/Messtechnik",
    "https://de.wikipedia.org/wiki/Toleranz_(Technik)",
    "https://de.wikipedia.org/wiki/Normung",
    "https://de.wikipedia.org/wiki/DIN-Norm",
    "https://de.wikipedia.org/wiki/ISO_9001",
    "https://de.wikipedia.org/wiki/Lean_Management",
    "https://de.wikipedia.org/wiki/Six_Sigma",
    "https://de.wikipedia.org/wiki/FMEA",
    "https://de.wikipedia.org/wiki/Projektmanagement",
    "https://de.wikipedia.org/wiki/Simultaneous_Engineering",
    "https://de.wikipedia.org/wiki/CAD",
    "https://de.wikipedia.org/wiki/CAM",
    "https://de.wikipedia.org/wiki/FEM",
    "https://de.wikipedia.org/wiki/Simulation",
    "https://de.wikipedia.org/wiki/Digitaler_Zwilling",
    "https://de.wikipedia.org/wiki/Industrie_4.0",
    "https://de.wikipedia.org/wiki/Additive_Fertigung",
    "https://de.wikipedia.org/wiki/3D-Druck",
]

# Stopwords (casefold)
_SW = frozenset(s.casefold() for s in {
    "aber","alle","allem","allen","aller","alles","als","also","am","an","auch","auf","aus",
    "bei","beim","bin","bis","bist","da","dabei","damit","danach","dann","das","dass","dein",
    "deine","dem","den","denn","der","des","dessen","deshalb","die","dies","diese","dieser",
    "dieses","doch","dort","du","durch","ein","eine","einem","einen","einer","eines","er","es",
    "etwas","euch","euer","eure","für","gegen","gewesen","hab","habe","haben","hat","hatte",
    "hattest","hier","hin","hinter","ich","ihr","ihre","im","in","indem","ins","ist","jede",
    "jeder","jedes","jetzt","kann","kannst","kein","keine","mit","muss","musst","nach","neben",
    "nicht","noch","nun","oder","ohne","sehr","sein","seine","sich","sie","sind","so","solche",
    "soll","sollte","sondern","sonst","über","um","und","uns","unter","vom","von","vor","war",
    "waren","warst","was","weg","weil","weiter","welche","welcher","wenn","wer","werde","werden",
    "wie","wieder","wir","wird","wirst","wo","wurde","wurden","zu","zum","zur","zwar","zwischen",
    "gut","gute","guten","gutem","guter","gutes","groß","große","großen","großem","großer","großes",
    "klein","kleine","kleinen","kleinem","kleiner","kleines","neu","neue","neuen","neuem","neuer",
    "neues","alt","alte","alten","altem","alter","altes","viel","viele","vielen","vielem","vieler",
    "vieles","wenig","wenige","wenigen","wenigem","weniger","ganz","ganze","ganzen","ganzem",
    "ganzer","ganzes","ander","andere","anderen","anderem","anderer","anderes","erst","erste",
    "ersten","erstem","erster","erstes","letzt","letzte","letzten","letztem","letzter","letztes",
    "immer","schon","nur","gern","gerne","fast","etwa","eher","daher","damals","dazu","deswegen",
    "trotzdem","dennoch","jedoch","allerdings","außerdem","zudem","ebenfalls","bereits","meist",
    "meistens","manchmal","oft","häufig","selten","früher","später","zuerst","zuletzt","endlich",
    "plötzlich","sofort","bisher","seitdem","davor","davon","daran","darin","darauf","darum",
    "darüber","darunter","dafür","dagegen","dadurch","dahinter","können","konnte","konnten",
    "könnte","könnten","müssen","musste","mussten","müsste","müssten","sollen","sollten","wollen",
    "wollte","wollten","darf","dürfen","durfte","durften","dürfte","dürften","mögen","mochte",
    "mochten","möchte","möchten","seid","wäre","wären","sei","seien","habt","hatten","hattet",
    "hätte","hätten","gehabt","werdet","würde","würden","würdet","geworden","geht","ging","gingen",
    "kommt","kam","kamen","macht","machte","machten","sagt","sagte","sagten","gibt","gab","gaben",
    "steht","stand","standen","liegt","lag","lagen","sieht","sah","sahen","nimmt","nahm","nahmen",
    "hält","hielt","hielten","lässt","ließ","ließen","bringt","brachte","brachten","denkt","dachte",
    "dachten","weiß","wusste","wussten","findet","fand","fanden","zeigt","zeigte","zeigten",
    "bleibt","blieb","blieben","heißt","hieß","hießen","Jahr","Jahre","Jahren","Zeit","Zeiten",
    "Teil","Teile","Form","Formen","Art","Arten","Fall","Fälle","Punkt","Punkte","Zahl","Zahlen",
    "Ende","Anfang","Bereich","Bereiche","Grund","Gründe","Beispiel","Beispiele","Ergebnis",
    "Ergebnisse","Problem","Probleme","Frage","Fragen","Antwort","Antworten","Möglichkeit",
    "Möglichkeiten","Bedeutung","Bedeutungen","Mensch","Menschen","Land","Länder","Stadt","Städte",
    "Welt","Leben","Weise","Stelle","Stellen","Seite","Seiten","the","and","for","that","this",
    "with","from","are","was","has","have","been","they","about","which","when","where","how",
    "can","will","not","but","more","also","some","than","then","there","here","other","used",
    "based","see","view","edit","januar","februar","märz","april","mai","juni","juli","august",
    "september","oktober","november","dezember","montag","dienstag","mittwoch","donnerstag",
    "freitag","samstag","sonntag","zweite","zweiten","dritte","dritten","vierte","vierten",
    "fünfte","fünften","unser","unsere","unseren","unserem","unserer","jener","jene","jenen",
    "jeden","jedem","mancher","manche","manchen","obwohl","während","bevor","nachdem","sobald",
    "solange","falls","sofern","gegenüber","innerhalb","außerhalb","anstatt","anstelle","aufgrund",
    "mithilfe","bezüglich","hinsichtlich","laut","gemäß","zufolge","entsprechend","seit","statt",
    "samt","wobei","sowie","hierbei","hierzu","daraus","somit","folglich","hingegen","vielmehr",
    "andererseits","einerseits","nämlich","schließlich","letztlich","insofern","soweit","sowohl",
    "weder","entweder","zumindest","mindestens","höchstens","tatsächlich","eigentlich","offenbar",
    "offensichtlich","anscheinend","möglicherweise","wahrscheinlich","jedenfalls","ohnehin","sowieso",
    "gleichwohl","indes","derweil","seither","fortan","nunmehr","grundsätzlich","weitgehend",
    "infolge","anhand","sodass","insgesamt","insbesondere","abschnitt","artikel","weblink","weblinks",
    "literatur","einzelnachweis","einzelnachweise","hauptartikel","kategorie","kategorien","siehe",
    "usw","bzw","evtl","ggf","inkl","exkl","sog","bspw","vgl",
})
_PN = frozenset({
    "berlin","münchen","hamburg","köln","frankfurt","stuttgart","düsseldorf","dortmund",
    "essen","leipzig","bremen","dresden","hannover","nürnberg","bonn","deutschland",
    "österreich","schweiz","europa","paris","london","washington","peking","tokio","moskau",
    "müller","schmidt","schneider","fischer","weber","becker","schulz","hoffmann","schäfer",
    "koch","richter","schwarz","volkswagen","mercedes","bmw","audi","porsche","opel","ford",
    "toyota","honda","nissan","hyundai","renault","peugeot","fiat","volvo","tesla",
    "bosch","continental","michelin","pirelli","bridgestone","siemens","magna","denso",
})

TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß]{3,}(?:-[A-Za-zÄÖÜäöüß]{2,})*")

def fx(url):
    p=_up.urlsplit(url)
    return _up.urlunsplit(p._replace(path=_up.quote(p.path,safe="/:@!$&'()*+,;=")))

def cf(s): return unicodedata.normalize("NFC",s).strip().casefold()
def sa(t):
    for a in ("der ","die ","das ","Der ","Die ","Das "):
        if t.startswith(a): return t[len(a):]
    return t
def sw(t): return cf(t) in _SW or cf(sa(t)) in _SW
def pn(t): return cf(t) in _PN

class VTE(HTMLParser):
    SK={"head","script","style","noscript","svg","canvas","nav","footer","header","aside","button","form","input","select","textarea","figure"}
    BL={"address","article","blockquote","br","div","figcaption","h1","h2","h3","h4","h5","h6","li","main","p","section","td","th","tr"}
    MN={"main","article"}
    SC={"references","reflist","reference","footnotes","toc","toccolours","mw-references-wrap","navbox","navbox-inner","navbox-group","mw-editsection","mw-jump-link","sidebar","sistersitebox","noprint","catlinks","printfooter","cookie","banner","advertisement","ad","ads","breadcrumb","pagination","menu","dropdown","related","recommendation"}
    SI={"toc","references","catlinks","mw-navigation","p-search","nav","footer","header","sidebar","menu","cookie-banner"}
    def __init__(self):
        super().__init__(); self.sd=self.md=0; self.ac=[]; self.mc=[]
    def _ska(self,a):
        d=dict(a); return d.get("id","") in self.SI or bool(set((d.get("class","") or "").split())&self.SC)
    def handle_starttag(self,t,a):
        if t in self.SK or self._ska(a): self.sd+=1; return
        if self.sd: return
        if t in self.MN: self.md+=1
        if t in self.BL: self._b()
    def handle_endtag(self,t):
        if self.sd: self.sd-=1; return
        if t in self.MN and self.md: self.md-=1
        if t in self.BL: self._b()
    def handle_data(self,d):
        if self.sd: return
        s=d.strip()
        if not s: return
        self.ac.append(s)
        if self.md: self.mc.append(s)
    def _b(self):
        self.ac.append("\n")
        if self.md: self.mc.append("\n")
    def get_text(self):
        def j(c):
            p=[]
            for x in c:
                if x=="\n":
                    if p and p[-1]!="\n": p.append("\n")
                elif x.strip(): p.append(x.strip())
            return " ".join(p).strip()
        m=j(self.mc); b=j(self.ac)
        t=m if len(m)>=200 else b
        return re.sub(r"\n{3,}","\n\n",re.sub(r"[ \t]{2,}"," ",t)).strip()

def fetch(url):
    url=fx(url)
    h={"User-Agent":"Mozilla/5.0 (compatible; AlmancaSozluk/1.0)","Accept-Language":"de-DE,de;q=0.9","Accept":"text/html,application/xhtml+xml"}
    try:
        with _ur.urlopen(_ur.Request(url,headers=h),timeout=20) as r:
            raw=r.read(); ch=r.headers.get_content_charset() or "utf-8"
            return raw.decode(ch,errors="replace")
    except Exception as e:
        print(f"  [HATA] {url}: {e}",file=sys.stderr); return ""

def lookup(term,cur):
    if cur is None: return {"translation":"","written_rep":""}
    lo=cf(sa(term)); cands=[term.strip(),lo]
    for sf,rp in [("iert","ieren"),("test","en"),("tet","en"),("st","en"),("te","en")]:
        if lo.endswith(sf) and len(lo)>len(sf)+2: cands.append(lo[:-len(sf)]+rp)
    for sf in ("en","es","e","s"):
        if sf=="s" and lo.endswith("ss"): continue
        mn=5 if sf in ("e","s") else 6
        if lo.endswith(sf) and len(lo)>=mn: cands.append(lo[:-len(sf)])
    if lo.endswith("t") and len(lo)>=6:
        r=lo[:-1]
        if not r.endswith(("ig","lich","isch","bar","sam","haft","voll","los")): cands.append(r+"en")
    seen=set()
    for lt in cands:
        k=cf(lt)
        if not k or k in seen: continue
        seen.add(k)
        row=cur.execute("SELECT written_rep,trans_list FROM simple_translation WHERE lower(written_rep)=lower(?) ORDER BY rel_importance DESC,max_score DESC LIMIT 1",(lt,)).fetchone()
        if row:
            ts,st=[],set()
            for p in str(row[1] or "").split("|"):
                p=p.strip(); k2=cf(p)
                if not p or k2 in st or len(p)<2: continue
                st.add(k2); ts.append(p)
            return {"translation":", ".join(ts[:4]),"written_rep":str(row[0] or "")}
    return {"translation":"","written_rep":""}

def gpos(tok):
    b=sa(tok)
    if tok[:1].isupper() and " " not in b: return "isim"
    bl=b.lower()
    if bl.endswith(("en","ern","eln")): return "fiil"
    if bl.endswith(("lich","isch","ig","bar","sam","haft","los","voll")): return "sıfat"
    return "isim"

def load():
    for p in DICT_PATHS:
        if p.exists():
            with open(p,encoding="utf-8") as f: return json.load(f)
    return []

def save(recs):
    for p in DICT_PATHS:
        try:
            with open(p,"w",encoding="utf-8") as f: json.dump(recs,f,ensure_ascii=False,indent=2)
            print(f"  Kaydedildi: {p}")
        except Exception as e: print(f"  [HATA] {p}: {e}",file=sys.stderr)

def keys(recs):
    k=set()
    for r in recs:
        a=(r.get("almanca","") or "").strip()
        k.add(cf(a)); k.add(cf(sa(a)))
    return k

def rl(almanca):
    w=sa(almanca); e=_up.quote(w)
    return {"duden":f"https://www.duden.de/suchen/dudenonline/{e}","dwds":f"https://www.dwds.de/wb/{e}","wiktionary_de":f"https://de.wiktionary.org/wiki/{e}"}

def extract(url,ak,cur):
    html=fetch(url)
    if not html: return []
    p=VTE(); p.feed(html); text=p.get_text()
    if not text: return []
    print(f"  {len(text):,} kar")
    counts=Counter(); labels={}; lc=set()
    for tok in TOKEN_RE.findall(text):
        if tok[:1].islower(): lc.add(cf(tok))
    for tok in TOKEN_RE.findall(text):
        n=cf(tok)
        if not n or len(n)<4 or len(n)>40: continue
        if sw(tok) or pn(tok): continue
        if n in ak: continue
        counts[n]+=1
        cl=labels.get(n)
        if cl is None or (tok[:1].isupper() and not cl[:1].isupper()): labels[n]=tok
    res=[]
    for n,freq in counts.most_common(500):
        german=labels.get(n,n)
        sug=lookup(german,cur)
        if not sug["translation"] or len(sug["translation"].strip())<2: continue
        wr=cf(sug.get("written_rep",""))
        if wr and wr!=n and wr in ak: continue
        skip=False
        for sf in ("es","en","er","em"):
            if german.endswith(sf) and cf(german[:-len(sf)]) in ak: skip=True; break
        if skip: continue
        res.append({"almanca":german,"turkce":sug["translation"],"pos":gpos(german),"written_rep":sug["written_rep"]})
    return res

def to_rec(cand,url):
    alm=cand["almanca"]; art=""
    for a in ("der ","die ","das "):
        if cand["written_rep"].lower().startswith(a): art=a.strip(); alm=cand["written_rep"][len(a):]; break
    src="kfz-tech.de" if "kfz-tech.de" in url else "Wikipedia DE"
    topic=url.split("/wiki/")[-1].replace("_"," ") if "/wiki/" in url else url.split("/")[-1]
    kat="otomotiv" if any(k in url for k in ["Motor","Getriebe","Fahrwerk","Bremse","Reifen","Karosserie","Elektro","Hybrid","Kfz","Kraftfahr","Turbo","Diesel","Benzin","Kupplung","Lenkung","Airbag","Crash","Renn","Formel","Motorsport","automobil","Automobil","fahrzeug","Fahrzeug","Antrieb","Zündung","Abgas","Kraftstoff","Batterie","Ladung","Ladesa"]) else "tarih" if any(k in url for k in ["Geschichte","Weltkrieg","Revolution","Reformation","Mittelalter","Antike","Krieg","Reich","Kolonial","Imperialism","Kaiser","Napoleon","Aufklärung","Renaissance","Wikinger","Feudal","Sklaverei","Apartheid"]) else "teknik"
    return {"almanca":alm,"artikel":art,"turkce":cand["turkce"],"kategoriler":[kat],"aciklama_turkce":"","ilgili_kayitlar":[],"tur":cand["pos"],"ornek_almanca":"","ornek_turkce":"","ornekler":[],"kaynak":f"WikDict; {src}","kaynak_url":f"https://kaikki.org/dewiktionary/rawdata.html; {url}","ceviri_durumu":"kaynak-izli","ceviri_inceleme_notu":"","ceviri_kaynaklari":[],"not":f"URL-import: {src} — {topic}","referans_linkler":rl(alm),"seviye":"","genitiv_endung":"","kelime_ailesi":[]}

def main():
    print("="*60)
    print("enrich_auto_history.py")
    print(f"URL: {len(SOURCE_URLS)} | min_freq=1 | encoding fix aktif")
    print("="*60)
    if WIKDICT_PATH.exists():
        conn=sqlite3.connect(str(WIKDICT_PATH)); cur=conn.cursor()
        print(f"WikDict: OK")
    else:
        conn=None; cur=None
        print("[UYARI] WikDict yok",file=sys.stderr)
    recs=load(); ak=keys(recs)
    print(f"Mevcut: {len(recs)} kayit\n")
    total=len(SOURCE_URLS); added=0; stats={}
    for i,url in enumerate(SOURCE_URLS,1):
        topic=url.split("/wiki/")[-1].replace("_"," ") if "/wiki/" in url else url.split("/")[-1]
        print(f"\n[{i}/{total}] {topic}")
        cands=extract(url,ak,cur)
        cnt=0
        for c in cands:
            n=cf(c["almanca"]); nb=cf(sa(c["almanca"]))
            if n in ak or nb in ak: continue
            r=to_rec(c,url); recs.append(r); ak.add(n); ak.add(nb); cnt+=1; added+=1
            print(f"    + {r['almanca']} -> {r['turkce']}")
        stats[topic]=cnt; print(f"  => {cnt} yeni")
        if i%20==0 and added>0:
            print(f"\n  [ARA KAYIT] +{added} toplam..."); save(recs)
    if conn: conn.close()
    print(f"\n{'='*60}\nTOPLAM YENI: {added}\nSozluk: {len(recs)} kayit\n{'='*60}")
    save(recs)
    top=sorted(stats.items(),key=lambda x:-x[1])[:20]
    print("\n--- En verimli konular ---")
    for t,c in top:
        if c: print(f"  {t}: +{c}")

if __name__=="__main__": main()
