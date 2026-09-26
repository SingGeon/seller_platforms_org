"""Which news tells us about a company's problems or development, the situations our services address.

Every article is tagged with the topics it covers (Romanian, English and German wording, accents ignored):
security incidents, IT outages, compliance and fines, digital transformation, automation / AI, cost cutting and
restructuring, financial pressure, operational problems, leadership changes and growth / investment. An article with
at least one topic is "topical"; a company needs a minimum of distinct recent topical stories before its situation
can be analysed (backend/app/newscuration.py).

BING_TOPIC_KEYWORDS holds the same themes as search keywords per language, so the news search asks for these stories
directly instead of only the company name (TOPIC_QUERIES: the Google News variant, opt-in since Google blocked bulk runs).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    key: str
    label: str
    services: tuple[str, ...]  # service slugs (backend/app/seed.py): apa, cyber, cloud, data, erp, iot
    plain: re.Pattern  # matched on lower-case text without accents
    exact: re.Pattern | None = None  # case-sensitive acronyms (AI, KI, SAP, ...)


def _p(*alternatives: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(alternatives) + ")", re.I)


def _x(*acronyms: str) -> re.Pattern:
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(acronyms) + r")(?![A-Za-z0-9])")


TOPICS: tuple[Topic, ...] = (
    # --- Intelligent Automation signals (Annex 1: the sales manager's manual checklist, now automatic) ---
    Topic("cost_efficiency", "Program de reducere a costurilor / eficiență operațională", ("apa",), _p(
        r"reduce(re|rea)? (a )?(costurilor|cheltuielilor|de costuri)", r"eficientiz", r"eficient(a|ei) operational", r"program(ul)? de eficient",
        r"optimiz(are|area) (a )?(costuri|proces|activit|operatiun)", r"restructur", r"reorganiz", r"cresterea productivitatii",
        r"cost[- ]cutting", r"cost reduction", r"efficiency (program|drive|plan)", r"operational efficiency", r"restructuring",
        r"kostensenk", r"sparprogramm", r"effizienzprogramm", r"umstrukturier", r"sparkurs",
    )),
    Topic("digital_transformation", "Transformare digitală / sisteme IT, cloud, date, ERP, IoT", ("apa", "cyber", "cloud", "data", "erp", "iot"), _p(
        r"digitaliz", r"transformar(e|ea) digital", r"cloud", r"platform(a|a) digital", r"platforma online", r"aplicati(a|e) mobil",
        r"migrar(e|ea) (in|catre|pe|la)", r"moderniz(are|area) (sistem|it|tehnolog)", r"sistem(ul)? informatic", r"core banking", r"software",
        r"sistem(ul)? erp", r"implementar(e|ea) (sap|erp|crm|unui sistem)", r"digital transformation", r"digitalisierung", r"it-?system",
        r"centr(u|ul) de date", r"data ?cent(er|re)", r"business intelligence", r"analiz(a|e) (a )?datelor", r"big data", r"data warehouse",
        r"internet of things", r"internetul lucrurilor", r"senzori", r"industr(ie|y) 4\.0", r"smart (metering|grid|factory)", r"contoare inteligente",
    ), _x("ERP", "SAP", "CRM", "IT", "IoT", "BI")),
    Topic("automation_ai", "Proiecte AI / RPA / Agentic AI / Process Mining", ("apa", "data"), _p(
        r"automatiz", r"robot", r"inteligent(a|ei) artificial", r"chatbot", r"asistent(ul)? virtual", r"agent(ul|i)? (ai|virtual|inteligent)", r"agentic",
        r"machine learning", r"invatare automata", r"algoritm", r"process mining", r"hyperautomation", r"automation", r"artificial intelligence",
        r"kuenstliche intelligenz", r"kunstliche intelligenz", r"automatisier",
    ), _x("AI", "IA", "KI", "RPA", "GenAI", "LLM")),
    Topic("hiring_tech", "Angajări relevante (IT, automatizare, securitate, date)", ("apa", "cyber", "cloud", "data", "erp"), _p(
        r"(angaj|recrut|cauta|caut)\w* .{0,60}(it|programator|developer|dezvoltator|ingineri? software|analist|securitate|automatiz|rpa|date|data|ai|inteligenta artificiala)",
        r"(specialisti|posturi|joburi|locuri de munca) (in )?(it|tech|tehnologi|securitate cibernetica|automatizare)",
        r"hiring .{0,40}(engineer|developer|analyst|security|automation|data)", r"(sucht|stellt ein|einstellen) .{0,40}(entwickler|it|informatiker|security|daten)",
        r"(it|tech)-?fachkraefte", r"(it|tech)-?fachkrafte",
    )),
    Topic("leadership_change", "Numire în conducere (CIO, COO, CDO, digital, automatizare)", ("apa", "cyber"), _p(
        r"(noul|noua|un nou|o noua) (director|presedinte|sef|manager|ceo|cfo|cio|cto|ciso|coo|cdo)", r"a fost (numit|numita|ales|aleasa|revocat|revocata)",
        r"numit(a)? (in functia de|director|la conducerea)", r"(si-a dat|isi da|a demisionat|demisia)", r"schimbar(e|i) la (conducere|varf)", r"preia conducerea",
        r"director(ul)? (de )?(it|tehnic|digital|digitalizare|operatiuni|operational|transformare|automatizare|inovare)", r"head of (digital|automation|process|it|operations|transformation)",
        r"chief (digital|operating|information|technology|transformation|automation)", r"appointed", r"new (ceo|cio|cto|ciso|coo|chief)", r"steps down",
        r"neue[rn]? (chef|vorstand|ceo|cio|geschaeftsfuehrer|geschaftsfuhrer)", r"vorstandswechsel",
    ), _x("CIO", "CTO", "CISO", "CDO", "COO")),
    Topic("shared_services", "Servicii partajate / consolidarea proceselor", ("apa",), _p(
        r"servicii partajate", r"centr(u|ul) de servicii", r"shared service", r"global business services", r"centr(u|ul) de competent",
        r"centr(u|ul) de excelent", r"center of excellence", r"centre of excellence", r"consolidar(e|ea) (a )?(proces|operatiun|activitat|functii)",
        r"centraliz(are|area) (a )?(proces|operatiun|activitat|functii)", r"back[- ]office", r"hub (operational|de servicii)", r"shared-service",
    ), _x("GBS", "SSC", "CoE")),
    Topic("tech_partners", "Tehnologii folosite / parteneri tehnologici", ("apa", "cyber", "cloud", "erp"), _p(
        r"uipath", r"automation anywhere", r"blue prism", r"celonis", r"servicenow", r"salesforce", r"microsoft (azure|dynamics|365|copilot)", r"azure",
        r"oracle", r"s/?4 ?hana", r"amazon web services", r"google cloud", r"ibm", r"accenture", r"deloitte", r"kpmg", r"capgemini", r"endava", r"ntt data",
        r"bitdefender", r"crowdstrike", r"palo alto", r"fortinet", r"partener(ul)? tehnologic", r"parteneriat (strategic|tehnologic|cu)",
        r"a (semnat|incheiat|castigat) (un )?contract", r"technology partner", r"partnership with", r"partnerschaft", r"kooperation mit",
    ), _x("AWS", "SAP")),
    # --- Problems that create an immediate need (cyber and automation) ---
    Topic("security_incident", "Incident de securitate / atac cibernetic", ("cyber",), _p(
        r"atac(uri)? (cibernetic|informatic)", r"hacker", r"ransomware", r"malware", r"phishing", r"ddos",
        r"bres[ae] de securitate", r"scurger(e|i) de date", r"furt(ul)? de date", r"date(le)? (personale )?(furate|expuse|compromise|sustrase)",
        r"incident(ul)? (de securitate|cibernetic|informatic)", r"securitat(e|ea) cibernetic", r"virus informatic",
        r"cyber ?attack", r"data breach", r"security (breach|incident)", r"hacked", r"data leak",
        r"cyberangriff", r"hackerangriff", r"datenleck", r"datendiebstahl", r"sicherheitsluecke", r"sicherheitslucke", r"cyberattacke",
    )),
    Topic("it_outage", "Pană IT / sistem indisponibil", ("cyber", "apa", "cloud"), _p(
        r"probleme tehnice", r"defectiun(e|i) tehnic", r"pana (de sistem|informatica|tehnica|generala)", r"sistem(ul)? informatic (a cazut|nu functioneaza|blocat)",
        r"(site|aplicatia|platforma|sistemul)(ul)? (a cazut|nu functioneaza|este indisponibil|indisponibil)", r"indisponibil", r"blocaj(ul)? (informatic|sistemului)",
        r"outage", r"downtime", r"system failure", r"it glitch", r"systemausfall", r"it-?stoerung", r"it-?storung", r"it-?panne", r"serverausfall",
    )),
    Topic("compliance", "Conformitate, amenzi, GDPR / NIS2 / DORA", ("cyber",), _p(
        r"gdpr", r"anspdcp", r"protectia datelor", r"amend(a|at|ata|at[ae]|ati)", r"sanctionat", r"sanctiun(e|i)", r"penalitat",
        r"conformitat", r"consiliul concurentei", r"autoritatea de supraveghere", r"control(ul)? (anaf|itm|anpc)", r"anpc",
        r"regulatory fine", r"\bfined\b", r"compliance", r"bussgeld", r"datenschutz", r"dsgvo", r"bafin", r"geldstrafe",
    ), _x("NIS2", "NIS 2", "DORA", "GDPR", "DSGVO")),
    Topic("operational_issues", "Probleme operaționale, reclamații", ("apa",), _p(
        r"intarzier", r"reclamati", r"nemultumi", r"plangeri", r"cozi (la|uriase|interminabile)", r"aglomerat", r"erori", r"greseli", r"haos",
        r"probleme (la|cu|in|grave|majore)", r"lips(a|a) de personal", r"lipsa personalului", r"criz(a|ei) (de|la)", r"scandal", r"blocaj",
        r"complaints", r"delays", r"backlog", r"beschwerde", r"verzoegerung", r"verzogerung", r"chaos", r"engpass", r"personalmangel",
    )),
    Topic("financial_pressure", "Pierderi, datorii, dificultăți financiare", ("apa",), _p(
        r"pierder(e|i|ea|ile)", r"datori(i|ile)", r"insolvent", r"faliment", r"scader(e|ea) (a )?(profit|cifrei|veniturilor|vanzarilor)",
        r"profit(ul)? (a )?(scazut|s-a prabusit|in scadere)", r"dificultat(i|ile) financiare", r"deficit", r"executar(e|ea) silit", r"\bnet loss", r"insolvency", r"bankrupt",
        r"insolvenz", r"verlust", r"gewinnwarnung", r"umsatzrueckgang", r"umsatzruckgang", r"gewinneinbruch",
    )),
    Topic("growth_investment", "Investiții, extindere, achiziții", ("apa", "cyber", "cloud", "erp"), _p(
        r"investi(tie|tii|tia|tiei|ti|ste|ta)", r"extind(e|ere|erea)", r"fabric(a|i) no(ua|i)", r"achizit(ie|ia|ionat)", r"preluar(e|ea)", r"fuziun", r"a cumparat",
        r"(noi|nou|noua) (sediu|centru|magazin|filiala|linie)", r"acquisition", r"acquires", r"merger", r"expansion", r"investment",
        r"uebernahme", r"ubernahme", r"investition", r"neues werk",
    )),
    # --- Negative signals (Annex 1: layoffs, hiring freeze, IT budget cuts lower the fit) ---
    Topic("layoffs_cuts", "Concedieri / înghețarea angajărilor / tăieri de buget IT (semnal negativ)", ("apa",), _p(
        r"concedi(er|a)", r"disponibiliz", r"somaj tehnic", r"reducer(e|ea) (de|a) personal", r"posturi (desfiintate|taiate|eliminate)",
        r"taier(i|ea) de (costuri|personal|posturi|buget)", r"inghet(are|area) (a )?angajarilor", r"layoffs?", r"job cuts", r"hiring freeze",
        r"stellenabbau", r"entlassung", r"einstellungsstopp",
    )),
)

TOPIC_KEYS = tuple(t.key for t in TOPICS)
TOPIC_LABELS = {t.key: t.label for t in TOPICS}
# Topics that name a need or a change project; growth news only adds context.
STRONG_TOPICS = frozenset(TOPIC_KEYS) - {"growth_investment"}
# Topics that lower the fit (Annex 1 negative signals).
NEGATIVE_TOPICS = frozenset({"layoffs_cuts"})


def plain(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s)


def classify(text: str) -> list[str]:
    """Topic keys covered by `text` (title + body), in TOPICS order."""
    low = plain(text)
    return [t.key for t in TOPICS if t.plain.search(low) or (t.exact is not None and t.exact.search(text or ""))]


def story_key(title: str) -> str:
    """Same story from several outlets -> same key (first 8 words of the plain title, outlet suffix dropped)."""
    t = re.split(r"\s[-|–]\s(?=[^-|–]+$)", title or "")[0]
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", plain(t)).split()[:8])


# Google News OR-queries per language (opt-in): each group covers a few topics.
TOPIC_QUERIES: dict[str, tuple[str, ...]] = {
    "ro": (
        '(eficientizare OR "reducerea costurilor" OR restructurare OR digitalizare OR "transformare digitala" OR cloud OR ERP)',
        '(automatizare OR "inteligenta artificiala" OR RPA OR robot OR "process mining" OR "servicii partajate" OR UiPath)',
        '(CIO OR COO OR "director IT" OR "director de digitalizare" OR "a fost numit" OR angajeaza OR parteneriat)',
        '(atac cibernetic OR hackeri OR ransomware OR GDPR OR NIS2 OR amenda OR "probleme tehnice" OR pierderi OR concedieri)',
    ),
    "de": (
        '(Effizienzprogramm OR Kostensenkung OR Umstrukturierung OR Digitalisierung OR Cloud OR SAP OR ERP)',
        '(Automatisierung OR KI OR "künstliche Intelligenz" OR RPA OR "Process Mining" OR "Shared Service" OR UiPath)',
        '(CIO OR COO OR CDO OR "neuer Vorstand" OR ernannt OR Partnerschaft OR "sucht IT")',
        "(Cyberangriff OR Hackerangriff OR Datenleck OR DSGVO OR NIS2 OR Bußgeld OR Störung OR Verlust OR Stellenabbau)",
    ),
    "en": (
        '("cost reduction" OR efficiency OR restructuring OR "digital transformation" OR cloud OR ERP OR SAP)',
        '(automation OR AI OR RPA OR "agentic AI" OR "process mining" OR "shared services" OR UiPath)',
        "(CIO OR COO OR CDO OR appointed OR hiring OR partnership)",
        '(cyberattack OR "data breach" OR ransomware OR GDPR OR NIS2 OR fine OR outage OR loss OR layoffs)',
    ),
}
# Bing News ignores OR, so the themes are asked one keyword per request (about 12 latest articles each).
BING_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ro": ("digitalizare", "automatizare", '"inteligenta artificiala"', '"atac cibernetic"', "restructurare", "pierderi",
           "director", "angajeaza"),
    "de": ("Digitalisierung", "Automatisierung", "KI", "Cyberangriff", "Umstrukturierung", "Verlust", "Vorstand", "Stellenabbau"),
    "en": ('"digital transformation"', "automation", "AI", "cyberattack", "restructuring", "loss", "appointed", "layoffs"),
}
COUNTRY_LANGUAGE = {"RO": "ro", "MD": "ro", "DE": "de", "AT": "de", "CH": "de"}


def topic_queries(country: str | None) -> tuple[str, ...]:
    """Google News OR-queries (opt-in provider google_topics)."""
    return TOPIC_QUERIES[COUNTRY_LANGUAGE.get(country or "", "en")]


def bing_topic_keywords(country: str | None) -> tuple[str, ...]:
    return BING_TOPIC_KEYWORDS[COUNTRY_LANGUAGE.get(country or "", "en")]


# GDELT wants plain OR lists of words / quoted phrases (no accents needed); one mixed-language query per company.
GDELT_TOPIC_TERMS = (  # fetch_gdelt quotes the multi-word ones
    "atac cibernetic", "hackeri", "ransomware", "GDPR", "NIS2", "digitalizare", "automatizare", "inteligenta artificiala",
    "restructurare", "concedieri", "pierderi", "insolventa", "Cyberangriff", "Digitalisierung", "Stellenabbau", "Insolvenz",
    "cyberattack", "data breach", "automation", "layoffs",
)
