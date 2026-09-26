"""News collection per company (GIG-20): Google News RSS and Bing News RSS (free, no key, local-language
editions), GDELT DOC API (free, 1 request / 5 s) and NewsAPI (key). Bulk runs also use the business-press
feeds in sources/localnews.py, which cover every company with one request per outlet."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, quote_plus, urlparse

import feedparser
import httpx

from ..documents import Document, clean_text, dedupe
from ..schemas import CompanyInfo
from ..sources.base import polite_request
from ..newstopics import GDELT_TOPIC_TERMS, topic_queries
from ..sources.companies import mentions_strictly, search_name

# (hl, gl, ceid) per market; kept here to avoid importing the discovery feeds module.
GOOGLE_EDITIONS = {
    "RO": ("ro", "RO", "RO:ro"), "MD": ("ro", "MD", "MD:ro"), "DE": ("de", "DE", "DE:de"), "AT": ("de", "AT", "AT:de"),
    "FR": ("fr", "FR", "FR:fr"), "NL": ("nl", "NL", "NL:nl"), "PL": ("pl", "PL", "PL:pl"), "IT": ("it", "IT", "IT:it"),
    "ES": ("es", "ES", "ES:es"), "GB": ("en-GB", "GB", "GB:en"), "US": ("en-US", "US", "US:en"),
}

# Bing News market per company country: (setlang, cc). MD has no own edition; the Romanian one covers it.
BING_MARKETS = {
    "RO": ("ro", "RO"), "MD": ("ro", "RO"), "DE": ("de", "DE"), "AT": ("de", "AT"), "FR": ("fr", "FR"), "NL": ("nl", "NL"),
    "PL": ("pl", "PL"), "IT": ("it", "IT"), "ES": ("es", "ES"), "GB": ("en", "GB"), "US": ("en", "US"),
}

log = logging.getLogger(__name__)

DEFAULT_KEYWORDS = [
    "automation",
    "efficiency",
    "digital transformation",
    "AI",
    "breach",
    "cyberattack",
    "CEO",
    "CIO",
    "acquisition",
    "restructuring",
]

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
NEWSAPI_URL = "https://newsapi.org/v2/everything"


def _gdelt_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def fetch_gdelt(client: httpx.AsyncClient, company: CompanyInfo, keywords: list[str], max_records: int = 50,
                      timespan: str = "6months") -> list[Document]:
    kw = " OR ".join(f'"{k}"' if " " in k else k for k in keywords)
    params = {
        "query": f'"{search_name(company.name)}" ({kw})',
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max_records),
        "timespan": timespan,
        "sort": "datedesc",
    }
    # GDELT enforces ~1 request / 5 s and answers 429 otherwise: shared throttle + backoff.
    resp = await polite_request(client, "GET", GDELT_URL, params=params, retries=2)
    resp.raise_for_status()
    try:
        articles = resp.json().get("articles", [])
    except ValueError:  # GDELT answers plain text on malformed queries
        log.warning("GDELT returned non-JSON for %s: %s", company.name, resp.text[:200])
        return []
    return [
        Document(
            source_type="news",
            url=a["url"],
            title=clean_text(a.get("title", "")),
            text=clean_text(a.get("title", "")),
            published_at=_gdelt_date(a.get("seendate")),
            source=a.get("domain", "gdelt"),
            meta={"provider": "gdelt", "language": a.get("language")},
        )
        for a in articles
        if a.get("url")
    ]


async def fetch_newsapi(client: httpx.AsyncClient, company: CompanyInfo, keywords: list[str], api_key: str) -> list[Document]:
    kw = " OR ".join(f'"{k}"' for k in keywords)
    params = {
        "q": f'"{search_name(company.name)}" AND ({kw})',
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": "50",
        "apiKey": api_key,
    }
    resp = await client.get(NEWSAPI_URL, params=params)
    resp.raise_for_status()
    docs = []
    for a in resp.json().get("articles", []):
        if not a.get("url"):
            continue
        text = " ".join(filter(None, [a.get("title"), a.get("description"), a.get("content")]))
        docs.append(
            Document(
                source_type="news",
                url=a["url"],
                title=clean_text(a.get("title") or ""),
                text=clean_text(text),
                published_at=_iso_date(a.get("publishedAt")),
                source=(a.get("source") or {}).get("name", "newsapi"),
                meta={"provider": "newsapi"},
            )
        )
    return docs


async def fetch_google_news(client: httpx.AsyncClient, company: CompanyInfo, keywords: list[str]) -> list[Document]:
    query = f'"{search_name(company.name)}" ' + " OR ".join(keywords[:6])
    return await _google_news_query(client, company, query, "google_news_rss")


async def fetch_google_news_topics(client: httpx.AsyncClient, company: CompanyInfo) -> list[Document]:
    """Google News searches for the company together with each theme of newstopics.TOPIC_QUERIES (cost cutting,
    digitalisation, AI / RPA, appointments, hiring, security incidents, ...), in the company's language."""
    docs: list[Document] = []
    for group in topic_queries(company.country):
        docs += await _google_news_query(client, company, f'"{search_name(company.name)}" {group}', "google_news_topics")
    return docs


