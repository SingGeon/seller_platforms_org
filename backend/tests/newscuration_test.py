"""News curation: topical news per company, hiding companies without enough of it, replacing them."""
import asyncio
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app import mongo
from app.newscuration import ACTIVE, INSUFFICIENT, curate
from app.orchestrator import execute_run
from sales_pipeline.sources.base import THROTTLE

NOW = datetime.now(timezone.utc)
TOPICAL = [
    "{n} lansează un program de reducere a costurilor", "{n} investește în automatizare și RPA", "Atac cibernetic la {n}",
    "{n} a fost amendată pentru GDPR", "{n} are un nou director de digitalizare", "{n} deschide un centru de servicii partajate",
]


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    monkeypatch.setattr(THROTTLE, "min_interval", {})


def add_company(name: str, titles: list[str], origin: str = "wikidata") -> int:
    c = mongo.insert_company({"name": name, "country": "RO", "industry": "Banking", "origin": origin})
    for i, t in enumerate(titles):
        mongo.insert(mongo.DOCUMENTS, {"company_id": c.id, "source_type": "news", "url": f"https://news.example/{c.id}/{i}", "title": t,
                                       "content": t, "source": "test", "published_at": NOW - timedelta(days=i), "content_hash": f"{c.id}-{i}",
                                       "meta": {}, "fetched_at": NOW})
    return c.id


def test_companies_without_enough_topical_news_are_hidden_from_leads(client, seeded):
    strong = add_company("Banca Alfa Test", [t.format(n="Banca Alfa Test") for t in TOPICAL])
    weak = add_company("Banca Beta Test", ["Atac cibernetic la Banca Beta Test", "Banca Beta Test sponsorizează un concert",
                                           "Banca Beta Test are un site nou", "Atac cibernetic la Banca Beta Test - Agerpres"])
    old = add_company("Banca Gama Test", [t.format(n="Banca Gama Test") for t in TOPICAL])
    mongo.db()[mongo.DOCUMENTS].update_many({"company_id": old}, {"$set": {"published_at": NOW - timedelta(days=365 * 5)}})
    run = mongo.create_run(kind="enrichment", params={}).id
    asyncio.run(execute_run(seeded, run, company_ids=[strong, weak, old], sources=()))

    stats = asyncio.run(curate(seeded, search=False, analyze=False, say=lambda m: None))

    assert mongo.get(mongo.COMPANIES, strong).status == ACTIVE
    profile = mongo.get(mongo.COMPANIES, strong).news_profile
    assert profile["stories"] == 6 and profile["topics"]["security_incident"] == 1 and profile["topics"]["shared_services"] == 1
    assert mongo.get(mongo.COMPANIES, weak).news_profile["stories"] == 1  # one topical story, reported twice
    assert mongo.get(mongo.COMPANIES, weak).status == INSUFFICIENT
    assert mongo.get(mongo.COMPANIES, old).status == INSUFFICIENT  # five-year-old news says nothing about today
    assert stats["hidden"] == 2
    listed = {row["company"]["id"] for row in client.get("/dashboard/companies?include_outside_icp=true").json()}
    assert strong in listed and weak not in listed and old not in listed
    assert all(lead["company_id"] not in (weak, old) for lead in client.get("/leads?include_outside_icp=true").json())
    # demo companies were entered by hand and are never hidden
    assert mongo.db()[mongo.COMPANIES].count_documents({"origin": "manual", "status": INSUFFICIENT}) == 0


def news_client() -> httpx.AsyncClient:
    """Wikidata returns RO companies 'RO Company i S.A.'; Google News has 6 topical stories for even i, 1 for odd i."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "query.wikidata.org":
            q = parse_qs(urlparse(str(request.url)).query)["query"][0]
            limit, offset = int(re.search(r"LIMIT (\d+)", q).group(1)), int(re.search(r"OFFSET (\d+)", q).group(1))
            rows = [{"item": {"value": f"http://www.wikidata.org/entity/QRO{i}"}, "itemLabel": {"value": f"RO Company {i} S.A."},
                     "website": {"value": f"https://rocompany{i}.example/"}, "sitelinks": {"value": "10"}, "industryLabel": {"value": "banking"}}
                    for i in range(offset, min(offset + limit, 20))]
            return httpx.Response(200, json={"results": {"bindings": rows}})
        if request.url.host == "news.google.com":
            name = re.search(r'"([^"]+)"', request.url.params["q"]).group(1)
            i = int(name.split()[-1])
            titles = [t.format(n=name) for t in TOPICAL] if i % 2 == 0 else [TOPICAL[2].format(n=name)]
            items = "".join(f"<item><title>{t}</title><link>https://news.example/{name.replace(' ', '-')}/{k}</link>"
                            f"<pubDate>{NOW.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate></item>" for k, t in enumerate(titles))
            return httpx.Response(200, text=f"<?xml version='1.0'?><rss><channel>{items}</channel></rss>")
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_hidden_companies_are_replaced_by_real_ones_that_have_enough_news(seeded):
    add_company("Banca Beta Test", ["Banca Beta Test sponsorizează un concert"])
    active_before = mongo.db()[mongo.COMPANIES].count_documents({"status": ACTIVE}) - 1  # Beta gets hidden
    stats = asyncio.run(curate(seeded, target=active_before + 3, countries=["RO"], search=False, analyze=False,
                               client=news_client(), say=lambda m: None))
    added = mongo.find(mongo.COMPANIES, {"origin": "wikidata", "status": ACTIVE})
    assert stats["replace"]["added"] == 3 and len(added) == 3
    assert all(int(c.name.split()[2]) % 2 == 0 for c in added)  # only candidates with >= 5 topical stories
    assert all(c.news_profile["stories"] >= 5 for c in added)
    assert mongo.db()[mongo.COMPANIES].count_documents({"name": {"$regex": "^RO Company [13579]"}}) == 0
    # rejected candidates are remembered, so the next run does not search them again
    assert mongo.db()["curation_rejects"].count_documents({}) == stats["replace"]["rejected"] > 0


def test_daily_refresh_never_hides_companies_that_were_not_curated_yet(seeded):
    from app.newscuration import tag_documents, update_status

    weak = add_company("Banca Beta Test", ["Banca Beta Test sponsorizează un concert"])
    tag_documents([weak])
    assert update_status([weak], only_curated=True) == {}
    assert mongo.get(mongo.COMPANIES, weak).status == ACTIVE
    asyncio.run(curate(seeded, search=False, analyze=False, say=lambda m: None))
    assert mongo.get(mongo.COMPANIES, weak).status == INSUFFICIENT
    assert update_status([weak], only_curated=True) == {INSUFFICIENT: 1}  # once curated, the daily refresh keeps it current
    assert mongo.get(mongo.COMPANIES, weak).news_profile["curated_at"]
