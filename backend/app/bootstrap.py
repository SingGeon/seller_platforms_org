"""Build a large, real company universe in one command.

    python -m app.bootstrap --countries RO,MD,DE,AT,PL,NL,GB --target 1000
    python -m app.bootstrap --target 1500 --gleif-fill --enrich-top 30 --gdelt

1. Companies: Wikidata (official website, industry, employees, LEI), best-known first;
   GLEIF tops a country up with registered legal entities when --gleif-fill is set.
2. News: real articles per company from Google News in the company's own language
   (plus GDELT with --gdelt: much slower, 1 request / 5 s).
3. Analysis: the signal pipeline answers every question on the stored documents and scores
   every company x service (heuristic offline, Claude when ANTHROPIC_API_KEY is set).
4. Enrichment: the best --enrich-top leads get the full crawl (website, ATS jobs, registries).

Nothing is invented: every company links to its Wikidata QID or LEI, every signal to a URL.
Re-running is safe: companies are matched by domain / normalised name and documents by hash.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx
from sqlalchemy.orm import sessionmaker

from sales_pipeline.collectors import collect_news
from sales_pipeline.llm import LLMBackend
from sales_pipeline.sources.bulk import COUNTRY_QID, RegistryCompany, gleif_companies, wikidata_companies
from sales_pipeline.sources.companies import normalize_company_name, normalize_domain

from . import mongo
from .mongo import MDoc
from .orchestrator import ENRICH_SOURCES, company_info, execute_run

log = logging.getLogger(__name__)
NEWS_FRESH_HOURS = 24


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def upsert_company(rc: RegistryCompany) -> tuple[MDoc, bool]:
    domain = normalize_domain(rc.domain)
    norm = normalize_company_name(rc.name)
    company = mongo.find_one(mongo.COMPANIES, {"domain": domain}) if domain else None
    if company is None and norm:
        company = mongo.find_one(mongo.COMPANIES, {"normalized_name": norm, "country": rc.country})
    profile = {rc.source: rc.registry_profile()}
    if company is None:
        company = mongo.insert_company({
            "name": rc.name[:300], "domain": domain, "country": rc.country, "industry": rc.industry, "employee_count": rc.employee_count,
            "origin": rc.source, "registry_profiles": profile, "aliases": [],
            "discovered_via": [{"source": rc.source, "signal": "registry", "at": utcnow().isoformat()}],
        })
        return company, True
    fields = {
        "industry": company.industry or rc.industry,
        "employee_count": company.employee_count or rc.employee_count,
        "country": company.country or rc.country,
        "registry_profiles": {**(company.registry_profiles or {}), **profile},
    }
    if domain and not company.domain and not mongo.domain_taken(domain):
        fields["domain"] = domain
    mongo.update_company(company.id, fields)
    company.update(fields)
    return company, False


async def fetch_registry(client: httpx.AsyncClient, countries: list[str], target: int, gleif_fill: bool, say: Callable[[str], None]) -> list[RegistryCompany]:
    """Split the target across countries; a country with fewer companies in Wikidata (e.g. MD)
    hands its shortfall to the countries that still have more, so the total reaches the target."""
    quota = math.ceil(target / len(countries))
    by_country: dict[str, list[RegistryCompany]] = {}
    exhausted: set[str] = set()
    for country in countries:
        got: list[RegistryCompany] = []
        try:
            got = await wikidata_companies(client, country, quota)
        except Exception as exc:  # noqa: BLE001 - one country failing must not stop the others
            say(f"  {country}: Wikidata failed ({type(exc).__name__}: {str(exc)[:120]})")
            exhausted.add(country)
        if len(got) < quota:
            exhausted.add(country)
        by_country[country] = got
    # second pass: redistribute the shortfall to countries that filled their quota
    for _ in range(3):
        shortfall = target - sum(len(v) for v in by_country.values())
        open_countries = [c for c in countries if c not in exhausted]
        if shortfall <= 0 or not open_countries:
            break
        extra = math.ceil(shortfall / len(open_countries))
        for country in open_countries:
            try:
                more = await wikidata_companies(client, country, extra, start=len(by_country[country]))
            except Exception as exc:  # noqa: BLE001
                say(f"  {country}: Wikidata failed ({type(exc).__name__}: {str(exc)[:120]})")
                more = []
            by_country[country] += more
            if len(more) < extra:
                exhausted.add(country)
    if gleif_fill:
        shortfall = target - sum(len(v) for v in by_country.values())
        for country in countries:
            if shortfall <= 0:
                break
            try:
                more = await gleif_companies(client, country, shortfall if country == countries[-1] else min(shortfall, quota))
            except Exception as exc:  # noqa: BLE001
                say(f"  {country}: GLEIF failed ({type(exc).__name__}: {str(exc)[:120]})")
                more = []
            by_country[country] += more
            shortfall -= len(more)
    for country, got in by_country.items():
        say(f"  {country}: {sum(r.source == 'wikidata' for r in got)} from Wikidata, {sum(r.source == 'gleif' for r in got)} from GLEIF")
    return [r for c in countries for r in by_country[c]]


def companies_needing_news(ids: list[int]) -> list[int]:
    cutoff = utcnow() - timedelta(hours=NEWS_FRESH_HOURS)
    fresh = set(
        mongo.db()[mongo.DOCUMENTS].distinct(
            "company_id", {"company_id": {"$in": ids}, "source_type": "news", "fetched_at": {"$gte": cutoff}}
        )
    )
    return [i for i in ids if i not in fresh]


async def fetch_news(sf: sessionmaker, client: httpx.AsyncClient, ids: list[int], *, gdelt: bool, concurrency: int, say: Callable[[str], None]) -> dict[str, int]:
    providers = ("google_news", "gdelt") if gdelt else ("google_news",)
    sem = asyncio.Semaphore(concurrency)
    stats = {"companies_with_news": 0, "news_documents": 0, "failed": 0}
    done = 0

    async def one(cid: int) -> None:
        nonlocal done
        async with sem:
            info = company_info(mongo.get(mongo.COMPANIES, cid))
            try:
                docs = await collect_news(info, client=client, providers=providers)
            except Exception:  # noqa: BLE001
                stats["failed"] += 1
                docs = []
            new = sum(mongo.store_document(cid, d) for d in docs)
            stats["news_documents"] += new
            stats["companies_with_news"] += int(bool(docs))
            done += 1
            if done % 50 == 0 or done == len(ids):
                say(f"  news: {done}/{len(ids)} companies, {stats['news_documents']} new articles")

    await asyncio.gather(*(one(i) for i in ids))
    return stats


async def bootstrap(
    sf: sessionmaker,
    *,
    countries: list[str],
    target: int = 1000,
    gleif_fill: bool = False,
    news: bool = True,
    gdelt: bool = False,
    analyze: bool = True,
    enrich_top_n: int = 0,
    news_concurrency: int = 6,
    llm: LLMBackend | None = None,
    client: httpx.AsyncClient | None = None,
    say: Callable[[str], None] = print,
    run_id: int | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    unknown = [c for c in countries if c not in COUNTRY_QID]
    if unknown:
        raise ValueError(f"unsupported countries: {unknown}; supported: {sorted(COUNTRY_QID)}")
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=60, follow_redirects=True, headers={"User-Agent": "OrangeSignals/0.1 (B2B sales research)"})
    stats: dict[str, Any] = {"countries": countries, "target": target}
    try:
        say(f"1/4 Companies from open registries ({', '.join(countries)}, target {target})")
        records = await fetch_registry(client, countries, target, gleif_fill, say)
        if not records:
            raise RuntimeError("no companies loaded: every registry request failed (network blocked or source down), see the log")
        created = 0
        ids: list[int] = []
        for rc in records:
            company, is_new = upsert_company(rc)
            created += int(is_new)
            ids.append(company.id)
        ids = list(dict.fromkeys(ids))
        stats.update(registry_records=len(records), companies=len(ids), companies_created=created)
        say(f"  {len(ids)} companies ({created} new)")

        if news and ids:
            todo = companies_needing_news(ids)
            say(f"2/4 News for {len(todo)} companies (skipping {len(ids) - len(todo)} refreshed in the last {NEWS_FRESH_HOURS} h)")
            stats["news"] = await fetch_news(sf, client, todo, gdelt=gdelt, concurrency=news_concurrency, say=say)

        if analyze and ids:
            say(f"3/4 Signal analysis and scoring for {len(ids)} companies")
            analysis_id = mongo.create_run(kind="enrichment", params={"stage": "bootstrap-analysis", "parent_run": run_id}).id
            await execute_run(sf, analysis_id, company_ids=ids, sources=(), llm=llm, explain=True)
            stats["analysis_run"] = analysis_id

        if enrich_top_n > 0 and ids:
            best: dict[int, float] = {}
            for lead in mongo.find(mongo.LEAD_SCORES, {"company_id": {"$in": ids}, "disqualified": False}):
                if not (lead.breakdown or {}).get("outside_icp"):
                    best[lead.company_id] = max(best.get(lead.company_id, 0.0), lead.final_score)
            top = [cid for cid, _ in sorted(best.items(), key=lambda kv: -kv[1])[:enrich_top_n]]
            enrich_id = mongo.create_run(kind="enrichment", params={"stage": "bootstrap-enrichment", "parent_run": run_id}).id
            say(f"4/4 Full enrichment (website, jobs, registries) for the top {len(top)} leads")
            await execute_run(sf, enrich_id, company_ids=top, sources=ENRICH_SOURCES, llm=llm)
            stats["enrichment_run"] = enrich_id

        stats["totals"] = summary()
        stats["duration_seconds"] = round(time.monotonic() - started, 1)
        say(f"Done in {stats['duration_seconds']}s: {stats['totals']}")
        return stats
    finally:
        if own_client:
            await client.aclose()


def summary() -> dict[str, int]:
    d = mongo.db()
    tiers = {r["_id"]: r["n"] for r in d[mongo.LEAD_SCORES].aggregate([{"$group": {"_id": "$tier", "n": {"$sum": 1}}}])}
    return {
        "companies": d[mongo.COMPANIES].count_documents({}),
        "companies_with_news": len(d[mongo.DOCUMENTS].distinct("company_id", {"source_type": "news"})),
        "documents": d[mongo.DOCUMENTS].count_documents({}),
        "hot": tiers.get("Hot", 0), "warm": tiers.get("Warm", 0), "cold": tiers.get("Cold", 0), "disqualified": tiers.get("Disqualified", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--countries", default="RO,MD,DE,AT,PL,NL,GB", help="ISO-2 list; supported: " + ",".join(sorted(COUNTRY_QID)))
    parser.add_argument("--target", type=int, default=1000, help="number of companies to load (split evenly across countries)")
    parser.add_argument("--gleif-fill", action="store_true", help="top up countries with GLEIF legal entities when Wikidata has too few")
    parser.add_argument("--no-news", action="store_true")
    parser.add_argument("--gdelt", action="store_true", help="also query GDELT (1 request / 5 s: ~1.5 h per 1000 companies)")
    parser.add_argument("--no-analyze", action="store_true")
    parser.add_argument("--enrich-top", type=int, default=0, help="full enrichment for the N best leads")
    parser.add_argument("--news-concurrency", type=int, default=6)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    from .db import SessionLocal
    from .seed import seed_config

    with SessionLocal() as db:
        seed_config(db)  # services, questions and rules must exist before scoring
    asyncio.run(
        bootstrap(
            SessionLocal, countries=[c.strip().upper() for c in args.countries.split(",") if c.strip()], target=args.target,
            gleif_fill=args.gleif_fill, news=not args.no_news, gdelt=args.gdelt, analyze=not args.no_analyze,
            enrich_top_n=args.enrich_top, news_concurrency=args.news_concurrency,
        )
    )


if __name__ == "__main__":
    main()
