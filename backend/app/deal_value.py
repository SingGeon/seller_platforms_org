"""Deal estimate per lead: what the project could bring Orange Systems, what it costs to deliver and the profit.

    value = base value of the service (first-year contract, EUR, company of `reference_employees`)
            x (employees / reference_employees) ^ size_elasticity   (clamped to size_factor_min..size_factor_max)
            x price level of the company's market
    cost   = value x (1 - gross margin of the service)
    profit = value x gross margin
    expected profit = profit x win probability of the lead's tier

The range is value x (1 - spread) .. value x (1 + spread); the spread is wider when the company size is guessed.
Every number is an assumption an admin can change (PUT /deal-model); the defaults come from public benchmarks,
listed in `sources` so the jury and the sales team can check them.
"""
from __future__ import annotations

import copy
from typing import Any

DEFAULT_DEAL_MODEL: dict[str, Any] = {
    "currency": "EUR",
    "reference_employees": 150,
    "size_elasticity": 0.6,  # a company 10x larger buys ~4x more, not 10x
    "size_factor_min": 0.25,
    "size_factor_max": 12.0,
    "listed_company_employees": 2000,  # size assumed for a stock-listed company without a headcount
    "unknown_company_employees": 150,
    "services": {
        # first-year value for a 150-employee company in a Western European market, and the delivery gross margin
        "apa": {"base_value": 60000, "gross_margin": 0.35,
                "basis": "3-5 automated processes; RPA/agent bots cost $10k-150k each, 70-75% of the bill is services"},
        "cyber": {"base_value": 45000, "gross_margin": 0.30,
                  "basis": "NIS2/DORA gap assessment + 24/7 MDR at $8-35 per endpoint per month"},
        "cloud": {"base_value": 80000, "gross_margin": 0.25,
                  "basis": "assessment, landing zone, migration waves; part of it is resold cloud capacity"},
        "data": {"base_value": 60000, "gross_margin": 0.35,
                 "basis": "governed data platform + BI dashboards + first predictive model"},
        "erp": {"base_value": 150000, "gross_margin": 0.30,
                "basis": "mid-market ERP implementations run $150k-750k (Panorama 2025), 1-3% of revenue"},
        "iot": {"base_value": 70000, "gross_margin": 0.22,
                "basis": "sensors, IoT platform, private 4G/5G; hardware lowers the margin"},
    },
    "default_service": {"base_value": 60000, "gross_margin": 0.30, "basis": "average of the services above"},
    # price level of IT services by market (Western Europe = 1)
    "market_price_level": {"DE": 1.0, "AT": 1.0, "NL": 1.0, "GB": 1.05, "US": 1.2, "PL": 0.65, "RO": 0.6, "MD": 0.45},
    "default_market_price_level": 0.8,
    "win_probability": {"Hot": 0.30, "Warm": 0.15, "Cold": 0.05, "Disqualified": 0.0},
    "spread_known_size": 0.35,
    "spread_guessed_size": 0.6,
    "sources": [
        "Systems integrators: 20% gross margin, 7.2% EBITDA margin (2024); professional services project margins 37.7% (SPI 2025)",
        "ERP: mid-market implementations $150k-750k, average ~$450k (Panorama Consulting 2025)",
        "MDR / managed SOC: $8-35 per endpoint per month",
        "RPA: $10k-150k per enterprise bot; licences 25-30% of the cost, services 70-75%",
        "IT rates: Romania ~$30-53/h for senior contractors vs ~$80-120/h in Germany",
        "Orange Business 2025: IT & Integration Services growing in Europe while connectivity declines",
    ],
}


def merged_model(stored: dict | None) -> dict[str, Any]:
    """The defaults overridden by what the admin saved (one level deep for services and markets)."""
    model = copy.deepcopy(DEFAULT_DEAL_MODEL)
    for key, value in (stored or {}).items():
        if isinstance(value, dict) and isinstance(model.get(key), dict):
            for k, v in value.items():
                model[key][k] = {**model[key][k], **v} if isinstance(v, dict) and isinstance(model[key].get(k), dict) else v
        else:
            model[key] = value
    return model


def company_size(company: Any, model: dict) -> tuple[int, str]:
    """(employees, basis): the known headcount, else a stock-listed guess, else the default guess."""
    employees = getattr(company, "employee_count", None)
    if isinstance(employees, (int, float)) and employees > 0:
        return int(employees), "known"
    profiles = getattr(company, "registry_profiles", None) or {}
    for p in profiles.values():
        n = (p or {}).get("employee_count")
        if isinstance(n, (int, float)) and n > 0:
            return int(n), "registry"
    if any((p or {}).get("listed") for p in profiles.values()):
        return int(model["listed_company_employees"]), "listed"
    return int(model["unknown_company_employees"]), "guessed"


def estimate_deal(company: Any, service_slug: str, tier: str, model: dict | None = None) -> dict[str, Any]:
    model = model or DEFAULT_DEAL_MODEL
    svc = model["services"].get(service_slug) or model["default_service"]
    employees, size_basis = company_size(company, model)
    size_factor = (employees / model["reference_employees"]) ** model["size_elasticity"]
    size_factor = min(max(size_factor, model["size_factor_min"]), model["size_factor_max"])
    country = (getattr(company, "country", None) or "").upper()
    price_level = model["market_price_level"].get(country, model["default_market_price_level"])
    value = svc["base_value"] * size_factor * price_level
    margin = svc["gross_margin"]
    spread = model["spread_known_size"] if size_basis in ("known", "registry") else model["spread_guessed_size"]
    win = model["win_probability"].get(tier, 0.0)
    profit = value * margin

    def r(x: float) -> int:
        return int(round(x, -2))

    return {
        "currency": model["currency"],
        "value": r(value), "value_low": r(value * (1 - spread)), "value_high": r(value * (1 + spread)),
        "cost": r(value - profit), "profit": r(profit),
        "profit_low": r(profit * (1 - spread)), "profit_high": r(profit * (1 + spread)),
        "gross_margin": margin, "win_probability": win, "expected_profit": r(profit * win),
        "confidence": "medium" if size_basis in ("known", "registry") else "low",
        "assumptions": {
            "employees": employees, "size_basis": size_basis, "size_factor": round(size_factor, 2),
            "country": country or None, "market_price_level": price_level, "base_value": svc["base_value"],
            "basis": svc.get("basis", ""),
        },
    }
