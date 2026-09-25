"""API contract (GIG-32). Frontend mocks should follow these shapes."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Weight = Literal["High", "Medium", "Low"]
SourceHint = Literal["news", "web", "jobs", "any"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- configuration


class ServiceIn(BaseModel):
    name: str
    slug: str
    description: str = ""
    value_proposition: str = ""
    event_weights: dict[str, Weight] = Field(default_factory=dict)
    active: bool = True


class ServiceOut(ORM, ServiceIn):
    id: int


class IcpIn(BaseModel):
    markets: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    employee_min: int | None = None
    employee_max: int | None = None
    revenue_min: float | None = None
    revenue_max: float | None = None
    min_fit: int = Field(0, ge=0, le=100)


class IcpOut(ORM, IcpIn):
    id: int
    service_id: int


class QuestionIn(BaseModel):
    text: str = Field(min_length=5)
    weight: Weight = "Medium"
    source_hint: SourceHint = "any"
    lookback_days: int = Field(365, ge=1, le=3650)
    is_negative: bool = False
    keywords: list[str] = Field(default_factory=list)
    active: bool = True


class QuestionOut(ORM, QuestionIn):
    id: int
    service_id: int


class RuleIn(BaseModel):
    name: str
    rule_type: Literal["field_rule", "llm_question"]
    field: str | None = None
    operator: Literal["eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in", "is_true", "is_false", "contains"] | None = None
    value: Any = None
    question: str | None = None
    keywords: list[str] = Field(default_factory=list)
    min_confidence: float = Field(0.7, ge=0, le=1)
    active: bool = True


class RuleOut(ORM, RuleIn):
    id: int
    service_id: int | None


class ScoringConfigIn(BaseModel):
    icp_weight: float = Field(0.3, ge=0, le=1)
    signal_weight: float = Field(0.7, ge=0, le=1)
    hot_threshold: float = Field(70, ge=0, le=100)
    warm_threshold: float = Field(40, ge=0, le=100)
    weight_values: dict[Weight, float] = Field(default_factory=lambda: {"High": 3, "Medium": 2, "Low": 1})
    recency_buckets: list[tuple[int | None, float]] = Field(default_factory=lambda: [(30, 1.0), (90, 0.7), (180, 0.4), (None, 0.1)])
    undated_recency: float = Field(0.5, ge=0, le=1)


class ScoringConfigOut(ORM, ScoringConfigIn):
    id: int


# ---------------------------------------------------------------- companies


class CompanyIn(BaseModel):
    name: str
    domain: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    revenue_musd: float | None = None
    country: str | None = Field(None, min_length=2, max_length=2)
    market: str | None = None
    description: str = ""
    crunchbase_url: str | None = None
    linkedin_url: str | None = None
    careers_url: str | None = None
    ats: dict[str, str] = Field(default_factory=dict)
    is_existing_client: bool = False
    is_competitor: bool = False
    status: str = "active"


class CompanyOut(ORM, CompanyIn):
    id: int
    linkedin_validation: dict = Field(default_factory=dict)
    created_at: datetime


class LinkedinValidationIn(BaseModel):
    """Manual LinkedIn / Sales Navigator validation (GIG-24). Entered by a rep; never scraped."""

    decision_makers: list[dict[str, str]] = Field(default_factory=list)  # [{name, title, profile_url}]
    notes: str = ""
    validated_by: str = ""
    management_change: bool | None = None


class ManualSignalIn(BaseModel):
    question_id: int
    answer: Literal["yes", "no", "unknown"]
    confidence: float = Field(0.9, ge=0, le=1)
    evidence_url: str | None = None
    evidence_quote: str = ""
    evidence_date: str | None = None
    note: str = ""
    created_by: str = "sales-rep"


class SignalOut(ORM):
    id: int
    company_id: int
    service_id: int | None
    question_id: int | None
    rule_id: int | None
    origin: str
    answer: str
    confidence: float
    evidence: list[dict]
    reasoning: str
    signal_date: datetime | None
    detected_at: datetime
    created_by: str | None = None


class EventOut(ORM):
    id: int
    event_type: str
    subtype: str
    title: str
    summary: str
    event_date: datetime | None
    url: str
    entities: list
    polarity: str


class DocumentOut(ORM):
    id: int
    source_type: str
    url: str
    title: str
    source: str
    published_at: datetime | None
    meta: dict
    fetched_at: datetime


class LeadOut(BaseModel):
    lead_id: int
    company_id: int
    company: str
    domain: str | None
    country: str | None
    industry: str | None
    employee_count: int | None
    service_id: int
    service: str
    icp_score: float
    signal_score: float
    final_score: float
    tier: str
    disqualified: bool
    disqualification_reasons: list[dict]
    outside_icp: bool
    top_signal: dict | None
    recommendation: str
    summary: str
    computed_at: datetime


class LeadDetail(ORM):
    service_id: int
    service: str
    icp_score: float
    signal_score: float
    final_score: float
    tier: str
    disqualified: bool
    disqualification_reasons: list[dict]
    breakdown: dict
    explanation: dict
    computed_at: datetime


class CompanyDetail(BaseModel):
    company: CompanyOut
    scores: list[LeadDetail]
    best_service: str | None
    signals: list[SignalOut]
    events: list[EventOut]
    documents_by_source: dict[str, int]


# ---------------------------------------------------------------- runs & outreach


class RunIn(BaseModel):
    company_ids: list[int] | None = None
    service_ids: list[int] | None = None
    sources: list[Literal["news", "web", "jobs"]] = Field(default_factory=lambda: ["news", "web", "jobs"])
    explain: bool = True


class RunOut(ORM):
    id: int
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    params: dict
    progress: dict
    stats: dict
    log: list
    error: str | None
    created_at: datetime


class OutreachOut(BaseModel):
    channel: str
    tone: str
    language: str
    subject: str = ""
    body: str = ""
    signals_used: list[str] = Field(default_factory=list)
    grounded: bool
    sources: list[dict]
    usage: dict
