"""Typed contracts between the backend, collectors and the AI pipeline."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AnswerValue = Literal["yes", "no", "unknown"]
EventType = Literal[
    "security_incident",
    "leadership_change",
    "tech_stack",
    "compliance_event",
    "corporate_event",
]
EVENT_TYPES: tuple[str, ...] = (
    "security_incident",
    "leadership_change",
    "tech_stack",
    "compliance_event",
    "corporate_event",
)


class CompanyInfo(BaseModel):
    id: int | None = None
    name: str
    domain: str | None = None
    industry: str | None = None
    country: str | None = None
    employee_count: int | None = None
    careers_url: str | None = None
    ats: dict[str, str] = Field(default_factory=dict)  # e.g. {"greenhouse": "acme"}


class QuestionSpec(BaseModel):
    """A signal question (GIG-16) or an `llm_question` disqualification rule (GIG-17)."""

    key: str  # "q:12" for signal questions, "rule:3" for disqualifier rules
    text: str
    source_hint: Literal["news", "web", "jobs", "any"] = "any"
    lookback_days: int = 365
    keywords: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    quote: str
    url: str
    date: str = "unknown"


class Answer(BaseModel):
    key: str
    answer: AnswerValue = "unknown"
    confidence: float = 0.0
    evidence: list[Evidence] = Field(default_factory=list)
    reasoning: str = ""


class DetectedEvent(BaseModel):
    event_type: EventType
    subtype: str = ""
    title: str
    summary: str = ""
    date: str = "unknown"
    url: str
    entities: list[str] = Field(default_factory=list)
    polarity: Literal["positive", "negative", "neutral"] = "neutral"


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    cache_hits: int = 0
    cost_usd: float = 0.0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.llm_calls += other.llm_calls
        self.cache_hits += other.cache_hits
        self.cost_usd = round(self.cost_usd + other.cost_usd, 6)


class PipelineResult(BaseModel):
    company: CompanyInfo
    answers: list[Answer] = Field(default_factory=list)
    events: list[DetectedEvent] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    meta: dict[str, Any] = Field(default_factory=dict)
