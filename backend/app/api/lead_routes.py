"""Leads, companies, runs, outreach and CRM endpoints (GIG-32, GIG-38, GIG-40)."""
from __future__ import annotations

import asyncio
import csv
import io
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import mongo
from ..config import get_settings
from ..crm import lead_row, push_to_hubspot, to_csv
from ..explain import generate_summary
from ..llm_factory import get_llm
from ..models import LeadAssignment, Service, SignalQuestion
from ..mongo import MDoc
from ..orchestrator import execute_run
from ..outreach import generate_outreach
from ..schemas import (
    CompanyDetail, CompanyIn, CompanyOut, DocumentOut, EventOut, LeadDetail, LeadOut, LinkedinValidationIn,
    ManualSignalIn, OutreachOut, RunIn, RunOut, SignalOut,
)
from ..scoring import signal_date_from_evidence
from ..scoring_service import recompute_scores
from ..auth import admin_guard
from .deps import company_or_404, get_db, get_or_404, mongo_or_404, resolve_service

router = APIRouter()
TIER_ORDER = {"Hot": 0, "Warm": 1, "Cold": 2, "Disqualified": 3}
NEW_LEAD_HOURS = 24


# ------------------------------------------------------------------ leads
def _lead_out(lead: MDoc, company: MDoc, service: Service) -> LeadOut:
    exp = lead.explanation or {}
    top = (exp.get("top_signals") or [None])[0]
    return LeadOut(
        lead_id=lead.id, company_id=company.id, company=company.name, domain=company.domain, country=company.country,
        industry=company.industry, employee_count=company.employee_count, service_id=service.id, service=service.name,
        icp_score=lead.icp_score, signal_score=lead.signal_score, final_score=lead.final_score, tier=lead.tier,
        disqualified=lead.disqualified, disqualification_reasons=lead.disqualification_reasons or [],
        outside_icp=bool((lead.breakdown or {}).get("outside_icp")), top_signal=top,
        recommendation=exp.get("recommendation", ""), summary=exp.get("summary", ""), computed_at=lead.computed_at,
        is_new=_aware(company.created_at) >= datetime.now(timezone.utc) - timedelta(hours=NEW_LEAD_HOURS),
        previous_score=lead.previous_score, score_changed_at=lead.score_changed_at,
        origin=company.origin or "manual", discovered_via=(company.discovered_via or [])[-3:],
    )


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _joined(db: Session, lead_query: dict | None = None, company_query: dict | None = None, sort: list | None = None):
    """(lead score, company, service) triples: scores and companies from Mongo, services from PostgreSQL."""
    services = {s.id: s for s in db.scalars(select(Service))}
    lq = dict(lead_query or {})
    if company_query:
        lq["company_id"] = {"$in": mongo.ids(mongo.COMPANIES, company_query)}
    leads = mongo.find(mongo.LEAD_SCORES, lq, sort=sort)
    # Companies without enough topical news (app/newscuration.py) stay out of leads and the dashboard.
    companies = {c.id: c for c in mongo.find(mongo.COMPANIES, {"_id": {"$in": list({l.company_id for l in leads})}, "status": {"$ne": "insufficient_news"}})}
    return [(l, companies[l.company_id], services[l.service_id]) for l in leads if l.company_id in companies and l.service_id in services]


