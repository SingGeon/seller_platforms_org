"""SEC EDGAR (US-listed companies): mandatory disclosures are the most reliable 'why now'.

- 8-K Item 1.05: material cybersecurity incident (must be filed within 4 business days)
- 8-K Item 5.02: departure / appointment of directors and officers (new CIO/CISO = new budget)
- Form D: new private funding rounds (partial Crunchbase replacement)
- Full-text search in 10-K reports for automation / cost-reduction language (enrichment)

SEC requires a User-Agent with a contact email (SEC_USER_AGENT); max 10 requests/s.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser

from ..documents import Document, clean_text
from .base import DiscoveredItem, SourceContext, SyncResult, cursor_since, get_json, get_text, parse_dt
from .companies import clean_display_name

EFTS = "https://efts.sec.gov/LATEST/search-index"
ITEM_LABELS = {
    "1.05": ("cyber:material_incident", "disclosed a material cybersecurity incident (Form 8-K Item 1.05)"),
    "5.02": ("leadership_change", "reported a change of directors or officers (Form 8-K Item 5.02)"),
}
US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())


def _headers(ctx: SourceContext) -> dict[str, str]:
    return {"User-Agent": ctx.sec_user_agent or "", "Accept-Encoding": "gzip, deflate"}


def filing_url(cik: str, adsh: str, doc_id: str) -> str:
    filename = doc_id.split(":", 1)[1] if ":" in doc_id else ""
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}"
    return f"{base}/{filename}" if filename else f"{base}/"


async def efts_search(ctx: SourceContext, q: str, *, forms: str, since: datetime, until: datetime | None = None, page_from: int = 0) -> list[dict]:
    params = {"q": q, "forms": forms, "dateRange": "custom", "startdt": since.date().isoformat(),
              "enddt": (until or datetime.now(timezone.utc)).date().isoformat(), "from": str(page_from)}
    data = await get_json(ctx.client, EFTS, params=params, headers=_headers(ctx))
    return (data.get("hits") or {}).get("hits", [])


async def _sync_8k_item(ctx: SourceContext, cursor: dict[str, Any], item: str) -> SyncResult:
    since = cursor_since(cursor, ctx, days=30)
    signal, phrase = ITEM_LABELS[item]
    seen = set(cursor.get("seen", []))
    items: list[DiscoveredItem] = []
    fetched = 0
    for page in range(0, 500, 100):
        hits = await efts_search(ctx, f'"Item {item}"', forms="8-K", since=since, page_from=page)
        fetched += len(hits)
        for h in hits:
            src = h.get("_source", {})
            if item not in (src.get("items") or []):
                continue  # the phrase can appear in a filing that doesn't report this item
            adsh = src.get("adsh") or h.get("_id", "").split(":")[0]
            if adsh in seen:
                continue
            seen.add(adsh)
            name = clean_display_name((src.get("display_names") or [""])[0])
            cik = (src.get("ciks") or ["0"])[0]
            if not name:
                continue
            filed = parse_dt(src.get("file_date"))
            state = (src.get("biz_states") or src.get("inc_states") or [None])[0]
            items.append(
                DiscoveredItem(
                    company_name=name, company_country="US" if state in US_STATES else None, signal=signal,
                    document=Document(
                        source_type="news", url=filing_url(cik, adsh, h.get("_id", "")), title=f"{name} {phrase}",
                        text=f"{name} {phrase}, filed on {src.get('file_date')}. Items reported: {', '.join(src.get('items') or [])}.",
                        published_at=filed, source="SEC EDGAR", meta={"provider": "sec_8k", "item": item, "cik": cik, "adsh": adsh, "kind": "filing"},
                    ),
                )
            )
        if len(hits) < 100:
            break
    return SyncResult(items=items[: ctx.max_items], fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat(), "seen": sorted(seen)[-5000:]})


async def sync_sec_8k_cyber(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    return await _sync_8k_item(ctx, cursor, "1.05")


async def sync_sec_8k_leadership(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    return await _sync_8k_item(ctx, cursor, "5.02")


FORM_D_FEED = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=D&company=&dateb=&owner=include&count=100&output=atom"
_FEED_TITLE = re.compile(r"^(?P<form>[\w/-]+) - (?P<name>.+?) \((?P<cik>\d+)\) \((?P<role>[^)]+)\)")


async def sync_sec_form_d(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=3)
    feed = feedparser.parse(await get_text(ctx.client, FORM_D_FEED, headers=_headers(ctx)))
    items = []
    for e in feed.entries:
        m = _FEED_TITLE.match(e.get("title", ""))
        updated = parse_dt(e.get("updated"))
        if not m or m.group("role") != "Filer" or (updated and updated < since):
            continue
        name = clean_display_name(m.group("name"))
        items.append(
            DiscoveredItem(
                company_name=name, company_country="US", signal="corporate:funding",
                document=Document(source_type="news", url=e.get("link", ""), title=f"{name} filed Form D (new securities offering)",
                                  text=f"{name} filed a Form {m.group('form')} notice of an exempt securities offering (private funding round) on {updated.date() if updated else 'n/a'}.",
                                  published_at=updated, source="SEC EDGAR", meta={"provider": "sec_form_d", "cik": m.group("cik"), "kind": "filing"}),
            )
        )
    return SyncResult(items=items, fetched=len(feed.entries), cursor={"since": datetime.now(timezone.utc).isoformat()})


# ------------------------------------------------------------------ enrichment: 10-K language
ANNUAL_REPORT_PHRASES = ['"robotic process automation"', '"intelligent automation"', '"cost reduction"', '"digital transformation"', '"cybersecurity incident"']


async def sec_annual_report_documents(ctx: SourceContext, company_name: str, years: int = 2) -> list[Document]:
    """Passages from the company's own 10-K filings mentioning automation / cost / cyber themes."""
    since = datetime.now(timezone.utc) - timedelta(days=365 * years)
    docs = []
    for phrase in ANNUAL_REPORT_PHRASES:
        hits = await efts_search(ctx, f'{phrase} "{company_name}"', forms="10-K", since=since)
        for h in hits[:3]:
            src = h.get("_source", {})
            name = clean_display_name((src.get("display_names") or [""])[0])
            if company_name.lower().split()[0] not in name.lower():
                continue
            adsh = src.get("adsh", "")
            docs.append(
                Document(
                    source_type="web", url=filing_url((src.get("ciks") or ["0"])[0], adsh, h.get("_id", "")),
                    title=f"{name} annual report (10-K, {src.get('period_ending') or src.get('file_date')}) mentions {phrase}",
                    text=clean_text(f"{name}'s annual report on Form 10-K filed {src.get('file_date')} mentions {phrase}."),
                    published_at=parse_dt(src.get("file_date")), source="SEC EDGAR",
                    meta={"provider": "sec_10k", "phrase": phrase.strip('"'), "adsh": adsh, "kind": "annual_report"},
                )
            )
    return docs
