"""Bulk company universe from open registries (real, verifiable companies only).

- Wikidata: companies per country that have an official website, ordered by how well known
  they are (number of Wikipedia sitelinks); industry, employees, LEI, stock exchange when present.
- GLEIF: active legal entities per country (legal name + LEI), used to top up a country
  when Wikidata has too few companies with websites. No domain/industry, so lower quality.

Every record carries its registry reference (Wikidata QID / LEI), so any company in the
platform can be traced back to its public source.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .base import get_json
from .companies import normalize_domain

log = logging.getLogger(__name__)

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
GLEIF_API = "https://api.gleif.org/api/v1"
UA = {"User-Agent": "OrangeSignals/0.1 (B2B sales research; https://github.com/SingGeon/seller_platforms_org)"}

COUNTRY_QID = {
    "RO": "Q218", "MD": "Q217", "DE": "Q183", "AT": "Q40", "CH": "Q39", "PL": "Q36", "NL": "Q55", "BE": "Q31", "LU": "Q32",
    "GB": "Q145", "IE": "Q27", "FR": "Q142", "IT": "Q38", "ES": "Q29", "PT": "Q45", "SE": "Q34", "DK": "Q35", "FI": "Q33",
    "NO": "Q20", "CZ": "Q213", "SK": "Q214", "HU": "Q28", "BG": "Q219", "GR": "Q41", "HR": "Q224", "SI": "Q215", "RS": "Q403",
    "UA": "Q212", "LT": "Q37", "LV": "Q211", "EE": "Q191", "US": "Q30", "CA": "Q16",
}
# instance-of classes that denote companies (direct P31 values; subclass walks time out at this scale)
COMPANY_CLASSES = [
    "Q4830453",  # business
    "Q6881511",  # enterprise
    "Q891723",   # public company
    "Q783794",   # company
    "Q167037",   # corporation
    "Q161726",   # multinational corporation
    "Q1589009",  # privately held company
    "Q219577",   # holding company
    "Q22687",    # bank
    "Q1058914",  # software company
    "Q46970",    # airline
    "Q18388277", # technology company
    "Q740752",   # transport company
    "Q1331793",  # media company
    "Q2401749",  # telecommunications company
]

# Wikidata industry labels -> the ICP industry vocabulary used by the scoring engine.
INDUSTRY_MAP: list[tuple[str, str]] = [
    (r"bank", "Banking"), (r"insur", "Insurance"), (r"financ|invest|asset management|payment|fintech|stock exchange", "Financial Services"),
    (r"airline|air transport|aviation|aerospace|airport", "Aviation"),
    (r"logistic|freight|shipping|courier|postal|parcel|maritime|port operat", "Logistics"),
    (r"rail|transport|bus |automotive retail", "Transportation"),
    (r"telecom|mobile network|internet service|broadband", "Telecommunications"),
    (r"retail|supermarket|e-commerce|wholesale|consumer goods|fashion", "Retail"),
    (r"energy|electric|oil|petroleum|natural gas|utility|power|renewable|nuclear|mining", "Energy"),
    (r"health|pharma|hospital|medical|biotech", "Healthcare"),
    (r"software|information technology|\bit\b|computer|internet|cloud|cybersecurity|video game", "Technology"),
    (r"government|public administration|state-owned|public sector", "Public Sector"),
    (r"automotive|manufactur|steel|chemical|machinery|industr|engineering|construction|metallurgy|food processing|brewery|beverage|tobacco|textile|electronics", "Manufacturing"),
    (r"media|broadcast|publishing|newspaper|television|film", "Media"),
]


def normalize_industry(label: str | None) -> str | None:
    if not label:
        return None
    low = label.lower()
    for pattern, industry in INDUSTRY_MAP:
        if re.search(pattern, low):
            return industry
    return label[:1].upper() + label[1:]


class RegistryCompany(BaseModel):
    name: str
    country: str
    domain: str | None = None
    website: str | None = None
    industry: str | None = None
    industry_raw: list[str] = Field(default_factory=list)
    employee_count: int | None = None
    lei: str | None = None
    wikidata_id: str | None = None
    listed: bool = False
    popularity: int = 0  # Wikipedia sitelinks
    source: str = "wikidata"

    def registry_profile(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, exclude={"name", "country", "domain"})


# Only companies with at least this many Wikipedia articles: they are the best-known ones we want first, and
# the filter keeps the sort small enough for Wikidata's 60 s limit in big countries (DE, GB, PL, NL).
MIN_SITELINKS = 3
PAGE_SIZES = (250, 100, 50, 25)  # a page that times out on Wikidata is retried smaller


def wikidata_query(country: str, limit: int, offset: int, min_sitelinks: int = MIN_SITELINKS) -> str:
    classes = " ".join(f"wd:{c}" for c in COMPANY_CLASSES)
    return f"""SELECT ?item ?itemLabel ?website ?industryLabel ?employees ?lei ?exchange ?sitelinks WHERE {{
  {{ SELECT DISTINCT ?item ?sitelinks WHERE {{
      VALUES ?class {{ {classes} }}
      ?item wdt:P31 ?class ; wdt:P17 wd:{COUNTRY_QID[country]} ; wdt:P856 [] ; wikibase:sitelinks ?sitelinks .
      FILTER(?sitelinks >= {min_sitelinks})
      FILTER NOT EXISTS {{ ?item wdt:P576 [] }}
    }} ORDER BY DESC(?sitelinks) LIMIT {limit} OFFSET {offset} }}
  ?item wdt:P856 ?website .
  OPTIONAL {{ ?item wdt:P452 ?industry . }}
  OPTIONAL {{ ?item wdt:P1128 ?employees . }}
  OPTIONAL {{ ?item wdt:P1278 ?lei . }}
  OPTIONAL {{ ?item wdt:P414 ?exchange . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ro,de,fr,mul". }}
}}"""


def parse_wikidata_rows(rows: list[dict], country: str) -> list[RegistryCompany]:
    """Collapse the one-row-per-(website, industry, employees) SPARQL output into companies."""
    by_item: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for r in rows:
        qid = r["item"]["value"].rsplit("/", 1)[-1]
        if qid not in by_item:
            order.append(qid)
            by_item[qid] = {"label": r.get("itemLabel", {}).get("value", ""), "websites": [], "industries": [], "employees": [], "lei": None, "listed": False, "sitelinks": 0}
        e = by_item[qid]
        if "website" in r and r["website"]["value"] not in e["websites"]:
            e["websites"].append(r["website"]["value"])
        if "industryLabel" in r and r["industryLabel"]["value"] not in e["industries"]:
            e["industries"].append(r["industryLabel"]["value"])
        if "employees" in r:
            try:
                e["employees"].append(int(float(r["employees"]["value"])))
            except ValueError:
                pass
        if "lei" in r:
            e["lei"] = r["lei"]["value"]
        if "exchange" in r:
            e["listed"] = True
        if "sitelinks" in r:
            e["sitelinks"] = max(e["sitelinks"], int(r["sitelinks"]["value"]))
    out = []
    for qid in order:
        e = by_item[qid]
        label = e["label"]
        if not label or re.fullmatch(r"Q\d+", label):  # no human-readable name
            continue
        website = next((w for w in e["websites"] if normalize_domain(w)), None)
        industries = [i for i in e["industries"] if not re.fullmatch(r"Q\d+", i)]
        out.append(
            RegistryCompany(
                name=label, country=country, website=website, domain=normalize_domain(website),
                industry=normalize_industry(industries[0]) if industries else None, industry_raw=industries[:5],
                employee_count=max(e["employees"]) if e["employees"] else None, lei=e["lei"], wikidata_id=qid,
                listed=e["listed"], popularity=e["sitelinks"], source="wikidata",
            )
        )
    return out


async def wikidata_companies(client, country: str, limit: int, page_size: int = 250, start: int = 0) -> list[RegistryCompany]:
    """Up to `limit` companies of `country`, skipping the `start` best-known ones already loaded."""
    if country not in COUNTRY_QID:
        raise ValueError(f"no Wikidata country mapping for {country}")
    out: list[RegistryCompany] = []
    offset = start
    sizes = [s for s in PAGE_SIZES if s <= page_size] or [page_size]
    while len(out) < limit:
        data = None
        for cap in sizes:
            size = min(cap, limit - len(out))
            try:
                data = await get_json(
                    client, WIKIDATA_SPARQL, params={"query": wikidata_query(country, size, offset), "format": "json"},
                    headers={**UA, "Accept": "application/sparql-results+json"}, timeout=90,
                )
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500 or cap == sizes[-1]:
                    raise
                log.info("wikidata %s page of %s timed out (%s), retrying smaller", country, size, exc.response.status_code)
        rows = (data.get("results") or {}).get("bindings", [])
        page = parse_wikidata_rows(rows, country)
        out += page
        if len({r["item"]["value"] for r in rows}) < size:
            break
        offset += size
    return out[:limit]


async def gleif_companies(client, country: str, limit: int, page_size: int = 200) -> list[RegistryCompany]:
    """Active general-category legal entities registered in `country` (legal name + LEI)."""
    out: list[RegistryCompany] = []
    page = 1
    while len(out) < limit:
        data = await get_json(
            client, f"{GLEIF_API}/lei-records",
            params={"filter[entity.legalAddress.country]": country, "filter[entity.status]": "ACTIVE",
                    "filter[entity.category]": "GENERAL", "page[size]": str(page_size), "page[number]": str(page)},
            headers=UA, timeout=60,
        )
        records = data.get("data", [])
        for rec in records:
            attrs = rec.get("attributes") or {}
            entity = attrs.get("entity") or {}
            name = (entity.get("legalName") or {}).get("name")
            if not name:
                continue
            out.append(RegistryCompany(name=name, country=country, lei=attrs.get("lei") or rec.get("id"), source="gleif"))
        if len(records) < page_size:
            break
        page += 1
    return out[:limit]
