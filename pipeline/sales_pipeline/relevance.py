"""Cheap relevance filter (GIG-25 node 2): pick, per question, the document
passages worth sending to the LLM. Lexical scoring keeps it free and
deterministic; the LLM only ever sees the top passages."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from .documents import Document
from .schemas import QuestionSpec

STOPWORDS = set(
    """a an and are as at be been by company companies does do for from has have hiring if in into is it its
    of on or recent recently roles such that the their this to was were what whether which with any mention
    currently subject suffered""".split()
)
CHUNK_CHARS = 1200

# Signal questions and their keywords are written in English, while RO / MD / DE news is not. Every English
# term (or a term containing it) also searches these stems; matching is accent-insensitive and prefix-based,
# so "automatiz" finds automatizare, automatizarea, automatizari, automatizeaza.
TERM_TRANSLATIONS: dict[str, list[str]] = {
    "automation": ["automatiz", "automatis", "automatisier"],
    "automate": ["automatiz"],
    "robotic process automation": ["rpa", "robotizarea proceselor"],
    "process optimization": ["optimizarea proceselor", "optimizare", "eficientiz", "prozessoptimierung"],
    "process excellence": ["excelenta operationala", "optimizarea proceselor"],
    "process mining": ["process mining", "minarea proceselor"],
    "process consolidation": ["consolidarea proceselor", "centralizare"],
    "cost reduction": ["reducerea costurilor", "reducere a costurilor", "costuri mai mici", "kostensenkung"],
    "savings": ["economii", "economisi", "einsparung"],
    "efficiency": ["eficient", "eficacit", "effizienz"],
    "digitalization": ["digitaliz", "digitalis", "digitalisierung"],
    "digital transformation": ["transformare digitala", "transformarea digitala", "digitaliz", "digitale transformation"],
    "artificial intelligence": ["inteligenta artificiala", "inteligentei artificiale", "kunstliche intelligenz"],
    "generative ai": ["ai generativ", "inteligenta artificiala generativa"],
    "agentic ai": ["agenti ai", "agenti inteligenti"],
    "ai use cases": ["inteligenta artificiala", "solutii ai", "solutii de ai"],
    "machine learning": ["invatare automata", "machine learning"],
    "shared service": ["servicii partajate", "centru de servicii", "shared services"],
    "global business services": ["servicii partajate", "hub regional"],
    "service centre": ["centru de servicii", "hub de servicii"],
    "partnership": ["parteneriat", "partener", "partnerschaft"],
    "partner": ["parteneriat", "partener"],
    "vendor": ["furnizor"],
    "third-party": ["furnizor", "partener"],
    "automation engineer": ["inginer automatizari", "specialist automatizare"],
    "business analyst": ["analist de business", "analist business"],
    "ai engineer": ["inginer ai", "specialist ai"],
    "center of excellence": ["centru de excelenta"],
    "centre of excellence": ["centru de excelenta"],
    "in-house": ["intern", "propriul departament"],
    "layoffs": ["concedier", "disponibiliz", "restructurar", "entlassung", "stellenabbau"],
    "hiring freeze": ["inghetarea angajarilor", "blocarea angajarilor"],
    "budget cuts": ["taieri bugetare", "reduceri bugetare", "reducerea bugetului"],
    "cost freeze": ["inghetarea costurilor"],
    "appointed": ["numit", "a fost numit", "a fost numita", "preia conducerea", "noul director", "noua directoare", "ernannt"],
    "joins as": ["se alatura", "preia functia"],
    "new cio": ["director it", "director de tehnologie", "noul cio"],
    "new coo": ["director operational", "noul coo"],
    "new ceo": ["director general", "noul ceo"],
    "chief digital officer": ["director digital"],
    "head of digital": ["director digital", "sef digital"],
    "chief information security officer": ["director de securitate", "responsabil cu securitatea"],
    "new ciso": ["director de securitate", "noul ciso"],
    "data breach": ["bresa de securitate", "scurgere de date", "scurgeri de date", "date furate", "datenleck"],
    "breach": ["bresa", "scurgere de date", "compromis"],
    "ransomware": ["ransomware", "atac cu ransomware", "rascumparare"],
    "cyberattack": ["atac cibernetic", "atacuri cibernetice", "atac informatic", "cyberangriff", "hackerangriff"],
    "cyber attack": ["atac cibernetic", "atac informatic"],
    "hacked": ["piratat", "spart", "atacat de hackeri", "hackeri"],
    "security incident": ["incident de securitate", "incident cibernetic", "sicherheitsvorfall"],
    "outage": ["pana", "avarie", "intrerupere", "nefunctional", "ausfall"],
    "nis2": ["nis2", "nis 2", "directiva nis"],
    "dora": ["dora", "reziliente operationale digitale"],
    "critical infrastructure": ["infrastructura critica", "kritische infrastruktur"],
    "essential entity": ["entitate esentiala", "entitati esentiale"],
    "security": ["securitat", "securitate cibernetica", "sicherheit"],
    "cloud migration": ["migrare in cloud", "migrarea in cloud", "trecerea in cloud"],
    "move to the cloud": ["in cloud"],
    "digital channels": ["canale digitale", "aplicatie mobila", "online banking"],
    "e-commerce": ["comert online", "magazin online", "ecommerce"],
    "managed security": ["securitate gestionata", "servicii de securitate"],
    "security partner": ["partener de securitate"],
    "selects": ["a ales", "a selectat", "contract cu"],
    "insolvency": ["insolventa", "intrat in insolventa", "insolvenz"],
    "bankruptcy": ["faliment", "falimentul", "konkurs"],
    "creditor protection": ["concordat preventiv", "protectia creditorilor"],
    "acquisition": ["achizitie", "achizitia", "preluare", "a preluat", "ubernahme"],
    "restructuring": ["restructurar", "reorganizar", "umstrukturierung"],
    "strategy 2030": ["strategia 2030", "strategie 2030"],
}


def fold(text: str) -> str:
    """Lower case without diacritics: 'Automatizări' -> 'automatizari'."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def expand_terms(terms: list[str]) -> list[str]:
    out: list[str] = []
    for term in terms:
        t = fold(term)
        for extra in [t, *(v for key, values in TERM_TRANSLATIONS.items() if key == t or key in t for v in values)]:
            if extra and extra not in out:
                out.append(extra)
    return out


