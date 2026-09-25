"""'Why this lead?' summaries (GIG-30), grounded only in the scored signals."""
from __future__ import annotations

from sqlalchemy.orm import Session

from sales_pipeline.llm import LLMBackend
from sales_pipeline.schemas import Usage

from .models import Company, LeadScore, Service


def explain_payload(company: Company, service: Service, lead: LeadScore) -> dict:
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


async def generate_summary(db: Session, lead: LeadScore, llm: LLMBackend) -> Usage:
    company = db.get(Company, lead.company_id)
    service = db.get(Service, lead.service_id)
    payload = explain_payload(company, service, lead)
    if not payload["top_signals"]:
        return Usage()
    summary, usage = await llm.explain_lead(payload)
    lead.explanation = {**(lead.explanation or {}), "summary": summary}
    return usage
