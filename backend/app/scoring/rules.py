"""Hard disqualification rules (GIG-17).

`field_rule` rules evaluate structured company data; `llm_question` rules are
answered by the AI pipeline and read back from `signals` (origin="rule").
"""
from __future__ import annotations

from typing import Any

RULE_FIELDS = {
    "name", "domain", "industry", "employee_count", "revenue_musd", "country", "market",
    "is_existing_client", "is_competitor", "status", "business_model", "origin",
}
OPERATORS = {"eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in", "is_true", "is_false", "contains"}


def _norm(v: Any) -> Any:
    return v.lower() if isinstance(v, str) else v


def evaluate_field_rule(rule, company) -> bool:
    """True when the rule matches, i.e. the company is disqualified."""
    if rule.field not in RULE_FIELDS:
        return False
    actual = getattr(company, rule.field, None)
    op, expected = rule.operator, rule.value
    if op == "is_true":
        return bool(actual)
    if op == "is_false":
        return not actual
    if actual is None:
        return False  # unknown data never disqualifies
    a = _norm(actual)
    if op in ("in", "not_in"):
        values = [_norm(x) for x in (expected or [])]
        return (a in values) if op == "in" else (a not in values)
    if op == "contains":
        return isinstance(a, str) and str(_norm(expected)) in a
    e = _norm(expected)
    try:
        return {
            "eq": lambda: a == e,
            "ne": lambda: a != e,
            "lt": lambda: float(a) < float(e),
            "lte": lambda: float(a) <= float(e),
            "gt": lambda: float(a) > float(e),
            "gte": lambda: float(a) >= float(e),
        }[op]()
    except (KeyError, TypeError, ValueError):
        return False


def disqualification_reasons(rules, company, rule_signals: dict[int, Any]) -> list[dict]:
    """`rule_signals` maps rule_id -> latest Signal for that llm_question rule."""
    reasons = []
    for rule in rules:
        if not rule.active:
            continue
        if rule.rule_type == "field_rule" and evaluate_field_rule(rule, company):
            reasons.append({"rule_id": rule.id, "rule": rule.name, "type": "field_rule", "detail": f"{rule.field} {rule.operator} {rule.value}"})
        elif rule.rule_type == "llm_question":
            sig = rule_signals.get(rule.id)
            if sig is not None and sig.answer == "yes" and sig.confidence >= rule.min_confidence:
                ev = (sig.evidence or [{}])[0]
                reasons.append(
                    {"rule_id": rule.id, "rule": rule.name, "type": "llm_question", "detail": sig.reasoning, "evidence": ev}
                )
    return reasons
