"""Discovery / enrichment sources with mocked HTTP (no network)."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from sales_pipeline.sources.base import SourceContext, polite_request
from sales_pipeline.sources.catalog import BY_NAME, SOURCES, render_markdown
from sales_pipeline.sources.companies import company_from_headline, company_from_hn_post, normalize_company_name, normalize_domain
from sales_pipeline.sources.cyber import kev_documents, sync_hibp, sync_ransomware_live
from sales_pipeline.sources.jobboards import sync_arbeitnow, sync_hn_hiring
from sales_pipeline.sources.newsfeeds import sync_globenewswire
from sales_pipeline.sources.registry import wikidata_profile
from sales_pipeline.sources.sec import sync_sec_8k_cyber, sync_sec_form_d
from sales_pipeline.sources.tenders import _ocds_release, ocds_to_item, sync_ted, sync_uk_contracts, ted_query

NOW = datetime.now(timezone.utc)
ISO = lambda days: (NOW - timedelta(days=days)).isoformat()  # noqa: E731


def ctx_for(routes, **kw):
    def handler(request: httpx.Request) -> httpx.Response:
        for (host, path), resp in routes.items():
            if request.url.host == host and request.url.path.startswith(path):
                return resp(request) if callable(resp) else resp
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SourceContext(client=client, since=NOW - timedelta(days=7), **kw)


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ company names
@pytest.mark.parametrize("raw,expected", [
    ("GitLab Inc.", "gitlab"), ("GITLAB INC  (GTLB)  (CIK 0001653482)", "gitlab"), ("Deutsche Lufthansa AG", "deutsche lufthansa"),
    ("S.C. Orange Romania S.A.", "s c orange romania"), ("The Coca-Cola Company", "coca cola"), ("Raiffeisen Bank International AG", "raiffeisen bank international"),
    ("Moldcell S.R.L.", "moldcell"), ("DHL Group", "dhl"),
])
def test_normalize_company_name(raw, expected):
    assert normalize_company_name(raw) == expected


def test_domain_and_headline_extraction():
    assert normalize_domain("https://www.Example.co.uk/about?x=1") == "example.co.uk"
    assert normalize_domain("not a domain") is None
    assert company_from_headline("Acme Robotics Announces Series B Funding - PR Newswire") == "Acme Robotics"
    assert company_from_headline("Nordic Bank appoints new Chief Information Security Officer") == "Nordic Bank"
    assert company_from_headline("Why ransomware is rising in 2026") is None
    assert company_from_hn_post("Acme (YC S21) | Senior RPA Engineer | Berlin | ONSITE") == "Acme"


# ------------------------------------------------------------------ tenders
TED_RESPONSE = {"notices": [
    {"publication-number": "612345-2026", "notice-title": {"eng": "Managed SOC and SIEM services"}, "buyer-name": {"ron": ["Primăria Municipiului Cluj-Napoca"]},
     "buyer-country": ["ROU"], "publication-date": "2026-09-20+02:00", "classification-cpv": ["72000000"], "links": {"html": {"ENG": "https://ted.europa.eu/en/notice/-/detail/612345-2026"}}},
    {"publication-number": "612346-2026", "notice-title": {"eng": "No buyer"}, "buyer-name": None},
], "totalNoticeCount": 2}


def test_ted_query_and_parsing():
    assert "buyer-country IN (ROU MDA)" in ted_query(NOW, ["RO", "MD"])
    bodies = []

    def ted(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=TED_RESPONSE)

    res = run(sync_ted(ctx_for({("api.ted.europa.eu", "/v3/notices/search"): ted}, countries=["RO"]), {}))
    assert bodies[0]["query"].startswith("classification-cpv IN (72000000")
    [item] = res.items
    assert item.company_name == "Primăria Municipiului Cluj-Napoca" and item.company_country == "RO"
    assert item.signal == "it_tender:cyber" and item.document.published_at.date().isoformat() == "2026-09-20"
    # cursor remembers what was seen
    again = run(sync_ted(ctx_for({("api.ted.europa.eu", "/v3/notices/search"): httpx.Response(200, json=TED_RESPONSE)}), res.cursor))
    assert again.items == []


def test_ocds_parsing_uk_and_mtender_merge():
    release = {"ocid": "ocds-1", "id": "abc", "date": ISO(1), "buyer": {"name": "NHS Digital"},
               "tender": {"title": "Robotic process automation platform", "description": "RPA licences and delivery", "classification": {"id": "72000000"}}}
    res = run(sync_uk_contracts(ctx_for({("www.contractsfinder.service.gov.uk", "/Published"): httpx.Response(200, json={"releases": [release, {"ocid": "x", "buyer": {"name": "Council"}, "tender": {"title": "Road resurfacing", "classification": {"id": "45233142"}}}]})}), {}))
    assert [i.company_name for i in res.items] == ["NHS Digital"] and res.items[0].signal == "it_tender:automation"

    mtender = {"records": [
        {"ocid": "ocds-b3wdp1-MD-1", "compiledRelease": {"ocid": "ocds-b3wdp1-MD-1", "date": ISO(2), "parties": [{"name": "Agenția Servicii Publice", "roles": ["buyer"]}], "tender": {"title": "Servicii de mentenanță a sistemului informațional"}}},
        {"ocid": "ocds-b3wdp1-MD-1-EV", "compiledRelease": {"tender": {"items": [{"classification": {"id": "72267000-4"}}]}}},
    ]}
    item = ocds_to_item(_ocds_release(mtender), provider="mtender", url="https://mtender.gov.md/tenders/x", default_country="MD")
    assert item.company_name == "Agenția Servicii Publice" and item.company_country == "MD"


# ------------------------------------------------------------------ jobs
def test_arbeitnow_keeps_relevant_roles_in_target_countries():
    data = {"data": [
        {"company_name": "Logistik GmbH", "title": "RPA Developer (UiPath)", "description": "<p>Automate finance</p>", "url": "https://arbeitnow.example/1", "location": "Berlin", "remote": False, "created_at": int(NOW.timestamp())},
        {"company_name": "Bakery", "title": "Baker", "description": "", "url": "https://arbeitnow.example/2", "location": "Berlin", "remote": False, "created_at": int(NOW.timestamp())},
        {"company_name": "Paris SA", "title": "Security Engineer", "description": "", "url": "https://arbeitnow.example/3", "location": "Paris", "remote": False, "created_at": int(NOW.timestamp())},
    ], "links": {"next": None}}
    res = run(sync_arbeitnow(ctx_for({("www.arbeitnow.com", "/api"): httpx.Response(200, json=data)}, countries=["DE"]), {}))
    assert [(i.company_name, i.company_country, i.signal) for i in res.items] == [("Logistik GmbH", "DE", "hiring:RPA")]


def test_hn_who_is_hiring():
    routes = {
        ("hn.algolia.com", "/api/v1/search_by_date"): httpx.Response(200, json={"hits": [{"objectID": "999", "title": "Ask HN: Who is hiring? (September 2026)"}]}),
        ("hn.algolia.com", "/api/v1/items/999"): httpx.Response(200, json={"children": [
            {"id": 1, "created_at": ISO(3), "text": "Acme Ops | Automation Engineer (RPA) | Bucharest, Romania | https://acmeops.example/careers<p>We automate back-office work."},
            {"id": 2, "created_at": ISO(3), "text": "Just a comment without the format"},
        ]}),
    }
    res = run(sync_hn_hiring(ctx_for(routes, countries=["RO"]), {}))
    [item] = res.items
    assert (item.company_name, item.company_domain, item.company_country) == ("Acme Ops", "acmeops.example", "RO")
    assert res.cursor == {"story": "999", "seen": ["1", "2"]}


# ------------------------------------------------------------------ news
GNW_RSS = """<?xml version="1.0"?><rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
<item><title>Board changes at a leading insurer</title><link>https://gnw.example/1</link><dc:contributor>Carpathia Insurance plc</dc:contributor>
<pubDate>{d}</pubDate><description>Carpathia names new Chief Digital Officer.</description></item>
<item><title>Market outlook for 2027</title><link>https://gnw.example/2</link><pubDate>{d}</pubDate></item>
</channel></rss>""".format(d=NOW.strftime("%a, %d %b %Y %H:%M:%S GMT"))


def test_globenewswire_uses_contributor_and_reports_unresolved():
    res = run(sync_globenewswire(ctx_for({("www.globenewswire.com", "/RssFeed"): httpx.Response(200, text=GNW_RSS)}), {}))
    assert {i.company_name for i in res.items} == {"Carpathia Insurance plc"}
    assert res.items[0].signal == "news:leadership_change"
    assert [d.url for d in res.unresolved][:1] == ["https://gnw.example/2"]


# ------------------------------------------------------------------ cyber
def test_ransomware_live_and_hibp():
    victims = [
        {"victim": "acme-logistics.ro", "group": "lockbit5", "attackdate": ISO(1), "country": "RO", "activity": "Transportation", "domain": "acme-logistics.ro"},
        {"victim": "Old Victim", "group": "x", "attackdate": ISO(60), "country": "RO"},
        {"victim": "Elsewhere Inc", "group": "x", "attackdate": ISO(1), "country": "BR"},
    ]
    res = run(sync_ransomware_live(ctx_for({("api.ransomware.live", "/v2"): httpx.Response(200, json=victims)}, countries=["RO", "MD"]), {}))
    [item] = res.items
    assert item.company_domain == "acme-logistics.ro" and item.signal == "cyber:ransomware_victim" and item.company_industry == "Transportation"

    breaches = [
        {"Name": "Acme", "Title": "Acme Retail", "Domain": "acmeretail.example", "BreachDate": "2026-08-01", "AddedDate": ISO(2), "PwnCount": 120000, "DataClasses": ["Email addresses"], "Description": "<p>Leak</p>"},
        {"Name": "Old", "Title": "Old", "Domain": "old.example", "BreachDate": "2019-01-01", "AddedDate": "2019-02-01T00:00:00Z"},
    ]
    res = run(sync_hibp(ctx_for({("haveibeenpwned.com", "/api/v3/breaches"): httpx.Response(200, json=breaches)}), {}))
    assert [(i.company_name, i.company_domain) for i in res.items] == [("Acme Retail", "acmeretail.example")]


def test_kev_matches_detected_tech_stack():
    kev = [{"cveID": "CVE-2026-1111", "vendorProject": "SAP", "product": "NetWeaver", "vulnerabilityName": "SAP NetWeaver RCE", "dateAdded": NOW.date().isoformat(), "shortDescription": "RCE"},
           {"cveID": "CVE-2020-1", "vendorProject": "SAP", "product": "Old", "dateAdded": "2020-01-01"}]
    docs = kev_documents("Acme", ["SAP", "Google Analytics"], kev)
    assert len(docs) == 1 and docs[0].meta["cves"] == ["CVE-2026-1111"]


# ------------------------------------------------------------------ SEC
def test_sec_8k_item_filter_and_form_d():
    hits = {"hits": {"hits": [
        {"_id": "0000950170-26-000111:acme-8k.htm", "_source": {"display_names": ["ACME CORP  (ACME)  (CIK 0000123456)"], "ciks": ["0000123456"], "file_date": "2026-09-20", "items": ["1.05", "9.01"], "adsh": "0000950170-26-000111", "biz_states": ["TX"]}},
        {"_id": "0000950170-26-000222:beta.htm", "_source": {"display_names": ["BETA INC (CIK 0000999)"], "ciks": ["0000999"], "file_date": "2026-09-21", "items": ["8.01"], "adsh": "0000950170-26-000222"}},
    ]}}
    seen_ua = []

    def efts(request):
        seen_ua.append(request.headers.get("user-agent"))
        return httpx.Response(200, json=hits)

    res = run(sync_sec_8k_cyber(ctx_for({("efts.sec.gov", "/LATEST"): efts}, sec_user_agent="Orange Signals ops@example.com"), {}))
    [item] = res.items
    assert item.company_name == "ACME CORP" and item.company_country == "US" and item.signal == "cyber:material_incident"
    assert item.document.url == "https://www.sec.gov/Archives/edgar/data/123456/000095017026000111/acme-8k.htm"
    assert seen_ua[0] == "Orange Signals ops@example.com"

    atom = f"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>D - Nimbus Robotics, Inc. (0001999999) (Filer)</title><link href="https://www.sec.gov/Archives/edgar/data/1999999/x-index.htm"/><updated>{NOW.isoformat()}</updated></entry>
<entry><title>D - Some Fund LP (0001888888) (Reporting)</title><link href="https://www.sec.gov/y"/><updated>{NOW.isoformat()}</updated></entry></feed>"""
    res = run(sync_sec_form_d(ctx_for({("www.sec.gov", "/cgi-bin"): httpx.Response(200, text=atom)}, sec_user_agent="x y@z.com"), {}))
    assert [i.company_name for i in res.items] == ["Nimbus Robotics, Inc."]


