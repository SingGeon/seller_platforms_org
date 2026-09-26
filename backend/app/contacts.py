"""Decision-maker contacts for a company, taken only from sources where they are really published.

Sources (each optional, each contact keeps where it came from: URL, the exact line, the date):

    website  the company's own pages (home, contact, team / management / about, Impressum): e-mail addresses on the
             company's domain and phone numbers published there, and "Name / Role" lines of decision makers, exactly
             as written on the page
    news     leadership changes already detected in the company's news (company_events: leadership_change)
    hunter   Hunter.io Domain Search (HUNTER_API_KEY): addresses Hunter found published on the web, with its sources
    apollo   Apollo.io people search (APOLLO_API_KEY): decision makers with title and LinkedIn; an e-mail only when
             Apollo returns an unlocked, verified one
    manual   added by a sales manager, marked with who added it

Nothing is generated: no guessed e-mail patterns, no invented names. A contact marked "do not contact" keeps its
record (so it is not found and added again) but the app will not offer it for messages.
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from . import mongo
from .config import get_settings

log = logging.getLogger(__name__)

CONTACTS = mongo.CONTACTS
USER_AGENT = "OrangeSignalsBot/0.1 (+sales-intelligence research; public company pages only)"
MAX_PAGES = 7
HUNTER_URL = "https://api.hunter.io/v2/domain-search"
APOLLO_URL = "https://api.apollo.io/api/v1/mixed_people/api_search"

# Pages of a company site where people and contact details are published (RO / EN / DE).
PAGE_HINTS = re.compile(
    r"contact|kontakt|despre|about|echipa|team|management|conducere|leadership|board|consiliu|impressum|"
    r"cine-suntem|who-we-are|ueber-uns|uber-uns|about-us|organizare|executive",
    re.I,
)

# Role words by decision level; the first match decides the level.
ROLE_LEVELS: list[tuple[str, re.Pattern]] = [
    ("c_level", re.compile(
        r"\b(ceo|cfo|cio|cto|coo|cdo|ciso|cmo|chief [a-z ]+ officer|director general|directorul general|"
        r"general manager|managing director|gesch[aä]ftsf[uü]hrer(?:in)?|vorstand\w*|pre[sș]edinte(?:le)?|president|"
        r"administrator|founder|fondator|owner|proprietar)\b", re.I)),
    ("director", re.compile(
        r"\b(director\w*|head of [a-z ]+|vice[- ]president|vp|leiter(?:in)?|bereichsleiter(?:in)?)\b", re.I)),
    ("manager", re.compile(r"\b(manager\w*|responsabil [a-z]+|dpo|data protection officer|team lead)\b", re.I)),
]
LEVEL_RANK = {"c_level": 0, "director": 1, "manager": 2, "other": 3, "unknown": 4}

# A person's name as printed: 2-4 capitalised words (diacritics and hyphens allowed).
NAME_WORD = r"[A-ZĂÂÎȘȚŞŢÄÖÜÉÈ][a-zăâîșțşţäöüßéèáíóúç'’-]+"
NAME_RE = re.compile(rf"^(?:Dr\.?\s+|Ing\.?\s+|Prof\.?\s+)?({NAME_WORD}(?:\s+{NAME_WORD}){{1,3}})$")
NOT_NAME_WORDS = {
    "Director", "General", "Manager", "Contact", "Contacte", "Despre", "Echipa", "Echipă", "Team", "Board", "Consiliul",
    "Management", "Conducere", "Leadership", "Impressum", "Kontakt", "Office", "Sales", "Vanzari", "Vânzări", "Suport",
    "Support", "Home", "Acasa", "Acasă", "Cariere", "Careers", "Servicii", "Services", "Produse", "Products", "Chief",
    "Officer", "Head", "Adresa", "Adresă", "Telefon", "Email", "Program", "Luni", "Vineri", "Str", "Strada", "Group",
    "Grup", "Holding", "Romania", "România", "Moldova", "Deutschland", "Austria", "Privacy", "Cookies", "Politica",
    # job, team and department words: "Logistics Coordinator" or "Investor Relations" are not people
    "Coordinator", "Coordonator", "Logistics", "Logistică", "Customer", "Customers", "Client", "Clients", "Clienți", "Service",
    "Serviciul", "Marketing", "Finance", "Financial", "Financiar", "Human", "Resources", "Resurse", "Umane", "Operations",
    "Operațiuni", "Project", "Projects", "Proiecte", "Account", "Accounts", "Business", "Development", "Solutions", "Technology",
    "Technical", "Tehnic", "Digital", "Global", "Regional", "International", "Investor", "Investors", "Relations", "Relații",
    "Media", "Press", "Presă", "Presse", "Corporate", "Corporates", "Communications", "Comunicare", "Kommunikation",
    "Procurement", "Achiziții", "Einkauf", "Supply", "Chain", "Quality", "Calitate", "Legal", "Juridic", "Compliance",
    "Security", "Risk", "Product", "Engineering", "Transport", "Transportation", "Freight", "Energy", "Network", "Retail",
    "Private", "Public", "Institutional", "Partner", "Partners", "Center", "Centre", "Unit", "Division", "Department",
    "Departamentul", "Abteilung", "Specialist", "Engineer", "Inginer", "Analyst", "Assistant", "Asistent", "Consultant",
    "Advisor", "Representative", "Reprezentant", "Executive", "Senior", "Junior", "Lead", "Leader", "Vertrieb", "Kunden",
    "Leitung", "Unternehmen", "Personal", "Recruiting", "Careers", "Jobs", "News", "Noutăți", "Investitori",
}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\(?\d[\d\s().\-/]{7,}\d")
PHONE_HINT = re.compile(r"\b(tel|telefon|phone|mobil|mobile|fon)\b", re.I)
FAX_HINT = re.compile(r"\bfax\b", re.I)


def role_level(text: str) -> str | None:
    for level, pattern in ROLE_LEVELS:
        if pattern.search(text):
            return level
    return None


def as_name(line: str) -> str | None:
    """The line when it is exactly a person's name (2-4 capitalised words), else None."""
    line = line.strip(" ,;:–-|•·")
    if len(line) > 48:
        return None
    m = NAME_RE.match(line)
    if not m:
        return None
    words = m.group(1).split()
    if any(w.strip("'’-") in NOT_NAME_WORDS for w in words):
        return None
    return m.group(1)