@router.get("/leads", response_model=list[LeadOut], tags=["leads"])
def list_leads(
    service: str | None = None,
    tier: str | None = Query(None, description="Hot | Warm | Cold | Disqualified (comma-separated allowed)"),
    country: str | None = None,
    industry: str | None = None,
    min_score: float | None = None,
    include_outside_icp: bool = False,
    origin: str | None = Query(None, description="manual | import | a discovery source name"),
    changed_since_hours: int | None = Query(None, ge=1, description="only leads discovered or re-scored in the last N hours"),
    sort: str = Query("score", pattern="^(score|-score|tier|company|recent)$"),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
):
    lq: dict = {}
    if service:
        lq["service_id"] = resolve_service(db, service).id
    if tier:
        lq["tier"] = {"$in": [t.strip().capitalize() for t in tier.split(",")]}
    if min_score is not None:
        lq["final_score"] = {"$gte": min_score}
    cq: dict = {}
    if country:
        cq["country"] = country.upper()
    if industry:
        cq["industry"] = {"$regex": re.escape(industry), "$options": "i"}
    if origin:
        cq["origin"] = origin
    rows = [_lead_out(l, c, s) for l, c, s in _joined(db, lq, cq)]
    if changed_since_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=changed_since_hours)
        rows = [r for r in rows if r.is_new or (r.score_changed_at and _aware(r.score_changed_at) >= cutoff)]
    if not include_outside_icp:
        rows = [r for r in rows if not r.outside_icp or r.disqualified]
    if sort == "score":
        rows.sort(key=lambda r: (r.disqualified, -r.final_score))
    elif sort == "-score":
        rows.sort(key=lambda r: r.final_score)
    elif sort == "tier":
        rows.sort(key=lambda r: (TIER_ORDER.get(r.tier, 9), -r.final_score))
    elif sort == "company":
        rows.sort(key=lambda r: r.company.lower())
    elif sort == "recent":
        rows.sort(key=lambda r: r.computed_at, reverse=True)
    return rows[:limit]


@router.get("/dashboard/companies", tags=["leads"], summary="Every scored company with per-service scores and evidence, in one call (for the dashboard)")
def dashboard_companies(include_outside_icp: bool = False, max_signals: int = Query(8, ge=0, le=50), db: Session = Depends(get_db)):
    """Joins both stores: scores and evidence from MongoDB, pipeline stage / owner from PostgreSQL."""
    rows = _joined(db)
    assignments = {a.company_id: a for a in db.scalars(select(LeadAssignment))}
    by_company: dict[int, dict] = {}
    for lead, company, service in rows:
        entry = by_company.get(company.id)
        if entry is None:
            entry = by_company[company.id] = {
                "company": CompanyOut.model_validate(company).model_dump(mode="json", exclude={"linkedin_validation", "registry_profiles"}),
                "registry_ref": {k: (v or {}).get("wikidata_id") or (v or {}).get("lei") or (v or {}).get("ref") for k, v in (company.registry_profiles or {}).items()},
                "scores": [],
                "outside_icp": True,
                "assignment": _assignment(assignments.get(company.id)),
            }
        outside = bool((lead.breakdown or {}).get("outside_icp"))
        entry["outside_icp"] = entry["outside_icp"] and outside
        items = [i for i in ((lead.breakdown or {}).get("signals") or {}).get("items", []) if i.get("points") and i.get("evidence")]
        entry["scores"].append({
            "lead_id": lead.id, "service_id": service.id, "service_slug": service.slug, "service": service.name,
            "final_score": lead.final_score, "previous_score": lead.previous_score, "score_changed_at": lead.score_changed_at,
            "icp_score": lead.icp_score, "signal_score": lead.signal_score, "tier": lead.tier, "disqualified": lead.disqualified,
            "disqualification_reasons": lead.disqualification_reasons or [], "outside_icp": outside,
            "summary": (lead.explanation or {}).get("summary", ""), "recommendation": (lead.explanation or {}).get("recommendation", ""),
            "computed_at": lead.computed_at, "signals": items[:max_signals],
        })
    out = [e for e in by_company.values() if include_outside_icp or not e["outside_icp"] or any(s["disqualified"] for s in e["scores"])]
    out.sort(key=lambda e: -max((s["final_score"] for s in e["scores"] if not s["disqualified"]), default=-1))
    return out


def _assignment(a: LeadAssignment | None) -> dict:
    if a is None:
        return {"stage": None, "seller_id": None, "owner": None, "notes": 0, "updated_at": None}
    return {"stage": a.stage, "seller_id": a.seller_id, "owner": a.seller.full_name if a.seller else None,
            "notes": len(a.notes or []), "updated_at": a.updated_at}


# ------------------------------------------------------------------ companies
@router.get("/companies", response_model=list[CompanyOut], tags=["companies"])
def list_companies(q: str | None = None):
    query = {"name": {"$regex": re.escape(q), "$options": "i"}} if q else {}
    return mongo.find(mongo.COMPANIES, query, sort=[("name", 1)])


