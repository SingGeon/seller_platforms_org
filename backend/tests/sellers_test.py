"""Seller accounts, the auth guard, the MongoDB activity log and the PostgreSQL <-> MongoDB integrity check."""
import pytest
from fastapi.testclient import TestClient

from app import mongo
from app.admin import create_admin
from app.main import create_app
from app.models import LeadAssignment
from sales_pipeline import HeuristicBackend

ADMIN = {"email": "admin@leadradar.md", "full_name": "Admin One", "password": "admin-pass-1"}


@pytest.fixture()
def api(seeded):
    with TestClient(create_app(seeded, llm_override=HeuristicBackend(), auth_required=True)) as c:
        yield c


@pytest.fixture()
def admin(seeded):
    """Admins are created in the database (python -m app.admin), never through the API."""
    with seeded() as db:
        return create_admin(db, ADMIN["email"], ADMIN["full_name"], ADMIN["password"])


def login(api, email, password):
    resp = api.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_no_account_can_be_created_without_an_admin_login(api):
    assert api.get("/auth/status").json() == {"auth_required": True, "has_sellers": False}
    # an empty database no longer hands out a free first (admin) account
    assert api.post("/sellers", json=ADMIN).status_code == 401
    assert api.post("/sellers", json={**ADMIN, "role": "seller"}).status_code == 401


def test_data_needs_login(api, admin):
    assert api.get("/leads").status_code == 401
    assert api.post("/auth/login", json={"email": ADMIN["email"], "password": "wrong"}).status_code == 401
    h = login(api, ADMIN["email"], ADMIN["password"])
    assert api.get("/leads", headers=h).status_code == 200
    assert api.get("/health").status_code == 200  # stays public
    api.post("/auth/logout", headers=h)
    assert api.get("/leads", headers=h).status_code == 401


def test_admins_are_never_created_promoted_or_removed_through_the_api(api, admin, seeded):
    h = login(api, ADMIN["email"], ADMIN["password"])
    assert api.post("/sellers", headers=h, json={**ADMIN, "email": "second-admin@leadradar.md", "role": "admin"}).status_code == 403
    ana = api.post("/sellers", headers=h, json={"email": "ana@leadradar.md", "full_name": "Ana", "password": "ana-pass-12"}).json()
    assert ana["role"] == "seller"
    assert api.put(f"/sellers/{ana['id']}", headers=h, json={"role": "admin"}).status_code == 403
    assert api.put(f"/sellers/{ana['id']}", headers=h, json={"active": False}).json()["active"] is False  # sellers: yes

    with seeded() as db:
        other = create_admin(db, "other-admin@leadradar.md", "Other Admin", "other-pass-1")
    assert api.put(f"/sellers/{other.id}", headers=h, json={"active": False}).status_code == 403
    assert api.put(f"/sellers/{other.id}", headers=h, json={"password": "hijack-pass-1"}).status_code == 403
    assert api.delete(f"/sellers/{other.id}", headers=h).status_code == 403
    assert api.put(f"/sellers/{admin.id}", headers=h, json={"role": "seller"}).status_code == 403
    assert api.put(f"/sellers/{admin.id}", headers=h, json={"full_name": "Admin Renamed"}).json()["full_name"] == "Admin Renamed"
    assert api.post("/auth/login", json={"email": "ana@leadradar.md", "password": "ana-pass-12"}).status_code == 401  # deactivated


def test_dashboard_joins_postgres_assignment_with_mongo_scores_and_logs_activity(api, admin):
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
    assert {"lead_stage", "lead_assign", "lead_note"} <= set(actions)  # detailed entries replace the generic audit ones
    assert "PUT /companies/{company_id}/assignment" not in actions
    assert all(a["seller"] == "Admin One" and a["seller_id"] for a in log)


def test_only_an_admin_assigns_leads_a_seller_takes_free_ones_or_gives_back_their_own(api, admin):
    h = login(api, ADMIN["email"], ADMIN["password"])
    ana = api.post("/sellers", headers=h, json={"email": "ana@leadradar.md", "full_name": "Ana", "password": "ana-pass-12"}).json()
    ion = api.post("/sellers", headers=h, json={"email": "ion@leadradar.md", "full_name": "Ion", "password": "ion-pass-12"}).json()
    free, taken = [c["id"] for c in api.get("/companies", headers=h).json()[:2]]
    assert api.put(f"/companies/{taken}/assignment", headers=h, json={"seller_id": ion["id"]}).json()["owner"] == "Ion"  # admin: anyone
    ah = login(api, "ana@leadradar.md", "ana-pass-12")

    assert api.put(f"/companies/{free}/assignment", headers=ah, json={"seller_id": ion["id"]}).status_code == 403  # not to someone else
    assert api.put(f"/companies/{taken}/assignment", headers=ah, json={"seller_id": ana["id"]}).status_code == 403  # not someone's lead
    assert api.put(f"/companies/{taken}/assignment", headers=ah, json={"unassign": True}).status_code == 403
    assert api.get(f"/companies/{taken}/assignment", headers=ah).json()["owner"] == "Ion"

    assert api.put(f"/companies/{free}/assignment", headers=ah, json={"seller_id": ana["id"]}).json()["owner"] == "Ana"  # take a free lead
    assert api.put(f"/companies/{free}/assignment", headers=ah, json={"stage": "contactat"}).json()["stage"] == "contactat"
    assert api.put(f"/companies/{free}/assignment", headers=ah, json={"unassign": True}).json()["owner"] is None  # give it back


