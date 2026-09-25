"""Job boards for discovery: who is hiring automation / AI / security roles right now.

Only postings that map to a relevant role category (RPA, AI/ML, Process
Excellence, Business Analysis, Security, Digital Transformation) become leads.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import feedparser
from bs4 import BeautifulSoup

from ..collectors.jobs import categorize_role
from ..documents import Document, clean_text
from .base import DiscoveredItem, SourceContext, SyncResult, cursor_since, get_json, get_text, parse_dt
from .companies import company_from_hn_post, normalize_domain

ADZUNA_COUNTRIES = {"GB", "AT", "BE", "DE", "FR", "IT", "NL", "PL", "ES", "CH", "US", "CA"}
COUNTRY_WORDS = {
    "DE": ["germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt", "köln", "cologne", "düsseldorf", "stuttgart"],
    "AT": ["austria", "österreich", "vienna", "wien"], "CH": ["switzerland", "schweiz", "zürich", "zurich", "geneva", "basel"],
    "NL": ["netherlands", "amsterdam", "rotterdam", "utrecht"], "RO": ["romania", "bucharest", "bucurești", "cluj", "iasi", "iași"],
    "MD": ["moldova", "chisinau", "chișinău"], "GB": ["united kingdom", "uk", "london", "manchester"], "FR": ["france", "paris", "lyon"],
    "PL": ["poland", "warsaw", "kraków", "krakow", "wrocław"], "ES": ["spain", "madrid", "barcelona"], "IT": ["italy", "milan", "rome"],
}


def html_to_text(html: str) -> str:
    return clean_text(BeautifulSoup(html or "", "html.parser").get_text(" "))


def country_from_location(location: str, countries: list[str]) -> str | None:
    loc = (location or "").lower()
    for code in countries or COUNTRY_WORDS:
        if any(w in loc for w in COUNTRY_WORDS.get(code, [])):
            return code
    return None


def job_item(*, company: str, title: str, description: str, url: str, posted: Any, location: str, board: str,
             country: str | None = None, domain: str | None = None) -> DiscoveredItem | None:
    cats = categorize_role(title, description)
    if not company or not cats or not url:
        return None
    return DiscoveredItem(
        company_name=company.strip(),
        company_domain=normalize_domain(domain),
        company_country=country,
        signal="hiring:" + ",".join(cats),
        document=Document(
            source_type="jobs", url=url, title=clean_text(title)[:300],
            text=clean_text(f"Job posting at {company}: {title}. Location: {location}. {description}")[:6000],
            published_at=parse_dt(posted), source=board,
            meta={"job_title": clean_text(title), "location": location, "categories": cats, "board": board},
        ),
    )


def _newer(doc_date: datetime | None, since: datetime) -> bool:
    return doc_date is None or doc_date >= since


def _finish(items: list[DiscoveredItem], since: datetime, max_items: int) -> list[DiscoveredItem]:
    fresh = [i for i in items if _newer(i.document.published_at, since)]
    return fresh[:max_items]


# ------------------------------------------------------------------ Arbeitnow (EU, aggregates ATS boards)
async def sync_arbeitnow(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=7)
    items, fetched = [], 0
    url: str | None = "https://www.arbeitnow.com/api/job-board-api"
    for _ in range(5):
        if not url:
            break
        data = await get_json(ctx.client, url)
        jobs = data.get("data", [])
        fetched += len(jobs)
        for j in jobs:
            country = country_from_location(j.get("location", ""), ctx.countries)
            if ctx.countries and not country and not j.get("remote"):
                continue
            item = job_item(company=j.get("company_name", ""), title=j.get("title", ""), description=html_to_text(j.get("description", "")),
                            url=j.get("url", ""), posted=j.get("created_at"), location=j.get("location", ""), board="arbeitnow", country=country)
            if item:
                items.append(item)
        oldest = parse_dt(jobs[-1].get("created_at")) if jobs else None
        if oldest and oldest < since:
            break
        url = (data.get("links") or {}).get("next")
    return SyncResult(items=_finish(items, since, ctx.max_items), fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat()})


# ------------------------------------------------------------------ Adzuna (key)
async def sync_adzuna(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=7)
    days = max(1, min(30, (datetime.now(timezone.utc) - since).days + 1))
    countries = [c for c in (ctx.countries or ["GB", "DE"]) if c in ADZUNA_COUNTRIES] or ["GB"]
    queries = ctx.all_keywords()[:6] or ["rpa developer", "automation engineer", "security engineer"]
    items, fetched = [], 0
    for country in countries[:4]:
        for q in queries:
            data = await get_json(
                ctx.client, f"https://api.adzuna.com/v1/api/jobs/{country.lower()}/search/1",
                params={"app_id": ctx.keys["adzuna_app_id"], "app_key": ctx.keys["adzuna_app_key"], "what": q,
                        "results_per_page": "50", "max_days_old": str(days), "content-type": "application/json"},
            )
            results = data.get("results", [])
            fetched += len(results)
            for r in results:
                item = job_item(company=(r.get("company") or {}).get("display_name", ""), title=r.get("title", ""),
                                description=html_to_text(r.get("description", "")), url=r.get("redirect_url", ""), posted=r.get("created"),
                                location=(r.get("location") or {}).get("display_name", ""), board="adzuna", country=country)
                if item:
                    items.append(item)
    return SyncResult(items=_finish(items, since, ctx.max_items), fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat()})


# ------------------------------------------------------------------ HN "Who is hiring" (Algolia)
async def sync_hn_hiring(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    stories = await get_json(ctx.client, "https://hn.algolia.com/api/v1/search_by_date", params={"tags": "story,author_whoishiring", "hitsPerPage": "5"})
    story = next((h for h in stories.get("hits", []) if "who is hiring" in (h.get("title") or "").lower()), None)
    if not story:
        return SyncResult(notes=["no 'Who is hiring' thread found"])
    seen = set(cursor.get("seen", [])) if cursor.get("story") == story["objectID"] else set()
    thread = await get_json(ctx.client, f"https://hn.algolia.com/api/v1/items/{story['objectID']}")
    items, fetched = [], 0
    for c in thread.get("children", []):
        fetched += 1
        cid = str(c.get("id"))
        if cid in seen or not c.get("text"):
            continue
        seen.add(cid)
        text = html_to_text(c["text"])
        company = company_from_hn_post(c["text"].replace("<p>", "\n"))
        if not company:
            continue
        domain = None
        m = re.search(r"https?://(?:www\.)?([a-z0-9.-]+\.[a-z]{2,})", c["text"], re.I)
        if m and not re.search(r"(greenhouse|lever|ashbyhq|workable|news\.ycombinator|linkedin|github)\.", m.group(1)):
            domain = m.group(1)
        first_line = text.split(" | ")
        title = " | ".join(first_line[1:3]) if len(first_line) > 1 else text[:120]
        item = job_item(company=company, title=title, description=text, url=f"https://news.ycombinator.com/item?id={cid}",
                        posted=c.get("created_at"), location=" | ".join(first_line[2:4]), board="hn_who_is_hiring",
                        country=country_from_location(text, ctx.countries), domain=domain)
        if item:
            items.append(item)
    return SyncResult(items=items[: ctx.max_items], fetched=fetched, cursor={"story": story["objectID"], "seen": sorted(seen)[-5000:]})


# ------------------------------------------------------------------ remote job boards (no key)
async def sync_remotive(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=7)
    items, fetched = [], 0
    for q in (ctx.all_keywords()[:5] or ["automation", "security", "machine learning"]):
        data = await get_json(ctx.client, "https://remotive.com/api/remote-jobs", params={"search": q, "limit": "100"})
        for j in data.get("jobs", []):
            fetched += 1
            item = job_item(company=j.get("company_name", ""), title=j.get("title", ""), description=html_to_text(j.get("description", "")),
                            url=j.get("url", ""), posted=j.get("publication_date"), location=j.get("candidate_required_location", ""), board="remotive")
            if item:
                items.append(item)
    return SyncResult(items=_finish(items, since, ctx.max_items), fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat()})


async def sync_remoteok(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=7)
    data = await get_json(ctx.client, "https://remoteok.com/api")
    items = []
    jobs = [j for j in data if isinstance(j, dict) and j.get("position")]  # first element is a legal notice
    for j in jobs:
        item = job_item(company=j.get("company", ""), title=j.get("position", ""), description=html_to_text(j.get("description", "")) + " " + " ".join(j.get("tags") or []),
                        url=j.get("url", ""), posted=j.get("date") or j.get("epoch"), location=j.get("location", ""), board="remoteok")
        if item:
            items.append(item)
    return SyncResult(items=_finish(items, since, ctx.max_items), fetched=len(jobs), cursor={"since": datetime.now(timezone.utc).isoformat()})


async def sync_jobicy(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=7)
    items, fetched = [], 0
    for tag in ("automation", "security", "machine learning", "data", "business analyst"):
        data = await get_json(ctx.client, "https://jobicy.com/api/v2/remote-jobs", params={"count": "50", "tag": tag})
        for j in data.get("jobs", []):
            fetched += 1
            item = job_item(company=j.get("companyName", ""), title=j.get("jobTitle", ""), description=html_to_text(j.get("jobDescription") or j.get("jobExcerpt", "")),
                            url=j.get("url", ""), posted=j.get("pubDate"), location=j.get("jobGeo", ""), board="jobicy")
            if item:
                items.append(item)
    return SyncResult(items=_finish(items, since, ctx.max_items), fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat()})


async def sync_himalayas(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=7)
    items, fetched = [], 0
    for offset in (0, 20, 40, 60, 80):
        data = await get_json(ctx.client, "https://himalayas.app/jobs/api", params={"limit": "20", "offset": str(offset)})
        for j in data.get("jobs", []):
            fetched += 1
            item = job_item(company=j.get("companyName", ""), title=j.get("title", ""), description=html_to_text(j.get("description") or j.get("excerpt", "")),
                            url=j.get("applicationLink") or j.get("guid", ""), posted=j.get("pubDate"), location=", ".join(j.get("locationRestrictions") or []), board="himalayas")
            if item:
                items.append(item)
    return SyncResult(items=_finish(items, since, ctx.max_items), fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat()})


async def sync_themuse(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=7)
    items, fetched = [], 0
    params: dict[str, Any] = {"page": "0", "descending": "true", "category": ["Data and Analytics", "Software Engineering", "IT"]}
    if ctx.keys.get("themuse_key"):
        params["api_key"] = ctx.keys["themuse_key"]
    for page in range(3):
        params["page"] = str(page)
        data = await get_json(ctx.client, "https://www.themuse.com/api/public/jobs", params=params)
        for j in data.get("results", []):
            fetched += 1
            location = ", ".join(l.get("name", "") for l in j.get("locations", []))
            item = job_item(company=(j.get("company") or {}).get("name", ""), title=j.get("name", ""), description=html_to_text(j.get("contents", "")),
                            url=(j.get("refs") or {}).get("landing_page", ""), posted=j.get("publication_date"), location=location,
                            board="themuse", country=country_from_location(location, ctx.countries))
            if item:
                items.append(item)
    return SyncResult(items=_finish(items, since, ctx.max_items), fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat()})


async def sync_wwr(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=7)
    feed = feedparser.parse(await get_text(ctx.client, "https://weworkremotely.com/remote-jobs.rss"))
    items = []
    for e in feed.entries:
        # WWR titles are "Company: Role"
        company, _, role = (e.get("title") or "").partition(":")
        item = job_item(company=company, title=role.strip() or e.get("title", ""), description=html_to_text(e.get("summary", "")),
                        url=e.get("link", ""), posted=e.get("published"), location=e.get("region", "Remote"), board="weworkremotely")
        if item:
            items.append(item)
    return SyncResult(items=_finish(items, since, ctx.max_items), fetched=len(feed.entries), cursor={"since": datetime.now(timezone.utc).isoformat()})
