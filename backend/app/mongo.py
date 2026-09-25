"""MongoDB store: companies and everything collected or inferred about them.

Collections (integer ids from `counters`, so API URLs and the frontend keep numeric ids):

    companies        firmographics, registry profiles, discovery trace, LinkedIn validation
    documents        collected news / web / jobs / registry text, deduped per company by content hash
    signals          AI (or manual) answers to signal questions and llm_question rules, with evidence
    company_events   alerts detected by the AI: incidents, leadership changes, compliance, ...
    lead_scores      one score per company x service, with breakdown and "why now"
    pipeline_runs    enrichment / discovery / bootstrap runs with progress, stats and log
    llm_cache        LLM responses keyed by (task, model, company, question, passages)
    activity_log     who did what: seller actions (seller_id -> PostgreSQL sellers.id) and system events

Every collection has a $jsonSchema validator (SCHEMAS) so the documents keep a fixed structure.

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
ACTIVITY = "activity_log"
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


INT = ["int", "long"]
NUM = ["int", "long", "double", "decimal"]
OPT_INT = ["int", "long", "null"]
OPT_STR = ["string", "null"]
OPT_DATE = ["date", "null"]

# Structure of every collection. validationLevel "moderate" checks inserts and updates of valid documents.
SCHEMAS: dict[str, dict] = {
    COMPANIES: {
        "required": ["name", "normalized_name", "origin", "created_at"],
        "properties": {
            "name": {"bsonType": "string", "minLength": 1}, "normalized_name": {"bsonType": "string"},
            "domain": {"bsonType": OPT_STR}, "industry": {"bsonType": OPT_STR}, "country": {"bsonType": OPT_STR},
            "employee_count": {"bsonType": [*NUM, "null"]}, "revenue_musd": {"bsonType": [*NUM, "null"]},
            "status": {"bsonType": "string"}, "business_model": {"enum": ["b2b", "b2c", "mixed", "unknown"]},
            "origin": {"bsonType": "string"}, "is_existing_client": {"bsonType": "bool"}, "is_competitor": {"bsonType": "bool"},
            "aliases": {"bsonType": "array"}, "discovered_via": {"bsonType": "array"}, "tech_stack": {"bsonType": "array"},
            "registry_profiles": {"bsonType": "object"}, "linkedin_validation": {"bsonType": "object"}, "ats": {"bsonType": "object"},
            "enriched_at": {"bsonType": OPT_DATE}, "created_at": {"bsonType": "date"},
        },
    },
    DOCUMENTS: {
        "required": ["company_id", "source_type", "url", "content_hash", "fetched_at"],
        "properties": {
            "company_id": {"bsonType": INT}, "source_type": {"bsonType": "string"}, "url": {"bsonType": "string"},
            "title": {"bsonType": "string"}, "content": {"bsonType": "string"}, "content_hash": {"bsonType": "string"},
            "published_at": {"bsonType": OPT_DATE}, "fetched_at": {"bsonType": "date"}, "meta": {"bsonType": "object"},
        },
    },
    SIGNALS: {
        "required": ["company_id", "origin", "answer", "confidence", "evidence", "detected_at"],
        "properties": {
            "company_id": {"bsonType": INT}, "service_id": {"bsonType": OPT_INT}, "question_id": {"bsonType": OPT_INT},
            "rule_id": {"bsonType": OPT_INT}, "run_id": {"bsonType": OPT_INT}, "seller_id": {"bsonType": OPT_INT},
            "origin": {"enum": ["question", "rule", "manual"]}, "answer": {"enum": ["yes", "no", "unknown"]},
            "confidence": {"bsonType": NUM, "minimum": 0, "maximum": 1}, "evidence": {"bsonType": "array"},
            "signal_date": {"bsonType": OPT_DATE}, "detected_at": {"bsonType": "date"},
        },
    },
    EVENTS: {
        "required": ["company_id", "event_type", "title", "detected_at"],
        "properties": {
            "company_id": {"bsonType": INT}, "event_type": {"bsonType": "string"}, "title": {"bsonType": "string"},
            "polarity": {"enum": ["positive", "negative", "neutral"]}, "event_date": {"bsonType": OPT_DATE},
            "url": {"bsonType": "string"}, "detected_at": {"bsonType": "date"},
        },
    },
    LEAD_SCORES: {
        "required": ["company_id", "service_id", "final_score", "tier", "computed_at"],
        "properties": {
            "company_id": {"bsonType": INT}, "service_id": {"bsonType": INT},
            "icp_score": {"bsonType": NUM}, "signal_score": {"bsonType": NUM}, "final_score": {"bsonType": NUM, "minimum": 0, "maximum": 100},
            "tier": {"enum": ["Hot", "Warm", "Cold", "Disqualified"]}, "disqualified": {"bsonType": "bool"},
            "breakdown": {"bsonType": "object"}, "explanation": {"bsonType": "object"},
            "previous_score": {"bsonType": [*NUM, "null"]}, "score_changed_at": {"bsonType": OPT_DATE}, "computed_at": {"bsonType": "date"},
        },
    },
    RUNS: {
        "required": ["status", "kind", "log", "created_at"],
        "properties": {
            "status": {"enum": ["queued", "running", "succeeded", "failed"]}, "kind": {"enum": ["enrichment", "discovery", "bootstrap"]},
            "params": {"bsonType": "object"}, "progress": {"bsonType": "object"}, "stats": {"bsonType": "object"},
            "log": {"bsonType": "array"}, "error": {"bsonType": OPT_STR}, "seller_id": {"bsonType": OPT_INT},
            "started_at": {"bsonType": OPT_DATE}, "finished_at": {"bsonType": OPT_DATE}, "created_at": {"bsonType": "date"},
        },
    },
    LLM_CACHE: {"required": ["value", "created_at"], "properties": {"created_at": {"bsonType": "date"}}},
    ACTIVITY: {
        "required": ["t", "action"],
        "properties": {
            "t": {"bsonType": "date"}, "action": {"bsonType": "string"}, "seller_id": {"bsonType": OPT_INT},
            "seller": {"bsonType": OPT_STR}, "company_id": {"bsonType": OPT_INT}, "details": {"bsonType": "object"},
        },
    },
}


def ensure_schema(d: Database) -> None:
    existing = set(d.list_collection_names())
    for name, spec in SCHEMAS.items():
        validator = {"$jsonSchema": {"bsonType": "object", **spec}}
        if name in existing:
            d.command("collMod", name, validator=validator, validationLevel="moderate", validationAction="error")
        else:
            d.create_collection(name, validator=validator, validationLevel="moderate", validationAction="error")


def ensure_indexes(d: Database) -> None:
    ensure_schema(d)
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
    d[ACTIVITY].create_index([("company_id", ASCENDING), ("t", DESCENDING)])
    d[ACTIVITY].create_index([("seller_id", ASCENDING), ("t", DESCENDING)])


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
    for coll in (DOCUMENTS, SIGNALS, EVENTS, LEAD_SCORES, ACTIVITY):
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


# ------------------------------------------------------------------ activity log (seller ids point to PostgreSQL)


def log_activity(action: str, seller=None, company_id: int | None = None, **details: Any) -> None:
    """Record who did what. `seller` is a PostgreSQL `Seller` (or None for the system)."""
    db()[ACTIVITY].insert_one({
        "t": utcnow(), "action": action, "seller_id": getattr(seller, "id", None), "seller": getattr(seller, "full_name", None),
        "company_id": company_id, "details": details,
    })
