"""Hiring signals from job postings (GIG-22).

Source 1: SerpAPI Google Jobs.
Source 2: public ATS boards (Greenhouse, Lever, Workable, Personio) and the
company's own careers page.
Every posting is normalised into a role category (RPA, AI/ML, ...).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from ..documents import Document, clean_text, dedupe
from ..schemas import CompanyInfo

log = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"
SERPAPI_QUERY = '"{company}" RPA OR automation OR "process excellence" OR "AI engineer" OR "security"'

ROLE_CATEGORIES: dict[str, list[str]] = {
    "RPA": [r"\brpa\b", r"uipath", r"automation anywhere", r"blue ?prism", r"power automate", r"intelligent automation", r"automation (developer|engineer|architect)"],
    "AI/ML": [r"\bai\b", r"artificial intelligence", r"machine learning", r"\bml\b", r"data scientist", r"\bllm\b", r"genai|generative ai", r"agentic"],
    "Process Excellence": [r"process excellence", r"process mining", r"celonis", r"lean", r"six sigma", r"continuous improvement", r"operational excellence"],
    "Business Analysis": [r"business analyst", r"process analyst", r"\bba\b"],
    "Security": [r"security", r"\bciso\b", r"\bsoc\b", r"cyber", r"penetration", r"\biam\b", r"nis2|dora|iso 27001"],
    "Digital Transformation": [r"digital transformation", r"transformation (lead|manager|director)", r"head of digital", r"chief digital"],
}


def categorize_role(title: str, description: str = "") -> list[str]:
    text = f"{title} {description[:1500]}".lower()
    title_l = title.lower()
    cats = []
    for cat, patterns in ROLE_CATEGORIES.items():
        # The title is the strong signal; the description only counts for
        # categories whose vocabulary is specific enough not to be noise.
        if any(re.search(p, title_l) for p in patterns):
            cats.append(cat)
        elif cat in ("RPA", "Process Excellence") and any(re.search(p, text) for p in patterns):
            cats.append(cat)
    return cats


def _relative_date(value: str | None) -> datetime | None:
    """Parse SerpAPI's '3 days ago' style strings."""
    if not value:
        return None
    m = re.search(r"(\d+)\s+(hour|day|week|month)", value)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta = {"hour": timedelta(hours=n), "day": timedelta(days=n), "week": timedelta(weeks=n), "month": timedelta(days=30 * n)}[unit]
    return datetime.now(timezone.utc) - delta


def _job_doc(company: CompanyInfo, *, title: str, url: str, description: str, location: str, posted_at: datetime | None, board: str) -> Document:
    categories = categorize_role(title, description)
    return Document(
        source_type="jobs",
        url=url,
        title=clean_text(title),
        text=clean_text(f"Job posting at {company.name}: {title}. Location: {location}. {description}")[:6000],
        published_at=posted_at,
        source=board,
        meta={"job_title": clean_text(title), "location": location, "categories": categories, "board": board},
    )


async def fetch_serpapi_jobs(client: httpx.AsyncClient, company: CompanyInfo, api_key: str) -> list[Document]:
    params = {"engine": "google_jobs", "q": SERPAPI_QUERY.format(company=company.name), "api_key": api_key, "hl": "en"}
    resp = await client.get(SERPAPI_URL, params=params)
    resp.raise_for_status()
    docs = []
    for job in resp.json().get("jobs_results", []):
        if company.name.split()[0].lower() not in (job.get("company_name") or "").lower():
            continue
        link = (job.get("apply_options") or [{}])[0].get("link") or job.get("share_link") or ""
        if not link:
            continue
        docs.append(
            _job_doc(
                company,
                title=job.get("title", ""),
                url=link,
                description=job.get("description", ""),
                location=job.get("location", ""),
                posted_at=_relative_date((job.get("detected_extensions") or {}).get("posted_at")),
                board="google_jobs",
            )
        )
    return docs


async def fetch_greenhouse(client: httpx.AsyncClient, company: CompanyInfo, slug: str) -> list[Document]:
    resp = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"})
    if resp.status_code != 200:
        return []
    docs = []
    for job in resp.json().get("jobs", []):
        desc = BeautifulSoup(job.get("content") or "", "html.parser").get_text(" ")
        updated = job.get("updated_at")
        docs.append(
            _job_doc(
                company,
                title=job.get("title", ""),
                url=job.get("absolute_url", ""),
                description=desc,
                location=(job.get("location") or {}).get("name", ""),
                posted_at=datetime.fromisoformat(updated) if updated else None,
                board="greenhouse",
            )
        )
    return docs


