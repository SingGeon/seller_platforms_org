"""AI results are kept when the AI quota runs out: 'why now' summaries and outreach drafts."""
import asyncio

from sales_pipeline import HeuristicBackend
from sales_pipeline.schemas import Usage

from app import mongo
from app.explain import generate_summary, needs_summary
from app.llm_factory import MongoCache
from app.models import Service
from app.outreach import generate_outreach

from .api_test import company_id, run_pipeline


class FakeAI(HeuristicBackend):
    """Answers like a model (llm_calls=1) with recognisable text."""

    async def explain_lead(self, payload):
        return f"AI summary for {payload['company']}", Usage(llm_calls=1)

    async def write_outreach(self, payload):
        self.calls = getattr(self, "calls", 0) + 1
        return {"subject": "AI", "body": f"AI draft {self.calls}", "signals_used": []}, Usage(llm_calls=1)


def _lead(session_factory, cid):
    with session_factory() as db:
        svc = db.query(Service).filter_by(slug="apa").one()
    return mongo.find_one(mongo.LEAD_SCORES, {"company_id": cid, "service_id": svc.id}), svc


def test_an_offline_summary_is_redone_by_the_ai_and_an_ai_summary_is_never_replaced_offline(client, session_factory):
    run_pipeline(client)  # offline analysis: summaries written by the template
    lead, _ = _lead(session_factory, company_id(client, "Lufthansa Group"))
    assert lead.explanation["summary"] and not lead.explanation["summary_ai"] and needs_summary(lead)

    with session_factory() as db:
        asyncio.run(generate_summary(db, lead, FakeAI()))
        assert not needs_summary(lead)
        asyncio.run(generate_summary(db, lead, HeuristicBackend()))  # quota gone
    saved = mongo.get(mongo.LEAD_SCORES, lead.id).explanation
    assert saved["summary"] == "AI summary for Lufthansa Group" and saved["summary_ai"]

    run_pipeline(client)  # same news, same signals: the AI summary stays
    assert mongo.get(mongo.LEAD_SCORES, lead.id).explanation["summary"] == "AI summary for Lufthansa Group"


def test_an_outreach_draft_is_saved_and_given_back_when_the_ai_is_out_of_quota(client, session_factory):
    run_pipeline(client)
    cid = company_id(client, "Lufthansa Group")
    lead, svc = _lead(session_factory, cid)
    company = mongo.get(mongo.COMPANIES, cid)
    ai, cache = FakeAI(), MongoCache()
    opts = {"channel": "email", "tone": "formal", "language": "RO", "cache": cache}

    first = asyncio.run(generate_outreach(ai, company, svc, lead, **opts))
    assert first["body"] == "AI draft 1"
    assert asyncio.run(generate_outreach(ai, company, svc, lead, **opts))["body"] == "AI draft 1"  # saved, no tokens
    assert ai.calls == 1
    assert asyncio.run(generate_outreach(HeuristicBackend(), company, svc, lead, **opts, fresh=True))["body"] == "AI draft 1"
    assert asyncio.run(generate_outreach(ai, company, svc, lead, **opts, fresh=True))["body"] == "AI draft 2"
