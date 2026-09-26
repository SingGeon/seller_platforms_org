"""Pipeline run orchestration (GIG-23): collect -> store -> AI signals -> score -> explain.

One run processes every selected company concurrently (bounded by a
semaphore). Documents are deduplicated by content hash, LLM calls are cached,
so re-running the same run is cheap and never creates duplicates.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pymongo import DESCENDING
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from sales_pipeline import CompanyInfo, Document, QuestionSpec, run_signal_pipeline
from sales_pipeline.collectors import collect_jobs, collect_news, collect_website
from sales_pipeline.llm import LLMBackend
from sales_pipeline.schemas import PipelineResult, Usage
from sales_pipeline.sources.base import SourceContext
from sales_pipeline.sources.cyber import kev_documents, load_kev
from sales_pipeline.sources.registry import gleif_profile, wikidata_profile
from sales_pipeline.sources.sec import sec_annual_report_documents

from .config import get_settings
from .explain import generate_summary, needs_summary
from . import mongo
from .llm_factory import MongoCache, get_llm
from .models import DisqualificationRule, Service, SignalQuestion
from .mongo import MDoc
from .scoring import signal_date_from_evidence
from .scoring_service import recompute_scores

log = logging.getLogger(__name__)
ENRICH_SOURCES = ("news", "web", "jobs", "registry")
ALL_SOURCES = ENRICH_SOURCES
_KEV_CACHE: dict[str, Any] = {"day": None, "items": []}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def company_info(c: MDoc) -> CompanyInfo:
    return CompanyInfo(
        id=c.id, name=c.name, domain=c.domain, industry=c.industry, country=c.country,
        employee_count=c.employee_count, careers_url=c.careers_url, ats=c.ats or {},
    )


def build_questions(db: Session, service_ids: list[int]) -> list[QuestionSpec]:
    """Every active signal question of the selected services plus every applicable
    `llm_question` rule, as one list so the pipeline can batch them per company."""
    specs: list[QuestionSpec] = []
    for q in db.scalars(
        select(SignalQuestion).where(SignalQuestion.service_id.in_(service_ids), SignalQuestion.active.is_(True))
    ):
        specs.append(QuestionSpec(key=f"q:{q.id}", text=q.text, source_hint=q.source_hint, lookback_days=q.lookback_days, keywords=q.keywords or []))
    for r in db.scalars(
        select(DisqualificationRule).where(
            DisqualificationRule.rule_type == "llm_question",
            DisqualificationRule.active.is_(True),
            or_(DisqualificationRule.service_id.in_(service_ids), DisqualificationRule.service_id.is_(None)),
        )
    ):
        if r.question:
            specs.append(QuestionSpec(key=f"rule:{r.id}", text=r.question, keywords=r.keywords or []))
    return specs


def _log(run_id: int, message: str, **progress: Any) -> None:
    log.info("run %s: %s", run_id, message)
    mongo.log_run(run_id, message, keep=200, **progress)


async def collect_documents(company: CompanyInfo, sources: tuple[str, ...], use_serpapi: bool = False) -> tuple[list[Document], dict[str, str]]:
    s = get_settings()
    jobs = {}
    if "news" in sources:
        jobs["news"] = collect_news(company, newsapi_key=s.newsapi_key or None, providers=("bing_news", "bing_topics", "newsapi"))
    if "web" in sources:
        jobs["web"] = collect_website(company, max_pages=s.crawl_max_pages, delay_seconds=s.crawl_delay_seconds, use_playwright=s.use_playwright)
    if "jobs" in sources:
        # SerpAPI's free tier is tiny: only the top-scored companies spend searches on it.
        jobs["jobs"] = collect_jobs(company, serpapi_key=(s.serpapi_key or None) if use_serpapi else None)
    docs: list[Document] = []
    errors: dict[str, str] = {}
    for name, result in zip(jobs, await asyncio.gather(*jobs.values(), return_exceptions=True)):
        if isinstance(result, BaseException):
            errors[name] = str(result)[:300]
        else:
            docs.extend(result)
    return docs, errors


def store_documents(company_id: int, docs: list[Document]) -> dict[str, int]:
    added: dict[str, int] = {}
    for d in docs:
        if mongo.store_document(company_id, d):
            added[d.source_type] = added.get(d.source_type, 0) + 1
    return added


def load_documents(company_id: int, max_age_days: int = 730) -> list[Document]:
    cutoff = utcnow() - timedelta(days=max_age_days)
    rows = mongo.find(mongo.DOCUMENTS, {"company_id": company_id, "$or": [{"published_at": None}, {"published_at": {"$gte": cutoff}}]})
    return [
        Document(source_type=r.source_type, url=r.url, title=r.title, text=r.content, published_at=r.published_at, source=r.source, meta=r.meta or {})
        for r in rows
    ]


def persist_result(company_id: int, result: PipelineResult, run_id: int | None, question_service: dict[int, int]) -> dict[str, int]:
    """Write new/changed signals and newly detected events (alerts). Unchanged answers are
    skipped so re-runs don't pile up duplicates."""
    new_signals = 0
    for a in result.answers:
        kind, _, raw_id = a.key.partition(":")
        ref_id = int(raw_id)
        field = "question_id" if kind == "q" else "rule_id"
        prev = mongo.find_one(mongo.SIGNALS, {"company_id": company_id, field: ref_id}, sort=[("detected_at", DESCENDING), ("_id", DESCENDING)])
        evidence = [e.model_dump() for e in a.evidence]
        if prev is not None and prev.origin == "manual":
            continue  # a rep's manual validation is not overwritten by the AI
        if prev is not None and prev.answer == a.answer and abs(prev.confidence - a.confidence) < 1e-6 and prev.evidence == evidence:
            continue
        mongo.insert(
            mongo.SIGNALS,
            {
                "company_id": company_id,
                "service_id": question_service.get(ref_id) if kind == "q" else None,
                "question_id": ref_id if kind == "q" else None,
                "rule_id": ref_id if kind == "rule" else None,
                "origin": "question" if kind == "q" else "rule",
                "answer": a.answer,
                "confidence": a.confidence,
                "evidence": evidence,
                "reasoning": a.reasoning,
                "signal_date": signal_date_from_evidence(evidence),
                "detected_at": utcnow(),
                "run_id": run_id,
                "created_by": None,
            },
        )
        new_signals += 1
    known = {(e.event_type, e.url) for e in mongo.find(mongo.EVENTS, {"company_id": company_id})}
    new_events = 0
    for e in result.events:
        if (e.event_type, e.url) in known:
            continue
        known.add((e.event_type, e.url))
        mongo.insert(
            mongo.EVENTS,
            {
                "company_id": company_id, "event_type": e.event_type, "subtype": e.subtype, "title": e.title, "summary": e.summary,
                "event_date": signal_date_from_evidence([{"date": e.date}]), "url": e.url, "entities": e.entities,
                "polarity": e.polarity, "detected_at": utcnow(),
            },
        )
        new_events += 1
    return {"signals": new_signals, "events": new_events}