# ------------------------------------------------------------------ registry
def test_wikidata_profile_prefers_domain_match():
    search = {"search": [{"id": "Q1"}, {"id": "Q2"}]}
    sparql = {"results": {"bindings": [
        {"item": {"value": "http://www.wikidata.org/entity/Q1"}, "itemLabel": {"value": "DHL"}, "website": {"value": "https://www.dhl.com"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q2"}, "itemLabel": {"value": "DHL Group"}, "industryLabel": {"value": "logistics"},
         "iso": {"value": "DE"}, "employees": {"value": "594879"}, "website": {"value": "https://group.dhl.com/en.html"}},
    ]}}
    ctx = ctx_for({("www.wikidata.org", "/w/api.php"): httpx.Response(200, json=search), ("query.wikidata.org", "/sparql"): httpx.Response(200, json=sparql)})
    p = run(wikidata_profile(ctx.client, "DHL Group", "group.dhl.com"))
    assert (p.ref, p.industry, p.country, p.employee_count, p.domain) == ("Q2", "Logistics", "DE", 594879, "group.dhl.com")


# ------------------------------------------------------------------ framework
def test_polite_request_retries_429():
    calls = []

    def flaky(request):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "0"}) if len(calls) < 3 else httpx.Response(200, json={"ok": True})

    ctx = ctx_for({("api.gdeltproject.org", "/"): flaky})
    resp = run(polite_request(ctx.client, "GET", "https://api.gdeltproject.org/api/v2/doc/doc", base_delay=0))
    assert resp.status_code == 200 and len(calls) == 3


