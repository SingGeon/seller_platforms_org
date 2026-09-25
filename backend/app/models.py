"""PostgreSQL schema (GIG-13). See the ERD in README.md."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, JSONType


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    value_proposition: Mapped[str] = mapped_column(Text, default="")
    # Which detected event types feed this service's score, e.g. {"security_incident": "High"}.
    event_weights: Mapped[dict] = mapped_column(JSONType, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    icp: Mapped["IcpCriteria | None"] = relationship(back_populates="service", uselist=False, cascade="all, delete-orphan")
    questions: Mapped[list["SignalQuestion"]] = relationship(back_populates="service", cascade="all, delete-orphan")
    rules: Mapped[list["DisqualificationRule"]] = relationship(back_populates="service", cascade="all, delete-orphan")


class IcpCriteria(Base):
    __tablename__ = "icp_criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), unique=True)
    markets: Mapped[list] = mapped_column(JSONType, default=list)  # e.g. ["DACH", "Nordics", "EU"]
    industries: Mapped[list] = mapped_column(JSONType, default=list)
    countries: Mapped[list] = mapped_column(JSONType, default=list)  # ISO-2 codes
    employee_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employee_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revenue_min: Mapped[float | None] = mapped_column(Float, nullable=True)  # USD millions
    revenue_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_fit: Mapped[int] = mapped_column(Integer, default=0)  # leads below this ICP fit are filtered out

    service: Mapped[Service] = relationship(back_populates="icp")


class SignalQuestion(Base):
    __tablename__ = "signal_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    weight: Mapped[str] = mapped_column(String(10), default="Medium")  # High | Medium | Low
    source_hint: Mapped[str] = mapped_column(String(10), default="any")  # news | web | jobs | any
    lookback_days: Mapped[int] = mapped_column(Integer, default=365)
    is_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    keywords: Mapped[list] = mapped_column(JSONType, default=list)  # optional hints for the relevance filter
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    service: Mapped[Service] = relationship(back_populates="questions")


class DisqualificationRule(Base):
    __tablename__ = "disqualification_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL service_id = global rule applied to every service.
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    rule_type: Mapped[str] = mapped_column(String(20))  # field_rule | llm_question
    field: Mapped[str | None] = mapped_column(String(50), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(20), nullable=True)  # eq ne lt lte gt gte in not_in is_true contains
    value: Mapped[object | None] = mapped_column(JSONType, nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list] = mapped_column(JSONType, default=list)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.7)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    service: Mapped[Service | None] = relationship(back_populates="rules")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    domain: Mapped[str | None] = mapped_column(String(300), unique=True, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revenue_musd: Mapped[float | None] = mapped_column(Float, nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    market: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    crunchbase_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    careers_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ats: Mapped[dict] = mapped_column(JSONType, default=dict)  # {"greenhouse": "slug"}
    is_existing_client: Mapped[bool] = mapped_column(Boolean, default=False)
    is_competitor: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="active")  # active | insolvent | acquired
    # Manual LinkedIn validation (GIG-24): decision-makers, notes — entered by reps, never scraped.
    linkedin_validation: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RawDocument(Base):
    __tablename__ = "raw_documents"
    __table_args__ = (UniqueConstraint("company_id", "content_hash", name="uq_raw_documents_company_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(20), index=True)  # news | web | jobs | crunchbase | manual
    url: Mapped[str] = mapped_column(String(2000))
    title: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(300), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    meta: Mapped[dict] = mapped_column(JSONType, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), nullable=True, index=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("signal_questions.id", ondelete="CASCADE"), nullable=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("disqualification_rules.id", ondelete="CASCADE"), nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="question")  # question | rule | manual
    answer: Mapped[str] = mapped_column(String(10))  # yes | no | unknown
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[list] = mapped_column(JSONType, default=list)  # [{quote, url, date}]
    reasoning: Mapped[str] = mapped_column(Text, default="")
    signal_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)


class CompanyEvent(Base):
    __tablename__ = "company_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    subtype: Mapped[str] = mapped_column(String(100), default="")
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str] = mapped_column(String(2000))
    entities: Mapped[list] = mapped_column(JSONType, default=list)
    polarity: Mapped[str] = mapped_column(String(10), default="neutral")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LeadScore(Base):
    __tablename__ = "lead_scores"
    __table_args__ = (UniqueConstraint("company_id", "service_id", name="uq_lead_scores_company_service"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    icp_score: Mapped[float] = mapped_column(Float, default=0.0)
    signal_score: Mapped[float] = mapped_column(Float, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    tier: Mapped[str] = mapped_column(String(20), default="Cold")  # Hot | Warm | Cold | Disqualified
    disqualified: Mapped[bool] = mapped_column(Boolean, default=False)
    disqualification_reasons: Mapped[list] = mapped_column(JSONType, default=list)
    breakdown: Mapped[dict] = mapped_column(JSONType, default=dict)
    explanation: Mapped[dict] = mapped_column(JSONType, default=dict)  # {summary, top_signals, recommendation}
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScoringConfig(Base):
    """Single-row table with the tunable scoring parameters (GIG-29)."""

    __tablename__ = "scoring_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    icp_weight: Mapped[float] = mapped_column(Float, default=0.3)
    signal_weight: Mapped[float] = mapped_column(Float, default=0.7)
    hot_threshold: Mapped[float] = mapped_column(Float, default=70)
    warm_threshold: Mapped[float] = mapped_column(Float, default=40)
    weight_values: Mapped[dict] = mapped_column(JSONType, default=lambda: {"High": 3, "Medium": 2, "Low": 1})
    recency_buckets: Mapped[list] = mapped_column(
        JSONType, default=lambda: [[30, 1.0], [90, 0.7], [180, 0.4], [None, 0.1]]
    )
    undated_recency: Mapped[float] = mapped_column(Float, default=0.5)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | succeeded | failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    params: Mapped[dict] = mapped_column(JSONType, default=dict)
    progress: Mapped[dict] = mapped_column(JSONType, default=dict)  # {companies_total, companies_done, stage}
    stats: Mapped[dict] = mapped_column(JSONType, default=dict)  # per-source counts, tokens, cost
    log: Mapped[list] = mapped_column(JSONType, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LlmCache(Base):
    """Persistent LLM response cache keyed on (task, model, company, question, docs) (GIG-28)."""

    __tablename__ = "llm_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[object] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