async def _kev(client: httpx.AsyncClient) -> list[dict]:
    today = utcnow().date()
    if _KEV_CACHE["day"] != today:
        _KEV_CACHE["items"] = await load_kev(client)
        _KEV_CACHE["day"] = today
    return _KEV_CACHE["items"]


async def enrich_company_profile(company_id: int, new_docs: list[Document]) -> tuple[list[Document], dict[str, str]]:
    """Registries fill missing firmographics (industry, country, size, domain) so discovered
    companies can be ICP-scored; tech stack + CISA KEV and SEC 10-K add cyber / annual-report docs."""
    s = get_settings()
    errors: dict[str, str] = {}
    extra: list[Document] = []
    c = mongo.get(mongo.COMPANIES, company_id)
    name, domain, country = c.name, c.domain, c.country
    profiles: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": "OrangeSignals/0.1 (B2B sales research)"}) as client:
        for key, fn in (("wikidata", lambda: wikidata_profile(client, name, domain)), ("gleif", lambda: gleif_profile(client, name, country))):
            try:
                p = await fn()
                if p:
                    profiles[key] = p.model_dump(exclude_none=True)
            except Exception as exc:  # noqa: BLE001
                errors[key] = str(exc)[:200]
        tech = sorted({t for d in new_docs for t in d.meta.get("tech_stack", [])})
        if tech:
            try:
                extra += kev_documents(name, tech, await _kev(client))
            except Exception as exc:  # noqa: BLE001
                errors["cisa_kev"] = str(exc)[:200]
        if s.sec_user_agent and (country == "US" or (profiles.get("wikidata") or {}).get("country") == "US"):
            try:
                ctx = SourceContext(client=client, sec_user_agent=s.sec_user_agent)
                extra += await sec_annual_report_documents(ctx, name)
            except Exception as exc:  # noqa: BLE001
                errors["sec_10k"] = str(exc)[:200]
    c = mongo.get(mongo.COMPANIES, company_id)
    wd, gl = profiles.get("wikidata", {}), profiles.get("gleif", {})
    fields: dict[str, Any] = {
        "industry": c.industry or wd.get("industry"),
        "country": c.country or wd.get("country") or gl.get("country"),
        "employee_count": c.employee_count or wd.get("employee_count"),
        "registry_profiles": {**(c.registry_profiles or {}), **profiles},
        "enriched_at": utcnow(),
    }
    if not c.domain and wd.get("domain") and not mongo.domain_taken(wd["domain"]):
        fields["domain"] = wd["domain"]
    if tech:
        fields["tech_stack"] = tech
    mongo.update_company(company_id, fields)
    return extra, errors


