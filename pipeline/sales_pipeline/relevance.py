"""Cheap relevance filter (GIG-25 node 2): pick, per question, the document
passages worth sending to the LLM. Lexical scoring keeps it free and
deterministic; the LLM only ever sees the top passages."""
from __future__ import annotations

import re
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


class Chunk(BaseModel):
    doc_index: int
    url: str
    title: str
    date: str
    source_type: str
    text: str


def question_terms(q: QuestionSpec) -> list[str]:
    if q.keywords:
        return [k.lower() for k in q.keywords]
    words = re.findall(r"[a-zA-Z0-9/]+", q.text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


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
    t = text.lower()
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
