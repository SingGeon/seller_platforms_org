"""MongoDB store: companies and everything collected or inferred about them.

Collections (integer ids from `counters`, so API URLs and the frontend keep numeric ids):

    companies        firmographics, registry profiles, discovery trace, LinkedIn validation
    documents        collected news / web / jobs / registry text, deduped per company by content hash
    signals          AI (or manual) answers to signal questions and llm_question rules, with evidence
    company_events   alerts detected by the AI: incidents, leadership changes, compliance, ...
    lead_scores      one score per company x service, with breakdown and "why now"
    pipeline_runs    enrichment / discovery / bootstrap runs with progress, stats and log
    llm_cache        LLM responses keyed by (task, model, company, question, passages)

PostgreSQL keeps the seller accounts and the configuration (see models.py).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .config import get_settings

COMPANIES = "companies"
DOCUMENTS = "documents"
SIGNALS = "signals"
EVENTS = "company_events"
LEAD_SCORES = "lead_scores"
RUNS = "pipeline_runs"
LLM_CACHE = "llm_cache"
COUNTERS = "counters"

_client: MongoClient | None = None
_db: Database | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MDoc(dict):
    """A Mongo document with attribute access (`company.name`), exposing `_id` as `id`, so the
    scoring engine and the Pydantic `from_attributes` schemas work on it unchanged."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            return None

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def wrap(raw: dict | None) -> MDoc | None:
    if raw is None:
        return None
    doc = MDoc(raw)
    doc["id"] = doc.pop("_id")
    return doc


def wrap_all(rows: Iterable[dict]) -> list[MDoc]:
    return [wrap(r) for r in rows]


def db() -> Database:
    """The configured Mongo database (tests swap it with `use`)."""
    global _client, _db
    if _db is None:
        s = get_settings()
        _client = MongoClient(s.mongo_uri, tz_aware=True, serverSelectionTimeoutMS=5000)
        _db = _client[s.mongo_db]
        ensure_indexes(_db)
    return _db


def use(database: Database) -> None:
    global _db
    _db = database
    ensure_indexes(database)


def ensure_indexes(d: Database) -> None:
    d[COMPANIES].create_index("domain", unique=True, partialFilterExpression={"domain": {"$type": "string"}})
    d[COMPANIES].create_index("normalized_name")
    d[COMPANIES].create_index([("country", ASCENDING), ("origin", ASCENDING)])
    d[DOCUMENTS].create_index([("company_id", ASCENDING), ("content_hash", ASCENDING)], unique=True)
    d[DOCUMENTS].create_index([("company_id", ASCENDING), ("source_type", ASCENDING), ("fetched_at", DESCENDING)])
    d[SIGNALS].create_index([("company_id", ASCENDING), ("detected_at", ASCENDING)])
    d[SIGNALS].create_index("question_id")
    d[SIGNALS].create_index("rule_id")
    d[EVENTS].create_index([("company_id", ASCENDING), ("event_date", DESCENDING)])
    d[LEAD_SCORES].create_index([("company_id", ASCENDING), ("service_id", ASCENDING)], unique=True)
    d[LEAD_SCORES].create_index([("final_score", DESCENDING)])
    d[RUNS].create_index("status")