@router.post("/companies", response_model=CompanyOut, status_code=201, tags=["companies"], dependencies=[Depends(admin_guard)])
def create_company(body: CompanyIn, db: Session = Depends(get_db)):
    data = body.model_dump()
    data["country"] = data["country"].upper() if data["country"] else None
    try:
        company = mongo.insert_company(data)
    except DuplicateKeyError:
        raise HTTPException(409, "A company with this domain already exists")
    recompute_scores(db, company_ids=[company.id])
    return company


IMPORT_ALIASES = {
    "organization name": "name", "company": "name", "website": "domain", "organization url": "crunchbase_url",
    "industries": "industry", "headquarters country": "country", "number of employees": "employee_count",
    "employees": "employee_count", "linkedin": "linkedin_url",
}


@router.post("/companies/import", tags=["companies"], summary="Import companies from CSV (Crunchbase export or name,domain,industry,... columns)", dependencies=[Depends(admin_guard)])
async def import_companies(file: UploadFile, db: Session = Depends(get_db)):
    text = (await file.read()).decode("utf-8-sig")
    created, skipped = 0, 0
    new_ids: list[int] = []
    fields = set(CompanyIn.model_fields)
    for raw in csv.DictReader(io.StringIO(text)):
        row = {}
        for k, v in raw.items():
            key = IMPORT_ALIASES.get((k or "").strip().lower(), (k or "").strip().lower())
            if key in fields and v not in (None, ""):
                row[key] = v.strip()
        if not row.get("name"):
            skipped += 1
            continue
        if "domain" in row:
            row["domain"] = row["domain"].lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]
        if "employee_count" in row:
            digits = "".join(ch for ch in row["employee_count"].split("-")[-1] if ch.isdigit())
            row["employee_count"] = int(digits) if digits else None
        if "country" in row and len(row["country"]) != 2:
            row.pop("country")  # only ISO-2 codes are accepted; leave for manual fix
        if row.get("domain") and mongo.domain_taken(row["domain"]):
            skipped += 1
            continue
        try:
            company = CompanyIn.model_validate(row)
        except ValueError:
            skipped += 1
            continue
        data = company.model_dump()
        data["country"] = data["country"].upper() if data["country"] else None
        try:
            new_ids.append(mongo.insert_company({**data, "origin": "import"}).id)
        except DuplicateKeyError:
            skipped += 1
            continue
        created += 1
    if new_ids:
        recompute_scores(db, company_ids=new_ids)
    return {"created": created, "skipped": skipped}


@router.get("/companies/{company_id}", response_model=CompanyDetail, tags=["companies"])
def company_detail(company_id: int, db: Session = Depends(get_db)):
    company = company_or_404(company_id)
    services = {s.id: s for s in db.scalars(select(Service))}
    leads = [(l, services[l.service_id]) for l in mongo.find(mongo.LEAD_SCORES, {"company_id": company_id}) if l.service_id in services]
    scores = [
        LeadDetail(
            service_id=s.id, service=s.name, icp_score=l.icp_score, signal_score=l.signal_score, final_score=l.final_score,
            tier=l.tier, disqualified=l.disqualified, disqualification_reasons=l.disqualification_reasons or [],
            breakdown=l.breakdown or {}, explanation=l.explanation or {}, computed_at=l.computed_at,
        )
        for l, s in leads
    ]
    eligible = [s for s in scores if not s.disqualified]
    best = max(eligible, key=lambda s: s.final_score).service if eligible else None
    signals = mongo.find(mongo.SIGNALS, {"company_id": company_id}, sort=[("detected_at", DESCENDING), ("_id", DESCENDING)])
    events = mongo.find(mongo.EVENTS, {"company_id": company_id}, sort=[("event_date", DESCENDING)])
    counts = {
        r["_id"]: r["n"]
        for r in mongo.db()[mongo.DOCUMENTS].aggregate([{"$match": {"company_id": company_id}}, {"$group": {"_id": "$source_type", "n": {"$sum": 1}}}])
    }
    return CompanyDetail(
        company=CompanyOut.model_validate(company),
        scores=sorted(scores, key=lambda s: -s.final_score),
        best_service=best,
        signals=[SignalOut.model_validate(s) for s in signals],
        events=[EventOut.model_validate(e) for e in events],
        documents_by_source=counts,
    )


