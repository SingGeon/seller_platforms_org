"""CRM hand-off (GIG-40): HubSpot company + note, with CSV/JSON export as fallback."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import httpx

from .models import Company, LeadScore, Service

HUBSPOT_API = "https://api.hubapi.com"
NOTE_TO_COMPANY_ASSOCIATION = 190  # HubSpot-defined association type id (note -> company)

EXPORT_COLUMNS = [
    "company", "domain", "country", "industry", "employees", "service", "tier", "final_score",
    "icp_score", "signal_score", "recommendation", "why_now", "top_signal_1", "top_signal_1_url",
    "top_signal_2", "top_signal_2_url", "top_signal_3", "top_signal_3_url",
]


def lead_row(company: Company, service: Service, lead: LeadScore) -> dict:
    exp = lead.explanation or {}
    row = {
        "company": company.name, "domain": company.domain or "", "country": company.country or "",
        "industry": company.industry or "", "employees": company.employee_count or "", "service": service.name,
        "tier": lead.tier, "final_score": lead.final_score, "icp_score": lead.icp_score, "signal_score": lead.signal_score,
        "recommendation": exp.get("recommendation", ""), "why_now": exp.get("summary", ""),
    }
    for i in range(3):
        sig = exp.get("top_signals", [])[i] if i < len(exp.get("top_signals", [])) else {}
        row[f"top_signal_{i + 1}"] = f"{sig.get('label', '')} — \"{sig.get('quote', '')}\" ({sig.get('date', '')})" if sig else ""
        row[f"top_signal_{i + 1}_url"] = sig.get("url", "")
    return row


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def note_html(company: Company, service: Service, lead: LeadScore) -> str:
    exp = lead.explanation or {}
    items = "".join(
        f'<li><b>{s["label"]}</b>: "{s["quote"]}" ({s["date"]}) <a href="{s["url"]}">source</a></li>'
        for s in exp.get("top_signals", [])
    )
    return (
        f"<p><b>Orange Signals — {service.name}</b>: {lead.tier} ({lead.final_score:.0f}/100), "
        f"recommendation: {exp.get('recommendation', '')}</p><p>{exp.get('summary', '')}</p><ul>{items}</ul>"
    )


async def push_to_hubspot(token: str, company: Company, service: Service, lead: LeadScore, client: httpx.AsyncClient | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    own = client is None
    client = client or httpx.AsyncClient(base_url=HUBSPOT_API, timeout=20, headers=headers)
    try:
        company_id = None
        if company.domain:
            resp = await client.post(
                "/crm/v3/objects/companies/search",
                json={"filterGroups": [{"filters": [{"propertyName": "domain", "operator": "EQ", "value": company.domain}]}], "limit": 1},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            company_id = results[0]["id"] if results else None
        props = {"name": company.name, "domain": company.domain or "", "country": company.country or "", "industry_description": company.industry or ""}
        if company_id:
            (await client.patch(f"/crm/v3/objects/companies/{company_id}", json={"properties": props})).raise_for_status()
            action = "updated"
        else:
            resp = await client.post("/crm/v3/objects/companies", json={"properties": props})
            resp.raise_for_status()
            company_id = resp.json()["id"]
            action = "created"
        note = await client.post(
            "/crm/v3/objects/notes",
            json={
                "properties": {"hs_note_body": note_html(company, service, lead), "hs_timestamp": datetime.now(timezone.utc).isoformat()},
                "associations": [
                    {"to": {"id": company_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": NOTE_TO_COMPANY_ASSOCIATION}]}
                ],
            },
        )
        note.raise_for_status()
        return {"hubspot_company_id": company_id, "company": action, "note_id": note.json().get("id")}
    finally:
        if own:
            await client.aclose()