def test_seller_cannot_manage_accounts(api, admin):
    h = login(api, ADMIN["email"], ADMIN["password"])
    api.post("/sellers", headers=h, json={"email": "ana@leadradar.md", "full_name": "Ana", "password": "ana-pass-12"})
    sh = login(api, "ana@leadradar.md", "ana-pass-12")
    assert api.post("/sellers", headers=sh, json={"email": "x@leadradar.md", "full_name": "X", "password": "x-pass-123"}).status_code == 403
    assert api.put(f"/sellers/{admin.id}", headers=sh, json={"full_name": "Hacked"}).status_code == 403
    me = api.get("/auth/me", headers=sh).json()
    assert api.put(f"/sellers/{me['id']}", headers=sh, json={"active": False}).status_code == 403
    assert api.put(f"/sellers/{me['id']}", headers=sh, json={"password": "ana-new-pass-1"}).status_code == 200


def test_integrity_finds_and_repairs_cross_database_orphans(api, admin, seeded):
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


def test_passwords_are_stored_in_plain_text_and_legacy_hashes_still_log_in(api, admin, seeded):
    import hashlib

    from app.models import Seller

    with seeded() as db:
        assert db.get(Seller, admin.id).password == ADMIN["password"]
        salt = "00" * 16
        digest = hashlib.pbkdf2_hmac("sha256", b"legacy-pass-1", bytes.fromhex(salt), 1000).hex()
        old = Seller(email="old@leadradar.md", full_name="Old", password=f"pbkdf2_sha256$1000${salt}${digest}", role="seller")
        db.add(old)
        db.commit()
        old_id = old.id

    assert api.post("/auth/login", json={"email": "old@leadradar.md", "password": "wrong"}).status_code == 401
    assert api.post("/auth/login", json={"email": "old@leadradar.md", "password": "legacy-pass-1"}).status_code == 200
    with seeded() as db:
        assert db.get(Seller, old_id).password == "legacy-pass-1"  # upgraded to plain text on login
    assert "password" not in api.get("/auth/me", headers=login(api, "old@leadradar.md", "legacy-pass-1")).json()  # never exposed


def test_only_admins_change_configuration_sources_runs_and_companies(api, admin):
    h = login(api, ADMIN["email"], ADMIN["password"])
    api.post("/sellers", headers=h, json={"email": "ana@leadradar.md", "full_name": "Ana", "password": "ana-pass-12"})
    ah = login(api, "ana@leadradar.md", "ana-pass-12")
    service = api.get("/services", headers=ah).json()[0]
    question = api.get(f"/services/{service['id']}/questions", headers=ah).json()[0]
    company = api.get("/companies", headers=ah).json()[0]
    changes = [
        ("post", "/services", {"name": "X", "slug": "x"}),
        ("put", f"/services/{service['id']}/questions/{question['id']}", {**question, "text": "Changed?"}),
        ("delete", f"/services/{service['id']}/questions/{question['id']}", None),
        ("post", "/rules", {"name": "r", "rule_type": "llm_question", "question": "q?"}),
        ("put", "/scoring-config", api.get("/scoring-config", headers=ah).json()),
        ("put", f"/icp/{service['id']}", {"industries": []}),
        ("post", "/scores/recompute", None),
        ("put", "/sources/bing_news", {"enabled": False}),
        ("post", "/discovery/runs", {}),
        ("post", "/runs", {}),
        ("delete", f"/companies/{company['id']}", None),
    ]
    for method, path, body in changes:
        kwargs = {"json": body} if body is not None else {}
        assert getattr(api, method)(path, headers=ah, **kwargs).status_code == 403, (method, path)  # a sales manager
    assert api.get(f"/services/{service['id']}/questions", headers=ah).json()[0]["text"] == question["text"]  # nothing changed
    # reading the configuration and working on leads stay open to sales managers
    assert api.get("/rules", headers=ah).status_code == 200 and api.get("/icp", headers=ah).status_code == 200
    assert api.put(f"/companies/{company['id']}/assignment", headers=ah, json={"stage": "contactat"}).status_code == 200
    assert api.post(f"/companies/{company['id']}/notes", headers=ah, json={"text": "called"}).status_code == 201
    # the admin still can
    assert api.put(f"/services/{service['id']}/questions/{question['id']}", headers=h, json={**question, "text": "Changed?"}).status_code == 200