@router.put("/companies/{company_id}", response_model=CompanyOut, tags=["companies"], dependencies=[Depends(admin_guard)])
def update_company(company_id: int, body: CompanyIn, db: Session = Depends(get_db)):
    company_or_404(company_id)
    data = body.model_dump()
    data["country"] = data["country"].upper() if data["country"] else None
    if data.get("domain") and mongo.domain_taken(data["domain"], exclude_id=company_id):
        raise HTTPException(409, "A company with this domain already exists")
    mongo.update_company(company_id, data)
    recompute_scores(db, company_ids=[company_id])
    return mongo.get(mongo.COMPANIES, company_id)


@router.delete("/companies/{company_id}", status_code=204, tags=["companies"], dependencies=[Depends(admin_guard)])
def delete_company(company_id: int, db: Session = Depends(get_db)):
    company_or_404(company_id)
    mongo.delete_company(company_id)
    assignment = db.get(LeadAssignment, company_id)
    if assignment is not None:
        db.delete(assignment)
        db.commit()
    return Response(status_code=204)


@router.get("/companies/{company_id}/events", response_model=list[EventOut], tags=["companies"], summary="Event timeline (GIG-27)")
def company_events(company_id: int):
    company_or_404(company_id)
    return mongo.find(mongo.EVENTS, {"company_id": company_id}, sort=[("event_date", DESCENDING)])


@router.get("/companies/{company_id}/documents", response_model=list[DocumentOut], tags=["companies"])
def company_documents(company_id: int, source_type: str | None = None):
    query: dict = {"company_id": company_id}
    if source_type:
        query["source_type"] = source_type
    return mongo.find(mongo.DOCUMENTS, query, sort=[("published_at", DESCENDING)])


@router.put("/companies/{company_id}/linkedin", response_model=CompanyOut, tags=["companies"], summary="Manual LinkedIn validation (GIG-24)")
def update_linkedin_validation(company_id: int, body: LinkedinValidationIn):
    company_or_404(company_id)
    mongo.update_company(company_id, {"linkedin_validation": {**body.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}})
    return mongo.get(mongo.COMPANIES, company_id)


@router.post("/companies/{company_id}/manual-signal", response_model=SignalOut, status_code=201, tags=["companies"])
def add_manual_signal(company_id: int, body: ManualSignalIn, request: Request, db: Session = Depends(get_db)):
    company_or_404(company_id)
    q = get_or_404(db, SignalQuestion, body.question_id)
    evidence = []
    if body.evidence_url or body.evidence_quote:
        evidence = [{"quote": body.evidence_quote, "url": body.evidence_url or "", "date": body.evidence_date or "unknown"}]
    now = datetime.now(timezone.utc)
    seller = getattr(request.state, "seller", None)
    sig = mongo.insert(mongo.SIGNALS, {
        "company_id": company_id, "service_id": q.service_id, "question_id": q.id, "rule_id": None, "origin": "manual",
        "answer": body.answer, "confidence": body.confidence, "evidence": evidence,
        "reasoning": body.note or "Validated manually by sales rep.",
        "signal_date": signal_date_from_evidence(evidence) or now, "detected_at": now, "run_id": None,
        "created_by": seller.full_name if seller else body.created_by, "seller_id": seller.id if seller else None,
    })
    recompute_scores(db, company_ids=[company_id], service_ids=[q.service_id])
    return sig


@router.post("/companies/{company_id}/explain", response_model=LeadDetail, tags=["companies"], summary="Regenerate the 'Why this lead?' summary")
async def explain_lead(company_id: int, service: str, db: Session = Depends(get_db)):
    svc = resolve_service(db, service)
    lead = mongo.find_one(mongo.LEAD_SCORES, {"company_id": company_id, "service_id": svc.id})
    if lead is None:
        raise HTTPException(404, "No score for this company/service yet")
    await generate_summary(db, lead, get_llm())
    return LeadDetail(
        service_id=svc.id, service=svc.name, icp_score=lead.icp_score, signal_score=lead.signal_score, final_score=lead.final_score,
        tier=lead.tier, disqualified=lead.disqualified, disqualification_reasons=lead.disqualification_reasons or [],
        breakdown=lead.breakdown or {}, explanation=lead.explanation or {}, computed_at=lead.computed_at,
    )


