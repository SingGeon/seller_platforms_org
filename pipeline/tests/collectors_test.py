"""Collector parsing tests with mocked HTTP (no network)."""
import asyncio

import httpx

from sales_pipeline import CompanyInfo
from sales_pipeline.collectors import collect_jobs, collect_news
from sales_pipeline.collectors.web import SiteCrawler

ACME = CompanyInfo(name="Acme Logistics", domain="acme.example")

GDELT = {"articles": [
    {"url": "https://news.example/a", "title": "Acme Logistics appoints new CIO", "seendate": "20260901T120000Z", "domain": "news.example"},
    {"url": "https://news.example/b", "title": "Unrelated story about shipping rates", "seendate": "20260902T120000Z", "domain": "news.example"},
]}
RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Acme Logistics launches automation programme - Trade Weekly</title><link>https://trade.example/1</link>
<pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate><description>Acme Logistics will automate finance processes.</description></item>
<item><title>Acme Logistics appoints new CIO</title><link>https://other.example/dupe</link><pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""
GREENHOUSE = {"jobs": [
    {"title": "Senior RPA Developer", "absolute_url": "https://boards.example/1", "location": {"name": "Berlin"}, "updated_at": "2026-09-01T10:00:00+00:00", "content": "&lt;p&gt;UiPath&lt;/p&gt;"},
    {"title": "Truck Driver", "absolute_url": "https://boards.example/2", "location": {"name": "Hamburg"}, "updated_at": "2026-09-01T10:00:00+00:00", "content": ""},
]}


def mock_client(routes):
    def handler(request: httpx.Request) -> httpx.Response:
        for (host, path), resp in routes.items():
            if request.url.host == host and request.url.path.startswith(path):
                return resp(request) if callable(resp) else resp
        return httpx.Response(404)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_news_parses_filters_and_dedupes():
    client = mock_client({
        ("api.gdeltproject.org", "/"): httpx.Response(200, json=GDELT),
        ("news.google.com", "/rss"): httpx.Response(200, text=RSS),
    })
    docs = asyncio.run(collect_news(ACME, client=client))
    titles = [d.title for d in docs]
    assert "Unrelated story about shipping rates" not in titles  # must mention the company
    assert sum("appoints new CIO" in t for t in titles) == 1  # syndicated duplicate removed
    assert any(d.meta["provider"] == "google_news_rss" for d in docs)
    assert docs[0].published_at is not None


def test_news_survives_provider_failure():
    client = mock_client({("news.google.com", "/rss"): httpx.Response(200, text=RSS)})  # GDELT -> 404
    assert asyncio.run(collect_news(ACME, client=client))


def test_jobs_from_ats_board_keep_relevant_roles():
    client = mock_client({("boards-api.greenhouse.io", "/v1/boards/acme/jobs"): httpx.Response(200, json=GREENHOUSE)})
    docs = asyncio.run(collect_jobs(CompanyInfo(name="Acme", domain="acme.example", ats={"greenhouse": "acme"}), client=client))
    assert [d.title for d in docs] == ["Senior RPA Developer"]
    assert docs[0].meta["categories"] == ["RPA"] and docs[0].meta["location"] == "Berlin"


def test_crawler_respects_robots_and_prioritises_news():
    pages = {
        "/robots.txt": "User-agent: *\nDisallow: /private",
        "/": '<html><body><a href="/news/2026/automation">News</a><a href="/private/x">Private</a>'
             '<script src="https://js.hs-scripts.com/1.js"></script>' + "<p>Acme Logistics moves freight across Europe. </p>" * 20 + "</body></html>",
        "/news/2026/automation": "<html><head><title>Automation programme</title></head><body><article>"
             + "<p>Acme Logistics launched an automation programme to improve operational efficiency.</p>" * 10 + "</article></body></html>",
    }
    fetched = []

    def serve(request):
        fetched.append(request.url.path)
        body = pages.get(request.url.path)
        return httpx.Response(200 if body else 404, text=body or "", headers={"content-type": "text/html"})

    client = mock_client({("acme.example", "/"): serve})
    docs = asyncio.run(SiteCrawler(max_pages=6, delay_seconds=0, client=client).crawl(ACME))
    assert "/private/x" not in fetched
    assert any("automation programme" in d.text for d in docs)
    tech = next(d for d in docs if d.meta.get("kind") == "tech_stack")
    assert tech.meta["tech_stack"] == ["HubSpot"]
