"""Discovery (signal -> company) through the API with mocked public sources."""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.discovery import due_sources, resolve_company
from app.main import create_app
from app.models import Company, SourceState
from app.scheduler import tick
from sales_pipeline import Document, HeuristicBackend
from sales_pipeline.sources.base import THROTTLE, DiscoveredItem

from .test_api import wait_for_run

NOW = datetime.now(timezone.utc)

TED = {"notices": [
    {"publication-number": "700001-2026", "notice-title": {"eng": "Robotic process automation platform and automation services for the tax office"},
     "buyer-name": {"ron": ["Agenția Națională de Administrare Fiscală"]}, "buyer-country": ["ROU"],
     "publication-date": NOW.date().isoformat(), "classification-cpv": ["72000000"]},
]}
RANSOMWARE = [
    {"victim": "Agentia Nationala de Administrare Fiscala", "group": "akira", "attackdate": NOW.isoformat(), "country": "RO", "activity": "Public Sector"},
    {"victim": "Moldova Logistics SRL", "group": "akira", "attackdate": NOW.isoformat(), "country": "MD", "activity": "Transportation", "domain": "moldlog.example"},
]


def mocked_client() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.ted.europa.eu":
            return httpx.Response(200, json=TED)
        if request.url.host == "api.ransomware.live":
            return httpx.Response(200, json=RANSOMWARE)
        return httpx.Response(503)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture()
def dclient(seeded, monkeypatch):
    monkeypatch.setattr(THROTTLE, "min_interval", {})
    app = create_app(seeded, llm_override=HeuristicBackend(), http_override=mocked_client())
    with TestClient(app) as c:
        yield c


def test_sources_catalog_and_key_status(dclient):
    sources = {s["name"]: s for s in dclient.get("/sources").json()}
    assert sources["ted"]["configured"] and sources["ted"]["limits"]
    assert sources["adzuna"]["missing_keys"] == ["adzuna_app_id", "adzuna_app_key"]
    assert sources["sec_8k_cyber"]["configured"] is False  # SEC needs SEC_USER_AGENT
    assert {s["mode"] for s in sources.values()} == {"discovery", "enrichment"}
    assert dclient.get("/sources/not-used").json()


def test_discovery_run_creates_resolves_and_scores_leads(dclient):
    resp = dclient.post("/discovery/runs", json={"sources": ["ted", "ransomware_live", "adzuna"], "enrich_top_n": 1})
    assert resp.status_code == 202
    run = wait_for_run(dclient, resp.json()["id"])
    assert run["status"] == "succeeded", run
    by_source = {s["source"]: s for s in run["stats"]["sources"]}
    assert by_source["adzuna"]["status"] == "skipped"
    assert by_source["ted"]["new_companies"] == 1
    # ANAF appears in TED and ransomware.live under different spellings -> one company
    assert by_source["ransomware_live"]["new_companies"] == 1
    assert set(run["stats"]["child_runs"]) >= {"analysis"}

    companies = {c["name"]: c for c in dclient.get("/companies").json()}
    anaf = companies["Agenția Națională de Administrare Fiscală"]
    assert anaf["origin"] == "ted" and anaf["country"] == "RO"
    assert {t["source"] for t in anaf["discovered_via"]} == {"ted", "ransomware_live"}
    assert "Agentia Nationala de Administrare Fiscala" in anaf["aliases"]
    assert companies["Moldova Logistics SRL"]["domain"] == "moldlog.example"

    detail = dclient.get(f"/companies/{anaf['id']}").json()
    assert detail["documents_by_source"]["news"] == 2
    assert any(s["answer"] == "yes" for s in detail["signals"])  # tender text answers the automation question

    leads = dclient.get("/leads", params={"origin": "ted", "include_outside_icp": True}).json()
    assert leads and all(l["is_new"] for l in leads)
    assert dclient.get("/leads", params={"changed_since_hours": 1, "include_outside_icp": True}).json()

    state = {s["name"]: s for s in dclient.get("/sources").json()}["ted"]
    assert state["last_status"] == "ok" and state["last_stats"]["new_companies"] == 1 and state["next_run_at"]

    # a second sync is incremental: the cursor remembers the notice, nothing new is created
    run2 = wait_for_run(dclient, dclient.post("/sources/ted/sync").json()["id"])
    assert run2["stats"]["new_companies"] == 0 and run2["stats"]["new_documents"] == 0


def test_failed_source_keeps_cursor_and_reports_error(dclient):
    run = wait_for_run(dclient, dclient.post("/discovery/runs", json={"sources": ["hibp"]}).json()["id"])
    assert run["status"] == "failed"
    hibp = dclient.get("/sources/hibp").json()
    assert hibp["last_status"] == "error" and "503" in hibp["last_error"]


def test_source_settings_and_enrichment_source_rejected(dclient):
    assert dclient.put("/sources/ted", json={"enabled": False, "interval_minutes": 120}).json()["interval_minutes"] == 120
    assert dclient.post("/sources/wikidata/sync").status_code == 422
    assert dclient.get("/sources/nope").status_code == 404


def test_discovery_countries_come_from_config(dclient):
    cfg = dclient.get("/scoring-config").json()
    assert cfg["discovery_countries"] == ["RO", "MD"]
    cfg["discovery_countries"] = ["de", "AT"]
    assert dclient.put("/scoring-config", json=cfg).json()["discovery_countries"] == ["DE", "AT"]


def test_resolve_company_by_domain_and_normalized_name(seeded):
    doc = Document(source_type="news", url="https://x.example/1", title="t", text="t")
    with seeded() as db:
        c1, created = resolve_company(db, DiscoveredItem(company_name="GitLab Inc.", company_domain="https://gitlab.com/", document=doc), "hn")
        assert created and c1.domain == "gitlab.com"
        c2, created = resolve_company(db, DiscoveredItem(company_name="GITLAB INC (GTLB) (CIK 0001653482)", document=doc), "sec")
        assert not created and c2.id == c1.id
        c3, created = resolve_company(db, DiscoveredItem(company_name="Totally Different", company_domain="gitlab.com", document=doc), "x")
        assert c3.id == c1.id
        db.commit()


def test_scheduler_runs_due_sources_once(seeded, monkeypatch):
    monkeypatch.setattr(THROTTLE, "min_interval", {})
    from sales_pipeline.sources import catalog

    only = [s for s in catalog.SOURCES if s.name == "ransomware_live"]
    monkeypatch.setattr("app.discovery.SOURCES", only)
    with seeded() as db:
        assert due_sources(db) == ["ransomware_live"]

    import app.discovery as disc

    original = disc.sync_source

    async def with_mock(sf, name, llm, client=None):
        return await original(sf, name, llm, client=mocked_client())

    monkeypatch.setattr(disc, "sync_source", with_mock)
    run_id = asyncio.run(tick(seeded, HeuristicBackend()))
    assert run_id is not None
    with seeded() as db:
        assert db.get(SourceState, "ransomware_live").last_status == "ok"
        assert due_sources(db) == []  # next_run_at is in the future now
        assert db.query(Company).filter(Company.origin == "ransomware_live").count() == 2
    assert asyncio.run(tick(seeded, HeuristicBackend())) is None
