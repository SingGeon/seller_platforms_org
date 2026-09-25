"""News and press-release feeds for discovery (what just happened, and to whom)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import feedparser

from ..collectors.news import GOOGLE_EDITIONS as NEWS_EDITIONS
from ..documents import Document, clean_text, dedupe
from .base import DiscoveredItem, SourceContext, SyncResult, cursor_since, get_json, get_text, parse_dt
from .companies import company_from_headline
from .jobboards import html_to_text

# Google News edition per market: (hl, gl, ceid)
GOOGLE_EDITIONS = {
    **NEWS_EDITIONS,
    "CH": ("de", "CH", "CH:de"), "SE": ("sv", "SE", "SE:sv"), "DK": ("da", "DK", "DK:da"), "BE": ("fr", "BE", "BE:fr"),
}
DEFAULT_TOPIC_QUERIES = {
    "apa": ['"digital transformation"', '"process automation"', '"shared services"', '"cost reduction" program', '"appoints" "chief digital officer"'],
    "cyber": ["ransomware attack", '"data breach"', '"cyber attack"', "NIS2", '"appoints" CISO'],
}


def google_news_url(query: str, country: str | None, window: str = "1d") -> str:
    hl, gl, ceid = GOOGLE_EDITIONS.get(country or "US", GOOGLE_EDITIONS["US"])
    return f"https://news.google.com/rss/search?q={quote_plus(f'{query} when:{window}')}&hl={hl}&gl={gl}&ceid={ceid}"


def signal_from_text(text: str) -> str:
    t = text.lower()
    if re.search(r"ransomware|breach|cyber ?attack|hack|outage|leak", t):
        return "news:security_incident"
    if re.search(r"appoint|names .* (chief|head)|new (ceo|cio|cto|ciso|coo|cdo)|joins as", t):
        return "news:leadership_change"
    if re.search(r"nis ?2|dora|gdpr|fine|regulat", t):
        return "news:compliance"
    if re.search(r"acquire|merger|funding|raises|investment|expan", t):
        return "news:corporate_event"
    if re.search(r"automat|digital transformation|\bai\b|artificial intelligence|efficien|cost", t):
        return "news:transformation"
    return "news:other"


def entry_document(entry: Any, provider: str, source_name: str) -> Document:
    title = clean_text(entry.get("title", ""))
    summary = html_to_text(entry.get("summary", ""))
    publisher = (entry.get("source") or {}).get("title") if isinstance(entry.get("source"), dict) else None
    return Document(
        source_type="news", url=entry.get("link", ""), title=title, text=clean_text(f"{title}. {summary}"),
        published_at=parse_dt(entry.get("published") or entry.get("updated")), source=publisher or source_name,
        meta={"provider": provider},
    )


def items_from_feed(feed: Any, *, provider: str, source_name: str, since: datetime, company_field: str | None = None) -> tuple[list[DiscoveredItem], list[Document]]:
    items, unresolved = [], []
    for e in feed.entries:
        doc = entry_document(e, provider, source_name)
        if not doc.url or (doc.published_at and doc.published_at < since):
            continue
        company = None
        if company_field == "contributor":  # feedparser exposes dc:contributor as a list of {name}
            company = ((e.get("contributors") or [{}])[0] or {}).get("name") or e.get("author")
        elif company_field:
            company = e.get(company_field)
        company = company or company_from_headline(doc.title)
        if company:
            items.append(DiscoveredItem(company_name=clean_text(company), signal=signal_from_text(doc.text), document=doc))
        else:
            unresolved.append(doc)
    return items, unresolved


async def sync_google_news_topics(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=2)
    window = "1h" if (datetime.now(timezone.utc) - since).total_seconds() < 3600 else "1d"
    queries = [q for qs in DEFAULT_TOPIC_QUERIES.values() for q in qs]
    queries += [f'"{k}"' for k in ctx.all_keywords()[:6]]
    items, unresolved, fetched = [], [], 0
    for country in (ctx.countries or ["US"])[:4]:
        for q in dict.fromkeys(queries):
            feed = feedparser.parse(await get_text(ctx.client, google_news_url(q, country, window)))
            fetched += len(feed.entries)
            its, unres = items_from_feed(feed, provider="google_news_topics", source_name="Google News", since=since)
            for i in its:
                i.company_country = i.company_country or country
            items += its
            unresolved += unres
    return SyncResult(items=items[: ctx.max_items], unresolved=dedupe(unresolved)[:100], fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat()})


async def _rss_source(ctx: SourceContext, cursor: dict[str, Any], urls: list[str], provider: str, source_name: str, company_field: str | None = None) -> SyncResult:
    since = cursor_since(cursor, ctx, days=2)
    items, unresolved, fetched = [], [], 0
    for url in urls:
        feed = feedparser.parse(await get_text(ctx.client, url))
        fetched += len(feed.entries)
        its, unres = items_from_feed(feed, provider=provider, source_name=source_name, since=since, company_field=company_field)
        items += its
        unresolved += unres
    return SyncResult(items=items[: ctx.max_items], unresolved=unresolved[:100], fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat()})


PRN_FEEDS = [
    "https://www.prnewswire.com/rss/news-releases-list.rss",
    "https://www.prnewswire.com/rss/computer-electronics-latest-news/computer-electronics-latest-news-list.rss",
    "https://www.prnewswire.com/rss/financial-services-latest-news/financial-services-latest-news-list.rss",
]
GNW_FEEDS = [
    "https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/GlobeNewswire%20-%20News%20about%20Public%20Companies",
    "https://www.globenewswire.com/RssFeed/subjectcode/19-Management%20Changes/feedTitle/GlobeNewswire%20-%20Management%20Changes",
]


async def sync_prnewswire(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    return await _rss_source(ctx, cursor, PRN_FEEDS, "prnewswire", "PR Newswire")


async def sync_globenewswire(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    # GlobeNewswire tags every release with the issuing organisation (dc:contributor).
    return await _rss_source(ctx, cursor, GNW_FEEDS, "globenewswire", "GlobeNewswire", company_field="contributor")


async def sync_bing_news(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    queries = ["ransomware attack company", "appoints chief information officer", "digital transformation program"]
    urls = [f"https://www.bing.com/news/search?q={quote_plus(q)}&format=rss" for q in queries]
    return await _rss_source(ctx, cursor, urls, "bing_news", "Bing News")


async def sync_databreaches(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    return await _rss_source(ctx, cursor, ["https://databreaches.net/feed/"], "databreaches_net", "DataBreaches.net")


async def sync_newsdata(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=2)
    items, unresolved, fetched = [], [], 0
    countries = ",".join(c.lower() for c in ctx.countries[:5]) or None
    for q in ["digital transformation", "ransomware", "automation"]:
        params = {"apikey": ctx.keys["newsdata_key"], "q": q}
        if countries:
            params["country"] = countries
        data = await get_json(ctx.client, "https://newsdata.io/api/1/latest", params=params)
        for a in data.get("results", []) or []:
            fetched += 1
            doc = Document(source_type="news", url=a.get("link", ""), title=clean_text(a.get("title", "")),
                           text=clean_text(f"{a.get('title', '')}. {a.get('description') or ''}"), published_at=parse_dt(a.get("pubDate")),
                           source=a.get("source_id", "newsdata"), meta={"provider": "newsdata"})
            if not doc.url or (doc.published_at and doc.published_at < since):
                continue
            company = company_from_headline(doc.title)
            country = ((a.get("country") or [None])[0] or "")
            if company:
                items.append(DiscoveredItem(company_name=company, company_country=_country_code(country), signal=signal_from_text(doc.text), document=doc))
            else:
                unresolved.append(doc)
    return SyncResult(items=items, unresolved=unresolved[:100], fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat()})


async def sync_currents(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=2)
    items, unresolved, fetched = [], [], 0
    for q in ["digital transformation", "ransomware", "automation"]:
        data = await get_json(ctx.client, "https://api.currentsapi.services/v1/search",
                              params={"apiKey": ctx.keys["currents_key"], "keywords": q, "language": "en", "start_date": since.strftime("%Y-%m-%dT%H:%M:%SZ")})
        for a in data.get("news", []):
            fetched += 1
            doc = Document(source_type="news", url=a.get("url", ""), title=clean_text(a.get("title", "")),
                           text=clean_text(f"{a.get('title', '')}. {a.get('description', '')}"), published_at=parse_dt(a.get("published")),
                           source="Currents", meta={"provider": "currents"})
            company = company_from_headline(doc.title)
            if company:
                items.append(DiscoveredItem(company_name=company, signal=signal_from_text(doc.text), document=doc))
            elif doc.url:
                unresolved.append(doc)
    return SyncResult(items=items, unresolved=unresolved[:100], fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat()})


COUNTRY_NAMES = {"romania": "RO", "moldova": "MD", "germany": "DE", "austria": "AT", "united kingdom": "GB", "france": "FR", "netherlands": "NL", "poland": "PL", "italy": "IT", "spain": "ES", "united states of america": "US", "united states": "US"}


def _country_code(value: str) -> str | None:
    v = (value or "").strip().lower()
    return COUNTRY_NAMES.get(v) or (v.upper() if len(v) == 2 else None)
