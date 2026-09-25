"""Seed demo configuration: two services with signal questions (GIG-16), ICPs,
negative signals and disqualification rules (GIG-17), a starter company list,
and optionally offline sample documents built from the Annex 1 examples.

    python -m app.seed                 # config + companies
    python -m app.seed --sample-docs   # also load Annex 1 sample documents (offline demo)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from sales_pipeline import Document

from . import mongo
from .models import DisqualificationRule, IcpCriteria, Service, SignalQuestion
from .scoring_service import get_scoring_config, recompute_scores

SERVICES = [
    {
        "name": "Agentic Process Automation",
        "slug": "apa",
        "description": "Intelligent / agentic process automation: RPA, AI agents, process mining and process excellence.",
        "value_proposition": (
            "Orange Systems designs and runs agentic automation programmes end to end: we find the processes worth "
            "automating with process mining, build AI agents and RPA bots on your existing platforms, and operate them "
            "with measurable cost and cycle-time targets."
        ),
        "event_weights": {"leadership_change": "Medium", "tech_stack": "Low", "corporate_event:positive": "Low", "corporate_event:negative": "Medium"},
        "icp": {
            "markets": ["EU", "UK&I", "North America"],
            "industries": ["Logistics", "Transportation", "Aviation", "Banking", "Insurance", "Manufacturing", "Retail", "Telecommunications", "Energy", "Public Sector"],
            "countries": ["MD"],
            "employee_min": 1000,
            "employee_max": 1_000_000,
            "min_fit": 40,
        },
        "questions": [
            {
                "text": "Does the company mention process optimization, cost reduction, operational efficiency, or automation initiatives?",
                "weight": "High", "source_hint": "any", "lookback_days": 365,
                "keywords": ["process optimization", "cost reduction", "efficiency", "automation", "robotic process automation", "digitalization", "process consolidation", "savings"],
            },
            {
                "text": "Is the company hiring RPA developers, business analysts, automation engineers, AI specialists, or process excellence roles?",
                "weight": "High", "source_hint": "jobs", "lookback_days": 120,
                "keywords": ["rpa", "uipath", "automation engineer", "automation developer", "business analyst", "process excellence", "ai engineer", "machine learning", "process mining"],
            },
            {
                "text": "Is the company running digital transformation, AI, Agentic AI, RPA or process mining projects?",
                "weight": "Medium", "source_hint": "any", "lookback_days": 365,
                "keywords": ["digital transformation", "agentic ai", "artificial intelligence", "ai use cases", "rpa", "robotic process automation", "process mining", "generative ai", "strategy 2030"],
            },
            {
                "text": "Has the company appointed a new CIO, COO, CDO, Head of Digital Transformation, Head of Automation or Process Excellence leader?",
                "weight": "Medium", "source_hint": "news", "lookback_days": 180,
                "keywords": ["appointed", "new cio", "new coo", "chief digital officer", "head of automation", "head of digital", "joins as"],
            },
            {
                "text": "Is the company consolidating processes into shared services or a global business services centre?",
                "weight": "Medium", "source_hint": "any", "lookback_days": 365,
                "keywords": ["shared service", "global business services", "process consolidation", "centralize", "service centre"],
            },
            {
                "text": "Does the company use or buy third-party AI / automation solutions or partners?",
                "weight": "Low", "source_hint": "any", "lookback_days": 730,
                "keywords": ["third-party", "partner", "partnership", "uipath", "celonis", "power automate", "vendor"],
            },
            {
                "text": "Does the company already have a mature in-house automation Center of Excellence or strong internal automation capabilities?",
                "weight": "Medium", "source_hint": "any", "lookback_days": 730, "is_negative": True,
                "keywords": ["center of excellence", "centre of excellence", "coe", "in-house", "internal development", "maturity", "internal digitalization", "automation capabilities", "internal capabilities"],
            },
            {
                "text": "Has the company announced layoffs, a hiring freeze or IT budget cuts?",
                "weight": "High", "source_hint": "news", "lookback_days": 180, "is_negative": True,
                "keywords": ["layoffs", "hiring freeze", "budget cuts", "cost freeze"],
            },
        ],
    },
    {
        "name": "Cybersecurity Services",
        "slug": "cyber",
        "description": "Managed security (SOC/MDR), incident response, NIS2 / DORA compliance and security architecture.",
        "value_proposition": (
            "Orange Systems helps regulated organisations get and stay compliant with NIS2 and DORA and cut incident "
            "response times: gap assessment, 24/7 managed detection and response, and hands-on remediation."
        ),
        "event_weights": {"security_incident": "High", "compliance_event": "High", "leadership_change": "Low", "corporate_event:negative": "Low"},
        "icp": {
            "markets": ["EU", "UK&I"],
            "industries": ["Banking", "Financial Services", "Insurance", "Energy", "Healthcare", "Logistics", "Manufacturing", "Public Sector", "Telecommunications", "Aviation", "Retail"],
            "countries": ["MD"],
            "employee_min": 250,
            "employee_max": 1_000_000,
            "min_fit": 40,
        },
        "questions": [
            {
                "text": "Has the company suffered a recent security incident, data breach, ransomware attack or major IT outage?",
                "weight": "High", "source_hint": "news", "lookback_days": 365,
                "keywords": ["data breach", "breach", "ransomware", "cyberattack", "cyber attack", "hacked", "security incident", "outage"],
            },
            {
                "text": "Is the company subject to NIS2 or DORA compliance, or preparing for it?",
                "weight": "High", "source_hint": "any", "lookback_days": 730,
                "keywords": ["nis2", "nis 2", "dora", "digital operational resilience", "critical infrastructure", "essential entity"],
            },
            {
                "text": "Is the company hiring security roles such as CISO, SOC analysts, security engineers or GRC specialists?",
                "weight": "Medium", "source_hint": "jobs", "lookback_days": 120,
                "keywords": ["security", "ciso", "soc analyst", "cyber", "penetration", "grc", "iam", "incident response"],
            },
            {
                "text": "Has the company appointed a new CISO, CIO or CTO recently?",
                "weight": "Medium", "source_hint": "news", "lookback_days": 180,
                "keywords": ["appointed", "new ciso", "chief information security officer", "new cio", "new cto", "joins as"],
            },
            {
                "text": "Is the company migrating to the cloud or expanding digital channels in a way that grows its attack surface?",
                "weight": "Low", "source_hint": "any", "lookback_days": 365,
                "keywords": ["cloud migration", "move to the cloud", "aws", "azure", "google cloud", "digital channels", "e-commerce"],
            },
            {
                "text": "Has the company recently signed a managed security (MSSP / SOC) contract with another provider?",
                "weight": "Medium", "source_hint": "news", "lookback_days": 365, "is_negative": True,
                "keywords": ["managed security", "mssp", "soc contract", "selects", "security partner"],
            },
        ],
    },
]

GLOBAL_RULES = [
    {"name": "Existing Orange Systems client", "rule_type": "field_rule", "field": "is_existing_client", "operator": "is_true"},
    {"name": "Direct competitor", "rule_type": "field_rule", "field": "is_competitor", "operator": "is_true"},
    {"name": "Company is insolvent", "rule_type": "field_rule", "field": "status", "operator": "eq", "value": "insolvent"},
    {"name": "Too small (< 50 employees)", "rule_type": "field_rule", "field": "employee_count", "operator": "lt", "value": 50},
    {"name": "Pure B2C business (only B2B)", "rule_type": "field_rule", "field": "business_model", "operator": "eq", "value": "b2c"},
    {"name": "Sanctioned country", "rule_type": "field_rule", "field": "country", "operator": "in", "value": ["RU", "BY", "IR", "KP", "SY", "CU"]},
    {
        "name": "Insolvency / bankruptcy reported",
        "rule_type": "llm_question",
        "question": "Has the company filed for insolvency, bankruptcy or creditor protection?",
        "keywords": ["insolvency", "bankruptcy", "creditor protection", "chapter 11"],
        "min_confidence": 0.7,
    },
]

COMPANIES = [
    {"name": "Lufthansa Group", "domain": "lufthansagroup.com", "industry": "Aviation", "country": "DE", "market": "DACH", "employee_count": 100000},
    {"name": "DHL Group", "domain": "group.dhl.com", "industry": "Logistics", "country": "DE", "market": "DACH", "employee_count": 600000},
    {"name": "A.P. Moller - Maersk", "domain": "maersk.com", "industry": "Logistics", "country": "DK", "market": "Nordics", "employee_count": 100000},
    {"name": "Raiffeisen Bank International", "domain": "rbinternational.com", "industry": "Banking", "country": "AT", "market": "DACH", "employee_count": 45000},
    {"name": "Siemens", "domain": "siemens.com", "industry": "Manufacturing", "country": "DE", "market": "DACH", "employee_count": 320000},
    {"name": "Vodafone Group", "domain": "vodafone.com", "industry": "Telecommunications", "country": "GB", "market": "UK&I", "employee_count": 90000},
    {"name": "ING Group", "domain": "ing.com", "industry": "Banking", "country": "NL", "market": "Benelux", "employee_count": 60000},
    {"name": "Carrefour", "domain": "carrefour.com", "industry": "Retail", "country": "FR", "market": "France", "employee_count": 300000},
]

SAMPLE_DOCS_PATH = Path(__file__).parent / "sample_data" / "annex1_documents.json"


def seed_config(db: Session) -> None:
    for spec in SERVICES:
        svc = db.scalar(select(Service).where(Service.slug == spec["slug"]))
        if svc is None:
            svc = Service(
                name=spec["name"], slug=spec["slug"], description=spec["description"],
                value_proposition=spec["value_proposition"], event_weights=spec["event_weights"],
            )
            db.add(svc)
            db.flush()
            db.add(IcpCriteria(service_id=svc.id, **spec["icp"]))
            for q in spec["questions"]:
                db.add(SignalQuestion(service_id=svc.id, **q))
    for rule in GLOBAL_RULES:
        if db.scalar(select(DisqualificationRule).where(DisqualificationRule.name == rule["name"])) is None:
            db.add(DisqualificationRule(service_id=None, **rule))
    get_scoring_config(db)
    db.commit()


def seed_companies() -> None:
    for c in COMPANIES:
        if not mongo.domain_taken(c["domain"]):
            mongo.insert_company(c)


def seed_sample_documents() -> int:
    """Offline demo documents paraphrasing the public facts listed in Annex 1.
    Marked `meta.sample = true`; URLs use the reserved .example domain."""
    data = json.loads(SAMPLE_DOCS_PATH.read_text())
    now = datetime.now(timezone.utc)
    added = 0
    for entry in data:
        company = mongo.find_one(mongo.COMPANIES, {"domain": entry["domain"]})
        if company is None:
            continue
        for d in entry["documents"]:
            doc = Document(
                source_type=d["source_type"], url=d["url"], title=d["title"], text=d["text"],
                published_at=now - timedelta(days=d["days_ago"]), source=d.get("source", "annex-1"),
                meta={"sample": True, **d.get("meta", {})},
            )
            if mongo.find_one(mongo.DOCUMENTS, {"company_id": company.id, "url": doc.url}):
                continue
            added += int(mongo.store_document(company.id, doc))
    return added


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-docs", action="store_true", help="load Annex 1 sample documents for an offline demo")
    args = parser.parse_args()
    from .db import SessionLocal

    with SessionLocal() as db:
        seed_config(db)
        seed_companies()
        if args.sample_docs:
            print(f"sample documents added: {seed_sample_documents()}")
        recompute_scores(db)
    print("seed complete")


if __name__ == "__main__":
    main()