def test_catalog_is_complete_and_documented():
    names = [s.name for s in SOURCES]
    assert len(names) == len(set(names))
    assert all(s.limits and s.fallback for s in SOURCES)
    assert all(s.sync is not None for s in SOURCES if s.mode == "discovery")
    assert BY_NAME["adzuna"].missing_keys({}) == ["adzuna_app_id", "adzuna_app_key"]
    md = render_markdown()
    assert "TED" in md and "Crunchbase API" in md


# ------------------------------------------------------------------ bulk universe helpers
def test_search_name_and_mentions():
    from sales_pipeline.sources.companies import mentions, search_name

    assert search_name("Banca Transilvania S.A.") == "Banca Transilvania"
    assert search_name("Siemens Aktiengesellschaft") == "Siemens"
    assert search_name("DHL Group") == "DHL Group"
    assert mentions("Banca Transilvania S.A.", "Banca Transilvania lansează un program")
    assert mentions("Petrom", "OMV Petrom anunță investiții")
    assert not mentions("Orange", "Orangeade sales rise")


def test_normalize_industry_to_icp_vocabulary():
    from sales_pipeline.sources.bulk import normalize_industry

    assert normalize_industry("banking") == "Banking"
    assert normalize_industry("air transport") == "Aviation"
    assert normalize_industry("telecommunications industry") == "Telecommunications"
    assert normalize_industry("automotive industry") == "Manufacturing"
    assert normalize_industry("wine") == "Wine"
    assert normalize_industry(None) is None


def test_network_errors_are_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("Temporary failure in name resolution", request=request)
        return httpx.Response(200, json={"ok": True})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await polite_request(client, "GET", "https://example.org/x")

    assert asyncio.run(go()).status_code == 200 and calls["n"] == 3


def test_wikidata_pages_that_time_out_are_retried_smaller():
    import re as _re

    from sales_pipeline.sources.bulk import wikidata_companies

    sizes = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        size = int(_re.search(r"LIMIT (\d+)", query).group(1))
        sizes.append(size)
        assert "FILTER(?sitelinks >= 3)" in query
        if size > 50:
            return httpx.Response(504)
        rows = [{"item": {"value": f"http://www.wikidata.org/entity/Q{i}"}, "itemLabel": {"value": f"Co {i}"},
                 "website": {"value": f"https://co{i}.example/"}} for i in range(size)]
        return httpx.Response(200, json={"results": {"bindings": rows}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await wikidata_companies(client, "DE", 60)

    companies = asyncio.run(go())
    assert len(companies) == 60
    assert 250 not in sizes and 60 in sizes and 50 in sizes  # 60 (=limit) -> 504 x retries, then 50 -> ok
