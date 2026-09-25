"""Public procurement: organisations buying IT services right now (strongest buying signal)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..documents import Document, clean_text
from .base import DiscoveredItem, SourceContext, SyncResult, cursor_since, first_text, get_json, parse_dt, polite_request

ISO2_TO_ISO3 = {
    "AT": "AUT", "BE": "BEL", "BG": "BGR", "HR": "HRV", "CY": "CYP", "CZ": "CZE", "DK": "DNK", "EE": "EST", "FI": "FIN",
    "FR": "FRA", "DE": "DEU", "GR": "GRC", "HU": "HUN", "IE": "IRL", "IT": "ITA", "LV": "LVA", "LT": "LTU", "LU": "LUX",
    "MT": "MLT", "NL": "NLD", "PL": "POL", "PT": "PRT", "RO": "ROU", "SK": "SVK", "SI": "SVN", "ES": "ESP", "SE": "SWE",
    "GB": "GBR", "NO": "NOR", "CH": "CHE", "IS": "ISL", "MD": "MDA", "UA": "UKR", "RS": "SRB", "AL": "ALB", "MK": "MKD",
    "BA": "BIH", "ME": "MNE", "US": "USA", "CA": "CAN",
}
ISO3_TO_ISO2 = {v: k for k, v in ISO2_TO_ISO3.items()}

# CPV 72* = IT services, 48* = software packages, 79411* = management consulting (process optimisation).
IT_CPV_PREFIXES = ("72", "48", "30211", "30213", "32420", "79411")
TED_CPV_CODES = [
    "72000000", "72100000", "72200000", "72210000", "72212000", "72220000", "72221000", "72222000", "72222300",
    "72230000", "72240000", "72250000", "72260000", "72262000", "72263000", "72266000", "72267000", "72300000",
    "72310000", "72312000", "72315000", "72316000", "72320000", "72400000", "72500000", "72510000", "72590000",
    "72600000", "72610000", "72700000", "72800000", "72900000", "48000000", "48600000", "48700000", "48800000",
    "48900000", "48730000", "48760000", "48761000",
]


def is_it_cpv(code: str | None) -> bool:
    return bool(code) and str(code).replace("-", "").startswith(IT_CPV_PREFIXES)


def tender_signal(text: str) -> str:
    t = text.lower()
    if re.search(r"secur|cyber|soc\b|siem|penetration|nis2|firewall|antivirus|backup", t):
        return "it_tender:cyber"
    if re.search(r"automat|rpa|robotic process|workflow|process mining|artificial intelligence|\bai\b|chatbot", t):
        return "it_tender:automation"
    return "it_tender:it"


# ------------------------------------------------------------------ TED (EU)

TED_SEARCH = "https://api.ted.europa.eu/v3/notices/search"
TED_FIELDS = [
    "publication-number", "notice-title", "buyer-name", "buyer-country", "publication-date",
    "classification-cpv", "notice-type", "deadline-receipt-tender-date-lot", "links",
]


def ted_query(since: datetime, countries: list[str]) -> str:
    q = f"classification-cpv IN ({' '.join(TED_CPV_CODES)}) AND publication-date>={since.strftime('%Y%m%d')}"
    iso3 = [ISO2_TO_ISO3[c] for c in countries if c in ISO2_TO_ISO3]
    if iso3:
        q += f" AND buyer-country IN ({' '.join(iso3)})"
    return q


async def sync_ted(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=14)
    seen = set(cursor.get("seen", []))
    items: list[DiscoveredItem] = []
    fetched = 0
    page = 1
    while len(items) < ctx.max_items and page <= 10:
        body = {"query": ted_query(since, ctx.countries), "fields": TED_FIELDS, "page": page, "limit": 100, "scope": "ALL", "paginationMode": "PAGE_NUMBER"}
        resp = await polite_request(ctx.client, "POST", TED_SEARCH, json=body)
        resp.raise_for_status()
        data = resp.json()
        notices = data.get("notices", [])
        fetched += len(notices)
        for n in notices:
            pub = first_text(n.get("publication-number"))
            if not pub or pub in seen:
                continue
            seen.add(pub)
            buyer = first_text(n.get("buyer-name"))
            if not buyer:
                continue
            title = clean_text(first_text(n.get("notice-title")))
            country3 = first_text(n.get("buyer-country"))
            url = first_text((n.get("links") or {}).get("html")) or f"https://ted.europa.eu/en/notice/-/detail/{pub}"
            cpv = first_text(n.get("classification-cpv"))
            deadline = first_text(n.get("deadline-receipt-tender-date-lot"))
            text = f"{buyer} published a public tender on TED: {title}. CPV {cpv}." + (f" Tender deadline: {deadline}." if deadline else "")
            items.append(
                DiscoveredItem(
                    company_name=buyer,
                    company_country=ISO3_TO_ISO2.get(country3.upper()) if country3 else None,
                    company_industry="Public Sector",
                    signal=tender_signal(title),
                    document=Document(
                        source_type="news", url=url, title=f"Tender: {title}"[:300], text=text,
                        published_at=parse_dt(first_text(n.get("publication-date"))[:10]), source="TED",
                        meta={"provider": "ted", "publication_number": pub, "cpv": cpv, "kind": "tender"},
                    ),
                )
            )
        if len(notices) < 100:
            break
        page += 1
    return SyncResult(items=items, fetched=fetched, cursor={"since": datetime.now(timezone.utc).date().isoformat(), "seen": sorted(seen)[-3000:]})


# ------------------------------------------------------------------ MTender (Moldova, OCDS)

MTENDER_LIST = "https://public.mtender.gov.md/tenders/"


def _ocds_release(record: dict) -> dict:
    """Merge an MTender response into one OCDS release.

    A tender's `records` hold several stages (planning / tender / evaluation); buyer,
    parties and items can each live in a different one, so fill gaps from all of them."""
    if not isinstance(record, dict):
        return {}
    records = record.get("records") or []
    releases = [r.get("compiledRelease") or (r.get("releases") or [{}])[-1] for r in records if isinstance(r, dict)]
    if not releases:
        releases = [record.get("compiledRelease") or (record.get("releases") or [record])[-1]]
    merged: dict = {}
    for rel in releases:
        for key in ("ocid", "date", "buyer"):
            merged.setdefault(key, rel.get(key))
        merged.setdefault("parties", [])
        merged["parties"] += rel.get("parties") or []
        tender = rel.get("tender") or {}
        mt = merged.setdefault("tender", {})
        for key in ("title", "description", "value", "classification", "tenderPeriod"):
            if not mt.get(key) and tender.get(key):
                mt[key] = tender[key]
        mt.setdefault("items", [])
        mt["items"] += tender.get("items") or []
    return merged


def ocds_to_item(release: dict, *, provider: str, url: str, default_country: str | None) -> DiscoveredItem | None:
    tender = release.get("tender") or {}
    buyer = (release.get("buyer") or {}).get("name") or ""
    if not buyer:
        for party in release.get("parties", []):
            if "buyer" in (party.get("roles") or []) or "procuringEntity" in (party.get("roles") or []):
                buyer = party.get("name", "")
                break
    title = clean_text(tender.get("title") or "")
    description = clean_text(tender.get("description") or "")
    codes = [((tender.get("classification") or {}).get("id"))] + [((it.get("classification") or {}).get("id")) for it in tender.get("items", [])]
    codes = [c for c in codes if c]
    if not buyer or not (any(is_it_cpv(c) for c in codes) or re.search(r"software|informatic|IT services|sistem informa", f"{title} {description}", re.I)):
        return None
    value = tender.get("value") or {}
    amount = f" Estimated value: {value.get('amount')} {value.get('currency', '')}." if value.get("amount") else ""
    country = None
    for party in release.get("parties", []):
        country = ((party.get("address") or {}).get("countryName") or "")[:2].upper() or None
        if country:
            break
    return DiscoveredItem(
        company_name=buyer,
        company_country=default_country or country,
        company_industry="Public Sector",
        signal=tender_signal(f"{title} {description}"),
        document=Document(
            source_type="news", url=url, title=f"Tender: {title or description[:120]}"[:300],
            text=f"{buyer} is buying IT services: {title}. {description[:1500]}{amount} CPV {', '.join(codes[:5])}.",
            published_at=parse_dt(release.get("date") or (tender.get("tenderPeriod") or {}).get("startDate")),
            source=provider, meta={"provider": provider, "ocid": release.get("ocid"), "cpv": codes[:5], "kind": "tender"},
        ),
    )


async def sync_mtender(ctx: SourceContext, cursor: dict[str, Any], detail_limit: int = 60) -> SyncResult:
    offset = cursor.get("offset") or cursor_since(cursor, ctx, days=7).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = await get_json(ctx.client, MTENDER_LIST, params={"offset": offset}, timeout=40)
    entries = data.get("data", []) if isinstance(data, dict) else []
    items: list[DiscoveredItem] = []
    for entry in entries[:detail_limit]:
        ocid = entry.get("ocid") or entry.get("id")
        if not ocid:
            continue
        try:
            record = await get_json(ctx.client, f"{MTENDER_LIST}{ocid}", timeout=40)
        except Exception:  # noqa: BLE001 - one broken record must not stop the sync
            continue
        item = ocds_to_item(_ocds_release(record), provider="mtender", url=f"https://mtender.gov.md/tenders/{ocid}", default_country="MD")
        if item:
            items.append(item)
    new_offset = data.get("offset") if isinstance(data, dict) else None
    return SyncResult(items=items, fetched=len(entries), cursor={"offset": new_offset or offset})


# ------------------------------------------------------------------ UK Contracts Finder (OCDS)

UK_CF_SEARCH = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"


async def sync_uk_contracts(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=7)
    params = {"publishedFrom": since.strftime("%Y-%m-%dT%H:%M:%S"), "stages": "tender", "size": "100"}
    url: str | None = UK_CF_SEARCH
    items: list[DiscoveredItem] = []
    fetched = 0
    pages = 0
    while url and pages < 10 and len(items) < ctx.max_items:
        data = await get_json(ctx.client, url, params=params if url == UK_CF_SEARCH else None, timeout=40)
        releases = data.get("releases", [])
        fetched += len(releases)
        for rel in releases:
            ocid = rel.get("ocid", "")
            notice_id = rel.get("id", ocid)
            item = ocds_to_item(rel, provider="uk_contracts_finder", url=f"https://www.contractsfinder.service.gov.uk/Notice/{notice_id}", default_country="GB")
            if item:
                items.append(item)
        url = (data.get("links") or {}).get("next")
        pages += 1
    return SyncResult(items=items, fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat()})


# ------------------------------------------------------------------ World Bank

WB_PROC = "https://search.worldbank.org/api/v2/procnotices"
WB_COUNTRY_NAMES = {"MD": "Moldova", "RO": "Romania", "UA": "Ukraine", "RS": "Serbia", "AL": "Albania", "MK": "North Macedonia", "BA": "Bosnia and Herzegovina", "ME": "Montenegro", "GE": "Georgia", "AM": "Armenia"}


async def sync_world_bank(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=30)
    seen = set(cursor.get("seen", []))
    items: list[DiscoveredItem] = []
    fetched = 0
    queries = ["software", "information technology", "cybersecurity", "automation", "digital"]
    for q in queries:
        data = await get_json(ctx.client, WB_PROC, params={"format": "json", "qterm": q, "rows": "100", "srt": "noticedate", "order": "desc"}, timeout=40)
        notices = data.get("procnotices", [])
        fetched += len(notices)
        for n in notices:
            nid = str(n.get("id", ""))
            published = parse_dt(n.get("noticedate") or n.get("submission_date"))
            if not nid or nid in seen or (published and published < since):
                continue
            country_name = n.get("project_ctry_name") or ""
            iso2 = next((k for k, v in WB_COUNTRY_NAMES.items() if v.lower() == country_name.lower()), None)
            if ctx.countries and iso2 not in ctx.countries and country_name:
                continue
            buyer = n.get("contact_organization") or n.get("borrower") or ""
            if not buyer:
                continue
            seen.add(nid)
            desc = clean_text(n.get("bid_description") or n.get("project_name") or "")
            items.append(
                DiscoveredItem(
                    company_name=buyer, company_country=iso2, company_industry="Public Sector", signal=tender_signal(desc),
                    document=Document(
                        source_type="news", url=f"https://projects.worldbank.org/en/projects-operations/procurement-detail/{nid}",
                        title=f"World Bank-funded tender: {desc[:200]}", text=f"{buyer} ({country_name}) issued a {n.get('notice_type', 'procurement notice')}: {desc}. Project: {n.get('project_name', '')}.",
                        published_at=published, source="World Bank", meta={"provider": "world_bank", "notice_id": nid, "kind": "tender"},
                    ),
                )
            )
    return SyncResult(items=items, fetched=fetched, cursor={"since": datetime.now(timezone.utc).isoformat(), "seen": sorted(seen)[-3000:]})
