"""Deal estimate: value, cost and profit for Orange per lead, and the admin-editable assumptions."""
from types import SimpleNamespace as NS

from app.deal_value import DEFAULT_DEAL_MODEL, estimate_deal, merged_model

from .api_test import company_id, run_pipeline


def test_the_estimate_grows_with_size_and_market_and_splits_value_into_cost_and_profit():
    small = estimate_deal(NS(employee_count=150, country="DE"), "erp", "Hot")
    assert small["value"] == 150000 and small["profit"] == 45000 and small["cost"] == 105000
    assert small["expected_profit"] == 13500 and small["confidence"] == "medium"
    assert small["value_low"] < small["value"] < small["value_high"]

    big = estimate_deal(NS(employee_count=15000, country="DE"), "erp", "Hot")
    assert 3 * small["value"] < big["value"] < 100 * small["value"]  # larger, but not proportionally
    ro = estimate_deal(NS(employee_count=150, country="RO"), "erp", "Hot")
    assert ro["value"] == 90000  # Romanian price level

    guessed = estimate_deal(NS(employee_count=None, country="MD", registry_profiles={}), "cyber", "Cold")
    assert guessed["confidence"] == "low" and guessed["assumptions"]["size_basis"] == "guessed"
    assert guessed["value_high"] - guessed["value_low"] > (small["value_high"] - small["value_low"]) * guessed["value"] / small["value"]
    listed = estimate_deal(NS(employee_count=None, country="RO", registry_profiles={"wikidata": {"listed": True}}), "cyber", "Warm")
    assert listed["assumptions"]["employees"] == DEFAULT_DEAL_MODEL["listed_company_employees"]
    assert estimate_deal(NS(employee_count=50, country="RO"), "unknown-service", "Disqualified")["expected_profit"] == 0


def test_admin_overrides_merge_over_the_defaults():
    model = merged_model({"services": {"erp": {"gross_margin": 0.4}}, "win_probability": {"Hot": 0.5}})
    assert model["services"]["erp"] == {**DEFAULT_DEAL_MODEL["services"]["erp"], "gross_margin": 0.4}
    assert model["services"]["cyber"] == DEFAULT_DEAL_MODEL["services"]["cyber"]
    assert model["win_probability"]["Warm"] == DEFAULT_DEAL_MODEL["win_probability"]["Warm"]


def test_leads_and_company_page_show_the_deal_and_the_admin_can_change_it(client):
    run_pipeline(client)
    lead = client.get("/leads", params={"service": "erp"}).json()[0]
    assert lead["deal_value"] > 0 and lead["expected_profit"] is not None
    cid = company_id(client, "Lufthansa Group")
    deal = client.get(f"/companies/{cid}").json()["scores"][0]["deal"]
    assert deal["profit"] + deal["cost"] - deal["value"] in (-100, 0, 100) and deal["assumptions"]["basis"]

    assert client.put("/deal-model", json={"services": {"erp": {"gross_margin": 1.5}}}).status_code == 422
    changed = client.put("/deal-model", json={"services": {"erp": {"base_value": 300000}}}).json()
    assert changed["services"]["erp"]["base_value"] == 300000 and client.get("/deal-model").json() == changed
    again = next(l for l in client.get("/leads", params={"service": "erp"}).json() if l["company_id"] == lead["company_id"])
    assert again["deal_value"] > lead["deal_value"]
    assert client.put("/deal-model", json={}).json() == DEFAULT_DEAL_MODEL  # back to the defaults
