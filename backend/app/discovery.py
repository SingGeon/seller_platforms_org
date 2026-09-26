"""Discovery (signal -> company) and source sync state (GIG-14, GIG-23).

One sync of one source:
  cursor -> source.sync() -> resolve every item to a company (domain, then normalised
  name; create it if new) -> store its document (deduped by hash) -> save cursor/stats.

A discovery run syncs several sources, analyses every touched company with the
signal pipeline (on the documents just found, no extra crawling), then fully
enriches the best `enrich_top_n` new leads (website, ATS, news, registries).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sales_pipeline import Document
from sales_pipeline.llm import LLMBackend
from sales_pipeline.sources.base import DiscoveredItem, SourceContext
from sales_pipeline.sources.catalog import BY_NAME, SOURCES
from sales_pipeline.sources.companies import normalize_company_name, normalize_domain

from . import mongo
from .config import get_settings
from .models import IcpCriteria, Service, SignalQuestion, SourceState
from .mongo import MDoc

log = logging.getLogger(__name__)
EXTRACT_BATCH = 25


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def source_keys() -> dict[str, str]:
    s = get_settings()
    return {
        "adzuna_app_id": s.adzuna_app_id, "adzuna_app_key": s.adzuna_app_key, "newsdata_key": s.newsdata_key,
        "currents_key": s.currents_key, "themuse_key": s.themuse_key, "serpapi_key": s.serpapi_key,
        "sec_user_agent": s.sec_user_agent, "newsapi_key": s.newsapi_key,
    }


def discovery_countries(db: Session) -> list[str]:
    """Markets searched by discovery: Config (scoring_config.discovery_countries) first, then the
    ICP country lists, then DISCOVERY_COUNTRIES. "Change the country" = edit the config, not code."""
    from .scoring_service import get_scoring_config

    configured = [c.upper() for c in (get_scoring_config(db).discovery_countries or [])]
    if configured:
        return configured
    countries: dict[str, None] = {}
    for icp in db.scalars(select(IcpCriteria).join(Service).where(Service.active.is_(True))):
        for c in icp.countries or []:
            countries.setdefault(c.upper(), None)
    if not countries:
        for c in get_settings().discovery_countries.split(","):
            if c.strip():
                countries.setdefault(c.strip().upper(), None)
    return list(countries)


def discovery_keywords(db: Session) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    rows = db.execute(
        select(Service.slug, SignalQuestion.keywords)
        .join(SignalQuestion, SignalQuestion.service_id == Service.id)
        .where(Service.active.is_(True), SignalQuestion.active.is_(True), SignalQuestion.is_negative.is_(False))
    )
    for slug, kws in rows:
        bucket = out.setdefault(slug, [])
        for k in kws or []:
            if k not in bucket and len(bucket) < 12:
                bucket.append(k)
    return out


def get_state(db: Session, name: str) -> SourceState:
    state = db.get(SourceState, name)
    if state is None:
        state = SourceState(name=name, cursor={}, last_stats={})
        db.add(state)
        db.flush()
    return state


def record_source_run(sf: sessionmaker, name: str, *, items: int = 0, new_documents: int = 0, new_companies: int = 0,
                      failed: int = 0, error: str | None = None, duration_seconds: float | None = None) -> None:
    """Record the outcome of a source that runs inside bootstrap, the daily news refresh or the news curation
    (company_news, business_press, wikidata), so /sources shows when it last ran and how it went."""
    now = utcnow()
    with sf() as db:
        state = get_state(db, name)
        spec = BY_NAME.get(name)
        state.last_run_at = now
        state.next_run_at = now + timedelta(minutes=state.interval_minutes or (spec.interval_minutes if spec else 1440))
        state.last_stats = {"items": items, "new_documents": new_documents, "new_companies": new_companies, "failed": failed,
                            **({"duration_seconds": duration_seconds} if duration_seconds is not None else {})}
        if error and not items and not new_documents:
            state.last_status, state.last_error = "error", error[:2000]
        else:
            state.last_status, state.last_error, state.last_success_at = "ok", error[:2000] if error else None, now
            state.total_items = (state.total_items or 0) + items
            state.total_new_companies = (state.total_new_companies or 0) + new_companies
        db.commit()


# ------------------------------------------------------------------ entity resolution


def resolve_company(item: DiscoveredItem, source: str) -> tuple[MDoc, bool]:
    domain = normalize_domain(item.company_domain)
    norm = normalize_company_name(item.company_name)
    company = None
    if domain:
        company = mongo.find_one(mongo.COMPANIES, {"domain": domain})
    if company is None and norm:
        company = mongo.find_one(mongo.COMPANIES, {"normalized_name": norm}, sort=[("_id", 1)])
    trace = {"source": source, "signal": item.signal, "at": utcnow().isoformat()}
    if company is None:
        company = mongo.insert_company({
            "name": item.company_name.strip()[:300], "domain": domain, "country": (item.company_country or None),
            "industry": item.company_industry, "origin": source, "discovered_via": [trace], "aliases": [],
        })
        return company, True
    # Fill gaps only; never overwrite what a rep or a registry already set.
    fields: dict[str, Any] = {}
    if domain and not company.domain and not mongo.domain_taken(domain):
        fields["domain"] = domain
    if not company.country and item.company_country:
        fields["country"] = item.company_country
    if not company.industry and item.company_industry:
        fields["industry"] = item.company_industry
    if item.company_name != company.name and item.company_name not in (company.aliases or []):
        fields["aliases"] = [*(company.aliases or []), item.company_name][:20]
    if not any(t.get("source") == source and t.get("signal") == item.signal for t in company.discovered_via or []):
        fields["discovered_via"] = [*(company.discovered_via or []), trace][-20:]
    if fields:
        mongo.update_company(company.id, fields)
        company.update(fields)
    return company, False


def store_document(company_id: int, doc: Document) -> bool:
    return mongo.store_document(company_id, doc)


async def resolve_unresolved(llm: LLMBackend, docs: list[Document]) -> list[DiscoveredItem]:
    """Ask the (small) model which company each unparsed headline is about."""
    items: list[DiscoveredItem] = []
    for i in range(0, len(docs), EXTRACT_BATCH):
        batch = docs[i : i + EXTRACT_BATCH]
        found, _ = await llm.extract_companies([f"{d.title} {d.text[:300]}" for d in batch])
        for f in found:
            doc = batch[f["index"]]
            country = (f.get("country") or "").upper()
            items.append(
                DiscoveredItem(
                    company_name=f["company"], company_domain=f.get("domain") or None,
                    company_country=country if len(country) == 2 else None, signal="news:llm_extracted", document=doc,
                )
            )
    return items


# ------------------------------------------------------------------ one source


async def sync_source(sf: sessionmaker, name: str, llm: LLMBackend, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    spec = BY_NAME[name]
    if spec.sync is None:
        raise ValueError(f"{name} is an enrichment source; it runs per company inside enrichment runs")
    s = get_settings()
    keys = source_keys()
    started = time.monotonic()
    with sf() as db:
        state = get_state(db, name)
        missing = spec.missing_keys(keys)
        interval = state.interval_minutes or spec.interval_minutes
        state.last_run_at = utcnow()
        state.next_run_at = utcnow() + timedelta(minutes=interval)
        if missing:
            state.last_status = "skipped"
            state.last_error = f"missing settings: {', '.join(m.upper() for m in missing)}"
            db.commit()
            return {"source": name, "status": "skipped", "missing": missing}
        cursor = dict(state.cursor or {})
        ctx_countries = discovery_countries(db)
        ctx_keywords = discovery_keywords(db)
        db.commit()

    own_client = client is None
    client = client or httpx.AsyncClient(timeout=45, follow_redirects=True, headers={"User-Agent": "OrangeSignals/0.1 (B2B sales research)"})
    try:
        ctx = SourceContext(
            client=client, keys=keys, countries=ctx_countries, keywords=ctx_keywords,
            max_items=s.discovery_max_items_per_source, sec_user_agent=s.sec_user_agent or None,
        )
        result = await spec.sync(ctx, cursor)
        items = list(result.items)
        if result.unresolved:
            try:
                items += await resolve_unresolved(llm, result.unresolved)
            except Exception as exc:  # noqa: BLE001 - extraction is best effort
                log.warning("company extraction failed for %s: %s", name, exc)
    except Exception as exc:  # noqa: BLE001 - record the failure, keep the old cursor
        with sf() as db:
            state = get_state(db, name)
            state.last_status = "error"
            state.last_error = f"{type(exc).__name__}: {exc}"[:2000]
            db.commit()
        log.warning("source %s failed: %s", name, exc)
        return {"source": name, "status": "error", "error": str(exc)[:300]}
    finally:
        if own_client:
            await client.aclose()

    touched: set[int] = set()
    new_companies = new_docs = 0
    for item in items:
        if not item.company_name.strip() or not item.document.url:
            continue
        company, created = resolve_company(item, name)
        new_companies += int(created)
        if store_document(company.id, item.document):
            new_docs += 1
            touched.add(company.id)
    with sf() as db:
        state = get_state(db, name)
        state.cursor = result.cursor
        state.last_status = "ok"
        state.last_error = None
        state.last_success_at = utcnow()
        stats = {
            "fetched": result.fetched, "items": len(items), "unresolved": len(result.unresolved),
            "new_companies": new_companies, "new_documents": new_docs, "duration_seconds": round(time.monotonic() - started, 1),
        }
        state.last_stats = stats
        state.total_items = (state.total_items or 0) + len(items)
        state.total_new_companies = (state.total_new_companies or 0) + new_companies
        db.commit()
    return {"source": name, "status": "ok", **stats, "touched_company_ids": sorted(touched)}


def due_sources(db: Session, now: datetime | None = None) -> list[str]:
    now = now or utcnow()
    keys = source_keys()
    due = []
    for spec in SOURCES:
        if spec.sync is None or spec.missing_keys(keys):
            continue
        state = db.get(SourceState, spec.name)
        if state is not None and not state.enabled:
            continue
        if state is None or state.next_run_at is None or _aware(state.next_run_at) <= now:
            due.append(spec.name)
    return due


# ------------------------------------------------------------------ discovery run


def _log(run_id: int, message: str, **progress: Any) -> None:
    log.info("discovery run %s: %s", run_id, message)
    mongo.log_run(run_id, message, keep=300, **progress)


async def run_discovery(
    sf: sessionmaker,
    run_id: int,
    *,
    sources: list[str] | None = None,
    enrich_top_n: int | None = None,
    llm: LLMBackend | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    from .llm_factory import get_llm
    from .orchestrator import ENRICH_SOURCES, execute_run

    llm = llm or get_llm()
    enrich_top_n = get_settings().enrich_top_n if enrich_top_n is None else enrich_top_n
    started = time.monotonic()
    names = sources or [s.name for s in SOURCES if s.sync is not None]
    mongo.update(mongo.RUNS, run_id, {"status": "running", "started_at": utcnow(), "progress": {"stage": "discovery", "sources_total": len(names), "sources_done": 0}})
    results: list[dict] = []
    touched: set[int] = set()
    try:
        for i, name in enumerate(names, 1):
            res = await sync_source(sf, name, llm, client=client)
            touched.update(res.pop("touched_company_ids", []))
            results.append(res)
            detail = res.get("error") or res.get("missing") or f"{res.get('new_companies', 0)} new companies, {res.get('new_documents', 0)} new documents"
            _log(run_id, f"{name}: {res['status']} ({detail})", sources_done=i)

        children: dict[str, int] = {}
        if touched:
            # 1) analyse every touched company on the documents discovery just stored (cheap, cached)
            analysis = mongo.create_run(kind="enrichment", params={"parent_run": run_id, "stage": "analysis"})
            children["analysis"] = analysis.id
            _log(run_id, f"Analysing {len(touched)} touched companies (run {analysis.id})", stage="analysis")
            await execute_run(sf, analysis.id, company_ids=sorted(touched), sources=(), llm=llm, explain=False)

            # 2) full enrichment for the best new/changed leads that pass the ICP and rules
            if enrich_top_n > 0:
                best: dict[int, float] = {}
                for lead in mongo.find(mongo.LEAD_SCORES, {"company_id": {"$in": sorted(touched)}, "disqualified": False}):
                    if (lead.breakdown or {}).get("outside_icp"):
                        continue
                    best[lead.company_id] = max(best.get(lead.company_id, 0.0), lead.final_score)
                top = [cid for cid, _ in sorted(best.items(), key=lambda kv: -kv[1])[:enrich_top_n]]
                if top:
                    children["enrichment"] = mongo.create_run(kind="enrichment", params={"parent_run": run_id, "stage": "enrichment"}).id
                if top:
                    _log(run_id, f"Enriching top {len(top)} leads (run {children['enrichment']})", stage="enrichment")
                    await execute_run(sf, children["enrichment"], company_ids=top, sources=ENRICH_SOURCES, llm=llm)

        ok = [r for r in results if r["status"] == "ok"]
        mongo.update(mongo.RUNS, run_id, {
            "status": "succeeded" if ok or not results else "failed",
            "finished_at": utcnow(),
            "progress.stage": "done",
            "stats": {
                "duration_seconds": round(time.monotonic() - started, 1),
                "sources": results,
                "new_companies": sum(r.get("new_companies", 0) for r in results),
                "new_documents": sum(r.get("new_documents", 0) for r in results),
                "touched_companies": len(touched),
                "child_runs": children,
            },
        })
        _log(run_id, f"Finished in {time.monotonic() - started:.1f}s")
    except Exception as exc:  # noqa: BLE001 - a run must always end in a terminal state
        log.exception("discovery run %s failed", run_id)
        mongo.update(mongo.RUNS, run_id, {"status": "failed", "error": str(exc)[:2000], "finished_at": utcnow()})