def _same_domain(host: str, domain: str) -> bool:
    host, domain = host.lower().removeprefix("www."), domain.lower().removeprefix("www.")
    return host == domain or host.endswith("." + domain)


def _clean_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if not 8 <= len(digits) <= 15:
        return None
    return re.sub(r"\s+", " ", raw.strip())


def _deobfuscate(text: str) -> str:
    return re.sub(r"\s*[\[(]\s*(?:at|@)\s*[\])]\s*", "@", re.sub(r"\s*[\[(]\s*(?:dot|punct)\s*[\])]\s*", ".", text, flags=re.I), flags=re.I)


def extract_from_page(html: str, url: str, domain: str) -> list[dict[str, Any]]:
    """People, e-mails and phones literally published on one page of the company's site."""
    soup = BeautifulSoup(html, "html.parser")
    mailtos = [a["href"][7:].split("?")[0] for a in soup.select('a[href^="mailto:"]')]
    tels = [a["href"][4:] for a in soup.select('a[href^="tel:"]')]
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in _deobfuscate(soup.get_text("\n")).split("\n")]
    lines = [ln for ln in lines if ln]

    def emails_in(text: str) -> list[str]:
        return [e.lower() for e in EMAIL_RE.findall(text) if _same_domain(e.split("@")[1], domain)]

    def phones_in(text: str) -> list[str]:
        if FAX_HINT.search(text) or not PHONE_HINT.search(text):
            return []
        return [p for p in (_clean_phone(m) for m in PHONE_RE.findall(text)) if p]

    found: list[dict[str, Any]] = []
    used: set[int] = set()
    # People: a role line with the name in the same line ("Ion Popescu, Director General") or on the line above
    # (team cards: name, then role underneath). Details within the next two lines belong to that person.
    for i, line in enumerate(lines):
        if len(line) > 140:
            continue
        level = role_level(line)
        if not level:
            continue
        name, role = None, line
        for sep in (" – ", " - ", ", ", " | ", ": "):
            if sep in line:
                left, right = line.split(sep, 1)
                if as_name(left) and role_level(right):
                    name, role = as_name(left), right
                    break
                if as_name(right) and role_level(left):
                    name, role = as_name(right), left
                    break
        if not name and i > 0 and as_name(lines[i - 1]):
            name = as_name(lines[i - 1])
        if not name:
            continue
        nearby = " ".join(lines[i : i + 3])
        found.append({
            "name": name, "role": role.strip(" ,;:–-|"), "level": level,
            "email": next(iter(emails_in(nearby)), None), "phone": next(iter(phones_in(nearby)), None),
            "source": "website", "url": url, "evidence": f"{lines[i - 1]} · {line}" if name == as_name(lines[i - 1] if i else "") else line,
        })
        used.update({i - 1, i, i + 1, i + 2})

    # Company-level details: published e-mails on the company domain and phone numbers.
    person_emails = {c["email"] for c in found if c["email"]}
    for e in dict.fromkeys(emails_in(" ".join(mailtos)) + emails_in("\n".join(lines))):
        if e not in person_emails:
            line = next((ln for ln in lines if e in ln.lower()), e)
            found.append({"name": None, "role": None, "level": "unknown", "email": e, "phone": None,
                          "source": "website", "url": url, "evidence": line[:200]})
    person_phones = {c["phone"] for c in found if c["phone"]}
    phones = [p for p in (_clean_phone(t) for t in tels) if p]
    phones += [p for j, ln in enumerate(lines) if j not in used for p in phones_in(ln)]
    for p in dict.fromkeys(phones):
        if p not in person_phones:
            line = next((ln for ln in lines if re.sub(r"\D", "", p) in re.sub(r"\D", "", ln)), p)
            found.append({"name": None, "role": None, "level": "unknown", "email": None, "phone": p,
                          "source": "website", "url": url, "evidence": line[:200]})
    return found


