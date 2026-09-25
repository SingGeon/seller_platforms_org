"""Source framework (GIG-14 / GIG-23).

A *source* is one public API or feed. Every source declares its limits and
fallback (the GIG-14 catalogue is generated from these declarations), keeps a
cursor so each sync only fetches what is new, and is rate limited per host.

Two modes:
- discovery  (signal -> company): the source returns signals that name a company;
  each item carries the company it is about so the backend can create the lead.
- enrichment (company -> signals): the source is queried for one known company.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from ..documents import Document

log = logging.getLogger(__name__)

Mode = Literal["discovery", "enrichment"]
Refresh = Literal["stream", "feed", "incremental", "snapshot", "daily"]
Category = Literal["jobs", "news", "tenders", "cyber", "corporate", "registry"]

DEFAULT_UA = "OrangeSignals/0.1 (B2B sales research)"


class DiscoveredItem(BaseModel):
    """A signal that names a company. `document` is stored as a raw document of that company."""

    company_name: str
    company_domain: str | None = None
    company_country: str | None = None  # ISO-2
    company_industry: str | None = None
    document: Document
    signal: str = ""  # short machine tag, e.g. "it_tender", "ransomware_victim", "hiring:RPA"


class SyncResult(BaseModel):
    items: list[DiscoveredItem] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)  # enrichment output
    # Discovery documents whose company could not be parsed; the backend may ask the LLM.
    unresolved: list[Document] = Field(default_factory=list)
    cursor: dict[str, Any] = Field(default_factory=dict)
    fetched: int = 0  # raw records looked at, before filtering
    notes: list[str] = Field(default_factory=list)


@dataclass
class SourceContext:
    """Everything a source needs for one sync; built by the backend from settings + config."""

    client: httpx.AsyncClient
    keys: dict[str, str] = field(default_factory=dict)
    countries: list[str] = field(default_factory=list)  # ISO-2 target markets from the ICP
    keywords: dict[str, list[str]] = field(default_factory=dict)  # service slug -> discovery keywords
    since: datetime | None = None  # used when the cursor is empty
    max_items: int = 200
    sec_user_agent: str | None = None

    def all_keywords(self) -> list[str]:
        seen: dict[str, None] = {}
        for kws in self.keywords.values():
            for k in kws:
                seen.setdefault(k, None)
        return list(seen)

    def default_since(self, days: int = 7) -> datetime:
        return self.since or (datetime.now(timezone.utc) - timedelta(days=days))


SyncFn = Callable[[SourceContext, dict[str, Any]], Awaitable[SyncResult]]


@dataclass
class SourceSpec:
    name: str
    label: str
    mode: Mode
    category: Category
    refresh: Refresh
    interval_minutes: int
    services: list[str]  # which Orange Systems services the signal serves ("apa", "cyber", "all")
    limits: str
    fallback: str
    requires: list[str] = field(default_factory=list)  # setting names that must be non-empty
    coverage: str = "global"
    sync: SyncFn | None = None
    notes: str = ""

    def missing_keys(self, keys: dict[str, str]) -> list[str]:
        return [k for k in self.requires if not keys.get(k)]


# ---------------------------------------------------------------- polite HTTP


class HostThrottle:
    """Minimum interval between requests to the same host, shared process-wide.

    GDELT, for example, answers 429 unless requests are >= 5 s apart."""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.min_interval: dict[str, float] = {
            "api.gdeltproject.org": 6.0,
            "efts.sec.gov": 0.2,  # SEC fair-access: max 10 req/s
            "www.sec.gov": 0.2,
            "public.mtender.gov.md": 1.0,
            "query.wikidata.org": 1.0,
            "api.ted.europa.eu": 0.5,
            "news.google.com": 0.3,  # bulk runs query it once per company
            "api.gleif.org": 1.0,  # 60 requests / minute
        }

    async def wait(self, host: str) -> None:
        interval = self.min_interval.get(host, 0.0)
        if interval <= 0:
            return
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            delta = time.monotonic() - self._last.get(host, 0.0)
            if delta < interval:
                await asyncio.sleep(interval - delta)
            self._last[host] = time.monotonic()


THROTTLE = HostThrottle()
RETRY_BASE_DELAY = 5.0  # seconds; doubled per attempt (tests set it to 0)


async def polite_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 3,
    base_delay: float | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Throttled request with exponential backoff on 429 / 5xx (honours Retry-After)."""
    host = urlparse(url).netloc
    base_delay = RETRY_BASE_DELAY if base_delay is None else base_delay
    for attempt in range(retries + 1):
        await THROTTLE.wait(host)
        resp = await client.request(method, url, **kwargs)
        if resp.status_code not in (429, 500, 502, 503, 504) or attempt == retries:
            return resp
        retry_after = resp.headers.get("retry-after")
        delay = float(retry_after) if retry_after and retry_after.isdigit() else base_delay * 2**attempt
        delay = min(delay, 60.0) + (random.uniform(0, 1) if base_delay else 0)
        log.info("%s %s -> %s, retrying in %.1fs", method, host, resp.status_code, delay)
        await asyncio.sleep(delay)
    return resp  # pragma: no cover


async def get_json(client: httpx.AsyncClient, url: str, **kwargs: Any) -> Any:
    resp = await polite_request(client, "GET", url, **kwargs)
    resp.raise_for_status()
    return resp.json()


async def get_text(client: httpx.AsyncClient, url: str, **kwargs: Any) -> str:
    resp = await polite_request(client, "GET", url, **kwargs)
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------- helpers


def parse_dt(value: Any) -> datetime | None:
    """Parse the many date formats public APIs use; always returns an aware datetime."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 10**11 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    s = str(value).strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(s)
        except (TypeError, ValueError):
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def first_text(value: Any, prefer: tuple[str, ...] = ("eng", "ENG", "en", "EN", "ron", "RON")) -> str:
    """Flatten multilingual / list-valued API fields (TED, OCDS) to one string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        for v in value:
            t = first_text(v, prefer)
            if t:
                return t
        return ""
    if isinstance(value, dict):
        for k in prefer:
            if k in value:
                t = first_text(value[k], prefer)
                if t:
                    return t
        for v in value.values():
            t = first_text(v, prefer)
            if t:
                return t
    return ""


def cursor_since(cursor: dict[str, Any], ctx: SourceContext, days: int = 7, key: str = "since") -> datetime:
    return parse_dt(cursor.get(key)) or ctx.default_since(days)


def keyword_hit(text: str, keywords: list[str]) -> list[str]:
    t = text.lower()
    return [k for k in keywords if k.lower() in t]
