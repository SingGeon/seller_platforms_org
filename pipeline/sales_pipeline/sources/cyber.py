"""Cybersecurity discovery: organisations that were just breached or hit by ransomware,
plus CISA KEV matched against each company's detected tech stack."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..documents import Document, clean_text
from .base import DiscoveredItem, SourceContext, SyncResult, cursor_since, get_json, parse_dt
from .companies import normalize_domain
from .jobboards import html_to_text


def _country(value: Any) -> str | None:
    v = str(value or "").strip().upper()
    return v if len(v) == 2 and v.isalpha() else None


async def sync_ransomware_live(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    since = cursor_since(cursor, ctx, days=7)
    data = await get_json(ctx.client, "https://api.ransomware.live/v2/recentvictims")
    victims = data if isinstance(data, list) else data.get("victims", [])
    items = []
    for v in victims:
        name = v.get("victim") or v.get("post_title") or ""
        when = parse_dt(v.get("attackdate") or v.get("discovered") or v.get("published"))
        country = _country(v.get("country"))
        if not name or (when and when < since):
            continue
        if ctx.countries and country and country not in ctx.countries:
            continue
        group = v.get("group") or v.get("group_name") or "unknown group"
        domain = normalize_domain(v.get("domain") or v.get("website"))
        sector = v.get("activity") or v.get("sector") or ""
        url = v.get("url") or v.get("post_url") or v.get("permalink") or f"https://www.ransomware.live/#/profiles?id={group}"
        text = f"{name} was listed as a victim of the {group} ransomware group on {when.date() if when else 'an unknown date'}."
        if sector:
            text += f" Sector: {sector}."
        if v.get("description"):
            text += " " + clean_text(v["description"])[:800]
        items.append(
            DiscoveredItem(
                company_name=name if not domain or "." not in name else name.split(".")[0].title(),
                company_domain=domain or normalize_domain(name),
                company_country=country, company_industry=sector or None, signal="cyber:ransomware_victim",
                document=Document(source_type="news", url=url, title=f"Ransomware: {name} listed by {group}", text=text,
                                  published_at=when, source="ransomware.live", meta={"provider": "ransomware_live", "group": group, "kind": "security_incident"}),
            )
        )
    return SyncResult(items=items[: ctx.max_items], fetched=len(victims), cursor={"since": datetime.now(timezone.utc).isoformat()})


async def sync_hibp(ctx: SourceContext, cursor: dict[str, Any]) -> SyncResult:
    """Public breach catalogue; incremental on `AddedDate`. Domain search is paid, the catalogue is free."""
    since = cursor_since(cursor, ctx, days=30)
    breaches = await get_json(ctx.client, "https://haveibeenpwned.com/api/v3/breaches", headers={"User-Agent": "OrangeSignals"})
    items = []
    for b in breaches:
        added = parse_dt(b.get("AddedDate"))
        if not added or added < since or b.get("IsSpamList") or b.get("IsFabricated"):
            continue
        name = b.get("Title") or b.get("Name", "")
        classes = ", ".join(b.get("DataClasses") or [])
        text = (f"{name} suffered a data breach on {b.get('BreachDate')} affecting {b.get('PwnCount', 'an unknown number of')} accounts "
                f"(added to Have I Been Pwned on {added.date()}). Exposed data: {classes}. {html_to_text(b.get('Description', ''))}")
        items.append(
            DiscoveredItem(
                company_name=name, company_domain=normalize_domain(b.get("Domain")), signal="cyber:data_breach",
                document=Document(source_type="news", url=f"https://haveibeenpwned.com/Breach/{b.get('Name')}", title=f"Data breach: {name}",
                                  text=text[:4000], published_at=added, source="Have I Been Pwned",
                                  meta={"provider": "hibp", "breach_date": b.get("BreachDate"), "pwn_count": b.get("PwnCount"), "kind": "security_incident"}),
            )
        )
    return SyncResult(items=items, fetched=len(breaches), cursor={"since": datetime.now(timezone.utc).isoformat()})


# ------------------------------------------------------------------ CISA KEV x tech stack (enrichment)

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
# Tech names from web.TECH_SIGNATURES -> KEV vendorProject/product patterns.
TECH_TO_KEV = {
    "SAP": r"^sap$", "Salesforce": r"salesforce", "Microsoft Dynamics": r"dynamics", "ServiceNow": r"servicenow",
    "Adobe Experience Manager": r"experience manager|^aem$", "Cloudflare": r"cloudflare", "Workday": r"workday",
    "HubSpot": r"hubspot", "UiPath": r"uipath", "OneTrust": r"onetrust",
}


async def load_kev(client) -> list[dict]:
    data = await get_json(client, KEV_URL)
    return data.get("vulnerabilities", [])


def kev_documents(company_name: str, tech_stack: list[str], kev: list[dict], since_days: int = 90) -> list[Document]:
    """'Company uses X, and X has a vulnerability being exploited right now' -> cyber signal."""
    now = datetime.now(timezone.utc)
    docs = []
    for tech in tech_stack:
        pattern = TECH_TO_KEV.get(tech)
        if not pattern:
            continue
        hits = [
            v for v in kev
            if (re.search(pattern, (v.get("vendorProject") or "").lower()) or re.search(pattern, (v.get("product") or "").lower()))
            and (d := parse_dt(v.get("dateAdded"))) and (now - d).days <= since_days
        ]
        if not hits:
            continue
        latest = max(hits, key=lambda v: v.get("dateAdded", ""))
        cves = ", ".join(v["cveID"] for v in hits[:5])
        docs.append(
            Document(
                source_type="web", url=f"https://nvd.nist.gov/vuln/detail/{latest['cveID']}",
                title=f"{company_name} runs {tech}, which has actively exploited vulnerabilities",
                text=(f"{company_name}'s website uses {tech}. CISA lists {len(hits)} actively exploited {tech} vulnerabilities added in the "
                      f"last {since_days} days ({cves}); latest: {latest.get('vulnerabilityName', '')}. {latest.get('shortDescription', '')}"),
                published_at=parse_dt(latest.get("dateAdded")), source="CISA KEV",
                meta={"provider": "cisa_kev", "tech": tech, "cves": [v["cveID"] for v in hits], "kind": "security_exposure"},
            )
        )
    return docs
