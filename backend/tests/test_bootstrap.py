"""Bulk company universe (Wikidata / GLEIF + news + scoring) with mocked registries."""
import asyncio
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from app.bootstrap import bootstrap
from app.main import create_app
from app.models import Company, RawDocument
from sales_pipeline import HeuristicBackend
from sales_pipeline.sources.base import THROTTLE

from .test_api import wait_for_run

NOW = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
INDUSTRIES = ["banking", "air transport", "logistics", "telecommunications industry", "retail", "software industry"]


def sparql_rows(country: str, n: int, offset: int) -> list[dict]:
    rows = []
    for i in range(offset, offset + n):
        qid = f"http://www.wikidata.org/entity/Q{country}{i}"
        base = {"item": {"value": qid}, "itemLabel": {"value": f"{country} Company {i} S.A."}, "website": {"value": f"https://www.{country.lower()}company{i}.example/"},
                "sitelinks": {"value": str(1000 - i)}}
        rows.append({**base, "industryLabel": {"value": INDUSTRIES[i % len(INDUSTRIES)]}, "employees": {"value": str(1000 + i * 10)}})
        rows.append({**base, "industryLabel": {"value": "holding company"}})  # second industry row for the same company
    return rows


def registry_client(per_country_available: int, news_hits: bool = True) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "query.wikidata.org":
            q = parse_qs(urlparse(str(request.url)).query)["query"][0]
            country = {"Q218": "RO", "Q217": "MD", "Q183": "DE"}[re.search(r"wdt:P17 wd:(Q\d+)", q).group(1)]
            limit = int(re.search(r"LIMIT (\d+)", q).group(1))
            offset = int(re.search(r"OFFSET (\d+)", q).group(1))
            n = max(0, min(limit, per_country_available - offset))
            return httpx.Response(200, json={"results": {"bindings": sparql_rows(country, n, offset)}})
        if host == "api.gleif.org":
            country = request.url.params["filter[entity.legalAddress.country]"]
            size = int(request.url.params["page[size]"])
            return httpx.Response(200, json={"data": [
                {"id": f"LEI{country}{i:04d}", "attributes": {"lei": f"LEI{country}{i:04d}", "entity": {"legalName": {"name": f"{country} Registered Entity {i} SRL"}}}}
                for i in range(size)
            ]})
        if host == "news.google.com":
            name = re.search(r'"([^"]+)"', request.url.params["q"]).group(1)
            items = "" if not news_hits else f"""<item><title>{name} launches automation and cost reduction programme - Ziarul</title>
<link>https://news.example/{name.replace(' ', '-')}</link><pubDate>{NOW}</pubDate>
<description>{name} will automate back-office processes to improve operational efficiency.</description></item>
<item><title>Unrelated market wrap</title><link>https://news.example/wrap</link><pubDate>{NOW}</pubDate></item>"""
            return httpx.Response(200, text=f"<?xml version='1.0'?><rss><channel>{items}</channel></rss>")
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    monkeypatch.setattr(THROTTLE, "min_interval", {})


def test_bootstrap_loads_real_registry_records_news_and_scores(seeded):
    stats = asyncio.run(bootstrap(seeded, countries=["RO", "MD"], target=40, llm=HeuristicBackend(), client=registry_client(50), say=lambda m: None))
    assert stats["companies"] == 40 and stats["companies_created"] == 40
    assert stats["news"]["companies_with_news"] == 40
    with seeded() as db:
        c = db.query(Company).filter(Company.name == "RO Company 3 S.A.").one()
        assert (c.domain, c.country, c.industry, c.employee_count, c.origin) == ("rocompany3.example", "RO", "Telecommunications", 1030, "wikidata")
        assert c.registry_profiles["wikidata"]["wikidata_id"] == "QRO3"
        docs = db.query(RawDocument).filter(RawDocument.company_id == c.id).all()
        # the unrelated market wrap does not mention the company and is dropped
        assert [d.url for d in docs] == ["https://news.example/RO-Company-3"]
    assert stats["totals"]["warm"] + stats["totals"]["hot"] > 0  # automation news -> real signals -> scored leads

    # re-running is idempotent: same companies, news not refetched within 24 h
    again = asyncio.run(bootstrap(seeded, countries=["RO", "MD"], target=40, llm=HeuristicBackend(), client=registry_client(50), say=lambda m: None))
    assert again["companies_created"] == 0 and again["news"]["news_documents"] == 0
    assert again["totals"]["companies"] == stats["totals"]["companies"]


