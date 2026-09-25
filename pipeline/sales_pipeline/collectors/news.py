"""News collection: GDELT DOC API (primary, free), NewsAPI (supplement) and
Google News RSS (GIG-20)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
import httpx

from ..documents import Document, clean_text, dedupe
from ..schemas import CompanyInfo

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
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


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


async def fetch_gdelt(client: httpx.AsyncClient, company: CompanyInfo, keywords: list[str], max_records: int = 50) -> list[Document]:
    kw = " OR ".join(f'"{k}"' if " " in k else k for k in keywords)
    params = {
        "query": f'"{company.name}" ({kw})',
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max_records),
        "timespan": "6months",
        "sort": "datedesc",
    }
    resp = await client.get(GDELT_URL, params=params)
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
        "q": f'"{company.name}" AND ({kw})',
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
    query = f'"{company.name}" ' + " OR ".join(keywords[:6])
    resp = await client.get(GOOGLE_NEWS_RSS.format(q=quote_plus(query)))
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
                meta={"provider": "google_news_rss"},
            )
        )
    return docs


async def collect_news(
    company: CompanyInfo,
    *,
    newsapi_key: str | None = None,
    keywords: list[str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[Document]:
    """Collect and deduplicate news for one company from every configured provider.

    A failing provider is logged and skipped so one outage never empties a run.
    """
    keywords = keywords or DEFAULT_KEYWORDS
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": "OrangeSignals/0.1"})
    try:
        jobs = [("gdelt", fetch_gdelt(client, company, keywords)), ("google_news", fetch_google_news(client, company, keywords))]
        if newsapi_key:
            jobs.append(("newsapi", fetch_newsapi(client, company, keywords, newsapi_key)))
        docs: list[Document] = []
        for name, job in jobs:
            try:
                docs.extend(await job)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                log.warning("news provider %s failed for %s: %s", name, company.name, exc)
        # Keep only articles that actually mention the company.
        needle = company.name.lower().split(" group")[0]
        docs = [d for d in docs if needle in (d.title + " " + d.text).lower()]
        docs.sort(key=lambda d: d.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return dedupe(docs)
    finally:
        if own_client:
            await client.aclose()