async def process_company(
    run_id: int, company_id: int, questions: list[QuestionSpec], question_service: dict[int, int], sources: tuple[str, ...],
    llm: LLMBackend, cache, use_serpapi: bool = False,
) -> dict[str, Any]:
    info = company_info(mongo.get(mongo.COMPANIES, company_id))
    stats: dict[str, Any] = {"company": info.name, "new_documents": {}, "collect_errors": {}}
    if sources and not get_settings().offline_collect:
        docs, errors = await collect_documents(info, sources, use_serpapi=use_serpapi)
        if "registry" in sources:
            extra, reg_errors = await enrich_company_profile(company_id, docs)
            docs += extra
            errors.update(reg_errors)
        stats["collect_errors"] = errors
        stats["new_documents"] = store_documents(company_id, docs)
    docs = load_documents(company_id)
    stats["documents"] = len(docs)
    result = await run_signal_pipeline(llm, info, questions, docs, cache=cache)
    stats.update(persist_result(company_id, result, run_id, question_service))
    stats["usage"] = result.usage.model_dump()
    stats["pipeline_errors"] = result.meta.get("errors", [])
    return stats


async def execute_run(
    sf: sessionmaker,
    run_id: int,
    *,
    company_ids: list[int] | None = None,
    service_ids: list[int] | None = None,
    sources: tuple[str, ...] = ALL_SOURCES,
    llm: LLMBackend | None = None,
    explain: bool = True,
) -> None:
    started = time.monotonic()
    llm = llm or get_llm()
    cache = MongoCache()
    with sf() as db:
        if not service_ids:
            service_ids = list(db.scalars(select(Service.id).where(Service.active.is_(True))))
        questions = build_questions(db, service_ids)
        question_service = dict(db.execute(select(SignalQuestion.id, SignalQuestion.service_id)).all())
    if not company_ids:
        company_ids = mongo.ids(mongo.COMPANIES)
    best: dict[int, float] = {}
    for lead in mongo.find(mongo.LEAD_SCORES, {"disqualified": False}):
        best[lead.company_id] = max(best.get(lead.company_id, 0.0), lead.final_score)
    serpapi_ids = {cid for cid, _ in sorted(best.items(), key=lambda kv: -kv[1])[: get_settings().serpapi_top_n]}
    run = mongo.get(mongo.RUNS, run_id)
    mongo.update(mongo.RUNS, run_id, {
        "status": "running", "started_at": utcnow(),
        "params": {**(run.params or {}), "company_ids": company_ids, "service_ids": service_ids, "sources": list(sources), "llm": llm.name},
        "progress": {"stage": "collect+analyze", "companies_total": len(company_ids), "companies_done": 0},
    })
    _log(run_id, f"Started: {len(company_ids)} companies, {len(service_ids)} services, {len(questions)} questions, llm={llm.name}")

    usage = Usage()
    per_source: dict[str, int] = {}
    per_company: list[dict] = []
    failures = 0
    sem = asyncio.Semaphore(get_settings().run_company_concurrency)
    done = 0

    async def guarded(cid: int):
        nonlocal done
        async with sem:
            try:
                return await process_company(run_id, cid, questions, question_service, sources, llm, cache, use_serpapi=cid in serpapi_ids)
            finally:
                done += 1
                _log(run_id, f"Company {cid} processed ({done}/{len(company_ids)})", companies_done=done)

    try:
        results = await asyncio.gather(*(guarded(cid) for cid in company_ids), return_exceptions=True)
        for cid, res in zip(company_ids, results):
            if isinstance(res, BaseException):
                failures += 1
                _log(run_id, f"Company {cid} failed: {res}")
                continue
            usage.add(Usage.model_validate(res.pop("usage")))
            for src, n in res["new_documents"].items():
                per_source[src] = per_source.get(src, 0) + n
            per_company.append({"company_id": cid, **res})

        _log(run_id, "Scoring leads", stage="scoring")
        with sf() as db:
            leads = recompute_scores(db, company_ids, service_ids)
            # every lead with signals, best first, so the AI quota goes to the leads that matter most
            to_explain = sorted((l for l in leads if needs_summary(l)), key=lambda l: -(l.final_score or 0))
        if explain and to_explain:
            _log(run_id, f"Writing explanations for {len(to_explain)} leads", stage="explain")

            async def explain_one(lead: MDoc):
                with sf() as db:
                    return await generate_summary(db, lead, llm)

            for u in await asyncio.gather(*(explain_one(l) for l in to_explain), return_exceptions=True):
                if isinstance(u, Usage):
                    usage.add(u)
        mongo.update(mongo.RUNS, run_id, {
            "status": "succeeded" if failures < len(company_ids) or not company_ids else "failed",
            "finished_at": utcnow(),
            "progress.stage": "done",
            "stats": {
                "duration_seconds": round(time.monotonic() - started, 1),
                "new_documents_by_source": per_source,
                "companies_failed": failures,
                "usage": usage.model_dump(),
                "estimated_cost_usd": usage.cost_usd,
                "companies": per_company,
            },
        })
        _log(run_id, f"Finished in {time.monotonic() - started:.1f}s, cost ≈ ${usage.cost_usd:.4f}")
    except Exception as exc:  # noqa: BLE001 - a run must always end in a terminal state
        log.exception("run %s failed", run_id)
        mongo.update(mongo.RUNS, run_id, {"status": "failed", "error": str(exc)[:2000], "finished_at": utcnow()})
