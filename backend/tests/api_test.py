import csv
import io
import time

from app.seed import SERVICES

SEEDED_SLUGS = {s["slug"] for s in SERVICES}


def wait_for_run(client, run_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/runs/{run_id}").json()
        if run["status"] in ("succeeded", "failed"):
            return run
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def run_pipeline(client):
    resp = client.post("/runs", json={})
    assert resp.status_code == 202
    run = wait_for_run(client, resp.json()["id"])
    assert run["status"] == "succeeded", run
    return run


def company_id(client, name):
    return next(c["id"] for c in client.get("/companies").json() if c["name"] == name)


def test_health_and_seeded_config(client):
    assert client.get("/health").json()["status"] == "ok"
    services = client.get("/services").json()
    assert {s["slug"] for s in services} == SEEDED_SLUGS == {"apa", "cyber", "cloud", "data", "erp", "iot"}
    apa = next(s for s in services if s["slug"] == "apa")
    questions = client.get(f"/services/{apa['id']}/questions").json()
    assert any("RPA developers" in q["text"] for q in questions)
    assert any(q["is_negative"] for q in questions)
    assert client.get(f"/icp/{apa['id']}").json()["min_fit"] == 40
    rules = client.get(f"/services/{apa['id']}/rules").json()
    assert {r["rule_type"] for r in rules} == {"field_rule", "llm_question"}


def test_run_scores_leads_with_evidence(client):
    run = run_pipeline(client)
    assert run["progress"]["companies_done"] == 8
    assert "estimated_cost_usd" in run["stats"]

    leads = client.get("/leads", params={"service": "apa"}).json()
    top = leads[0]
    assert top["company"] in ("Lufthansa Group", "DHL Group")
    assert top["tier"] in ("Hot", "Warm")
    assert top["top_signal"]["url"].startswith("https://annex1.example/")
    assert top["summary"]  # 'why now' generated for Hot/Warm leads
    assert [l["final_score"] for l in leads] == sorted((l["final_score"] for l in leads), reverse=True)

    detail = client.get(f"/companies/{top['company_id']}").json()
    assert detail["best_service"] == "Agentic Process Automation"
    signals = [s for s in detail["signals"] if s["answer"] == "yes"]
    assert signals and all(s["evidence"] for s in signals)
    items = detail["scores"][0]["breakdown"]["signals"]["items"]
    assert any(i["points"] > 0 for i in items)

    # Re-running is idempotent: no duplicate signals or documents.
    n_signals = len(detail["signals"])
    run_pipeline(client)
    assert len(client.get(f"/companies/{top['company_id']}").json()["signals"]) == n_signals


def test_new_question_is_used_by_next_run(client):
    apa = client.get("/services").json()[0]
    q = client.post(
        f"/services/{apa['id']}/questions",
        json={"text": "Does the company mention RFQ processing automation?", "weight": "Low", "keywords": ["rfq processing", "automated"]},
    ).json()
    run_pipeline(client)
    dhl = client.get(f"/companies/{company_id(client, 'DHL Group')}").json()
    answered = [s for s in dhl["signals"] if s["question_id"] == q["id"]]
    assert answered and answered[0]["answer"] == "yes"


def test_config_change_recomputes_instantly(client):
    run_pipeline(client)
    lufthansa = company_id(client, "Lufthansa Group")
    before = next(l for l in client.get("/leads", params={"service": "apa"}).json() if l["company_id"] == lufthansa)
    cfg = client.get("/scoring-config").json()
    cfg.update(icp_weight=0.0, signal_weight=1.0, hot_threshold=30, warm_threshold=10)
    assert client.put("/scoring-config", json=cfg).status_code == 200
    after = next(l for l in client.get("/leads", params={"service": "apa"}).json() if l["company_id"] == lufthansa)
    assert after["final_score"] == after["signal_score"] != before["final_score"]
    assert after["tier"] == ("Hot" if after["final_score"] >= 30 else "Warm" if after["final_score"] >= 10 else "Cold"), after


def test_disqualified_lead_shows_reason(client):
    cid = company_id(client, "Siemens")
    body = client.get(f"/companies/{cid}").json()["company"]
    body = {k: v for k, v in body.items() if k not in ("id", "created_at", "linkedin_validation")}
    body["is_existing_client"] = True
    assert client.put(f"/companies/{cid}", json=body).status_code == 200
    leads = client.get("/leads", params={"tier": "Disqualified"}).json()
    siemens = [l for l in leads if l["company_id"] == cid]
    assert len(siemens) == len(SEEDED_SLUGS)  # one disqualified lead per service
    assert siemens[0]["disqualification_reasons"][0]["rule"] == "Existing Orange Systems client"


def test_outside_icp_is_filtered(client):
    c = client.post("/companies", json={"name": "Tiny Games", "domain": "tinygames.example", "industry": "Gaming", "country": "US", "employee_count": 120}).json()
    assert all(l["company_id"] != c["id"] for l in client.get("/leads").json())
    assert any(l["company_id"] == c["id"] for l in client.get("/leads", params={"include_outside_icp": True}).json())


def test_manual_signal_overrides_ai(client):
    run_pipeline(client)
    cid = company_id(client, "Maersk".join(["A.P. Moller - ", ""]))
    apa = client.get("/services").json()[0]
    q = client.get(f"/services/{apa['id']}/questions").json()[0]
    before = next(l for l in client.get("/leads", params={"service": "apa"}).json() if l["company_id"] == cid)
    resp = client.post(
        f"/companies/{cid}/manual-signal",
        json={"question_id": q["id"], "answer": "yes", "confidence": 0.9, "evidence_url": "https://maersk.example/pr", "evidence_quote": "We launched a cost programme"},
    )
    assert resp.status_code == 201
    after = next(l for l in client.get("/leads", params={"service": "apa"}).json() if l["company_id"] == cid)
    assert after["signal_score"] > before["signal_score"]
    run_pipeline(client)  # the AI run must not overwrite the rep's validation
    again = next(l for l in client.get("/leads", params={"service": "apa"}).json() if l["company_id"] == cid)
    assert again["signal_score"] == after["signal_score"]


def test_outreach_references_real_signal(client):
    run_pipeline(client)
    cid = company_id(client, "Lufthansa Group")
    for channel in ("email", "linkedin", "followup"):
        draft = client.post(f"/companies/{cid}/outreach", params={"service": "apa", "channel": channel}).json()
        assert draft["grounded"], draft
        assert draft["sources"]
    linkedin = client.post(f"/companies/{cid}/outreach", params={"service": "apa", "channel": "linkedin"}).json()
    assert len(linkedin["body"]) <= 300


def test_csv_export_and_hubspot_guard(client):
    run_pipeline(client)
    resp = client.get("/export/leads.csv")
    assert resp.status_code == 200
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert rows and {r["tier"] for r in rows} <= {"Hot", "Warm"}
    assert rows[0]["top_signal_1_url"]
    assert client.post("/crm/hubspot", json=[1]).status_code == 400  # no token configured


def test_csv_import(client):
    data = "Organization Name,Website,Industries,Headquarters Country,Number of Employees\nNordic Freight AB,https://www.nordicfreight.example/,Logistics,SE,1001-5000\n"
    resp = client.post("/companies/import", files={"file": ("cb.csv", data, "text/csv")})
    assert resp.json() == {"created": 1, "skipped": 0}
    c = next(c for c in client.get("/companies").json() if c["name"] == "Nordic Freight AB")
    assert c["domain"] == "nordicfreight.example" and c["employee_count"] == 5000 and c["country"] == "SE"


def test_linkedin_manual_validation(client):
    cid = company_id(client, "ING Group")
    resp = client.put(
        f"/companies/{cid}/linkedin",
        json={"decision_makers": [{"name": "Jane Doe", "title": "COO", "profile_url": "https://linkedin.example/jane"}], "notes": "Met at event", "validated_by": "ana"},
    )
    assert resp.json()["linkedin_validation"]["validated_by"] == "ana"


def test_rule_validation(client):
    bad = client.post("/rules", json={"name": "x", "rule_type": "field_rule", "field": "password", "operator": "eq", "value": 1})
    assert bad.status_code == 422