async def fetch_lever(client: httpx.AsyncClient, company: CompanyInfo, slug: str) -> list[Document]:
    resp = await client.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    if resp.status_code != 200:
        return []
    docs = []
    for job in resp.json():
        created = job.get("createdAt")
        docs.append(
            _job_doc(
                company,
                title=job.get("text", ""),
                url=job.get("hostedUrl", ""),
                description=job.get("descriptionPlain", ""),
                location=(job.get("categories") or {}).get("location", ""),
                posted_at=datetime.fromtimestamp(created / 1000, tz=timezone.utc) if created else None,
                board="lever",
            )
        )
    return docs


async def fetch_workable(client: httpx.AsyncClient, company: CompanyInfo, slug: str) -> list[Document]:
    resp = await client.get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
    if resp.status_code != 200:
        return []
    docs = []
    for job in resp.json().get("jobs", []):
        published = job.get("published_on")
        docs.append(
            _job_doc(
                company,
                title=job.get("title", ""),
                url=job.get("url") or job.get("shortlink", ""),
                description=job.get("description", ""),
                location=", ".join(filter(None, [job.get("city"), job.get("country")])),
                posted_at=datetime.fromisoformat(published).replace(tzinfo=timezone.utc) if published else None,
                board="workable",
            )
        )
    return docs


async def fetch_personio(client: httpx.AsyncClient, company: CompanyInfo, slug: str) -> list[Document]:
    resp = await client.get(f"https://{slug}.jobs.personio.de/xml")
    if resp.status_code != 200:
        return []
    root = ElementTree.fromstring(resp.content)
    docs = []
    for pos in root.findall("position"):
        job_id = pos.findtext("id", "")
        desc = " ".join(clean_text(v.text or "") for v in pos.iter("value"))
        created = pos.findtext("createdAt")
        docs.append(
            _job_doc(
                company,
                title=pos.findtext("name", ""),
                url=f"https://{slug}.jobs.personio.de/job/{job_id}",
                description=BeautifulSoup(desc, "html.parser").get_text(" "),
                location=pos.findtext("office", ""),
                posted_at=datetime.fromisoformat(created) if created else None,
                board="personio",
            )
        )
    return docs


async def fetch_careers_page(client: httpx.AsyncClient, company: CompanyInfo) -> list[Document]:
    """Parse job-looking links from the company's own careers page."""
    url = company.careers_url or (f"https://{company.domain}/careers" if company.domain else None)
    if not url:
        return []
    try:
        resp = await client.get(url)
    except httpx.HTTPError:
        return []
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    docs = []
    for a in soup.find_all("a", href=True):
        title = clean_text(a.get_text(" "))
        if not (8 <= len(title) <= 120):
            continue
        if not categorize_role(title):
            continue
        docs.append(
            _job_doc(company, title=title, url=urljoin(str(resp.url), a["href"]), description="", location="", posted_at=None, board="careers_page")
        )
    return docs


def guess_ats_slugs(company: CompanyInfo) -> list[str]:
    slugs = []
    if company.domain:
        slugs.append(company.domain.lower().removeprefix("www.").split(".")[0])
    slugs.append(re.sub(r"[^a-z0-9]", "", company.name.lower()))
    return list(dict.fromkeys(s for s in slugs if s))


async def collect_jobs(
    company: CompanyInfo,
    *,
    serpapi_key: str | None = None,
    client: httpx.AsyncClient | None = None,
    probe_ats: bool = True,
) -> list[Document]:
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": "OrangeSignals/0.1"})
    try:
        jobs = []
        if serpapi_key:
            jobs.append(("serpapi", fetch_serpapi_jobs(client, company, serpapi_key)))
        boards = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "workable": fetch_workable, "personio": fetch_personio}
        for board, slug in company.ats.items():
            if board in boards:
                jobs.append((board, boards[board](client, company, slug)))
        if probe_ats and not company.ats:
            for slug in guess_ats_slugs(company):
                jobs.append((f"greenhouse:{slug}", fetch_greenhouse(client, company, slug)))
                jobs.append((f"lever:{slug}", fetch_lever(client, company, slug)))
        jobs.append(("careers_page", fetch_careers_page(client, company)))
        docs: list[Document] = []
        for name, job in jobs:
            try:
                docs.extend(await job)
            except (httpx.HTTPError, ValueError, KeyError, ElementTree.ParseError) as exc:
                log.warning("jobs source %s failed for %s: %s", name, company.name, exc)
        docs = [d for d in docs if d.url]
        # Only keep postings relevant to the services we sell; generic roles are noise.
        relevant = [d for d in docs if d.meta.get("categories")]
        return dedupe(relevant)
    finally:
        if own_client:
            await client.aclose()


def hiring_summary(docs: list[Document]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in docs:
        for cat in d.meta.get("categories", []):
            counts[cat] = counts.get(cat, 0) + 1
    return counts