def next_id(collection: str) -> int:
    row = db()[COUNTERS].find_one_and_update(
        {"_id": collection}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return int(row["seq"])


def insert(collection: str, data: dict) -> MDoc:
    doc = {k: v for k, v in data.items() if k != "id"}
    doc["_id"] = next_id(collection)
    db()[collection].insert_one(doc)
    return wrap(doc)


def get(collection: str, obj_id: int) -> MDoc | None:
    return wrap(db()[collection].find_one({"_id": obj_id}))


def update(collection: str, obj_id: int, fields: dict) -> None:
    fields = {k: v for k, v in fields.items() if k != "id"}
    if fields:
        db()[collection].update_one({"_id": obj_id}, {"$set": fields})


def find(collection: str, query: dict | None = None, sort: list | None = None, limit: int = 0) -> list[MDoc]:
    cur = db()[collection].find(query or {})
    if sort:
        cur = cur.sort(sort)
    if limit:
        cur = cur.limit(limit)
    return wrap_all(cur)


def find_one(collection: str, query: dict, sort: list | None = None) -> MDoc | None:
    return wrap(db()[collection].find_one(query, sort=sort))


def ids(collection: str, query: dict | None = None) -> list[int]:
    return [r["_id"] for r in db()[collection].find(query or {}, {"_id": 1}).sort("_id", ASCENDING)]


# ------------------------------------------------------------------ companies


def company_defaults(data: dict) -> dict:
    from sales_pipeline.sources.companies import normalize_company_name

    now = utcnow()
    out = {
        "name": "", "domain": None, "industry": None, "employee_count": None, "revenue_musd": None, "country": None,
        "market": None, "description": "", "crunchbase_url": None, "linkedin_url": None, "careers_url": None, "ats": {},
        "is_existing_client": False, "is_competitor": False, "status": "active", "linkedin_validation": {},
        "aliases": [], "business_model": "unknown", "origin": "manual", "discovered_via": [], "registry_profiles": {},
        "tech_stack": [], "enriched_at": None, "created_at": now,
    }
    out.update({k: v for k, v in data.items() if k != "id"})
    out["normalized_name"] = normalize_company_name(out["name"])
    return out


def insert_company(data: dict) -> MDoc:
    """Raises DuplicateKeyError when the domain is already taken."""
    return insert(COMPANIES, company_defaults(data))


def update_company(company_id: int, fields: dict) -> None:
    if "name" in fields:
        from sales_pipeline.sources.companies import normalize_company_name

        fields = {**fields, "normalized_name": normalize_company_name(fields["name"])}
    update(COMPANIES, company_id, fields)


def domain_taken(domain: str, exclude_id: int | None = None) -> bool:
    q: dict = {"domain": domain}
    if exclude_id is not None:
        q["_id"] = {"$ne": exclude_id}
    return db()[COMPANIES].count_documents(q, limit=1) > 0


def delete_company(company_id: int) -> None:
    d = db()
    for coll in (DOCUMENTS, SIGNALS, EVENTS, LEAD_SCORES):
        d[coll].delete_many({"company_id": company_id})
    d[COMPANIES].delete_one({"_id": company_id})


# ------------------------------------------------------------------ documents


def store_document(company_id: int, doc) -> bool:
    """Store a sales_pipeline Document once per (company, content hash); True when new."""
    try:
        insert(
            DOCUMENTS,
            {
                "company_id": company_id, "source_type": doc.source_type, "url": doc.url[:2000], "title": doc.title,
                "content": doc.text, "source": doc.source[:300], "published_at": doc.published_at,
                "content_hash": doc.content_hash, "meta": doc.meta or {}, "fetched_at": utcnow(),
            },
        )
        return True
    except DuplicateKeyError:
        return False


# ------------------------------------------------------------------ runs


def create_run(**fields: Any) -> MDoc:
    data = {
        "status": "queued", "kind": "enrichment", "started_at": None, "finished_at": None, "params": {}, "progress": {},
        "stats": {}, "log": [], "error": None, "created_at": utcnow(),
    }
    data.update(fields)
    return insert(RUNS, data)


def active_run() -> MDoc | None:
    return find_one(RUNS, {"status": {"$in": ["queued", "running"]}})


def log_run(run_id: int, message: str, keep: int = 300, **progress: Any) -> None:
    upd: dict = {"$push": {"log": {"$each": [{"t": utcnow().isoformat(), "msg": message}], "$slice": -keep}}}
    if progress:
        upd["$set"] = {f"progress.{k}": v for k, v in progress.items()}
    db()[RUNS].update_one({"_id": run_id}, upd)


# ------------------------------------------------------------------ cascades from PostgreSQL config


def forget_service(service_id: int, question_ids: list[int]) -> None:
    d = db()
    d[LEAD_SCORES].delete_many({"service_id": service_id})
    d[SIGNALS].delete_many({"$or": [{"service_id": service_id}, {"question_id": {"$in": question_ids}}]})


def forget_question(question_id: int, keep_manual: bool = False) -> None:
    q: dict = {"question_id": question_id}
    if keep_manual:
        q["origin"] = {"$ne": "manual"}
    db()[SIGNALS].delete_many(q)


def forget_rule(rule_id: int) -> None:
    db()[SIGNALS].delete_many({"rule_id": rule_id})
