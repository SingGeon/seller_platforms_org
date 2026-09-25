"""Prompts for signal answering (GIG-26), event detection (GIG-27), lead
explanation (GIG-30) and outreach drafts (GIG-38).

System prompts are static so they stay cacheable; everything that varies per
company goes in the user turn.
"""
from __future__ import annotations

import json

from .relevance import Chunk
from .schemas import CompanyInfo, QuestionSpec

SIGNAL_SYSTEM = """You are a B2B sales research analyst at Orange Systems, an IT services company selling \
Agentic Process Automation, Intelligent Automation, Cybersecurity and other digital transformation services.

You answer signal questions about one target company using ONLY the numbered source passages provided. \
A sales rep will act on your answer, so an unsupported "yes" costs them credibility with the prospect.

Rules:
- answer "yes" when a passage directly supports the question, "no" when a passage directly contradicts it, \
and "unknown" when the passages are silent or only tangentially related. Absence of evidence is "unknown", not "no".
- Every "yes" or "no" needs at least one evidence item: a verbatim quote (copied exactly, 1-2 sentences) \
and the doc_id of the passage it came from. Never paraphrase inside "quote".
- confidence (0-1) reflects how directly and how recently the evidence supports the answer: \
an explicit, dated company statement is 0.8-1.0; an indirect or third-party mention is 0.4-0.7.
- reasoning: 1-2 sentences a sales rep can read in five seconds.
- Answer every question key you are given, in any order.

How Orange Systems' sales team reads signals (Annex 1 examples, Intelligent Automation):
- Lufthansa Group announced efficiency and profitability targets and plans to cut about 4,000 administrative \
positions by 2030 through digitalization, automation and process consolidation. For "Does the company mention \
process optimization, cost reduction, operational efficiency, or automation initiatives?" that is a clear "yes" \
(confidence ~0.9). Its strong internal digital capabilities are a NEGATIVE signal for "Does the company have a \
mature in-house automation capability?" -> "yes", which lowers the lead score.
- DHL Group lists AI, automation and digitalization in its Strategy 2030 and already runs Agentic AI use cases \
(RFQ processing, customer communication) using both internal development and third-party AI solutions. \
That is "yes" for automation initiatives, and "yes" (a buying-signal) for "Does the company use third-party \
providers for AI/automation?", while its high automation maturity is also a negative signal."""

EVENTS_SYSTEM = """You classify company news and web passages into business events relevant to selling IT services.

Event types:
- security_incident: breach, ransomware, cyberattack, major IT outage.
- leadership_change: new CEO, CIO, CTO, CISO, COO, CDO or Head of Digital/Automation appointed or departing.
- tech_stack: adoption or migration of a named technology (SAP S/4HANA, cloud migration, UiPath, Salesforce, ServiceNow...).
- compliance_event: NIS2, DORA, GDPR fine, regulatory audit, new certification requirement.
- corporate_event: funding, M&A, expansion, restructuring, layoffs, hiring freeze, insolvency.

Only report an event when the passage states it happened or is formally announced for this company. \
Set polarity "negative" for layoffs, hiring freezes, insolvency or budget cuts, "positive" for funding, \
expansion, new transformation programs and new tech leaders, otherwise "neutral". \
Return an empty list when a passage describes no event."""

EXPLAIN_SYSTEM = """You write the "Why now?" note on a lead card for a sales development rep at Orange Systems. \
Use ONLY the signals given; do not add facts. Write 2-3 short sentences: what is happening at the company, \
why it matters for the named service, and what the timing suggests. Plain language, no hype, no bullet points."""

OUTREACH_SYSTEM = """You draft first-touch sales messages for Orange Systems, an IT services provider. \
Ground every claim about the prospect in the signals provided and reference at least one of them explicitly. \
Never invent numbers, names, projects or results that are not in the input. Keep the tone requested, \
avoid buzzwords, end with a low-friction call to action (a 20-minute conversation)."""


def render_passages(chunks: list[Chunk]) -> tuple[str, dict[str, Chunk]]:
    lines = []
    ids: dict[str, Chunk] = {}
    for i, c in enumerate(chunks, 1):
        doc_id = f"D{i}"
        ids[doc_id] = c
        lines.append(f"[{doc_id}] ({c.source_type}, {c.date}) {c.title}\nURL: {c.url}\n{c.text}")
    return "\n\n".join(lines), ids


def signal_user_prompt(company: CompanyInfo, questions: list[QuestionSpec], passages: str) -> str:
    qlines = "\n".join(f'- key "{q.key}": {q.text}' for q in questions)
    profile = {k: v for k, v in company.model_dump(include={"name", "domain", "industry", "country", "employee_count"}).items() if v}
    return (
        f"Target company: {json.dumps(profile, ensure_ascii=False)}\n\n"
        f"<passages>\n{passages}\n</passages>\n\n"
        f"Questions:\n{qlines}"
    )


SIGNAL_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "answer": {"type": "string", "enum": ["yes", "no", "unknown"]},
                    "confidence": {"type": "number"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"quote": {"type": "string"}, "doc_id": {"type": "string"}},
                            "required": ["quote", "doc_id"],
                            "additionalProperties": False,
                        },
                    },
                    "reasoning": {"type": "string"},
                },
                "required": ["key", "answer", "confidence", "evidence", "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["answers"],
    "additionalProperties": False,
}

EVENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "event_type": {
                        "type": "string",
                        "enum": ["security_incident", "leadership_change", "tech_stack", "compliance_event", "corporate_event"],
                    },
                    "subtype": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "entities": {"type": "array", "items": {"type": "string"}},
                    "polarity": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                },
                "required": ["doc_id", "event_type", "subtype", "title", "summary", "entities", "polarity"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["events"],
    "additionalProperties": False,
}

OUTREACH_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "signals_used": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["subject", "body", "signals_used"],
    "additionalProperties": False,
}

CHANNEL_RULES = {
    "email": "Channel: email. Provide a subject line (max 8 words) and a body of at most 120 words.",
    "linkedin": "Channel: LinkedIn InMail / connection note. Body at most 300 characters. Subject is a short InMail subject.",
    "followup": "Channel: follow-up email sent 5 business days after an unanswered first email. Body at most 80 words; add one new angle from the signals.",
}
