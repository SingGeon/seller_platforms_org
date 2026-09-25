"""Anti-hallucination guard (GIG-26): every quote the LLM returns must exist in
the source text it cites; answers left without valid evidence become `unknown`."""
from __future__ import annotations

from rapidfuzz import fuzz

from .documents import clean_text, normalize_url
from .relevance import Chunk
from .schemas import Answer, Evidence

QUOTE_MATCH_THRESHOLD = 85


def quote_in_text(quote: str, text: str, threshold: int = QUOTE_MATCH_THRESHOLD) -> bool:
    q = clean_text(quote).lower().strip(" .\"'…")
    t = clean_text(text).lower()
    if len(q) < 12:
        return False
    if q in t:
        return True
    return fuzz.partial_ratio(q, t) >= threshold


def validate_answer(answer: Answer, chunks: list[Chunk]) -> Answer:
    by_url: dict[str, list[Chunk]] = {}
    for c in chunks:
        by_url.setdefault(normalize_url(c.url), []).append(c)
    valid: list[Evidence] = []
    for ev in answer.evidence:
        candidates = by_url.get(normalize_url(ev.url), [])
        match = next((c for c in candidates if quote_in_text(ev.quote, c.text)), None)
        if match:
            valid.append(Evidence(quote=ev.quote, url=match.url, date=ev.date if ev.date != "unknown" else match.date))
    out = answer.model_copy(update={"evidence": valid})
    if not valid and answer.answer != "unknown":
        dropped = len(answer.evidence)
        out.answer = "unknown"
        out.confidence = 0.0
        out.reasoning = (
            f"No verifiable evidence ({dropped} quote(s) not found in sources). Original: {answer.reasoning}"
            if dropped
            else "No evidence in the collected documents."
        )
    out.confidence = max(0.0, min(1.0, out.confidence))
    return out
