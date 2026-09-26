"""Decision-maker contacts: only what a source really publishes, never a guessed address."""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app import contacts, mongo
from app.admin import create_admin
from app.main import create_app
from sales_pipeline import HeuristicBackend

HOME = """<html><body><nav><a href="/despre-noi/echipa">Echipa</a> <a href="/contact">Contact</a>
<a href="https://other.example/partners">Parteneri</a></nav><h1>Rompetrol Test</h1></body></html>"""

TEAM = """<html><body><h2>Echipa de conducere</h2>
<div class="card"><h3>Ion Popescu</h3><p>Director General</p><p>ion.popescu@rompetrol.test</p></div>
<div class="card"><p>Maria Ionescu, Chief Information Officer</p></div>
<div class="card"><h3>Despre noi</h3><p>Director de proiecte multe</p></div>
<div class="card"><h3>Logistics Coordinator</h3><p>Logistics Manager/Director</p></div>
<div class="card"><p>Investor Relations - Head of Group Investor Relations</p></div>
<p>Scrie-ne și la partener@gmail.com</p></body></html>"""

CONTACT = """<html><body><h2>Contact</h2><p>Email: office [at] rompetrol.test</p>
<p>Telefon: +40 21 206 75 00</p><p>Fax: +40 21 206 75 01</p><a href="tel:+40212067555">Sună-ne</a></body></html>"""


def site(request: httpx.Request) -> httpx.Response:
    pages = {"/": HOME, "/despre-noi/echipa": TEAM, "/contact": CONTACT}
    body = pages.get(request.url.path)
    return httpx.Response(200, text=body, headers={"content-type": "text/html"}) if body else httpx.Response(404)


def test_website_gives_only_what_is_published_on_the_company_domain():
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as client:
            return await contacts.from_website(client, "rompetrol.test")

    found = asyncio.run(go())
    people = {c["name"]: c for c in found if c["name"]}
    assert set(people) == {"Ion Popescu", "Maria Ionescu"}  # "Despre noi", job titles and teams are not people
    assert people["Ion Popescu"]["level"] == "c_level" and people["Ion Popescu"]["email"] == "ion.popescu@rompetrol.test"
    assert people["Maria Ionescu"]["role"] == "Chief Information Officer" and people["Maria Ionescu"]["email"] is None
    emails = {c["email"] for c in found if c["email"]}
    assert "office@rompetrol.test" in emails  # de-obfuscated "[at]"
    assert "partener@gmail.com" not in emails  # another domain is not the company's
    phones = {c["phone"] for c in found if c["phone"]}
    assert "+40 21 206 75 00" in phones and "+40212067555" in phones
    assert not any("75 01" in p for p in phones)  # fax lines are skipped
    assert all(c["url"].startswith("https://rompetrol.test") and c["evidence"] for c in found)


def test_hunter_keeps_only_addresses_it_found_published():
    payload = {"data": {"emails": [
        {"value": "Ana.Rusu@rompetrol.test", "first_name": "Ana", "last_name": "Rusu", "position": "CFO", "seniority": "executive",
         "sources": [{"uri": "https://rompetrol.test/raport"}], "verification": {"status": "valid"}},
        {"value": "guess@rompetrol.test", "first_name": "No", "last_name": "Source", "sources": []},
    ]}}

    async def go():
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
        async with httpx.AsyncClient(transport=transport) as client:
            return await contacts.from_hunter(client, "rompetrol.test", "k")

    found = asyncio.run(go())
    assert [c["email"] for c in found] == ["ana.rusu@rompetrol.test"]
    assert found[0]["level"] == "c_level" and found[0]["verified"] and found[0]["url"] == "https://rompetrol.test/raport"


def test_apollo_drops_locked_or_unverified_emails():
    payload = {"people": [
        {"name": "Dan Pop", "title": "CTO", "email": "email_not_unlocked@domain.com", "email_status": "verified", "linkedin_url": "https://www.linkedin.com/in/danpop"},
        {"name": "Eva Lungu", "title": "Head of IT", "email": "eva@rompetrol.test", "email_status": "guessed"},
        {"name": "Vlad Cojocaru", "title": "CEO", "email": "vlad@rompetrol.test", "email_status": "verified"},
    ]}

    async def go():
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
        async with httpx.AsyncClient(transport=transport) as client:
            return await contacts.from_apollo(client, "rompetrol.test", "k")

    found = {c["name"]: c for c in asyncio.run(go())}
    assert found["Dan Pop"]["email"] is None and found["Dan Pop"]["linkedin"]
    assert found["Eva Lungu"]["email"] is None  # a guessed address is never kept
    assert found["Vlad Cojocaru"]["email"] == "vlad@rompetrol.test" and found["Vlad Cojocaru"]["level"] == "c_level"