@router.post("/companies/{company_id}/outreach", response_model=OutreachOut, tags=["outreach"])
async def outreach(
    company_id: int,
    service: str,
    channel: str = Query("email", pattern="^(email|linkedin|followup)$"),
    tone: str = Query("consultative", pattern="^(formal|consultative)$"),
    language: str = Query("EN", pattern="^(EN|RO|DE)$"),
    db: Session = Depends(get_db),
):
    company = company_or_404(company_id)
    svc = resolve_service(db, service)
    lead = mongo.find_one(mongo.LEAD_SCORES, {"company_id": company_id, "service_id": svc.id})
    return await generate_outreach(get_llm(), company, svc, lead, channel=channel, tone=tone, language=language)


# ------------------------------------------------------------------ CRM / export
def _export_rows(db: Session, service: str | None, tiers: list[str]) -> list[dict]:
    lq: dict = {"tier": {"$in": tiers}}
    if service:
        lq["service_id"] = resolve_service(db, service).id
    return [lead_row(c, s, l) for l, c, s in _joined(db, lq, sort=[("final_score", DESCENDING)])]


@router.get("/export/leads.csv", tags=["crm"])
def export_csv(service: str | None = None, tiers: str = "Hot,Warm", db: Session = Depends(get_db)):
    rows = _export_rows(db, service, [t.strip() for t in tiers.split(",")])
    return Response(
        content=to_csv(rows),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="orange-signals-leads.csv"'},
    )


@router.get("/export/leads.json", tags=["crm"])
def export_json(service: str | None = None, tiers: str = "Hot,Warm", db: Session = Depends(get_db)):
    return _export_rows(db, service, [t.strip() for t in tiers.split(",")])


@router.post("/crm/hubspot", tags=["crm"], summary="Send one or more leads to HubSpot (company + note)")
async def send_to_hubspot(lead_ids: list[int], db: Session = Depends(get_db)):
    token = get_settings().hubspot_token
    if not token:
        raise HTTPException(400, "HUBSPOT_TOKEN is not configured; use /export/leads.csv instead")
    results = []
    for lead_id in lead_ids:
        lead = mongo_or_404(mongo.LEAD_SCORES, lead_id, "Lead")
        company, svc = mongo.get(mongo.COMPANIES, lead.company_id), db.get(Service, lead.service_id)
        try:
            results.append({"lead_id": lead_id, "ok": True, **await push_to_hubspot(token, company, svc, lead)})
        except Exception as exc:  # noqa: BLE001 - report per-lead failures, keep going
            results.append({"lead_id": lead_id, "ok": False, "error": str(exc)[:300]})
    return results


# ------------------------------------------------------------------ runs
@router.post("/runs", response_model=RunOut, status_code=202, tags=["runs"], dependencies=[Depends(admin_guard)])
async def start_run(body: RunIn, request: Request):
    active = mongo.active_run()
    if active is not None:
        raise HTTPException(409, f"Run {active.id} is still {active.status}")
    seller = getattr(request.state, "seller", None)
    run = mongo.create_run(params=body.model_dump(), seller_id=seller.id if seller else None)
    task = asyncio.create_task(
        execute_run(
            request.app.state.session_factory, run.id, company_ids=body.company_ids, service_ids=body.service_ids,
            sources=tuple(body.sources), explain=body.explain, llm=request.app.state.llm_override,
        )
    )
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)
    return run


@router.get("/runs", response_model=list[RunOut], tags=["runs"])
def list_runs(limit: int = 20):
    return mongo.find(mongo.RUNS, {}, sort=[("_id", DESCENDING)], limit=limit)


@router.get("/runs/{run_id}", response_model=RunOut, tags=["runs"])
def get_run(run_id: int):
    return mongo_or_404(mongo.RUNS, run_id, "Run")
