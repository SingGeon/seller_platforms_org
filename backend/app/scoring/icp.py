"""ICP fit score 0-100 with partial matches (GIG-15)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

MARKET_COUNTRIES: dict[str, set[str]] = {
    "DACH": {"DE", "AT", "CH"},
    "NORDICS": {"SE", "NO", "DK", "FI", "IS"},
    "BENELUX": {"BE", "NL", "LU"},
    "UK&I": {"GB", "IE"},
    "CEE": {"PL", "CZ", "SK", "HU", "RO", "BG", "SI", "HR", "RS", "MD", "LT", "LV", "EE", "UA"},
    "SEE": {"RO", "BG", "GR", "HR", "RS", "SI", "MD", "AL", "MK", "BA", "ME"},
    "SOUTHERN EUROPE": {"IT", "ES", "PT", "GR", "MT", "CY"},
    "FRANCE": {"FR"},
    "NORTH AMERICA": {"US", "CA"},
    "MIDDLE EAST": {"AE", "SA", "QA", "KW", "BH", "OM", "IL"},
}
MARKET_COUNTRIES["EU"] = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT",
    "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
}
MARKET_COUNTRIES["EUROPE"] = MARKET_COUNTRIES["EU"] | {"GB", "CH", "NO", "IS", "MD", "UA", "RS", "AL", "MK", "BA", "ME"}

COMPONENT_WEIGHTS = {"industry": 30, "geography": 30, "size": 30, "revenue": 10}
UNKNOWN_CREDIT = 0.5  # missing company data is neither a match nor a miss


@dataclass
class IcpResult:
    score: float
    components: dict[str, dict] = field(default_factory=dict)


def _range_fit(value: float | None, lo: float | None, hi: float | None) -> float:
    if value is None:
        return UNKNOWN_CREDIT
    if (lo is None or value >= lo) and (hi is None or value <= hi):
        return 1.0
    bound = lo if lo is not None and value < lo else hi
    if not bound or value <= 0:
        return 0.0
    # One order of magnitude outside the range -> 0; closer -> partial credit up to 0.8.
    return round(max(0.0, 1 - abs(math.log10(value / bound))) * 0.8, 3)


def _industry_fit(industry: str | None, wanted: list[str]) -> float:
    if not industry:
        return UNKNOWN_CREDIT
    ind = industry.lower()
    return 1.0 if any(w.lower() in ind or ind in w.lower() for w in wanted) else 0.0


def _geo_fit(country: str | None, market: str | None, countries: list[str], markets: list[str]) -> float:
    if not country and not market:
        return UNKNOWN_CREDIT
    c = (country or "").upper()
    if c and c in {x.upper() for x in countries}:
        return 1.0
    for m in markets:
        if market and market.lower() == m.lower():
            return 1.0
        if c and c in MARKET_COUNTRIES.get(m.upper(), set()):
            return 1.0
    return 0.0


def icp_fit(company, icp) -> IcpResult:
    """`company`/`icp` are ORM objects or anything with the same attributes."""
    if icp is None:
        return IcpResult(score=100.0, components={})
    comps: dict[str, dict] = {}
    if icp.industries:
        comps["industry"] = {"fit": _industry_fit(company.industry, icp.industries), "value": company.industry}
    if icp.countries or icp.markets:
        comps["geography"] = {
            "fit": _geo_fit(company.country, company.market, icp.countries or [], icp.markets or []),
            "value": company.country or company.market,
        }
    if icp.employee_min is not None or icp.employee_max is not None:
        comps["size"] = {"fit": _range_fit(company.employee_count, icp.employee_min, icp.employee_max), "value": company.employee_count}
    if icp.revenue_min is not None or icp.revenue_max is not None:
        comps["revenue"] = {"fit": _range_fit(company.revenue_musd, icp.revenue_min, icp.revenue_max), "value": company.revenue_musd}
    if not comps:
        return IcpResult(score=100.0, components={})
    total_w = sum(COMPONENT_WEIGHTS[k] for k in comps)
    exact = 0.0
    for k, c in comps.items():
        pts = 100 * COMPONENT_WEIGHTS[k] * c["fit"] / total_w
        exact += pts
        c["weight"] = COMPONENT_WEIGHTS[k]
        c["points"] = round(pts, 1)
    return IcpResult(score=round(exact, 1), components=comps)
