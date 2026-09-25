"""Leads, companies, runs, outreach and CRM endpoints (GIG-32, GIG-38, GIG-40)."""
from __future__ import annotations

import asyncio
import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..crm import lead_row, push_to_hubspot, to_csv
from ..explain import generate_summary
from ..llm_factory import get_llm
from ..models import Company, CompanyEvent, LeadScore, PipelineRun, RawDocument, Service, Signal, SignalQuestion
from ..orchestrator import execute_run
from ..outreach import generate_outreach
from ..schemas import (
    CompanyDetail, CompanyIn, CompanyOut, DocumentOut, EventOut, LeadDetail, LeadOut, LinkedinValidationIn,
    ManualSignalIn, OutreachOut, RunIn, RunOut, SignalOut,
)
from ..scoring import signal_date_from_evidence
from ..scoring_service import recompute_scores
from .deps import get_db, get_or_404, resolve_service

router = APIRouter()
TIER_ORDER = {"Hot": 0, "Warm": 1, "Cold": 2, "Disqualified": 3}
NEW_LEAD_HOURS = 24


# ------------------------------------------------------------------ leads
def _lead_out(lead: LeadScore, company: Company, service: Service) -> LeadOut:
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
    stmt = select(LeadScore, Company, Service).join(Company, Company.id == LeadScore.company_id).join(Service, Service.id == LeadScore.service_id)
    if service:
        stmt = stmt.where(LeadScore.service_id == resolve_service(db, service).id)
    if tier:
        stmt = stmt.where(LeadScore.tier.in_([t.strip().capitalize() for t in tier.split(",")]))
    if country:
        stmt = stmt.where(func.upper(Company.country) == country.upper())
    if industry:
        stmt = stmt.where(func.lower(Company.industry).contains(industry.lower()))
    if min_score is not None:
        stmt = stmt.where(LeadScore.final_score >= min_score)
    if origin:
        stmt = stmt.where(Company.origin == origin)
    rows = [_lead_out(l, c, s) for l, c, s in db.execute(stmt)]
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


# ------------------------------------------------------------------ companies
@router.get("/companies", response_model=list[CompanyOut], tags=["companies"])
def list_companies(q: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Company).order_by(Company.name)
    if q:
        stmt = stmt.where(func.lower(Company.name).contains(q.lower()))
    return list(db.scalars(stmt))


@router.post("/companies", response_model=CompanyOut, status_code=201, tags=["companies"])
def create_company(body: CompanyIn, db: Session = Depends(get_db)):
    data = body.model_dump()
    data["country"] = data["country"].upper() if data["country"] else None
    company = Company(**data)
    db.add(company)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A company with this domain already exists")
    recompute_scores(db, company_ids=[company.id])
    return company


IMPORT_ALIASES = {
    "organization name": "name", "company": "name", "website": "domain", "organization url": "crunchbase_url",
    "industries": "industry", "headquarters country": "country", "number of employees": "employee_count",
    "employees": "employee_count", "linkedin": "linkedin_url",
}


@router.post("/companies/import", tags=["companies"], summary="Import companies from CSV (Crunchbase export or name,domain,industry,... columns)")
async def import_companies(file: UploadFile, db: Session = Depends(get_db)):
    text = (await file.read()).decode("utf-8-sig")
    created, skipped = 0, 0
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
        if row.get("domain") and db.scalar(select(Company).where(Company.domain == row["domain"])):
            skipped += 1
            continue
        try:
            company = CompanyIn.model_validate(row)
        except ValueError:
            skipped += 1
            continue
        data = company.model_dump()
        data["country"] = data["country"].upper() if data["country"] else None
        db.add(Company(**data, origin="import"))
        created += 1
    db.commit()
    recompute_scores(db)
    return {"created": created, "skipped": skipped}


@router.get("/companies/{company_id}", response_model=CompanyDetail, tags=["companies"])
def company_detail(company_id: int, db: Session = Depends(get_db)):
    company = get_or_404(db, Company, company_id)
    leads = db.execute(
        select(LeadScore, Service).join(Service, Service.id == LeadScore.service_id).where(LeadScore.company_id == company_id)
    ).all()
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
    signals = list(db.scalars(select(Signal).where(Signal.company_id == company_id).order_by(Signal.detected_at.desc())))
    events = list(db.scalars(select(CompanyEvent).where(CompanyEvent.company_id == company_id).order_by(CompanyEvent.event_date.desc())))
    counts = dict(db.execute(select(RawDocument.source_type, func.count()).where(RawDocument.company_id == company_id).group_by(RawDocument.source_type)).all())
    return CompanyDetail(
        company=CompanyOut.model_validate(company),
        scores=sorted(scores, key=lambda s: -s.final_score),
        best_service=best,
        signals=[SignalOut.model_validate(s) for s in signals],
        events=[EventOut.model_validate(e) for e in events],
        documents_by_source=counts,
    )


@router.put("/companies/{company_id}", response_model=CompanyOut, tags=["companies"])
def update_company(company_id: int, body: CompanyIn, db: Session = Depends(get_db)):
    company = get_or_404(db, Company, company_id)
    data = body.model_dump()
    data["country"] = data["country"].upper() if data["country"] else None
    for k, v in data.items():
        setattr(company, k, v)
    db.commit()
    recompute_scores(db, company_ids=[company_id])
    return company


