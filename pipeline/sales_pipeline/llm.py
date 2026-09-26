"""LLM backends.

- `AnthropicBackend`: Claude via the official Anthropic SDK. The large model
  answers signal questions, writes explanations and outreach; the small model
  classifies events (GIG-28: small model for classification, large for answers).
- `HeuristicBackend`: deterministic keyword-based stand-in so the whole
  platform runs (demo, tests, CI) without an API key.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from typing import Any, Protocol

from .documents import clean_text
from .prompts import (
    CHANNEL_RULES,
    EVENTS_SCHEMA,
    EVENTS_SYSTEM,
    EXPLAIN_SYSTEM,
    OUTREACH_SCHEMA,
    OUTREACH_SYSTEM,
    SIGNAL_SCHEMA,
    SIGNAL_SYSTEM,
    render_passages,
    signal_user_prompt,
)
from .relevance import Chunk, fold, question_terms, score_text

EXTRACT_SYSTEM = """For each numbered news headline or snippet, name the single company or public organisation it is \
primarily about (the one that announced, suffered or did the thing), as it would appear in a company register. \
Skip items about people only, countries, markets or several companies equally. Only include a domain or ISO-2 \
country code when the text states it; otherwise use an empty string."""
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "companies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "company": {"type": "string"},
                    "domain": {"type": "string"},
                    "country": {"type": "string"},
                },
                "required": ["index", "company", "domain", "country"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["companies"],
    "additionalProperties": False,
}
from .schemas import Answer, CompanyInfo, DetectedEvent, Evidence, QuestionSpec, Usage

log = logging.getLogger(__name__)

# USD per million tokens (input, output).
PRICING = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICING.get(model, (5.0, 25.0))
    return round((input_tokens * pin + output_tokens * pout) / 1_000_000, 6)


class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value


def cache_key(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


class LLMBackend(Protocol):
    name: str

    async def answer_questions(self, company: CompanyInfo, questions: list[QuestionSpec], chunks: list[Chunk]) -> tuple[list[Answer], Usage]: ...
    async def classify_events(self, company: CompanyInfo, chunks: list[Chunk]) -> tuple[list[DetectedEvent], Usage]: ...
    async def explain_lead(self, payload: dict[str, Any]) -> tuple[str, Usage]: ...
    async def write_outreach(self, payload: dict[str, Any]) -> tuple[dict[str, Any], Usage]: ...
    async def extract_companies(self, texts: list[str]) -> tuple[list[dict[str, Any]], Usage]: ...


def _map_evidence(raw: list[dict[str, str]], ids: dict[str, Chunk]) -> list[Evidence]:
    out = []
    for ev in raw:
        chunk = ids.get(ev.get("doc_id", "").strip("[] "))
        if chunk:
            out.append(Evidence(quote=ev.get("quote", ""), url=chunk.url, date=chunk.date))
    return out


# --------------------------------------------------------------------------- Claude


class AnthropicBackend:
    name = "anthropic"

    def __init__(
        self,
        *,
        model: str = "claude-opus-5",
        small_model: str = "claude-haiku-4-5",
        effort: str = "medium",
        max_concurrency: int = 8,
        client: Any | None = None,
    ) -> None:
        import anthropic

        self._anthropic = anthropic
        self.client = client or anthropic.AsyncAnthropic(max_retries=3)
        self.model = model
        self.small_model = small_model
        self.effort = effort
        self._sem = asyncio.Semaphore(max_concurrency)

    async def _json_call(self, *, model: str, system: str, user: str, schema: dict, max_tokens: int = 16000, effort: str | None = None) -> tuple[dict, Usage]:
        """One structured-output call, returning parsed JSON and usage."""
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        async with self._sem:
            if model.startswith("claude-haiku"):
                # Haiku 4.5 has no effort control; plain structured output is enough for classification.
                response = await self.client.messages.create(**kwargs)
            else:
                kwargs["output_config"]["effort"] = effort or self.effort
                # Server-side fallback: if a safety classifier declines, the API re-runs the
                # request on Anthropic's recommended fallback model inside the same call.
                response = await self.client.beta.messages.create(
                    **kwargs,
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )
        usage = Usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            llm_calls=1,
            cost_usd=estimate_cost(model, response.usage.input_tokens, response.usage.output_tokens),
        )
        if response.stop_reason == "refusal":
            log.warning("model declined request (%s)", getattr(response.stop_details, "category", None))
            return {}, usage
        if response.stop_reason == "max_tokens":
            log.warning("structured output truncated at max_tokens=%s", max_tokens)
            return {}, usage
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return json.loads(text), usage
        except json.JSONDecodeError:
            log.warning("invalid JSON from model: %s", text[:200])
            return {}, usage

    async def answer_questions(self, company, questions, chunks):
        passages, ids = render_passages(chunks)
        data, usage = await self._json_call(
            model=self.model, system=SIGNAL_SYSTEM, user=signal_user_prompt(company, questions, passages), schema=SIGNAL_SCHEMA
        )
        by_key = {a.get("key"): a for a in data.get("answers", [])}
        answers = []
        for q in questions:
            raw = by_key.get(q.key)
            if not raw:
                answers.append(Answer(key=q.key, reasoning="Model returned no answer."))
                continue
            answers.append(
                Answer(
                    key=q.key,
                    answer=raw.get("answer", "unknown"),
                    confidence=float(raw.get("confidence", 0)),
                    evidence=_map_evidence(raw.get("evidence", []), ids),
                    reasoning=raw.get("reasoning", ""),
                )
            )
        return answers, usage

    async def classify_events(self, company, chunks):
        passages, ids = render_passages(chunks)
        data, usage = await self._json_call(
            model=self.small_model,
            system=EVENTS_SYSTEM,
            user=f"Company: {company.name}\n\n<passages>\n{passages}\n</passages>",
            schema=EVENTS_SCHEMA,
            max_tokens=8000,
        )
        events = []
        for e in data.get("events", []):
            chunk = ids.get(e.get("doc_id", ""))
            if not chunk:
                continue
            events.append(
                DetectedEvent(
                    event_type=e["event_type"],
                    subtype=e.get("subtype", ""),
                    title=e.get("title", "")[:300],
                    summary=e.get("summary", ""),
                    date=chunk.date,
                    url=chunk.url,
                    entities=e.get("entities", []),
                    polarity=e.get("polarity", "neutral"),
                )
            )
        return events, usage

    async def explain_lead(self, payload):
        async with self._sem:
            response = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=2000,
                system=EXPLAIN_SYSTEM,
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}],
            )
        usage = Usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            llm_calls=1,
            cost_usd=estimate_cost(self.model, response.usage.input_tokens, response.usage.output_tokens),
        )
        if response.stop_reason == "refusal":
            return "", usage
        return next((b.text for b in response.content if b.type == "text"), "").strip(), usage

    async def write_outreach(self, payload):
        channel = payload.get("channel", "email")
        user = (
            f"{CHANNEL_RULES.get(channel, CHANNEL_RULES['email'])}\n"
            f"Tone: {payload.get('tone', 'consultative')}. Language: {payload.get('language', 'EN')}.\n\n"
            f"<input>\n{json.dumps(payload, ensure_ascii=False, default=str)}\n</input>"
        )
        data, usage = await self._json_call(model=self.model, system=OUTREACH_SYSTEM, user=user, schema=OUTREACH_SCHEMA, max_tokens=4000, effort="low")
        return data, usage


    async def extract_companies(self, texts):
        """Name the organisation each headline is about (discovery items the regex could not parse)."""
        numbered = "\n".join(f"[{i}] {t}" for i, t in enumerate(texts))
        data, usage = await self._json_call(
            model=self.small_model, system=EXTRACT_SYSTEM, user=numbered, schema=EXTRACT_SCHEMA, max_tokens=4000
        )
        out = [e for e in data.get("companies", []) if isinstance(e.get("index"), int) and 0 <= e["index"] < len(texts) and e.get("company")]
        return out, usage


# --------------------------------------------------------------------------- Offline


EVENT_PATTERNS: dict[str, list[tuple[str, str, str]]] = {
    # event_type: [(regex, subtype, polarity)]; matched on lower-case text without diacritics (relevance.fold),
    # English first, then Romanian for the RO / MD press.
    "security_incident": [
        (r"data breach|breach of|ransomware|cyber ?attack|hack(ed|ers)|security incident|outage", "incident", "neutral"),
        (r"atac(ul|uri)? (cibernetic|informatic)|bresa de securitate|scurger(e|i)(a)? de date|atacat de hackeri|incident (de securitate|cibernetic)", "incident", "neutral"),
    ],
    "leadership_change": [
        (r"(appoint|named|hires?|joins?|new)\b.{0,60}\b(ceo|cio|cto|ciso|coo|cdo|chief [a-z]+ officer|head of (digital|automation|it))", "appointment", "positive"),
        (r"(ceo|cio|cto|ciso|coo|cdo)\b.{0,40}\b(steps down|resigns|to leave|departs)", "departure", "neutral"),
        (r"(a fost numit|a fost numita|preia (conducerea|functia)|noul|noua)\b.{0,60}\b(director general|director executiv|ceo|cio|cto|cfo|coo|director it|director de tehnologie|presedinte)", "appointment", "positive"),
        (r"(director general|ceo|presedinte)\b.{0,40}\b(demisioneaza|a demisionat|pleaca de la conducere)", "departure", "neutral"),
    ],
    "tech_stack": [
        (r"s/4hana|sap migration|migrat\w+ to (the )?cloud|uipath|salesforce|servicenow|celonis|power automate", "technology", "neutral"),
        (r"migrare(a)? in cloud|trecerea in cloud|implementarea (sap|erp)", "technology", "neutral"),
    ],
    "compliance_event": [
        (r"\bnis ?2\b|\bdora\b|gdpr fine|fined .{0,40}(gdpr|data protection)|regulatory audit|iso 27001", "regulation", "neutral"),
        (r"\banspdcp\b|amend\w* .{0,40}(gdpr|protectia datelor)|directiva nis", "regulation", "neutral"),
    ],
    "corporate_event": [
        (r"layoffs?|job cuts|cut .{0,20}(jobs|positions)|hiring freeze|insolven", "downsizing", "negative"),
        (r"acquires|acquisition of|merger|to acquire", "m&a", "positive"),
        (r"raises? \$?€?\d|funding round|series [a-e]\b", "funding", "positive"),
        (r"restructur|transformation program|efficiency program", "restructuring", "neutral"),
        (r"concedier|disponibiliz|insolventa|faliment", "downsizing", "negative"),
        (r"achizitia|a achizitionat|a preluat|preluarea|fuziune", "m&a", "positive"),
        (r"runda de finantare|a atras .{0,30}(euro|lei|dolari)|investitie de .{0,20}(milioane|mil\.)", "funding", "positive"),
        (r"reorganizar|program de eficientizare", "restructuring", "neutral"),
    ],
}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20]


class HeuristicBackend:
    """Keyword-matching stand-in for an LLM. Quotes are copied verbatim from the
    passages, so they always pass evidence validation."""

    name = "heuristic"
    model = "heuristic"
    small_model = "heuristic"

    def __init__(self, min_hits: float = 2.0) -> None:
        self.min_hits = min_hits

    async def answer_questions(self, company, questions, chunks):
        answers = []
        for q in questions:
            terms = question_terms(q)
            best: list[tuple[float, str, Chunk]] = []
            for c in chunks:
                for sent in _sentences(c.text):
                    s = score_text(sent, terms)
                    if s >= self.min_hits:
                        best.append((s, sent, c))
            best.sort(key=lambda x: -x[0])
            if not best:
                answers.append(Answer(key=q.key, answer="unknown", confidence=0.0, reasoning="No matching passages."))
                continue
            top = best[:2]
            conf = min(0.9, 0.45 + 0.1 * top[0][0])
            answers.append(
                Answer(
                    key=q.key,
                    answer="yes",
                    confidence=round(conf, 2),
                    evidence=[Evidence(quote=s[:400], url=c.url, date=c.date) for _, s, c in top],
                    reasoning=f"Keyword match in {len(best)} passage(s), e.g. '{top[0][1][:120]}'.",
                )
            )
        return answers, Usage()

    async def classify_events(self, company, chunks):
        events: list[DetectedEvent] = []
        for c in chunks:
            text = f"{c.title}. {c.text}"
            folded = fold(text)
            for etype, patterns in EVENT_PATTERNS.items():
                for pattern, subtype, polarity in patterns:
                    m = re.search(pattern, folded)
                    if m:
                        sentence = next((s for s in _sentences(text) if re.search(pattern, fold(s))), c.title)
                        events.append(
                            DetectedEvent(
                                event_type=etype, subtype=subtype, title=clean_text(c.title or sentence)[:300],
                                summary=sentence[:400], date=c.date, url=c.url, entities=[m.group(0)], polarity=polarity,
                            )
                        )
                        break
        return events, Usage()

    async def explain_lead(self, payload):
        sigs = payload.get("top_signals", [])
        if not sigs:
            return "", Usage()
        parts = [f"{payload['company']} shows {len(sigs)} relevant signal(s) for {payload['service']}"]
        parts.append("; ".join(s["question"].rstrip("?") + (f" ({s['date']})" if s.get("date") and s["date"] != "unknown" else "") for s in sigs[:3]))
        return f"{parts[0]}: {parts[1]}. Recommended action: {payload.get('recommendation', 'monitor')}.", Usage()

    async def write_outreach(self, payload):
        company = payload["company"]
        sig = (payload.get("top_signals") or [{}])[0]
        quote = sig.get("quote", "")
        language = str(payload.get("language") or "EN").upper()
        t = OUTREACH_TEMPLATES.get(language, OUTREACH_TEMPLATES["EN"])
        service = SERVICE_NAMES_BY_LANGUAGE.get(language, {}).get(payload["service"], payload["service"])
        # The configured value proposition is written in English; other languages use their own sentence.
        vp = (payload.get("value_proposition") if language == "EN" else None) or t["vp"].format(service=service)
        hook = t["hook_quote"].format(company=company, quote=quote[:160]) if quote else t["hook"].format(company=company)
        channel = payload.get("channel", "email")
        if channel == "linkedin":
            body = t["linkedin"].format(hook=hook[:170], service=service)
            subject = t["subject_linkedin"].format(service=service, company=company)
            return {"subject": subject[:1].upper() + subject[1:], "body": body[:300],
                    "signals_used": [sig.get("question", "")]}, Usage()
        body = t["body"].format(hook=hook, vp=vp)
        subject = (t["subject_email"] if channel == "email" else t["subject_followup"]).format(service=service, company=company)
        subject = subject[:1].upper() + subject[1:]
        return {"subject": subject, "body": body, "signals_used": [sig.get("question", "")]}, Usage()


# Offline outreach templates per language (the Anthropic backend writes the language itself).
OUTREACH_TEMPLATES: dict[str, dict[str, str]] = {
    "EN": {
        "hook_quote": 'I noticed that {company} recently shared: "{quote}"', "hook": "I have been following {company}'s recent announcements",
        "vp": "{service} delivered by Orange Systems",
        "body": "Hello,\n\n{hook}.\n\n{vp}\n\nWould a 20-minute conversation in the next two weeks be useful to compare notes?\n\nBest regards,\nOrange Systems",
        "linkedin": "{hook}. We help teams like yours with {service}. Open to a short chat?",
        "subject_email": "{service} for {company}", "subject_followup": "Following up: {service} at {company}", "subject_linkedin": "{service} at {company}",
    },
    "RO": {
        "hook_quote": "Am văzut recent în presă despre {company}: „{quote}”", "hook": "Urmăresc anunțurile recente ale {company}",
        "vp": "Orange Systems ajută companii ca a dumneavoastră cu {service}, de la analiză până la implementare și suport.",
        "body": "Bună ziua,\n\n{hook}.\n\n{vp}\n\nAr fi utilă o discuție de 20 de minute în următoarele două săptămâni?\n\nCu stimă,\nOrange Systems",
        "linkedin": "{hook}. Ajutăm echipe ca a dumneavoastră cu {service}. Sunteți deschis(ă) unei scurte discuții?",
        "subject_email": "{service} pentru {company}", "subject_followup": "Revin: {service} la {company}", "subject_linkedin": "{service} la {company}",
    },
    "DE": {
        "hook_quote": "Ich habe kürzlich über {company} gelesen: „{quote}“", "hook": "Ich verfolge die jüngsten Ankündigungen von {company}",
        "vp": "Orange Systems unterstützt Unternehmen wie Ihres bei {service}, von der Analyse bis zu Umsetzung und Betrieb.",
        "body": "Guten Tag,\n\n{hook}.\n\n{vp}\n\nWäre ein 20-minütiges Gespräch in den nächsten zwei Wochen hilfreich?\n\nMit freundlichen Grüßen\nOrange Systems",
        "linkedin": "{hook}. Wir unterstützen Teams wie Ihres bei {service}. Offen für ein kurzes Gespräch?",
        "subject_email": "{service} für {company}", "subject_followup": "Nachfrage: {service} bei {company}", "subject_linkedin": "{service} bei {company}",
    },
}
SERVICE_NAMES_BY_LANGUAGE: dict[str, dict[str, str]] = {
    "RO": {"Agentic Process Automation": "automatizarea proceselor cu agenți AI", "Cybersecurity Services": "securitate cibernetică",
           "Cloud & Infrastructure": "cloud și infrastructură", "Data & AI (BI)": "date și AI (BI)",
           "ERP / CRM & Integration": "ERP / CRM și integrare", "IoT & Telecom": "IoT și telecomunicații"},
    "DE": {"Agentic Process Automation": "Prozessautomatisierung mit KI-Agenten", "Cybersecurity Services": "Cybersicherheit",
           "Cloud & Infrastructure": "Cloud und Infrastruktur", "Data & AI (BI)": "Daten und KI (BI)",
           "ERP / CRM & Integration": "ERP / CRM und Integration", "IoT & Telecom": "IoT und Telekommunikation"},
}


async def _no_extraction(self, texts):
    return [], Usage()


HeuristicBackend.extract_companies = _no_extraction  # headlines are already parsed by regex offline


def make_backend(provider: str | None = None, **kwargs: Any) -> LLMBackend:
    """`provider`: "anthropic" | "heuristic" | None (auto: anthropic when a key is configured)."""
    import os

    if provider is None:
        provider = "anthropic" if (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")) else "heuristic"
    if provider == "anthropic":
        return AnthropicBackend(**kwargs)
    return HeuristicBackend()
