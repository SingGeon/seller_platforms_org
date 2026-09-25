"""Business-press RSS feeds of the target markets (RO, MD).

One request per outlet returns its latest articles for every company at once, so a bulk run covers
1,000 companies with a few dozen requests instead of one search per company, and is not throttled
like Google News. Articles are matched to companies by name:

- the name as the press writes it (legal form dropped, accents and punctuation ignored) must appear
  as whole words, and
- a one-word name (e.g. "Digi", "Catena") must also appear capitalised exactly like that in the
  original text and be at least 4 characters long, so ordinary words do not create false matches;
- one-word names that are also first names or everyday words (AMBIGUOUS, e.g. "Roman") are skipped here:
  the press uses them for people and places far more often than for the company.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from ..documents import Document, clean_text
from .base import polite_request
from .companies import _plain, search_name

log = logging.getLogger(__name__)

# One-word company names that the press mostly uses for people or places (normalised, lower case).
AMBIGUOUS = frozenset("""
roman victoria maria elena ana ion ioana mihai andrei alexandru alexandra cristian cristina daniel daniela
elisabeta ecaterina florin gabriel george stefan petru pavel adrian marius sergiu victor vlad nicolae
delta alfa beta gama omega nova star europa romania moldova carpati unirea prima lux sigma atlas titan
orizont progres viitorul speranta aurora
""".split())


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    countries: tuple[str, ...]
    paged: bool = False  # WordPress feeds accept ?paged=N for older articles


# Checked on 2026-09-26: every feed answered 200 with 10-25 current articles.
LOCAL_FEEDS: tuple[Feed, ...] = (
    Feed("Ziarul Financiar", "https://www.zf.ro/rss", ("RO",)),
    Feed("Economica.net", "https://www.economica.net/rss", ("RO",)),
    Feed("Profit.ro", "https://www.profit.ro/rss", ("RO",)),
    Feed("StartupCafe", "https://www.startupcafe.ro/rss", ("RO",)),
    Feed("HotNews", "https://hotnews.ro/feed", ("RO",), paged=True),
    Feed("G4Media", "https://www.g4media.ro/feed", ("RO",), paged=True),
    Feed("Biziday", "https://www.biziday.ro/feed/", ("RO",), paged=True),
    Feed("NewsMaker", "https://newsmaker.md/ro/feed/", ("MD",), paged=True),
    Feed("Ziarul de Gardă", "https://www.zdg.md/feed/", ("MD",), paged=True),
    Feed("Bani.md", "https://bani.md/rss", ("MD",)),
    Feed("Diez", "https://diez.md/feed/", ("MD",), paged=True),
)


def _published(entry) -> datetime | None:
    raw = entry.get("published") or entry.get("updated")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


async def fetch_feed(client: httpx.AsyncClient, feed: Feed, pages: int = 1) -> list[Document]:
    docs: list[Document] = []
    for page in range(1, (pages if feed.paged else 1) + 1):
        url = feed.url if page == 1 else f"{feed.url}{'&' if '?' in feed.url else '?'}paged={page}"
        resp = await polite_request(client, "GET", url, retries=2)
        if resp.status_code == 404 and page > 1:
            break  # no older page
        resp.raise_for_status()
        entries = feedparser.parse(resp.text).entries
        for e in entries:
            if not e.get("link"):
                continue
            title = clean_text(e.get("title", ""))
            body = e.get("content", [{}])[0].get("value") if e.get("content") else e.get("summary", "")
            docs.append(
                Document(
                    source_type="news", url=e.link, title=title, text=clean_text(f"{title}. {body}"),
                    published_at=_published(e), source=feed.name, meta={"provider": "local_rss", "outlet": feed.name},
                )
            )
        if not entries:
            break
    return docs


async def fetch_local_feeds(client: httpx.AsyncClient, countries: list[str] | None = None, pages: int = 3) -> tuple[list[Document], dict[str, str]]:
    """Latest articles of every outlet covering `countries` (all outlets when None); failures are reported, not raised."""
    feeds = [f for f in LOCAL_FEEDS if not countries or set(f.countries) & set(countries)]
    results = await asyncio.gather(*(fetch_feed(client, f, pages) for f in feeds), return_exceptions=True)
    docs: dict[str, Document] = {}
    errors: dict[str, str] = {}
    for feed, res in zip(feeds, results):
        if isinstance(res, BaseException):
            errors[feed.name] = f"{type(res).__name__}: {res}"[:200]
            log.warning("local feed %s failed: %s", feed.name, res)
            continue
        for d in res:
            docs.setdefault(d.url, d)
    return list(docs.values()), errors


class CompanyMatcher:
    """Finds which companies an article names (see the module docstring for the rules)."""

    def __init__(self, companies: list[tuple[int, str]]) -> None:
        self._needles: list[tuple[int, str, re.Pattern | None]] = []
        for cid, name in companies:
            display = search_name(name)
            needle = _plain(display).strip()
            if not needle:
                continue
            exact = None
            if " " not in needle:
                if len(needle) < 4 or needle in AMBIGUOUS:
                    continue
                exact = re.compile(rf"(?<!\w){re.escape(display)}(?!\w)")
            self._needles.append((cid, f" {needle} ", exact))

    def match(self, doc: Document) -> list[int]:
        raw = f"{doc.title} {doc.text}"
        plain = _plain(raw)
        return [cid for cid, needle, exact in self._needles if needle in plain and (exact is None or exact.search(raw))]

    def assign(self, docs: list[Document]) -> dict[int, list[Document]]:
        out: dict[int, list[Document]] = {}
        for d in docs:
            for cid in self.match(d):
                out.setdefault(cid, []).append(d)
        return out