class Chunk(BaseModel):
    doc_index: int
    url: str
    title: str
    date: str
    source_type: str
    text: str


def question_terms(q: QuestionSpec) -> list[str]:
    if q.keywords:
        return expand_terms(q.keywords)
    words = re.findall(r"[a-zA-Z0-9/]+", fold(q.text))
    return expand_terms([w for w in words if w not in STOPWORDS and len(w) > 2])


def split_chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, cur = [], ""
    for s in sentences:
        if len(cur) + len(s) > size and cur:
            chunks.append(cur.strip())
            cur = ""
        cur += s + " "
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def score_text(text: str, terms: list[str]) -> float:
    t = fold(text)
    score = 0.0
    for term in terms:
        hits = len(re.findall(r"(?<![a-z])" + re.escape(term), t))
        if hits:
            score += 1 + min(hits - 1, 3) * 0.25 + (0.5 if " " in term else 0)
    return score


def within_lookback(doc: Document, days: int, now: datetime | None = None) -> bool:
    if doc.published_at is None:
        return True  # undated website pages stay eligible; recency scoring discounts them
    now = now or datetime.now(timezone.utc)
    published = doc.published_at if doc.published_at.tzinfo else doc.published_at.replace(tzinfo=timezone.utc)
    return published >= now - timedelta(days=days)


def select_chunks(docs: list[Document], question: QuestionSpec, top_k: int = 6, min_score: float = 1.0) -> list[Chunk]:
    terms = question_terms(question)
    candidates: list[tuple[float, Chunk]] = []
    for i, doc in enumerate(docs):
        if question.source_hint != "any" and doc.source_type != question.source_hint:
            continue
        if not within_lookback(doc, question.lookback_days):
            continue
        for part in split_chunks(f"{doc.title}. {doc.text}" if doc.title and doc.title not in doc.text[:200] else doc.text):
            s = score_text(part, terms)
            if s >= min_score:
                candidates.append(
                    (s, Chunk(doc_index=i, url=doc.url, title=doc.title, date=doc.date_str, source_type=doc.source_type, text=part))
                )
    candidates.sort(key=lambda x: -x[0])
    return [c for _, c in candidates[:top_k]]
