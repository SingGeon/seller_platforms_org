"""Rule-based, explainable lead scoring (GIG-29) and score breakdown (GIG-30).

    signal_score = (Σ w·c·r over positive "yes" signals + event bonus
                    − Σ w·c·r over negative "yes" signals) / Σ w(positive questions) × 100
    final_score  = icp_weight × icp_fit + signal_weight × signal_score
    tier         = Hot ≥ hot_threshold, Warm ≥ warm_threshold, else Cold;
                   Disqualified when a hard rule matches.

Everything here is a pure function of already-stored data, so scores can be
recomputed instantly whenever the configuration changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .icp import icp_fit
from .rules import disqualification_reasons

DEFAULT_WEIGHTS = {"High": 3, "Medium": 2, "Low": 1}
DEFAULT_RECENCY = [[30, 1.0], [90, 0.7], [180, 0.4], [None, 0.1]]
EVENT_CONFIDENCE = 0.8


@dataclass
class ScoreParams:
    icp_weight: float = 0.3
    signal_weight: float = 0.7
    hot_threshold: float = 70
    warm_threshold: float = 40
    weight_values: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    recency_buckets: list = field(default_factory=lambda: [list(b) for b in DEFAULT_RECENCY])
    undated_recency: float = 0.5

    @classmethod
    def from_model(cls, cfg) -> "ScoreParams":
        if cfg is None:
            return cls()
        return cls(
            icp_weight=cfg.icp_weight,
            signal_weight=cfg.signal_weight,
            hot_threshold=cfg.hot_threshold,
            warm_threshold=cfg.warm_threshold,
            weight_values=cfg.weight_values or dict(DEFAULT_WEIGHTS),
            recency_buckets=cfg.recency_buckets or [list(b) for b in DEFAULT_RECENCY],
            undated_recency=cfg.undated_recency,
        )


@dataclass
class ScoreResult:
    icp_score: float
    signal_score: float
    final_score: float
    tier: str
    disqualified: bool
    disqualification_reasons: list[dict]
    outside_icp: bool
    breakdown: dict[str, Any]
    top_signals: list[dict]
    recommendation: str
    freshest_days: int | None


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _aware(value)
    if isinstance(value, str) and value and value != "unknown":
        try:
            return _aware(datetime.fromisoformat(value))
        except ValueError:
            return None
    return None


def recency_factor(when: datetime | None, params: ScoreParams, now: datetime) -> tuple[float, int | None]:
    when = _aware(when)
    if when is None:
        return params.undated_recency, None
    days = max(0, (now - when).days)
    for limit, factor in params.recency_buckets:
        if limit is None or days < limit:
            return float(factor), days
    return float(params.recency_buckets[-1][1]), days


def tier_for(score: float, params: ScoreParams) -> str:
    if score >= params.hot_threshold:
        return "Hot"
    if score >= params.warm_threshold:
        return "Warm"
    return "Cold"


def recommendation_for(tier: str, freshest_days: int | None) -> str:
    if tier == "Disqualified":
        return "exclude"
    if tier == "Hot":
        return "contact now" if freshest_days is None or freshest_days <= 90 else "nurture"
    if tier == "Warm":
        return "nurture"
    return "monitor"


def _event_weight(service, event) -> tuple[str | None, bool]:
    weights = (service.event_weights or {}) if service is not None else {}
    w = weights.get(f"{event.event_type}:{event.polarity}") or weights.get(event.event_type)
    return w, event.polarity == "negative"


def score_lead(
    *,
    company,
    service,
    icp,
    questions: list,
    signals_by_question: dict[int, Any],
    rules: list,
    rule_signals: dict[int, Any],
    events: list,
    params: ScoreParams | None = None,
    now: datetime | None = None,
) -> ScoreResult:
    params = params or ScoreParams()
    now = now or datetime.now(timezone.utc)
    wv = params.weight_values

    icp_res = icp_fit(company, icp)
    outside_icp = icp is not None and icp_res.score < (icp.min_fit or 0)

    contributions: list[dict] = []
    max_possible = sum(wv.get(q.weight, 1) for q in questions if q.active and not q.is_negative)
    raw = 0.0
    freshest: int | None = None
    for q in questions:
        if not q.active:
            continue
        sig = signals_by_question.get(q.id)
        w = wv.get(q.weight, 1)
        item = {
            "kind": "negative" if q.is_negative else "question",
            "question_id": q.id,
            "label": q.text,
            "weight": q.weight,
            "answer": sig.answer if sig else "unknown",
            "confidence": round(sig.confidence, 2) if sig else 0.0,
            "recency": None,
            "points": 0.0,
            "evidence": (sig.evidence or []) if sig else [],
        }
        if sig is not None and sig.answer == "yes":
            r, days = recency_factor(sig.signal_date, params, now)
            value = w * sig.confidence * r
            raw += -value if q.is_negative else value
            item["recency"] = r
            item["_value"] = -value if q.is_negative else value
            if not q.is_negative and days is not None:
                freshest = days if freshest is None else min(freshest, days)
        contributions.append(item)

    # Detected events mapped to this service add a bonus (or a penalty when negative).
    best_event: dict[str, dict] = {}
    for ev in events:
        weight_label, negative = _event_weight(service, ev)
        if not weight_label:
            continue
        r, days = recency_factor(ev.event_date, params, now)
        value = wv.get(weight_label, 1) * EVENT_CONFIDENCE * r * (-1 if negative else 1)
        key = f"{ev.event_type}:{'neg' if negative else 'pos'}"
        if key not in best_event or abs(value) > abs(best_event[key]["_value"]):
            best_event[key] = {
                "kind": "event",
                "event_type": ev.event_type,
                "label": ev.title,
                "weight": weight_label,
                "answer": "yes",
                "confidence": EVENT_CONFIDENCE,
                "recency": r,
                "points": 0.0,
                "evidence": [{"quote": ev.summary or ev.title, "url": ev.url, "date": ev.event_date.date().isoformat() if ev.event_date else "unknown"}],
                "_value": value,
                "_days": days,
            }
    # One article can yield several event types (e.g. a leadership change that is also a corporate event): it counts
    # once, with its strongest reading, so it is neither scored nor shown twice.
    by_article: dict[str, dict] = {}
    for key, item in best_event.items():
        url = (item["evidence"][0].get("url") or key).lower().rstrip("/")
        if url not in by_article or abs(item["_value"]) > abs(by_article[url]["_value"]):
            by_article[url] = item
    for item in by_article.values():
        raw += item["_value"]
        if item["_value"] > 0 and item["_days"] is not None:
            freshest = item["_days"] if freshest is None else min(freshest, item["_days"])
        contributions.append(item)

    signal_score = 0.0 if max_possible <= 0 else max(0.0, min(100.0, 100 * raw / max_possible))
    for item in contributions:
        v = item.pop("_value", 0.0)
        item.pop("_days", None)
        item["points"] = round(100 * v / max_possible, 1) if max_possible else 0.0

    final = round(params.icp_weight * icp_res.score + params.signal_weight * signal_score, 1)
    reasons = disqualification_reasons(rules, company, rule_signals)
    disqualified = bool(reasons)
    tier = "Disqualified" if disqualified else tier_for(final, params)

    positives = sorted((c for c in contributions if c["points"] > 0 and c["evidence"]), key=lambda c: -c["points"])
    top_signals = [
        {
            "label": c["label"],
            "kind": c["kind"],
            "points": c["points"],
            "quote": c["evidence"][0].get("quote", ""),
            "url": c["evidence"][0].get("url", ""),
            "date": c["evidence"][0].get("date", "unknown"),
        }
        for c in positives[:3]
    ]
    breakdown = {
        "formula": "final = {:.2f} × icp + {:.2f} × signal".format(params.icp_weight, params.signal_weight),
        "icp": {"score": icp_res.score, "components": icp_res.components, "weighted": round(params.icp_weight * icp_res.score, 1)},
        "signals": {
            "score": round(signal_score, 1),
            "weighted": round(params.signal_weight * signal_score, 1),
            "max_possible_weight": max_possible,
            "items": sorted(contributions, key=lambda c: -abs(c["points"])),
        },
        "outside_icp": outside_icp,
    }
    return ScoreResult(
        icp_score=icp_res.score,
        signal_score=round(signal_score, 1),
        final_score=final,
        tier=tier,
        disqualified=disqualified,
        disqualification_reasons=reasons,
        outside_icp=outside_icp,
        breakdown=breakdown,
        top_signals=top_signals,
        recommendation=recommendation_for(tier, freshest),
        freshest_days=freshest,
    )


def signal_date_from_evidence(evidence: list[dict]) -> datetime | None:
    dates = [d for d in (_parse_date(e.get("date")) for e in evidence or []) if d]
    return max(dates) if dates else None
