from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from app.scoring import ScoreParams, evaluate_field_rule, icp_fit, recency_factor, score_lead

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def company(**kw):
    base = dict(name="Acme", domain="acme.com", industry="Logistics", country="DE", market=None, employee_count=5000,
                revenue_musd=None, is_existing_client=False, is_competitor=False, status="active")
    return NS(**{**base, **kw})


def icp(**kw):
    base = dict(markets=["EU"], industries=["Logistics", "Banking"], countries=[], employee_min=1000, employee_max=100000,
                revenue_min=None, revenue_max=None, min_fit=40)
    return NS(**{**base, **kw})


def q(id, weight="High", negative=False):
    return NS(id=id, text=f"question {id}", weight=weight, is_negative=negative, active=True)


def sig(answer="yes", conf=1.0, days_ago=10):
    return NS(answer=answer, confidence=conf, signal_date=NOW - timedelta(days=days_ago),
              evidence=[{"quote": "evidence quote", "url": "https://x.example/a", "date": "2026-08-01"}], reasoning="r", origin="question")


def test_icp_full_partial_and_unknown():
    assert icp_fit(company(), icp()).score == 100
    # wrong industry: loses the industry third
    assert icp_fit(company(industry="Gaming"), icp()).score == pytest.approx(66.7, abs=0.1)
    # unknown size gets half credit
    assert icp_fit(company(employee_count=None), icp()).score == pytest.approx(83.3, abs=0.1)
    # 500 employees vs min 1000: partial credit, not zero
    partial = icp_fit(company(employee_count=500), icp()).components["size"]["fit"]
    assert 0 < partial < 1
    # market expands to countries
    assert icp_fit(company(country="US"), icp()).components["geography"]["fit"] == 0
    assert icp_fit(company(country="RO"), icp()).components["geography"]["fit"] == 1


def test_recency_buckets():
    p = ScoreParams()
    assert recency_factor(NOW - timedelta(days=5), p, NOW)[0] == 1.0
    assert recency_factor(NOW - timedelta(days=60), p, NOW)[0] == 0.7
    assert recency_factor(NOW - timedelta(days=120), p, NOW)[0] == 0.4
    assert recency_factor(NOW - timedelta(days=400), p, NOW)[0] == 0.1
    assert recency_factor(None, p, NOW)[0] == 0.5


def test_signal_formula_matches_spec():
    questions = [q(1, "High"), q(2, "Medium"), q(3, "Low"), q(4, "High", negative=True)]
    signals = {1: sig(conf=0.9, days_ago=10), 2: sig(conf=0.5, days_ago=60), 3: sig("no")}
    res = score_lead(company=company(), service=NS(event_weights={}), icp=icp(), questions=questions,
                     signals_by_question=signals, rules=[], rule_signals={}, events=[], now=NOW)
    # (3*0.9*1.0 + 2*0.5*0.7) / (3+2+1) * 100 = 56.67
    assert res.signal_score == pytest.approx(56.7, abs=0.1)
    assert res.final_score == pytest.approx(0.3 * 100 + 0.7 * 56.67, abs=0.1)
    assert res.tier == "Warm"
    assert res.recommendation == "nurture"
    assert res.top_signals[0]["label"] == "question 1"

    signals[4] = sig(conf=1.0, days_ago=5)  # negative signal subtracts its weight
    res2 = score_lead(company=company(), service=NS(event_weights={}), icp=icp(), questions=questions,
                      signals_by_question=signals, rules=[], rule_signals={}, events=[], now=NOW)
    assert res2.signal_score == pytest.approx(56.67 - 50, abs=0.1)


def test_events_add_bonus_and_hot_tier():
    questions = [q(1, "High")]
    events = [NS(event_type="security_incident", polarity="neutral", title="Ransomware attack", summary="s",
                 url="https://x.example/e", event_date=NOW - timedelta(days=3))]
    res = score_lead(company=company(), service=NS(event_weights={"security_incident": "High"}), icp=icp(), questions=questions,
                     signals_by_question={1: sig(conf=0.8)}, rules=[], rule_signals={}, events=events, now=NOW)
    assert res.signal_score == 100  # clamped
    assert res.tier == "Hot"
    assert res.recommendation == "contact now"
    assert any(i["kind"] == "event" for i in res.breakdown["signals"]["items"])


def test_disqualification_rules():
    rules = [
        NS(id=1, name="Existing client", rule_type="field_rule", field="is_existing_client", operator="is_true", value=None, active=True),
        NS(id=2, name="Too small", rule_type="field_rule", field="employee_count", operator="lt", value=50, active=True),
        NS(id=3, name="Insolvency", rule_type="llm_question", field=None, operator=None, value=None, active=True, min_confidence=0.7),
    ]
    base = dict(service=NS(event_weights={}), icp=icp(), questions=[q(1)], signals_by_question={1: sig()}, rules=rules, events=[], now=NOW)
    assert score_lead(company=company(), rule_signals={}, **base).tier != "Disqualified"
    res = score_lead(company=company(is_existing_client=True), rule_signals={}, **base)
    assert res.tier == "Disqualified" and res.disqualification_reasons[0]["rule"] == "Existing client"
    assert score_lead(company=company(employee_count=10), rule_signals={}, **base).disqualified
    assert score_lead(company=company(employee_count=None), rule_signals={}, **base).disqualified is False
    res = score_lead(company=company(), rule_signals={3: sig(conf=0.9)}, **base)
    assert res.disqualified and res.recommendation == "exclude"
    assert not score_lead(company=company(), rule_signals={3: sig(conf=0.5)}, **base).disqualified


def test_field_rule_operators():
    r = lambda op, field, value: NS(field=field, operator=op, value=value)  # noqa: E731
    c = company(country="RU")
    assert evaluate_field_rule(r("in", "country", ["ru", "by"]), c)
    assert not evaluate_field_rule(r("not_in", "country", ["RU"]), c)
    assert evaluate_field_rule(r("contains", "industry", "logist"), c)
    assert not evaluate_field_rule(r("gt", "unknown_field", 1), c)


def test_one_article_counts_once_even_when_it_yields_several_event_types():
    service = NS(event_weights={"leadership_change": "Low", "corporate_event": "Low"})
    url = "https://news.example/new-ceo"
    both = [NS(event_type=t, polarity="positive", title="New CEO", summary="s", url=url, event_date=NOW - timedelta(days=3))
            for t in ("leadership_change", "corporate_event")]
    one = both[:1]
    base = dict(company=company(), service=service, icp=icp(), questions=[q(1, "High")], signals_by_question={}, rules=[],
                rule_signals={}, now=NOW)
    res_both, res_one = score_lead(events=both, **base), score_lead(events=one, **base)
    items = [i for i in res_both.breakdown["signals"]["items"] if i["kind"] == "event"]
    assert len(items) == 1 and items[0]["evidence"][0]["url"] == url
    assert res_both.signal_score == res_one.signal_score  # no double points