@router.delete("/companies/{company_id}", status_code=204, tags=["companies"])
def delete_company(company_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Company, company_id))
    db.commit()
    return Response(status_code=204)


@router.get("/companies/{company_id}/events", response_model=list[EventOut], tags=["companies"], summary="Event timeline (GIG-27)")
def company_events(company_id: int, db: Session = Depends(get_db)):
    get_or_404(db, Company, company_id)
    return list(db.scalars(select(CompanyEvent).where(CompanyEvent.company_id == company_id).order_by(CompanyEvent.event_date.desc())))


@router.get("/companies/{company_id}/documents", response_model=list[DocumentOut], tags=["companies"])
def company_documents(company_id: int, source_type: str | None = None, db: Session = Depends(get_db)):
    stmt = select(RawDocument).where(RawDocument.company_id == company_id).order_by(RawDocument.published_at.desc())
    if source_type:
        stmt = stmt.where(RawDocument.source_type == source_type)
    return list(db.scalars(stmt))


@router.put("/companies/{company_id}/linkedin", response_model=CompanyOut, tags=["companies"], summary="Manual LinkedIn validation (GIG-24)")
def update_linkedin_validation(company_id: int, body: LinkedinValidationIn, db: Session = Depends(get_db)):
    company = get_or_404(db, Company, company_id)
    company.linkedin_validation = {**body.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}
    db.commit()
    return company


@router.post("/companies/{company_id}/manual-signal", response_model=SignalOut, status_code=201, tags=["companies"])
def add_manual_signal(company_id: int, body: ManualSignalIn, db: Session = Depends(get_db)):
    get_or_404(db, Company, company_id)
    q = get_or_404(db, SignalQuestion, body.question_id)
    evidence = []
    if body.evidence_url or body.evidence_quote:
        evidence = [{"quote": body.evidence_quote, "url": body.evidence_url or "", "date": body.evidence_date or "unknown"}]
    sig = Signal(
        company_id=company_id, service_id=q.service_id, question_id=q.id, origin="manual", answer=body.answer,
        confidence=body.confidence, evidence=evidence, reasoning=body.note or "Validated manually by sales rep.",
        signal_date=signal_date_from_evidence(evidence) or datetime.now(timezone.utc), created_by=body.created_by,
    )
    db.add(sig)
    db.commit()
    recompute_scores(db, company_ids=[company_id], service_ids=[q.service_id])
    return sig


@router.post("/companies/{company_id}/explain", response_model=LeadDetail, tags=["companies"], summary="Regenerate the 'Why this lead?' summary")
async def explain_lead(company_id: int, service: str, db: Session = Depends(get_db)):
    svc = resolve_service(db, service)
    lead = db.scalar(select(LeadScore).where(LeadScore.company_id == company_id, LeadScore.service_id == svc.id))
    if lead is None:
        raise HTTPException(404, "No score for this company/service yet")
    await generate_summary(db, lead, get_llm())
    db.commit()
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
    company = get_or_404(db, Company, company_id)
    svc = resolve_service(db, service)
    lead = db.scalar(select(LeadScore).where(LeadScore.company_id == company_id, LeadScore.service_id == svc.id))
    return await generate_outreach(get_llm(), company, svc, lead, channel=channel, tone=tone, language=language)


# ------------------------------------------------------------------ CRM / export
def _export_rows(db: Session, service: str | None, tiers: list[str]) -> list[dict]:
    stmt = select(LeadScore, Company, Service).join(Company, Company.id == LeadScore.company_id).join(Service, Service.id == LeadScore.service_id)
    if service:
        stmt = stmt.where(LeadScore.service_id == resolve_service(db, service).id)
    stmt = stmt.where(LeadScore.tier.in_(tiers)).order_by(LeadScore.final_score.desc())
    return [lead_row(c, s, l) for l, c, s in db.execute(stmt)]


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
        lead = get_or_404(db, LeadScore, lead_id)
        company, svc = db.get(Company, lead.company_id), db.get(Service, lead.service_id)
        try:
            results.append({"lead_id": lead_id, "ok": True, **await push_to_hubspot(token, company, svc, lead)})
        except Exception as exc:  # noqa: BLE001 - report per-lead failures, keep going
            results.append({"lead_id": lead_id, "ok": False, "error": str(exc)[:300]})
    return results


# ------------------------------------------------------------------ runs
@router.post("/runs", response_model=RunOut, status_code=202, tags=["runs"])
async def start_run(body: RunIn, request: Request, db: Session = Depends(get_db)):
    active = db.scalar(select(PipelineRun).where(PipelineRun.status.in_(["queued", "running"])).limit(1))
    if active is not None:
        raise HTTPException(409, f"Run {active.id} is still {active.status}")
    run = PipelineRun(status="queued", params=body.model_dump())
    db.add(run)
    db.commit()
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
def list_runs(limit: int = 20, db: Session = Depends(get_db)):
    return list(db.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(limit)))


@router.get("/runs/{run_id}", response_model=RunOut, tags=["runs"])
def get_run(run_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, PipelineRun, run_id)