def test_shortfall_is_redistributed_to_countries_with_more_companies(seeded):
    def client():
        def handler(request):
            q = parse_qs(urlparse(str(request.url)).query)["query"][0]
            country = {"Q218": "RO", "Q217": "MD"}[re.search(r"wdt:P17 wd:(Q\d+)", q).group(1)]
            available = {"RO": 500, "MD": 5}[country]
            limit, offset = int(re.search(r"LIMIT (\d+)", q).group(1)), int(re.search(r"OFFSET (\d+)", q).group(1))
            return httpx.Response(200, json={"results": {"bindings": sparql_rows(country, max(0, min(limit, available - offset)), offset)}})
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    stats = asyncio.run(bootstrap(seeded, countries=["RO", "MD"], target=100, news=False, analyze=False, client=client(), say=lambda m: None))
    assert stats["companies"] == 100
    with seeded() as db:
        assert db.query(Company).filter(Company.country == "MD", Company.origin == "wikidata").count() == 5
        assert db.query(Company).filter(Company.country == "RO", Company.origin == "wikidata").count() == 95


def test_bootstrap_fails_loudly_when_registries_are_unreachable(seeded):
    down = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    with pytest.raises(RuntimeError, match="no companies loaded"):
        asyncio.run(bootstrap(seeded, countries=["RO"], target=10, client=down, say=lambda m: None))


def test_gleif_fills_countries_with_few_wikidata_companies(seeded):
    stats = asyncio.run(bootstrap(seeded, countries=["MD"], target=30, gleif_fill=True, news=False, analyze=False,
                                  client=registry_client(10), say=lambda m: None))
    assert stats["companies"] == 30
    with seeded() as db:
        assert db.query(Company).filter(Company.origin == "gleif").count() == 20
        e = db.query(Company).filter(Company.origin == "gleif").first()
        assert e.registry_profiles["gleif"]["lei"].startswith("LEIMD")


def test_bootstrap_api_and_dashboard(seeded):
    app = create_app(seeded, llm_override=HeuristicBackend(), http_override=registry_client(20))
    with TestClient(app) as c:
        assert c.post("/bootstrap/runs", json={"countries": ["XX"]}).status_code == 422
        run = wait_for_run(c, c.post("/bootstrap/runs", json={"countries": ["DE"], "target": 20}).json()["id"], timeout=60)
        assert run["status"] == "succeeded" and run["kind"] == "bootstrap", run
        assert any("Signal analysis" in l["msg"] for l in run["log"])
        dash = c.get("/dashboard/companies", params={"include_outside_icp": True}).json()
        assert len(dash) >= 20
        de = next(d for d in dash if d["company"]["name"] == "DE Company 0 S.A.")
        assert de["registry_ref"]["wikidata"] == "QDE0"
        assert {s["service_slug"] for s in de["scores"]} == {"apa", "cyber"}
        assert any(s["signals"] for s in de["scores"])


@pytest.mark.skipif(os.getenv("LOAD_TEST") != "1", reason="load test; run with LOAD_TEST=1 pytest tests/test_bootstrap.py -k thousand -s")
def test_thousand_companies_load(seeded):
    t0 = time.monotonic()
    stats = asyncio.run(bootstrap(seeded, countries=["RO", "MD", "DE"], target=1002, llm=HeuristicBackend(), client=registry_client(400), say=print))
    print("elapsed", round(time.monotonic() - t0, 1), stats["totals"])
    assert stats["totals"]["companies"] >= 1000