def test_failed_logins_are_in_the_activity_log_without_the_password(api, admin):
    assert api.post("/auth/login", json={"email": ADMIN["email"], "password": "wrong-guess-1"}).status_code == 401
    assert api.post("/auth/login", json={"email": "nobody@leadradar.md", "password": "x"}).status_code == 401
    h = login(api, ADMIN["email"], ADMIN["password"])
    failed = [a for a in api.get("/activity", headers=h).json() if a["action"] == "login_failed"]
    assert {(a["details"]["email"], a["details"]["reason"]) for a in failed} == {
        (ADMIN["email"], "wrong_password"), ("nobody@leadradar.md", "unknown_email")}
    assert next(a for a in failed if a["details"]["reason"] == "wrong_password")["seller"] == "Admin One"
    assert "wrong-guess-1" not in str(failed)


@pytest.mark.parametrize("language,greeting", [("RO", "Bună ziua"), ("DE", "Guten Tag"), ("EN", "Hello")])
def test_contact_message_follows_the_chosen_language(api, admin, language, greeting):
    h = login(api, ADMIN["email"], ADMIN["password"])
    company = api.get("/companies", headers=h).json()[0]
    service = api.get("/services", headers=h).json()[0]
    draft = api.post(f"/companies/{company['id']}/outreach?service={service['id']}&channel=email&language={language}", headers=h).json()
    assert draft["body"].startswith(greeting) and draft["language"] == language


def test_a_lead_leaves_nou_only_with_an_owner(api, admin):
    h = login(api, ADMIN["email"], ADMIN["password"])
    api.post("/sellers", headers=h, json={"email": "ana@leadradar.md", "full_name": "Ana", "password": "ana-pass-12"})
    ah = login(api, "ana@leadradar.md", "ana-pass-12")
    free, other = [c["id"] for c in api.get("/companies", headers=h).json()[:2]]

    assert api.put(f"/companies/{free}/assignment", headers=h, json={"stage": "calificat"}).status_code == 400  # admin, no owner
    assert api.get(f"/companies/{free}/assignment", headers=h).json()["stage"] == "nou"
    # a sales manager who moves a free lead forward becomes its owner
    moved = api.put(f"/companies/{free}/assignment", headers=ah, json={"stage": "calificat"}).json()
    assert (moved["stage"], moved["owner"]) == ("calificat", "Ana")
    # giving a lead back sends it to "nou"
    back = api.put(f"/companies/{free}/assignment", headers=ah, json={"unassign": True}).json()
    assert (back["stage"], back["owner"]) == ("nou", None)
    # stage "nou" without an owner stays allowed
    assert api.put(f"/companies/{other}/assignment", headers=h, json={"stage": "nou"}).status_code == 200


def test_pipeline_history_lists_every_change_with_who_and_from_to(api, admin):
    h = login(api, ADMIN["email"], ADMIN["password"])
    ana = api.post("/sellers", headers=h, json={"email": "ana@leadradar.md", "full_name": "Ana", "password": "ana-pass-12"}).json()
    company = api.get("/companies", headers=h).json()[0]
    api.put(f"/companies/{company['id']}/assignment", headers=h, json={"stage": "contactat", "seller_id": ana["id"]})
    ah = login(api, "ana@leadradar.md", "ana-pass-12")
    api.put(f"/companies/{company['id']}/assignment", headers=ah, json={"stage": "negociere"})
    api.post(f"/companies/{company['id']}/notes", headers=ah, json={"text": "Ofertă trimisă"})

    history = api.get("/pipeline/history", headers=ah).json()
    assert [(e["action"], e["seller"]) for e in history] == [
        ("lead_note", "Ana"), ("lead_stage", "Ana"), ("lead_assign", "Admin One"), ("lead_stage", "Admin One")]
    assert history[1]["details"] == {"stage_from": "contactat", "stage_to": "negociere"}
    assert history[2]["details"]["owner_to"] == "Ana" and history[3]["details"] == {"stage_from": "nou", "stage_to": "contactat"}
    assert history[0]["details"]["excerpt"] == "Ofertă trimisă" and all(e["company"] == company["name"] for e in history)
    assert api.get(f"/pipeline/history?company_id={company['id'] + 999}", headers=ah).json() == []
    assert len(api.get("/pipeline/history?limit=2", headers=ah).json()) == 2