def test_save_merges_the_same_person_from_several_sources(seeded):
    cid = mongo.find_one(mongo.COMPANIES, {"domain": "lufthansagroup.com"}).id
    web = {"name": "Ion Popescu", "role": "Director General", "level": "c_level", "email": None, "phone": None,
           "source": "website", "url": "https://x/echipa", "evidence": "Ion Popescu · Director General"}
    assert contacts.save_found(cid, [web]) == 1
    assert contacts.save_found(cid, [web]) == 0  # found again: no duplicate, no second source entry
    hunter = {**web, "email": "ion@lufthansagroup.com", "source": "hunter", "url": "https://x/raport", "verified": True}
    assert contacts.save_found(cid, [hunter]) == 0
    [c] = contacts.list_contacts(cid)
    assert c.email == "ion@lufthansagroup.com" and c.verified and [s["source"] for s in c.sources] == ["website", "hunter"]


@pytest.fixture()
def api(seeded):
    with TestClient(create_app(seeded, llm_override=HeuristicBackend(), auth_required=True)) as c:
        yield c


def login(api, email, password):
    return {"Authorization": f"Bearer {api.post('/auth/login', json={'email': email, 'password': password}).json()['access_token']}"}


def test_contacts_api_discover_add_do_not_contact_and_permissions(api, seeded, monkeypatch):
    with seeded() as db:
        create_admin(db, "admin@leadradar.md", "Admin One", "admin-pass-1")
    ah = login(api, "admin@leadradar.md", "admin-pass-1")
    api.post("/sellers", headers=ah, json={"email": "ana@leadradar.md", "full_name": "Ana", "password": "ana-pass-12"})
    api.post("/sellers", headers=ah, json={"email": "ion@leadradar.md", "full_name": "Ion", "password": "ion-pass-12"})
    sh, ih = login(api, "ana@leadradar.md", "ana-pass-12"), login(api, "ion@leadradar.md", "ion-pass-12")
    cid = mongo.find_one(mongo.COMPANIES, {"domain": "lufthansagroup.com"}).id

    async def fake_site(client, domain):
        return [{"name": "Carsten Spohr", "role": "CEO", "level": "c_level", "email": None, "phone": None,
                 "source": "website", "url": f"https://{domain}/board", "evidence": "Carsten Spohr · CEO"}]

    monkeypatch.setattr(contacts, "from_website", fake_site)
    out = api.post(f"/companies/{cid}/contacts/discover", headers=sh).json()
    assert out["stats"]["website"] == {"found": 1} and out["stats"]["new"] == 1 and out["stats"]["keys"] == {"hunter": False, "apollo": False}
    assert [c["name"] for c in out["contacts"]] == ["Carsten Spohr"]

    # by hand: needs at least one channel, and it is marked with who added it
    assert api.post(f"/companies/{cid}/contacts", headers=sh, json={"name": "Anna Weber"}).status_code == 422
    added = api.post(f"/companies/{cid}/contacts", headers=sh,
                     json={"name": "Anna Weber", "role": "Head of IT", "email": "a.weber@lufthansagroup.com", "note": "recepție"}).json()
    assert added["added_by"] == "Ana" and added["level"] == "director" and added["sources"][0]["source"] == "manual"

    listed = api.get(f"/companies/{cid}/contacts", headers=ih).json()
    assert [c["name"] for c in listed] == ["Carsten Spohr", "Anna Weber"]  # decision makers first

    assert api.post(f"/contacts/{added['id']}/sent", headers=sh, json={"channel": "email"}).status_code == 204
    assert api.put(f"/contacts/{added['id']}", headers=sh, json={"do_not_contact": True}).json()["do_not_contact"] is True
    assert api.post(f"/contacts/{added['id']}/sent", headers=sh, json={"channel": "email"}).status_code == 409
    actions = [a["action"] for a in api.get(f"/activity?company_id={cid}", headers=ah).json()]
    assert "contact_message" in actions and "contact_do_not_contact" in actions

    assert api.delete(f"/contacts/{added['id']}", headers=ih).status_code == 403  # not Ion's
    assert api.delete(f"/contacts/{out['contacts'][0]['id']}", headers=sh).status_code == 403  # found by a source: admin only
    assert api.delete(f"/contacts/{added['id']}", headers=sh).status_code == 204
    assert api.delete(f"/contacts/{out['contacts'][0]['id']}", headers=ah).status_code == 204
