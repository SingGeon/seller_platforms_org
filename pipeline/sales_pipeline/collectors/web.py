"""Company website crawler (GIG-21).

Limited, polite crawl: robots.txt respected, max N pages per domain, rate
limited, prioritising news / press / investors / about / strategy / careers.
Plain HTTP (httpx) is the default; Playwright is used as an optional fallback
for JavaScript-rendered pages when it is installed and enabled.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
from bs4 import BeautifulSoup

from ..documents import Document, clean_text, normalize_url
from ..schemas import CompanyInfo

log = logging.getLogger(__name__)

USER_AGENT = "OrangeSignalsBot/0.1 (+sales-intelligence research; respects robots.txt)"
PRIORITY_PATTERNS = [
    (r"/(news|newsroom|press|media|stories)", 10),
    (r"/(investor|investors|ir|annual-report|reports?)", 9),
    (r"/(strategy|sustainability|about|company|who-we-are)", 8),
    (r"/(careers?|jobs|join-us)", 7),
    (r"/(digital|innovation|technology|transformation|ai)", 6),
]
SKIP_EXT = re.compile(r"\.(jpg|jpeg|png|gif|svg|webp|zip|mp4|mp3|css|js|ico|xml|docx?|xlsx?)$", re.I)

TECH_SIGNATURES = {
    "SAP": [r"\bsap\b", r"s/4hana", r"successfactors"],
    "Salesforce": [r"salesforce", r"force\.com", r"pardot"],
    "UiPath": [r"uipath"],
    "Microsoft Dynamics": [r"dynamics\s?365", r"dynamics\.com"],
    "ServiceNow": [r"servicenow"],
    "Workday": [r"myworkdayjobs", r"workday"],
    "HubSpot": [r"hs-scripts\.com", r"hubspot"],
    "Adobe Experience Manager": [r"/etc\.clientlibs/", r"adobedtm"],
    "Google Analytics": [r"googletagmanager", r"google-analytics"],
    "AWS": [r"amazonaws\.com", r"cloudfront\.net"],
    "Azure": [r"azureedge\.net", r"azurewebsites\.net"],
    "Cloudflare": [r"cloudflare"],
    "OneTrust": [r"onetrust", r"cookielaw\.org"],
}


def url_priority(url: str) -> int:
    path = urlparse(url).path.lower()
    if path.endswith(".pdf") and re.search(r"annual|report|strategy|integrated", path):
        return 9
    for pattern, score in PRIORITY_PATTERNS:
        if re.search(pattern, path):
            return score
    return 1


def detect_tech_stack(html: str, headers: dict[str, str] | None = None) -> list[str]:
    haystack = html.lower() + " " + " ".join(f"{k}:{v}" for k, v in (headers or {}).items()).lower()
    return sorted(name for name, patterns in TECH_SIGNATURES.items() if any(re.search(p, haystack) for p in patterns))


def extract_links(base_url: str, html: str, domain: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        parsed = urlparse(href)
        if parsed.scheme not in ("http", "https"):
            continue
        host = parsed.netloc.lower().removeprefix("www.")
        if host != domain and not host.endswith("." + domain):
            continue
        if SKIP_EXT.search(parsed.path):
            continue
        links.append(href.split("#")[0])
    return links


def extract_html_text(html: str, url: str) -> tuple[str, str, datetime | None]:
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=False) or ""
    meta = trafilatura.extract_metadata(html, default_url=url)
    title = (meta.title if meta and meta.title else "") or ""
    published = None
    if meta and meta.date:
        try:
            published = datetime.fromisoformat(meta.date)
        except ValueError:
            published = None
    if len(text) < 200:
        # Boilerplate removal can be too aggressive on short pages; keep the raw text if richer.
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        raw = soup.get_text(" ")
        if len(clean_text(raw)) > len(text):
            text = raw
    return clean_text(title), clean_text(text), published


def extract_pdf_text(data: bytes, max_pages: int = 15) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages[:max_pages]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - malformed pages are common in annual reports
            continue
    return clean_text(" ".join(parts))


async def _render_with_playwright(url: str) -> str | None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(user_agent=USER_AGENT)
            await page.goto(url, wait_until="networkidle", timeout=20000)
            return await page.content()
        finally:
            await browser.close()


class SiteCrawler:
    def __init__(
        self,
        *,
        max_pages: int = 12,
        delay_seconds: float = 1.0,
        timeout: float = 15.0,
        use_playwright: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.max_pages = max_pages
        self.delay = delay_seconds
        self.use_playwright = use_playwright
        self._client = client
        self._timeout = timeout

    async def _robots(self, client: httpx.AsyncClient, root: str) -> RobotFileParser:
        rp = RobotFileParser()
        try:
            resp = await client.get(urljoin(root, "/robots.txt"))
            rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
        except httpx.HTTPError:
            rp.parse([])
        return rp

    async def crawl(self, company: CompanyInfo) -> list[Document]:
        if not company.domain:
            return []
        domain = company.domain.lower().removeprefix("www.")
        root = f"https://{domain}/"
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        try:
            robots = await self._robots(client, root)
            queue: list[tuple[int, str]] = [(100, root)]
            for path in ("/news", "/press", "/newsroom", "/investors", "/about", "/strategy", "/careers"):
                queue.append((url_priority(path), urljoin(root, path)))
            seen: set[str] = set()
            docs: list[Document] = []
            tech: set[str] = set()
            fetched = 0
            while queue and fetched < self.max_pages:
                queue.sort(key=lambda x: -x[0])
                _, url = queue.pop(0)
                key = normalize_url(url)
                if key in seen:
                    continue
                seen.add(key)
                if not robots.can_fetch(USER_AGENT, url):
                    log.info("robots.txt disallows %s", url)
                    continue
                try:
                    resp = await client.get(url)
                except httpx.HTTPError as exc:
                    log.debug("fetch failed %s: %s", url, exc)
                    continue
                fetched += 1
                if resp.status_code != 200:
                    continue
                ctype = resp.headers.get("content-type", "")
                if "pdf" in ctype or url.lower().endswith(".pdf"):
                    text = extract_pdf_text(resp.content)
                    if text:
                        docs.append(Document(source_type="web", url=str(resp.url), title=urlparse(url).path.rsplit("/", 1)[-1], text=text, source=domain, meta={"kind": "pdf"}))
                    continue
                html = resp.text
                title, text, published = extract_html_text(html, str(resp.url))
                if len(text) < 200 and self.use_playwright:
                    rendered = await _render_with_playwright(str(resp.url))
                    if rendered:
                        html = rendered
                        title, text, published = extract_html_text(html, str(resp.url))
                tech.update(detect_tech_stack(html, dict(resp.headers)))
                if len(text) >= 150:
                    docs.append(
                        Document(
                            source_type="web",
                            url=str(resp.url),
                            title=title or urlparse(url).path,
                            text=text[:20000],
                            published_at=published,
                            source=domain,
                            meta={"kind": "html", "priority": url_priority(url)},
                        )
                    )
                for link in extract_links(str(resp.url), html, domain):
                    if normalize_url(link) not in seen:
                        queue.append((url_priority(link), link))
                await asyncio.sleep(self.delay)
            if tech and docs:
                docs[0].meta["tech_stack"] = sorted(tech)
            if tech:
                docs.append(
                    Document(
                        source_type="web",
                        url=root + "?view=tech-stack",  # distinct URL so dedupe keeps it
                        title=f"Technologies detected on {domain}",
                        text=f"Technologies detected on the {company.name} website: {', '.join(sorted(tech))}.",
                        source=domain,
                        meta={"kind": "tech_stack", "tech_stack": sorted(tech)},
                    )
                )
            return docs
        finally:
            if self._client is None:
                await client.aclose()


async def collect_website(company: CompanyInfo, **kwargs) -> list[Document]:
    return await SiteCrawler(**kwargs).crawl(company)
