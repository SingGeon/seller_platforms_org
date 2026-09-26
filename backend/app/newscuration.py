"""News curation: keep only companies whose news explains their situation, and find more of that news.

Automates what a sales manager did by hand (Annex 1, steps 3-6): read the public news about each account, keep the
stories that show a need for our services (cost / efficiency programs, digital transformation, AI / RPA / process
mining projects, relevant hiring, CIO / COO / digital appointments, shared services, technologies and partners,
security incidents, outages, compliance, financial or operational problems) and drop the rest.

1. Tag every stored article with its topics (sales_pipeline.newstopics) and whether it really names the company.
2. Companies with fewer than `search_below` distinct recent topical stories get a targeted search: Google News once
   per theme keyword in the company's language (8 requests), the latest Bing News for the name, and the business /
   tech / security press feeds.
3. A company with at least `min_stories` such stories is "active"; one below it becomes "insufficient_news" and is
   hidden from leads and the dashboard (its data stays, a later run can bring it back).
4. With `target`, new real companies from Wikidata replace the hidden ones: each candidate is searched first and only
   stored when it already has `min_stories` topical stories.
5. The kept companies are analysed and scored again.

    cd backend
    python -m app.newscuration                      # tag, search, update statuses, analyse
    python -m app.newscuration --target 984         # ... and replace hidden companies until 984 are active
    python -m app.newscuration --no-search          # only re-tag the stored news and update statuses
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
from collections import Counter
from datetime import timedelta
from typing import Any, Callable

import httpx
from pymongo import UpdateOne
from sqlalchemy.orm import sessionmaker

from sales_pipeline.collectors import collect_news
from sales_pipeline.newstopics import NEGATIVE_TOPICS, STRONG_TOPICS, TOPIC_LABELS, classify, story_key
from sales_pipeline.schemas import CompanyInfo
from sales_pipeline.sources.bulk import RegistryCompany, wikidata_companies
from sales_pipeline.sources.companies import mentions_strictly, normalize_company_name, normalize_domain

from . import mongo
from .mongo import utcnow

log = logging.getLogger(__name__)

MIN_STORIES = 5  # distinct recent topical stories a company needs to stay in the lead list
SEARCH_BELOW = 10  # companies with fewer stories than this get a targeted search
RECENT_YEARS = 3  # older news no longer describes the company's situation
ACTIVE, INSUFFICIENT = "active", "insufficient_news"
# Google News ("google_topics") blocked the laptop's bulk runs for hours (503) and GDELT ("gdelt_topics") allows
# 1 request / 5 s with nothing for RO / MD companies, so both are opt-in; the news already collected from them stays.
TOPIC_PROVIDERS = ("bing_topics", "bing_news")
REJECTS = "curation_rejects"  # candidates checked and turned down, so later runs skip them
REJECT_DAYS = 30


# ------------------------------------------------------------------ tagging and profiles


def tag_documents(company_ids: list[int] | None = None) -> int:
    """(Re)compute meta.topics and meta.about_company for the stored articles of `company_ids` (all when None)."""
    d = mongo.db()
    query: dict = {"source_type": "news"}
    if company_ids is not None:
        query["company_id"] = {"$in": company_ids}
    names = {c["_id"]: c["name"] for c in d[mongo.COMPANIES].find({} if company_ids is None else {"_id": {"$in": company_ids}}, {"name": 1})}
    ops: list[UpdateOne] = []
    for doc in d[mongo.DOCUMENTS].find(query, {"company_id": 1, "title": 1, "content": 1, "meta": 1}):
        text = f"{doc.get('title') or ''}. {doc.get('content') or ''}"
        topics = classify(text)
        about = mentions_strictly(names.get(doc["company_id"], ""), text)
        meta = doc.get("meta") or {}
        if meta.get("topics") != topics or meta.get("about_company") != about:
            ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": {"meta.topics": topics, "meta.about_company": about}}))
        if len(ops) >= 1000:
            d[mongo.DOCUMENTS].bulk_write(ops, ordered=False)
            ops = []
    if ops:
        d[mongo.DOCUMENTS].bulk_write(ops, ordered=False)
    return len(ops)


def news_profile(company_id: int) -> dict[str, Any]:
    """Distinct recent stories that name the company and cover at least one topic."""
    cutoff = utcnow() - timedelta(days=365 * RECENT_YEARS)
    stories: dict[str, dict] = {}
    for doc in mongo.db()[mongo.DOCUMENTS].find(
        {"company_id": company_id, "source_type": "news", "meta.about_company": True, "meta.topics.0": {"$exists": True},
         "$or": [{"published_at": None}, {"published_at": {"$gte": cutoff}}]},
        {"title": 1, "published_at": 1, "meta.topics": 1},
    ):
        key = story_key(doc.get("title") or "")
        seen = stories.setdefault(key, {"topics": set(), "published_at": doc.get("published_at")})
        seen["topics"].update(doc["meta"]["topics"])
    topics = Counter(t for s in stories.values() for t in s["topics"])
    dates = [s["published_at"] for s in stories.values() if s["published_at"]]
    return {
        "stories": len(stories),
        "strong_stories": sum(1 for s in stories.values() if s["topics"] & STRONG_TOPICS),
        "negative_stories": sum(1 for s in stories.values() if s["topics"] & NEGATIVE_TOPICS),
        "topics": {k: topics[k] for k in TOPIC_LABELS if topics[k]},
        "last_story_at": max(dates) if dates else None,
        "checked_at": utcnow(),
    }


def update_status(company_ids: list[int], min_stories: int = MIN_STORIES, only_curated: bool = False) -> dict[str, int]:
    """Store each company's news profile and set it active / insufficient_news. Manual companies are never hidden.
    only_curated: leave companies that never went through a curation run alone (the daily refresh must not hide
    companies before their targeted search has run)."""
    counts = Counter()
    query: dict = {"_id": {"$in": company_ids}}
    if only_curated:
        query["news_profile.curated_at"] = {"$exists": True}
    for c in mongo.db()[mongo.COMPANIES].find(query, {"origin": 1, "status": 1, "news_profile.curated_at": 1}):
        profile = news_profile(c["_id"])
        curated_at = (c.get("news_profile") or {}).get("curated_at")
        if curated_at:
            profile["curated_at"] = curated_at
        status = ACTIVE if profile["stories"] >= min_stories or c.get("origin") in ("manual", "import") else INSUFFICIENT
        if c.get("status") not in (ACTIVE, INSUFFICIENT):
            status = c.get("status")  # a status set by a person (e.g. archived) wins
        mongo.db()[mongo.COMPANIES].update_one({"_id": c["_id"]}, {"$set": {"news_profile": profile, "status": status}})
        counts[status] += 1
    return dict(counts)


def stories_below(company_ids: list[int], limit: int) -> list[int]:
    return [c["_id"] for c in mongo.db()[mongo.COMPANIES].find({"_id": {"$in": company_ids}}, {"news_profile.stories": 1})
            if ((c.get("news_profile") or {}).get("stories") or 0) < limit]


# ------------------------------------------------------------------ targeted search


async def search_companies(client: httpx.AsyncClient, company_ids: list[int], *, concurrency: int, say: Callable[[str], None],
                           providers: tuple[str, ...] = TOPIC_PROVIDERS) -> dict[str, int]:
    from .orchestrator import company_info

    sem = asyncio.Semaphore(concurrency)
    stats = {"companies": len(company_ids), "new_documents": 0, "failed": 0}
    done = 0

    async def one(cid: int) -> None:
        nonlocal done
        async with sem:
            try:
                docs = await collect_news(company_info(mongo.get(mongo.COMPANIES, cid)), client=client, providers=providers)
            except Exception:  # noqa: BLE001 - one company must not stop the run
                log.exception("news search failed for company %s", cid)
                stats["failed"] += 1
                docs = []
            stats["new_documents"] += sum(mongo.store_document(cid, d) for d in docs)
            done += 1
            if done % 25 == 0 or done == len(company_ids):
                say(f"  targeted search: {done}/{len(company_ids)} companies, {stats['new_documents']} new articles")

    await asyncio.gather(*(one(i) for i in company_ids))
    return stats


# ------------------------------------------------------------------ replacements


def _known(rc: RegistryCompany) -> bool:
    domain = normalize_domain(rc.domain)
    d = mongo.db()[mongo.COMPANIES]
    if domain and d.count_documents({"domain": domain}, limit=1):
        return True
    norm = normalize_company_name(rc.name)
    if d.count_documents({"normalized_name": norm, "country": rc.country}, limit=1):
        return True
    recent = utcnow() - timedelta(days=REJECT_DAYS)
    return bool(mongo.db()[REJECTS].count_documents({"normalized_name": norm, "country": rc.country, "checked_at": {"$gte": recent}}, limit=1))


async def replace_companies(client: httpx.AsyncClient, *, target: int, countries: list[str], min_stories: int, concurrency: int,
                            say: Callable[[str], None], batch: int = 60, max_candidates: int = 3000) -> dict[str, Any]:
    """Add real companies from Wikidata (next best-known after the ones already loaded) that already have
    `min_stories` topical stories, until `target` companies are active."""
    from .bootstrap import upsert_company

    stats: dict[str, Any] = {"candidates": 0, "added": 0, "rejected": 0, "exhausted": []}
    offsets = {c: mongo.db()[mongo.COMPANIES].count_documents({"country": c, "origin": "wikidata"})
               + mongo.db()[REJECTS].count_documents({"country": c}) for c in countries}
    live = list(countries)
    sem = asyncio.Semaphore(concurrency)

    def active() -> int:
        return mongo.db()[mongo.COMPANIES].count_documents({"status": ACTIVE})

    async def check(rc: RegistryCompany) -> None:
        async with sem:
            info = CompanyInfo(name=rc.name, domain=rc.domain, country=rc.country, industry=rc.industry, employee_count=rc.employee_count)
            try:
                docs = await collect_news(info, client=client, providers=TOPIC_PROVIDERS)
            except Exception:  # noqa: BLE001
                log.exception("news search failed for candidate %s", rc.name)
                docs = []
        cutoff = utcnow() - timedelta(days=365 * RECENT_YEARS)
        stories = {story_key(d.title) for d in docs if classify(f"{d.title}. {d.text}")
                   and (d.published_at is None or d.published_at >= cutoff)}
        if len(stories) < min_stories:
            stats["rejected"] += 1
            mongo.db()[REJECTS].update_one(
                {"normalized_name": normalize_company_name(rc.name), "country": rc.country},
                {"$set": {"name": rc.name, "stories": len(stories), "checked_at": utcnow()}}, upsert=True)
            return
        if active() >= target:
            return  # other candidates of this batch already filled the list
        company, _ = upsert_company(rc)
        for d in docs:
            mongo.store_document(company.id, d)
        tag_documents([company.id])
        update_status([company.id], min_stories)
        mongo.db()[mongo.COMPANIES].update_one({"_id": company.id}, {"$set": {"news_profile.curated_at": utcnow()}})
        stats["added"] += 1

    while active() < target and live and stats["candidates"] < max_candidates:
        need = target - active()
        for country in list(live):
            per_country = max(10, min(batch, need * 3 // max(1, len(live)) + 1))
            try:
                found = await wikidata_companies(client, country, per_country, start=offsets[country])
            except Exception as exc:  # noqa: BLE001
                say(f"  {country}: Wikidata failed ({type(exc).__name__}), skipping it")
                live.remove(country)
                continue
            offsets[country] += per_country
            fresh = [rc for rc in found if not _known(rc)]
            if not found:
                live.remove(country)
                stats["exhausted"].append(country)
                continue
            stats["candidates"] += len(fresh)
            await asyncio.gather(*(check(rc) for rc in fresh))
            say(f"  {country}: {len(fresh)} new candidates checked; total added {stats['added']}, rejected {stats['rejected']}, "
                f"active {active()}/{target}")
            if active() >= target:
                break
    return stats


# ------------------------------------------------------------------ the whole curation


async def curate(
    sf: sessionmaker, *, min_stories: int = MIN_STORIES, search_below: int = SEARCH_BELOW, search: bool = True,
    target: int | None = None, countries: list[str] | None = None, analyze: bool = True, concurrency: int = 2,
    only_ids: list[int] | None = None,
    client: httpx.AsyncClient | None = None, say: Callable[[str], None] = print,
) -> dict[str, Any]:
    from .bootstrap import local_press_news, record_news_sources
    from .discovery import record_source_run
    from .orchestrator import execute_run

    started = time.monotonic()
    stats: dict[str, Any] = {}
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=60, follow_redirects=True, headers={"User-Agent": "OrangeSignals/0.1 (B2B sales research)"})
    try:
        ids = mongo.ids(mongo.COMPANIES, {"status": {"$in": [ACTIVE, INSUFFICIENT]}})
        countries = countries or sorted({c for c in mongo.db()[mongo.COMPANIES].distinct("country", {"_id": {"$in": ids}}) if c})
        say(f"1/5 Tagging the stored news of {len(ids)} companies")
        tag_documents(ids)
        update_status(ids, min_stories)
        if search:
            say("2/5 Business, tech and security press feeds")
            stats["press"] = await local_press_news(client, ids, say)
            todo = stories_below(only_ids if only_ids is not None else ids, search_below)
            say(f"3/5 Targeted news search for {len(todo)} companies with fewer than {search_below} topical stories")
            stats["search"] = await search_companies(client, todo, concurrency=concurrency, say=say)
            record_news_sources(sf, stats)
            tag_documents(ids)
        stats["status"] = update_status(ids, min_stories)
        mongo.db()[mongo.COMPANIES].update_many({"_id": {"$in": ids}}, {"$set": {"news_profile.curated_at": utcnow()}})
        say(f"  status: {stats['status']}")
        if target:
            say(f"4/5 Replacing hidden companies until {target} are active ({', '.join(countries)})")
            stats["replace"] = await replace_companies(client, target=target, countries=countries, min_stories=min_stories,
                                                       concurrency=concurrency, say=say)
            record_source_run(sf, "wikidata", items=stats["replace"]["candidates"], new_companies=stats["replace"]["added"])
    finally:
        if own_client:
            await client.aclose()
    active = mongo.ids(mongo.COMPANIES, {"status": ACTIVE})
    if analyze and active:
        say(f"5/5 Signal analysis and scoring for {len(active)} active companies")
        run_id = mongo.create_run(kind="enrichment", params={"stage": "news-curation-analysis"}).id
        await execute_run(sf, run_id, company_ids=active, sources=(), explain=True)
        stats["analysis_run"] = run_id
    stats["active"] = len(active)
    stats["hidden"] = mongo.db()[mongo.COMPANIES].count_documents({"status": INSUFFICIENT})
    stats["duration_seconds"] = round(time.monotonic() - started, 1)
    say(f"Done in {stats['duration_seconds']}s: {stats['active']} active companies, {stats['hidden']} hidden for too little news")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--min-stories", type=int, default=MIN_STORIES, help="topical stories a company needs to stay listed")
    parser.add_argument("--search-below", type=int, default=SEARCH_BELOW, help="search more news for companies below this many stories")
    parser.add_argument("--no-search", action="store_true", help="only re-tag the stored news and update the statuses")
    parser.add_argument("--target", type=int, default=None, help="add new companies with enough news until this many are active")
    parser.add_argument("--countries", default=None, help="countries for new companies (default: those already stored)")
    parser.add_argument("--no-analyze", action="store_true")
    parser.add_argument("--concurrency", type=int, default=2, help="companies searched in parallel (Google News blocks above ~2)")
    parser.add_argument("--only", default=None, help="search only these company ids (comma-separated), e.g. the ones a blocked run missed")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    from .db import SessionLocal

    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()] if args.countries else None
    asyncio.run(curate(SessionLocal, min_stories=args.min_stories, search_below=args.search_below, search=not args.no_search,
                       target=args.target, countries=countries, analyze=not args.no_analyze, concurrency=args.concurrency,
                       only_ids=[int(i) for i in args.only.split(",") if i.strip()] if args.only else None))


if __name__ == "__main__":
    main()
