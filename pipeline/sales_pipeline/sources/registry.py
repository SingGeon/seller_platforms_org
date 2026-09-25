"""Company profile enrichment from open registries (Crunchbase replacement, GIG-19).

- Wikidata: industry, HQ country, employees, website, stock ticker (good for large companies)
- GLEIF: legal name, LEI, legal-address country, ultimate parent (group structure)
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .base import get_json
from .companies import normalize_company_name, normalize_domain

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
GLEIF_API = "https://api.gleif.org/api/v1"


class CompanyProfile(BaseModel):
    source: str
    name: str | None = None
    industry: str | None = None
    country: str | None = None
    employee_count: int | None = None
    website: str | None = None
    domain: str | None = None
    lei: str | None = None
    parent_name: str | None = None
    ref: str | None = None  # Wikidata QID / LEI
    extra: dict[str, Any] = Field(default_factory=dict)


SPARQL = """SELECT ?item ?itemLabel ?industryLabel ?iso ?employees ?website WHERE {
  VALUES ?item { %s }
  OPTIONAL { ?item wdt:P452 ?industry. }
  OPTIONAL { ?item wdt:P17 ?c. ?c wdt:P297 ?iso. }
  OPTIONAL { ?item wdt:P1128 ?employees. }
  OPTIONAL { ?item wdt:P856 ?website. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}"""


async def wikidata_profile(client, name: str, domain: str | None = None) -> CompanyProfile | None:
    headers = {"User-Agent": "OrangeSignals/0.1 (B2B sales research)"}
    found = await get_json(client, WIKIDATA_API, params={"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": "5", "format": "json"}, headers=headers)
    qids = [h["id"] for h in found.get("search", []) if h.get("id")]
    if not qids:
        return None
    query = SPARQL % " ".join(f"wd:{q}" for q in qids)
    data = await get_json(client, WIKIDATA_SPARQL, params={"query": query, "format": "json"}, headers={**headers, "Accept": "application/sparql-results+json"})
    rows = (data.get("results") or {}).get("bindings", [])
    by_item: dict[str, dict[str, Any]] = {}
    for r in rows:
        qid = r["item"]["value"].rsplit("/", 1)[-1]
        p = by_item.setdefault(qid, {"industries": [], "employees": []})
        p["label"] = r.get("itemLabel", {}).get("value")
        if "industryLabel" in r:
            p["industries"].append(r["industryLabel"]["value"])
        if "iso" in r:
            p["iso"] = r["iso"]["value"]
        if "employees" in r:
            try:
                p["employees"].append(int(float(r["employees"]["value"])))
            except ValueError:
                pass
        if "website" in r:
            p.setdefault("website", r["website"]["value"])

    def score(qid: str) -> tuple[int, int, int]:
        p = by_item[qid]
        dom_match = int(bool(domain) and normalize_domain(p.get("website")) == normalize_domain(domain))
        name_match = int(normalize_company_name(p.get("label") or "") == normalize_company_name(name))
        # Companies have industries/employees; homonyms (people, places) usually don't.
        is_company = int(bool(p["industries"] or p["employees"]))
        return (dom_match, name_match and is_company, is_company)

    candidates = [q for q in qids if q in by_item]
    if not candidates:
        return None
    best = max(candidates, key=lambda q: (score(q), -qids.index(q)))
    p = by_item[best]
    if score(best) == (0, 0, 0):
        return None
    return CompanyProfile(
        source="wikidata", ref=best, name=p.get("label"), industry=(p["industries"] or [None])[0],
        country=p.get("iso"), employee_count=max(p["employees"]) if p["employees"] else None,
        website=p.get("website"), domain=normalize_domain(p.get("website")), extra={"industries": p["industries"][:5]},
    )


async def gleif_profile(client, name: str, country: str | None = None) -> CompanyProfile | None:
    params = {"filter[entity.legalName]": name, "page[size]": "5"}
    if country:
        params["filter[entity.legalAddress.country]"] = country
    data = await get_json(client, f"{GLEIF_API}/lei-records", params=params)
    records = data.get("data", [])
    if not records:
        data = await get_json(client, f"{GLEIF_API}/fuzzycompletions", params={"field": "entity.legalName", "q": name})
        leis = [((d.get("relationships") or {}).get("lei-records") or {}).get("data", {}).get("id") for d in data.get("data", [])]
        leis = [l for l in leis if l][:1]
        if not leis:
            return None
        records = [(await get_json(client, f"{GLEIF_API}/lei-records/{leis[0]}")).get("data", {})]
    active = [r for r in records if ((r.get("attributes") or {}).get("entity") or {}).get("status") == "ACTIVE"] or records
    rec = active[0]
    attrs = rec.get("attributes") or {}
    entity = attrs.get("entity") or {}
    lei = attrs.get("lei") or rec.get("id")
    parent_name = None
    try:
        parent = await get_json(client, f"{GLEIF_API}/lei-records/{lei}/ultimate-parent")
        parent_name = (((parent.get("data") or {}).get("attributes") or {}).get("entity") or {}).get("legalName", {}).get("name")
    except Exception:  # noqa: BLE001 - most entities report no parent (404)
        parent_name = None
    return CompanyProfile(
        source="gleif", ref=lei, lei=lei, name=(entity.get("legalName") or {}).get("name"),
        country=(entity.get("legalAddress") or {}).get("country"), parent_name=parent_name,
        extra={"legal_form": (entity.get("legalForm") or {}).get("id"), "status": entity.get("status")},
    )