def contact_pages(html: str, base_url: str, domain: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("#")[0]
        parsed = urlparse(href)
        if parsed.scheme not in ("http", "https") or not _same_domain(parsed.netloc, domain):
            continue
        if PAGE_HINTS.search(parsed.path) or PAGE_HINTS.search(a.get_text(" ")[:60]):
            if href not in out and href.rstrip("/") != base_url.rstrip("/"):
                out.append(href)
    return out[: MAX_PAGES - 1]


async def from_website(client: httpx.AsyncClient, domain: str) -> list[dict[str, Any]]:
    home = f"https://{domain.removeprefix('www.')}"
    try:
        r = await client.get(home)
        r.raise_for_status()
    except httpx.HTTPError:
        r = await client.get(f"https://www.{domain.removeprefix('www.')}")
        r.raise_for_status()
    base = str(r.url)
    found = extract_from_page(r.text, base, domain)
    for url in contact_pages(r.text, base, domain):
        try:
            page = await client.get(url)
            if page.status_code == 200 and "html" in page.headers.get("content-type", "html"):
                found += extract_from_page(page.text, str(page.url), domain)
        except httpx.HTTPError as exc:
            log.info("contact page %s: %s", url, exc)
    return found


def from_news(company_id: int) -> list[dict[str, Any]]:
    """Names in leadership-change events already found in the company's news ("X appointed CEO")."""
    out = []
    for e in mongo.find(mongo.EVENTS, {"company_id": company_id, "event_type": "leadership_change"}):
        title = e.title or ""
        level = role_level(title)
        if not level:
            continue
        # a name is 2-4 capitalised words somewhere in the headline
        for m in re.finditer(rf"{NAME_WORD}(?:\s+{NAME_WORD}){{1,3}}", title):
            name = as_name(m.group(0))
            if name:
                out.append({"name": name, "role": None, "level": level, "email": None, "phone": None,
                            "source": "news", "url": e.url or "", "evidence": title[:200]})
                break
    return out


def _level_from(title: str | None, seniority: str | None) -> str:
    return role_level(title or "") or {"executive": "c_level", "c_suite": "c_level", "owner": "c_level", "founder": "c_level",
                                       "vp": "director", "director": "director", "head": "director",
                                       "senior": "manager", "manager": "manager"}.get((seniority or "").lower(), "other")


async def from_hunter(client: httpx.AsyncClient, domain: str, key: str) -> list[dict[str, Any]]:
    """Hunter Domain Search: only addresses Hunter found published (each with at least one source page)."""
    r = await client.get(HUNTER_URL, params={"domain": domain, "api_key": key, "limit": 10})
    r.raise_for_status()
    out = []
    for e in (r.json().get("data") or {}).get("emails") or []:
        sources = e.get("sources") or []
        if not e.get("value") or not sources:
            continue
        name = " ".join(x for x in (e.get("first_name"), e.get("last_name")) if x) or None
        out.append({
            "name": name, "role": e.get("position"), "level": _level_from(e.get("position"), e.get("seniority")) if name else "unknown",
            "email": e["value"].lower(), "phone": e.get("phone_number"), "linkedin": e.get("linkedin"),
            "source": "hunter", "url": sources[0].get("uri") or "", "evidence": f"Hunter.io: găsit pe {len(sources)} pagini publice",
            "verified": (e.get("verification") or {}).get("status") == "valid",
        })
    return out


async def from_apollo(client: httpx.AsyncClient, domain: str, key: str) -> list[dict[str, Any]]:
    """Apollo people search: decision makers; an e-mail only when Apollo returns an unlocked, verified one."""
    r = await client.post(
        APOLLO_URL, headers={"X-Api-Key": key, "Cache-Control": "no-cache"},
        json={"q_organization_domains_list": [domain], "person_seniorities": ["owner", "founder", "c_suite", "vp", "head", "director"],
              "page": 1, "per_page": 10},
    )
    r.raise_for_status()
    out = []
    for p in r.json().get("people") or []:
        name = p.get("name") or " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
        if not name:
            continue
        email = p.get("email") if p.get("email_status") == "verified" and "not_unlocked" not in (p.get("email") or "") else None
        out.append({
            "name": name, "role": p.get("title"), "level": _level_from(p.get("title"), p.get("seniority")),
            "email": email.lower() if email else None, "phone": None, "linkedin": p.get("linkedin_url"),
            "source": "apollo", "url": p.get("linkedin_url") or "https://app.apollo.io/", "evidence": "Apollo.io: profil profesional",
            "verified": bool(email),
        })
    return out


# ------------------------------------------------------------------ storage


def _key(c: dict) -> str:
    if c.get("email"):
        return "e:" + c["email"].lower()
    if c.get("name"):
        return "n:" + re.sub(r"\s+", " ", c["name"].lower())
    return "p:" + re.sub(r"\D", "", c.get("phone") or "")


def list_contacts(company_id: int) -> list[mongo.MDoc]:
    rows = mongo.find(CONTACTS, {"company_id": company_id})
    return sorted(rows, key=lambda c: (bool(c.do_not_contact), LEVEL_RANK.get(c.level or "unknown", 4), not c.name, c.name or c.email or ""))


def save_found(company_id: int, found: list[dict[str, Any]]) -> int:
    """Merge contacts into the company's list (one per e-mail / name / phone); returns how many are new."""
    existing = {_key(c): c for c in mongo.find(CONTACTS, {"company_id": company_id})}
    new = 0
    for f in found:
        key = _key(f)
        if key in ("p:", "n:", "e:"):
            continue
        # a person first seen without e-mail may come back with one: match on the name too
        match = existing.get(key) or (existing.get("n:" + f["name"].lower()) if f.get("name") else None)
        source = {"source": f["source"], "url": f.get("url") or "", "evidence": f.get("evidence") or "", "found_at": mongo.utcnow()}
        if match:
            fields: dict[str, Any] = {}
            for k in ("name", "role", "email", "phone", "linkedin"):
                if f.get(k) and not match.get(k):
                    fields[k] = f[k]
            if LEVEL_RANK.get(f.get("level", "unknown"), 4) < LEVEL_RANK.get(match.level or "unknown", 4):
                fields["level"] = f["level"]
            if f.get("verified"):
                fields["verified"] = True
            if not any(s.get("source") == source["source"] and s.get("url") == source["url"] for s in match.sources or []):
                fields["sources"] = [*(match.sources or []), source]
            if fields:
                mongo.update(CONTACTS, match.id, fields)
                match.update(fields)
            continue
        doc = mongo.insert(CONTACTS, {
            "company_id": company_id, "name": f.get("name"), "role": f.get("role"), "level": f.get("level") or "unknown",
            "email": f.get("email"), "phone": f.get("phone"), "linkedin": f.get("linkedin"), "verified": bool(f.get("verified")),
            "sources": [source], "do_not_contact": False, "added_by": None, "created_at": mongo.utcnow(),
        })
        existing[key] = doc
        new += 1
    return new


async def discover(company: mongo.MDoc, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Look for contacts in every available source; each source that fails is reported, the others still count."""
    settings = get_settings()
    own = client is None
    client = client or httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    stats: dict[str, Any] = {}
    found: list[dict[str, Any]] = []
    try:
        steps: list[tuple[str, Any]] = [("news", None)]
        if company.domain:
            steps.insert(0, ("website", from_website(client, company.domain)))
            if settings.hunter_api_key:
                steps.append(("hunter", from_hunter(client, company.domain, settings.hunter_api_key)))
            if settings.apollo_api_key:
                steps.append(("apollo", from_apollo(client, company.domain, settings.apollo_api_key)))
        for name, job in steps:
            try:
                rows = from_news(company.id) if name == "news" else await job
                stats[name] = {"found": len(rows)}
                found += rows
            except Exception as exc:  # noqa: BLE001 - one source failing must not stop the others
                log.info("contacts %s for %s: %s", name, company.domain, exc)
                stats[name] = {"error": (str(exc) or type(exc).__name__)[:200]}
    finally:
        if own:
            await client.aclose()
    stats["new"] = save_found(company.id, found)
    stats["keys"] = {"hunter": bool(settings.hunter_api_key), "apollo": bool(settings.apollo_api_key)}
    return stats
