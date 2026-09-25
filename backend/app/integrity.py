"""Cross-database integrity between PostgreSQL and MongoDB.

The two stores reference each other by integer id, without foreign keys:

    Mongo lead_scores.service_id, signals.service_id  -> PostgreSQL services.id
    Mongo signals.question_id                          -> PostgreSQL signal_questions.id
    Mongo signals.rule_id                              -> PostgreSQL disqualification_rules.id
    Mongo signals.seller_id, activity_log.seller_id    -> PostgreSQL sellers.id (the log keeps the name too)
    PostgreSQL lead_assignments.company_id             -> Mongo companies._id
    Mongo documents / signals / events / lead_scores   -> Mongo companies._id

Deletes cascade in code (mongo.forget_*, mongo.delete_company); this module finds and
removes anything left behind (e.g. after a crash or a manual edit in DBeaver / Compass).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import mongo
from .models import DisqualificationRule, LeadAssignment, Seller, Service, SignalQuestion


def _missing(collection: str, field: str, valid: set[int]) -> dict:
    q = {field: {"$nin": sorted(valid), "$ne": None}}
    return {"collection": collection, "field": field, "query": q, "count": mongo.db()[collection].count_documents(q)}


def check(db: Session) -> dict:
    services = set(db.scalars(select(Service.id)))
    questions = set(db.scalars(select(SignalQuestion.id)))
    rules = set(db.scalars(select(DisqualificationRule.id)))
    sellers = set(db.scalars(select(Seller.id)))
    companies = set(mongo.ids(mongo.COMPANIES))
    mongo_orphans = [
        _missing(mongo.LEAD_SCORES, "service_id", services),
        _missing(mongo.SIGNALS, "service_id", services),
        _missing(mongo.SIGNALS, "question_id", questions),
        _missing(mongo.SIGNALS, "rule_id", rules),
        _missing(mongo.SIGNALS, "seller_id", sellers),
        *(_missing(c, "company_id", companies) for c in (mongo.DOCUMENTS, mongo.SIGNALS, mongo.EVENTS, mongo.LEAD_SCORES)),
    ]
    orphan_assignments = [a for a in db.scalars(select(LeadAssignment.company_id)) if a not in companies]
    return {
        "ok": not orphan_assignments and all(o["count"] == 0 for o in mongo_orphans),
        "counts": {
            "postgres": {"services": len(services), "signal_questions": len(questions), "rules": len(rules), "sellers": len(sellers),
                         "lead_assignments": db.scalar(select(func.count()).select_from(LeadAssignment)) or 0},
            "mongodb": {c: mongo.db()[c].estimated_document_count() for c in (
                mongo.COMPANIES, mongo.DOCUMENTS, mongo.SIGNALS, mongo.EVENTS, mongo.LEAD_SCORES, mongo.RUNS, mongo.LLM_CACHE, mongo.ACTIVITY)},
        },
        "orphans": [
            *({"store": "mongodb", "collection": o["collection"], "field": o["field"], "count": o["count"]} for o in mongo_orphans if o["count"]),
            *([{"store": "postgres", "table": "lead_assignments", "field": "company_id", "count": len(orphan_assignments)}] if orphan_assignments else []),
        ],
        "_mongo_queries": mongo_orphans,
        "_orphan_assignments": orphan_assignments,
    }


def repair(db: Session) -> dict:
    """Delete every orphan found by `check`; seller references are cleared instead of deleted."""
    report = check(db)
    removed: dict[str, int] = {}
    for o in report["_mongo_queries"]:
        if not o["count"]:
            continue
        key = f"{o['collection']}.{o['field']}"
        if o["field"] == "seller_id":
            removed[key] = mongo.db()[o["collection"]].update_many(o["query"], {"$set": {"seller_id": None}}).modified_count
        else:
            removed[key] = mongo.db()[o["collection"]].delete_many(o["query"]).deleted_count
    for company_id in report["_orphan_assignments"]:
        db.delete(db.get(LeadAssignment, company_id))
        removed["lead_assignments.company_id"] = removed.get("lead_assignments.company_id", 0) + 1
    db.commit()
    return {"removed": removed, "after": public(check(db))}


def public(report: dict) -> dict:
    return {k: v for k, v in report.items() if not k.startswith("_")}
