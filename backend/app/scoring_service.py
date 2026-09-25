"""Load stored data, run the scoring engine and upsert `lead_scores`.

Configuration (services, ICP, questions, rules, weights) comes from PostgreSQL; companies,
signals, events and the resulting scores live in MongoDB."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import mongo
from .models import DisqualificationRule, ScoringConfig, Service, SignalQuestion
from .mongo import MDoc
from .scoring import ScoreParams, score_lead

BATCH = 500


def get_scoring_config(db: Session) -> ScoringConfig:
    cfg = db.scalar(select(ScoringConfig).limit(1))
    if cfg is None:
        cfg = ScoringConfig()
        db.add(cfg)
        db.flush()
    return cfg


def pick_latest(signals: list[MDoc]) -> tuple[dict[int, MDoc], dict[int, MDoc]]:
    """Latest signal per question and per llm_question rule (input sorted oldest first). Manual
    signals win over AI ones detected at the same time or later, because a rep validated them."""
    by_q: dict[int, MDoc] = {}
    by_rule: dict[int, MDoc] = {}
    for s in signals:
        if s.question_id is not None:
            prev = by_q.get(s.question_id)
            if prev is not None and prev.origin == "manual" and s.origin != "manual":
                continue
            by_q[s.question_id] = s
        elif s.rule_id is not None:
            by_rule[s.rule_id] = s
    return by_q, by_rule


def latest_signals(company_id: int) -> tuple[dict[int, MDoc], dict[int, MDoc]]:
    return pick_latest(mongo.find(mongo.SIGNALS, {"company_id": company_id}, sort=[("detected_at", ASCENDING), ("_id", ASCENDING)]))


def _config(db: Session, service_ids: list[int] | None):
    stmt = select(Service).where(Service.active.is_(True))
    if service_ids:
        stmt = stmt.where(Service.id.in_(service_ids))
    services = list(db.scalars(stmt))
    questions = defaultdict(list)
    for q in db.scalars(select(SignalQuestion)):
        questions[q.service_id].append(q)
    rules = {
        s.id: list(db.scalars(select(DisqualificationRule).where(or_(DisqualificationRule.service_id == s.id, DisqualificationRule.service_id.is_(None)))))
        for s in services
    }
    return services, questions, rules


def compute_lead(db: Session, company: MDoc, service: Service, params: ScoreParams | None = None, now: datetime | None = None):
    params = params or ScoreParams.from_model(get_scoring_config(db))
    questions = list(db.scalars(select(SignalQuestion).where(SignalQuestion.service_id == service.id)))
    rules = list(db.scalars(select(DisqualificationRule).where(or_(DisqualificationRule.service_id == service.id, DisqualificationRule.service_id.is_(None)))))
    by_q, by_rule = latest_signals(company.id)
    events = mongo.find(mongo.EVENTS, {"company_id": company.id})
    return score_lead(
        company=company, service=service, icp=service.icp, questions=questions, signals_by_question=by_q, rules=rules,
        rule_signals=by_rule, events=events, params=params, now=now,
    )


def recompute_scores(db: Session, company_ids: list[int] | None = None, service_ids: list[int] | None = None) -> list[MDoc]:
    params = ScoreParams.from_model(get_scoring_config(db))
    db.commit()
    services, questions, rules = _config(db, service_ids)
    if not services:
        return []
    now = datetime.now(timezone.utc)
    all_ids = company_ids if company_ids else mongo.ids(mongo.COMPANIES)
    out: list[MDoc] = []
    coll = mongo.db()[mongo.LEAD_SCORES]
    for i in range(0, len(all_ids), BATCH):
        chunk = all_ids[i : i + BATCH]
        companies = mongo.find(mongo.COMPANIES, {"_id": {"$in": chunk}})
        sigs: dict[int, list[MDoc]] = defaultdict(list)
        for s in mongo.find(mongo.SIGNALS, {"company_id": {"$in": chunk}}, sort=[("detected_at", ASCENDING), ("_id", ASCENDING)]):
            sigs[s.company_id].append(s)
        events: dict[int, list[MDoc]] = defaultdict(list)
        for e in mongo.find(mongo.EVENTS, {"company_id": {"$in": chunk}}):
            events[e.company_id].append(e)
        existing = {
            (r.company_id, r.service_id): r
            for r in mongo.find(mongo.LEAD_SCORES, {"company_id": {"$in": chunk}, "service_id": {"$in": [s.id for s in services]}})
        }
        for company in companies:
            by_q, by_rule = pick_latest(sigs[company.id])
            for service in services:
                res = score_lead(
                    company=company, service=service, icp=service.icp, questions=questions[service.id], signals_by_question=by_q,
                    rules=rules[service.id], rule_signals=by_rule, events=events[company.id], params=params, now=now,
                )
                prev = existing.get((company.id, service.id))
                previous_score = prev.previous_score if prev else None
                score_changed_at = prev.score_changed_at if prev else None
                if prev is not None and abs((prev.final_score or 0) - res.final_score) >= 0.5:
                    previous_score = prev.final_score
                    score_changed_at = now
                prev_exp = (prev.explanation or {}) if prev else {}
                fields = {
                    "icp_score": res.icp_score, "signal_score": res.signal_score, "final_score": res.final_score, "tier": res.tier,
                    "disqualified": res.disqualified, "disqualification_reasons": res.disqualification_reasons,
                    "breakdown": res.breakdown,
                    "explanation": {
                        # The AI summary is only regenerated by a pipeline run or /explain; keep it
                        # while the underlying top signals are unchanged.
                        "summary": prev_exp.get("summary", "") if prev_exp.get("top_signals", []) == res.top_signals else "",
                        "top_signals": res.top_signals,
                        "recommendation": res.recommendation,
                        "freshest_signal_days": res.freshest_days,
                    },
                    "previous_score": previous_score, "score_changed_at": score_changed_at, "computed_at": now,
                }
                if prev is None:
                    try:
                        row = mongo.insert(mongo.LEAD_SCORES, {"company_id": company.id, "service_id": service.id, **fields})
                    except DuplicateKeyError:  # a concurrent recompute created it first
                        coll.update_one({"company_id": company.id, "service_id": service.id}, {"$set": fields})
                        row = mongo.find_one(mongo.LEAD_SCORES, {"company_id": company.id, "service_id": service.id})
                else:
                    coll.update_one({"_id": prev.id}, {"$set": fields})
                    row = MDoc({**prev, **fields})
                out.append(row)
    return out
