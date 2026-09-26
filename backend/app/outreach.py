"""Personalised outreach drafts (GIG-38)."""
from __future__ import annotations

from sales_pipeline.documents import clean_text
from sales_pipeline.llm import LLMBackend, cache_key
from sales_pipeline.schemas import Usage

from .models import Service
from .mongo import MDoc

CHANNEL_LIMITS = {"email": 120, "followup": 80}  # words
LINKEDIN_MAX_CHARS = 300


def _enforce_limits(channel: str, draft: dict) -> dict:
    body = draft.get("body", "")
    if channel == "linkedin" and len(body) > LINKEDIN_MAX_CHARS:
        body = body[: LINKEDIN_MAX_CHARS - 1].rsplit(" ", 1)[0] + "…"
    limit = CHANNEL_LIMITS.get(channel)
    if limit:
        words = body.split(" ")
        if len(words) > limit:
            body = " ".join(words[:limit]).rstrip(",;") + "…"
    return {**draft, "body": body}


def grounded_in_signals(body: str, top_signals: list[dict]) -> bool:
    """AC check: the message must reference at least one real signal. We accept either a
    fragment of an evidence quote or a distinctive term from it appearing in the body."""
    text = clean_text(body).lower()
    for s in top_signals:
        quote = clean_text(s.get("quote", "")).lower()
        if quote and quote[:40] in text:
            return True
        terms = [w for w in quote.replace(",", " ").split() if len(w) > 6]
        if sum(1 for w in set(terms) if w in text) >= 2:
            return True
    return False


async def generate_outreach(
    llm: LLMBackend, company: MDoc, service: Service, lead: MDoc | None, *, channel: str, tone: str, language: str,
    cache=None, fresh: bool = False,
) -> dict:
    """An AI draft is saved under its inputs: the same lead, signals and options give it back without spending tokens
    (`fresh` asks the AI for a new one). When every AI provider is out of quota, the saved draft is returned instead
    of the offline template; the offline one is never saved."""
    top = (lead.explanation or {}).get("top_signals", []) if lead else []
    payload = {
        "company": company.name,
        "industry": company.industry,
        "country": company.country,
        "service": service.name,
        "value_proposition": service.value_proposition,
        "channel": channel,
        "tone": tone,
        "language": language,
        "why_now": (lead.explanation or {}).get("summary", "") if lead else "",
        "top_signals": [{"question": s["label"], "quote": s["quote"], "date": s["date"], "url": s["url"]} for s in top],
    }
    key = cache_key("outreach", payload)
    saved = cache.get(key) if cache else None
    if saved is not None and not fresh:
        draft, usage = saved, Usage(cache_hits=1)
    else:
        draft, usage = await llm.write_outreach(payload)
        if usage.llm_calls and draft and cache:
            cache.set(key, draft)
        elif not usage.llm_calls and saved is not None:
            draft = saved
    draft = _enforce_limits(channel, draft or {"subject": "", "body": "", "signals_used": []})
    return {
        "channel": channel,
        "tone": tone,
        "language": language,
        **draft,
        "grounded": grounded_in_signals(draft.get("body", ""), top) if top else False,
        "sources": [{"url": s["url"], "date": s["date"]} for s in top],
        "usage": usage.model_dump(),
    }
