"""Seller accounts, the auth guard, the MongoDB activity log and the PostgreSQL <-> MongoDB integrity check."""
import pytest
from fastapi.testclient import TestClient

from app import mongo
from app.main import create_app
from app.models import LeadAssignment
from sales_pipeline import HeuristicBackend

ADMIN = {"email": "admin@leadradar.md", "full_name": "Admin One", "password": "admin-pass-1"}


@pytest.fixture()
def api(seeded):
    with TestClient(create_app(seeded, llm_override=HeuristicBackend(), auth_required=True)) as c:
        yield c


def login(api, email, password):
    resp = api.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_first_account_is_admin_and_data_needs_login(api):
    assert api.get("/auth/status").json() == {"auth_required": True, "has_sellers": False}
    assert api.get("/leads").status_code == 401
    assert api.post("/sellers", json=ADMIN).json()["role"] == "admin"
    assert api.post("/sellers", json={**ADMIN, "email": "x@y.md"}).status_code == 403  # only admins after the first
    assert api.post("/auth/login", json={"email": ADMIN["email"], "password": "wrong"}).status_code == 401
    h = login(api, ADMIN["email"], ADMIN["password"])
    assert api.get("/leads", headers=h).status_code == 200
    assert api.get("/health").status_code == 200  # stays public
    api.post("/auth/logout", headers=h)
    assert api.get("/leads", headers=h).status_code == 401


def test_dashboard_joins_postgres_assignment_with_mongo_scores_and_logs_activity(api):
    api.post("/sellers", json=ADMIN)
    h = login(api, ADMIN["email"], ADMIN["password"])
    ana = api.post("/sellers", headers=h, json={"email": "ana@leadradar.md", "full_name": "Ana Popescu", "password": "ana-pass-12"}).json()
    api.post("/scores/recompute", headers=h)
    cid = api.get("/companies", headers=h).json()[0]["id"]
    assert api.put(f"/companies/{cid}/assignment", headers=h, json={"stage": "contactat", "seller_id": ana["id"]}).status_code == 200
    api.post(f"/companies/{cid}/notes", headers=h, json={"text": "Sunat CIO"})

    entry = next(e for e in api.get("/dashboard/companies?include_outside_icp=true", headers=h).json() if e["company"]["id"] == cid)
    assert entry["assignment"]["stage"] == "contactat" and entry["assignment"]["owner"] == "Ana Popescu" and entry["assignment"]["notes"] == 1
    assert all(s["lead_id"] for s in entry["scores"])

    log = api.get(f"/activity?company_id={cid}", headers=h).json()
    actions = [a["action"] for a in log]
    assert "PUT /companies/{company_id}/assignment" in actions and "POST /companies/{company_id}/notes" in actions
    assert all(a["seller"] == "Admin One" and a["seller_id"] for a in log)


def test_integrity_finds_and_repairs_cross_database_orphans(api, seeded):
    api.post("/sellers", json=ADMIN)
    h = login(api, ADMIN["email"], ADMIN["password"])
    assert api.get("/admin/integrity", headers=h).json()["ok"] is True

    mongo.db()[mongo.LEAD_SCORES].insert_one({"_id": 999999, "company_id": 1, "service_id": 424242, "final_score": 1.0, "tier": "Cold",
                                              "computed_at": mongo.utcnow()})
    with seeded() as db:
        db.add(LeadAssignment(company_id=777777, stage="nou", notes=[]))
        db.commit()
    report = api.get("/admin/integrity", headers=h).json()
    assert report["ok"] is False
    assert {(o.get("collection") or o.get("table"), o["field"]) for o in report["orphans"]} == {("lead_scores", "service_id"), ("lead_assignments", "company_id")}

    fixed = api.post("/admin/integrity/repair", headers=h).json()
    assert fixed["removed"] == {"lead_scores.service_id": 1, "lead_assignments.company_id": 1}
    assert fixed["after"]["ok"] is True


def test_mongo_rejects_documents_that_break_the_schema(api):
    from pymongo.errors import WriteError

    with pytest.raises(WriteError):
        mongo.db()[mongo.LEAD_SCORES].insert_one({"company_id": 1, "service_id": 1, "final_score": 150, "tier": "Boiling", "computed_at": mongo.utcnow()})
