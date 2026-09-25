"""Configuration API: services, ICP (GIG-15), signal questions (GIG-16),
disqualification rules (GIG-17) and scoring parameters (GIG-29)."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import mongo
from ..models import DisqualificationRule, IcpCriteria, Service, SignalQuestion
from ..schemas import (
    IcpIn, IcpOut, QuestionIn, QuestionOut, RuleIn, RuleOut, ScoringConfigIn, ScoringConfigOut, ServiceIn, ServiceOut,
)
from ..scoring.rules import RULE_FIELDS
from ..scoring_service import get_scoring_config, recompute_scores
from .deps import get_db, get_or_404

router = APIRouter()


# ------------------------------------------------------------------ services
@router.get("/services", response_model=list[ServiceOut], tags=["config"])
def list_services(db: Session = Depends(get_db)):
    return list(db.scalars(select(Service).order_by(Service.id)))


@router.post("/services", response_model=ServiceOut, status_code=201, tags=["config"])
def create_service(body: ServiceIn, db: Session = Depends(get_db)):
    svc = Service(**body.model_dump())
    db.add(svc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A service with this name or slug already exists")
    return svc


@router.get("/services/{service_id}", response_model=ServiceOut, tags=["config"])
def get_service(service_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, Service, service_id)


@router.put("/services/{service_id}", response_model=ServiceOut, tags=["config"])
def update_service(service_id: int, body: ServiceIn, db: Session = Depends(get_db)):
    svc = get_or_404(db, Service, service_id)
    for k, v in body.model_dump().items():
        setattr(svc, k, v)
    db.commit()
    recompute_scores(db, service_ids=[service_id])
    return svc


@router.delete("/services/{service_id}", status_code=204, tags=["config"])
def delete_service(service_id: int, db: Session = Depends(get_db)):
    svc = get_or_404(db, Service, service_id)
    question_ids = [q.id for q in svc.questions]
    db.delete(svc)
    db.commit()
    mongo.forget_service(service_id, question_ids)
    return Response(status_code=204)


# ------------------------------------------------------------------ ICP
@router.get("/icp", response_model=list[IcpOut], tags=["config"])
def list_icp(db: Session = Depends(get_db)):
    return list(db.scalars(select(IcpCriteria)))


@router.get("/icp/{service_id}", response_model=IcpOut, tags=["config"])
def get_icp(service_id: int, db: Session = Depends(get_db)):
    icp = db.scalar(select(IcpCriteria).where(IcpCriteria.service_id == service_id))
    if icp is None:
        raise HTTPException(404, "No ICP defined for this service")
    return icp


@router.put("/icp/{service_id}", response_model=IcpOut, tags=["config"])
def upsert_icp(service_id: int, body: IcpIn, db: Session = Depends(get_db)):
    get_or_404(db, Service, service_id)
    icp = db.scalar(select(IcpCriteria).where(IcpCriteria.service_id == service_id))
    if icp is None:
        icp = IcpCriteria(service_id=service_id)
        db.add(icp)
    data = body.model_dump()
    data["countries"] = [c.upper() for c in data["countries"]]
    for k, v in data.items():
        setattr(icp, k, v)
    db.commit()
    recompute_scores(db, service_ids=[service_id])
    return icp


@router.delete("/icp/{service_id}", status_code=204, tags=["config"])
def delete_icp(service_id: int, db: Session = Depends(get_db)):
    icp = db.scalar(select(IcpCriteria).where(IcpCriteria.service_id == service_id))
    if icp:
        db.delete(icp)
        db.commit()
        recompute_scores(db, service_ids=[service_id])
    return Response(status_code=204)


# ------------------------------------------------------------------ questions
@router.get("/services/{service_id}/questions", response_model=list[QuestionOut], tags=["config"])
def list_questions(service_id: int, db: Session = Depends(get_db)):
    get_or_404(db, Service, service_id)
    return list(db.scalars(select(SignalQuestion).where(SignalQuestion.service_id == service_id).order_by(SignalQuestion.id)))


@router.post("/services/{service_id}/questions", response_model=QuestionOut, status_code=201, tags=["config"])
def create_question(service_id: int, body: QuestionIn, db: Session = Depends(get_db)):
    get_or_404(db, Service, service_id)
    q = SignalQuestion(service_id=service_id, **body.model_dump())
    db.add(q)
    db.commit()
    recompute_scores(db, service_ids=[service_id])
    return q


@router.put("/services/{service_id}/questions/{question_id}", response_model=QuestionOut, tags=["config"])
def update_question(service_id: int, question_id: int, body: QuestionIn, db: Session = Depends(get_db)):
    q = get_or_404(db, SignalQuestion, question_id)
    if q.service_id != service_id:
        raise HTTPException(404, "Question does not belong to this service")
    text_changed = q.text != body.text
    for k, v in body.model_dump().items():
        setattr(q, k, v)
    db.commit()
    if text_changed:
        # Old answers were for a different question; drop them so the next run re-asks.
        mongo.forget_question(question_id, keep_manual=True)
    recompute_scores(db, service_ids=[service_id])
    return q


@router.delete("/services/{service_id}/questions/{question_id}", status_code=204, tags=["config"])
def delete_question(service_id: int, question_id: int, db: Session = Depends(get_db)):
    q = get_or_404(db, SignalQuestion, question_id)
    if q.service_id != service_id:
        raise HTTPException(404, "Question does not belong to this service")
    db.delete(q)
    db.commit()
    mongo.forget_question(question_id)
    recompute_scores(db, service_ids=[service_id])
    return Response(status_code=204)


# ------------------------------------------------------------------ rules
def _validate_rule(body: RuleIn) -> None:
    if body.rule_type == "field_rule":
        if body.field not in RULE_FIELDS or not body.operator:
            raise HTTPException(422, f"field_rule needs operator and field in {sorted(RULE_FIELDS)}")
    elif not body.question:
        raise HTTPException(422, "llm_question rule needs a question")



@router.get("/rules", response_model=list[RuleOut], tags=["config"])
def list_all_rules(db: Session = Depends(get_db)):
    return list(db.scalars(select(DisqualificationRule).order_by(DisqualificationRule.id)))


@router.post("/rules", response_model=RuleOut, status_code=201, tags=["config"], summary="Create a global rule (all services)")
def create_global_rule(body: RuleIn, db: Session = Depends(get_db)):
    _validate_rule(body)
    rule = DisqualificationRule(service_id=None, **body.model_dump())
    db.add(rule)
    db.commit()
    recompute_scores(db)
    return rule


@router.get("/services/{service_id}/rules", response_model=list[RuleOut], tags=["config"])
def list_rules(service_id: int, db: Session = Depends(get_db)):
    get_or_404(db, Service, service_id)
    return list(
        db.scalars(
            select(DisqualificationRule)
            .where((DisqualificationRule.service_id == service_id) | DisqualificationRule.service_id.is_(None))
            .order_by(DisqualificationRule.id)
        )
    )


@router.post("/services/{service_id}/rules", response_model=RuleOut, status_code=201, tags=["config"])
def create_rule(service_id: int, body: RuleIn, db: Session = Depends(get_db)):
    get_or_404(db, Service, service_id)
    _validate_rule(body)
    rule = DisqualificationRule(service_id=service_id, **body.model_dump())
    db.add(rule)
    db.commit()
    recompute_scores(db, service_ids=[service_id])
    return rule


@router.put("/rules/{rule_id}", response_model=RuleOut, tags=["config"])
def update_rule(rule_id: int, body: RuleIn, db: Session = Depends(get_db)):
    rule = get_or_404(db, DisqualificationRule, rule_id)
    _validate_rule(body)
    for k, v in body.model_dump().items():
        setattr(rule, k, v)
    db.commit()
    recompute_scores(db)
    return rule


@router.delete("/rules/{rule_id}", status_code=204, tags=["config"])
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, DisqualificationRule, rule_id))
    db.commit()
    mongo.forget_rule(rule_id)
    recompute_scores(db)
    return Response(status_code=204)


# ------------------------------------------------------------------ scoring config
@router.get("/scoring-config", response_model=ScoringConfigOut, tags=["config"])
def read_scoring_config(db: Session = Depends(get_db)):
    cfg = get_scoring_config(db)
    db.commit()
    return cfg


@router.put("/scoring-config", response_model=ScoringConfigOut, tags=["config"])
def update_scoring_config(body: ScoringConfigIn, db: Session = Depends(get_db)):
    if body.warm_threshold > body.hot_threshold:
        raise HTTPException(422, "warm_threshold must be <= hot_threshold")
    cfg = get_scoring_config(db)
    data = body.model_dump()
    data["recency_buckets"] = [list(b) for b in data["recency_buckets"]]
    data["discovery_countries"] = [c.strip().upper() for c in data["discovery_countries"] if len(c.strip()) == 2]
    for k, v in data.items():
        setattr(cfg, k, v)
    db.commit()
    recompute_scores(db)
    return cfg


@router.post("/scores/recompute", tags=["config"])
def recompute(db: Session = Depends(get_db)):
    rows = recompute_scores(db)
    return {"recomputed": len(rows)}