async def _google_news_query(client: httpx.AsyncClient, company: CompanyInfo, query: str, provider: str) -> list[Document]:
    # Local-language edition for the company's market (gl/hl), e.g. RO/MD news in Romanian.
    hl, gl, ceid = GOOGLE_EDITIONS.get(company.country or "US", GOOGLE_EDITIONS["US"])
    resp = await polite_request(client, "GET", f"https://news.google.com/rss/search?q={quote_plus(query)}&hl={hl}&gl={gl}&ceid={ceid}", retries=2)
    resp.raise_for_status()
    feed = feedparser.parse(resp.text)
    docs = []
    for entry in feed.entries:
        published = None
        if entry.get("published"):
            try:
                published = parsedate_to_datetime(entry.published)
            except (TypeError, ValueError):
                published = None
        summary = clean_text(entry.get("summary", ""))
        docs.append(
            Document(
                source_type="news",
                url=entry.link,
                title=clean_text(entry.get("title", "")),
                text=clean_text(f"{entry.get('title', '')}. {summary}"),
                published_at=published,
                source=(entry.get("source") or {}).get("title", "google-news"),
                meta={"provider": provider},
            )
        )
    return docs


def _bing_target(link: str) -> str:
    """Bing wraps every article in apiclick.aspx?...&url=<real url>; keep the publisher's URL."""
    target = parse_qs(urlparse(link).query).get("url", [""])[0]
    return target or link


async def fetch_bing_news(client: httpx.AsyncClient, company: CompanyInfo, keywords: list[str] | None = None) -> list[Document]:
    """Latest articles naming the company, from Bing News in the company's market (no key, ~12 items)."""
    setlang, cc = BING_MARKETS.get(company.country or "US", BING_MARKETS["US"])
    query = quote_plus(f'"{search_name(company.name)}"')
    resp = await polite_request(client, "GET", f"https://www.bing.com/news/search?q={query}&format=rss&setlang={setlang}&cc={cc}", retries=2)
    resp.raise_for_status()
    docs = []
    for entry in feedparser.parse(resp.text).entries:
        if not entry.get("link"):
            continue
        published = None
        if entry.get("published"):
            try:
                published = parsedate_to_datetime(entry.published)
            except (TypeError, ValueError):
                published = None
        title = clean_text(entry.get("title", ""))
        docs.append(
            Document(
                source_type="news",
                url=_bing_target(entry.link),
                title=title,
                text=clean_text(f"{title}. {entry.get('summary', '')}"),
                published_at=published,
                source=entry.get("news_source") or "bing-news",
                meta={"provider": "bing_news_rss"},
            )
        )
    return docs


async def collect_news(
    company: CompanyInfo,
    *,
    newsapi_key: str | None = None,
    keywords: list[str] | None = None,
    client: httpx.AsyncClient | None = None,
    providers: tuple[str, ...] = ("gdelt", "google_news", "bing_news", "newsapi"),
) -> list[Document]:
    """Collect and deduplicate news for one company from every configured provider.

    A failing provider is logged and skipped so one outage never empties a run. Bulk runs
    over thousands of companies pass providers=("google_news", "bing_news"): GDELT allows 1 request / 5 s.
    """
    keywords = keywords or DEFAULT_KEYWORDS
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": "OrangeSignals/0.1"})
    try:
        jobs = []
        if "gdelt" in providers:
            jobs.append(("gdelt", fetch_gdelt(client, company, keywords)))
        if "gdelt_topics" in providers:
            jobs.append(("gdelt_topics", fetch_gdelt(client, company, list(GDELT_TOPIC_TERMS), timespan="3months")))
        if "google_topics" in providers:
            jobs.append(("google_topics", fetch_google_news_topics(client, company)))
        if "google_news" in providers:
            jobs.append(("google_news", fetch_google_news(client, company, keywords)))
        if "bing_news" in providers:
            jobs.append(("bing_news", fetch_bing_news(client, company, keywords)))
        if newsapi_key and "newsapi" in providers:
            jobs.append(("newsapi", fetch_newsapi(client, company, keywords, newsapi_key)))
        docs: list[Document] = []
        # Providers live on different hosts with their own throttles, so they run in parallel.
        results = await asyncio.gather(*(job for _, job in jobs), return_exceptions=True)
        for (name, _), res in zip(jobs, results):
            if isinstance(res, (httpx.HTTPError, ValueError, KeyError)):
                log.warning("news provider %s failed for %s: %s", name, company.name, res)
            elif isinstance(res, BaseException):
                raise res
            else:
                docs.extend(res)
        # Keep only articles that actually mention the company (legal form and accents optional; a one-word
        # name must be written exactly, so "energie electrică" is not news about Electrica).
        docs = [d for d in docs if mentions_strictly(company.name, d.title + " " + d.text)]
        docs.sort(key=lambda d: d.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return dedupe(docs)
    finally:
        if own_client:
            await client.aclose()
