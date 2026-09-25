"""PostgreSQL schema: seller accounts and configuration. Companies and everything about them
(documents, signals, events, scores, runs, LLM cache) live in MongoDB, see mongo.py."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
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
    # Markets that discovery sources search (ISO-2); "change the country" = edit this list.
    discovery_countries: Mapped[list] = mapped_column(JSONType, default=lambda: ["RO", "MD"])


class SourceState(Base):
    """Per-source sync state (GIG-14 refresh rules): cursor, schedule and last outcome."""

    __tablename__ = "source_state"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = catalogue default
    cursor: Mapped[dict] = mapped_column(JSONType, default=dict)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(20), default="never")  # never | ok | error | skipped
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_stats: Mapped[dict] = mapped_column(JSONType, default=dict)  # fetched, items, new_companies, new_documents
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    total_new_companies: Mapped[int] = mapped_column(Integer, default=0)


class Seller(Base):
    """A sales rep (or admin) account. The password is stored in plain text (team decision, see README)."""

    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="seller")  # seller | admin
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list["SellerSession"]] = relationship(back_populates="seller", cascade="all, delete-orphan")


class SellerSession(Base):
    """Bearer token issued at login (only its SHA-256 is stored)."""

    __tablename__ = "seller_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    seller: Mapped[Seller] = relationship(back_populates="sessions")


class LeadAssignment(Base):
    """CRM state of a company for the sales team: pipeline stage, owner and notes.
    `company_id` points to a MongoDB `companies` document (no FK across databases)."""

    __tablename__ = "lead_assignments"

    company_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int | None] = mapped_column(ForeignKey("sellers.id", ondelete="SET NULL"), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(20), default="nou")  # nou | calificat | contactat | negociere | castigat | descalificat
    notes: Mapped[list] = mapped_column(JSONType, default=list)  # [{t, seller_id, author, text}]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    seller: Mapped[Seller | None] = relationship()
