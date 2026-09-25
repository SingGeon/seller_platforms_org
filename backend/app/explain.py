"""'Why this lead?' summaries (GIG-30), grounded only in the scored signals."""
from __future__ import annotations

from sqlalchemy.orm import Session

from sales_pipeline.llm import LLMBackend
from sales_pipeline.schemas import Usage

from . import mongo
from .models import Service
from .mongo import MDoc


def explain_payload(company: MDoc, service: Service, lead: MDoc) -> dict:
    exp = lead.explanation or {}
    return {
        "company": company.name,
        "service": service.name,
        "tier": lead.tier,
        "final_score": lead.final_score,
        "recommendation": exp.get("recommendation", "monitor"),
        "top_signals": [
            {"question": s["label"], "quote": s["quote"], "date": s["date"], "url": s["url"]} for s in exp.get("top_signals", [])
        ],
    }


async def generate_summary(db: Session, lead: MDoc, llm: LLMBackend) -> Usage:
    """Write the AI "why now" summary onto the Mongo lead score (and onto `lead` itself)."""
    company = mongo.get(mongo.COMPANIES, lead.company_id)
    service = db.get(Service, lead.service_id)
    payload = explain_payload(company, service, lead)
    if not payload["top_signals"]:
        return Usage()
    summary, usage = await llm.explain_lead(payload)
    lead.explanation = {**(lead.explanation or {}), "summary": summary}
    mongo.update(mongo.LEAD_SCORES, lead.id, {"explanation.summary": summary})
    return usage
