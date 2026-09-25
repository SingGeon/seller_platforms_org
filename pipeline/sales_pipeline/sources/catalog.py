"""Catalogue of every public data source: limits, fallback and refresh cadence (GIG-14).

`docs/data-sources.md` is generated from this list (python -m sales_pipeline.sources.catalog),
and the backend's /sources API and scheduler read it too, so the limits the team
agreed on live next to the code that must respect them.
"""
from __future__ import annotations

from .base import SourceSpec
from .cyber import sync_hibp, sync_ransomware_live
from .jobboards import sync_adzuna, sync_arbeitnow, sync_himalayas, sync_hn_hiring, sync_jobicy, sync_remoteok, sync_remotive, sync_themuse, sync_wwr
from .newsfeeds import sync_bing_news, sync_currents, sync_databreaches, sync_globenewswire, sync_google_news_topics, sync_newsdata, sync_prnewswire
from .sec import sync_sec_8k_cyber, sync_sec_8k_leadership, sync_sec_form_d
from .tenders import sync_mtender, sync_ted, sync_uk_contracts, sync_world_bank

D, E = "discovery", "enrichment"

SOURCES: list[SourceSpec] = [
    # ---------------------------------------------------------------- tenders
    SourceSpec("ted", "TED: EU public tenders (API v3)", D, "tenders", "incremental", 60, ["all"],
               limits="No key. Filter by CPV (72*/48* IT), buyer country, publication date.", fallback="Country-specific portals (MTender, Contracts Finder).",
               coverage="EU/EEA", sync=sync_ted),
    SourceSpec("mtender", "MTender: Moldova public tenders (OCDS)", D, "tenders", "incremental", 60, ["all"],
               limits="No key. Slow (~10 s per call), paged by `offset` timestamp; one detail call per tender.", fallback="TED does not cover MD; World Bank notices for donor-funded projects.",
               coverage="MD", sync=sync_mtender),
    SourceSpec("uk_contracts_finder", "UK Contracts Finder (OCDS)", D, "tenders", "incremental", 60, ["all"],
               limits="No key. `publishedFrom` incremental search.", fallback="Find a Tender (UK, above-threshold notices); TED no longer covers the UK.", coverage="GB",
               sync=sync_uk_contracts),
    SourceSpec("world_bank", "World Bank procurement notices", D, "tenders", "incremental", 360, ["all"],
               limits="No key. Full-text `qterm` search, 100+ countries incl. MD/RO neighbours.", fallback="TED / MTender.", sync=sync_world_bank),
    # ---------------------------------------------------------------- jobs
    SourceSpec("arbeitnow", "Arbeitnow: EU job board API", D, "jobs", "snapshot", 180, ["all"],
               limits="No key, 100 jobs per page, aggregates ATS boards.", fallback="Adzuna (key), remote boards.", coverage="EU (DE-heavy)", sync=sync_arbeitnow),
    SourceSpec("adzuna", "Adzuna job search", D, "jobs", "incremental", 360, ["all"], requires=["adzuna_app_id", "adzuna_app_key"],
               limits="Free: 250 requests/day, 2,500/month; commercial use = 14-day trial.", fallback="Arbeitnow + ATS boards.",
               coverage="GB DE FR NL AT BE CH IT ES PL US CA", sync=sync_adzuna),
    SourceSpec("hn_who_is_hiring", "Hacker News 'Who is hiring' (Algolia)", D, "jobs", "snapshot", 720, ["apa"],
               limits="No key. One thread per month; free text, company = text before the first '|'.", fallback="Remote job boards.", sync=sync_hn_hiring),
    SourceSpec("remotive", "Remotive remote jobs", D, "jobs", "snapshot", 360, ["all"], limits="No key; please keep to a few calls per day.", fallback="RemoteOK / Jobicy.", sync=sync_remotive),
    SourceSpec("remoteok", "RemoteOK", D, "jobs", "snapshot", 360, ["all"], limits="No key; attribution link required when displaying jobs.", fallback="Remotive.", sync=sync_remoteok),
    SourceSpec("jobicy", "Jobicy remote jobs", D, "jobs", "snapshot", 360, ["all"], limits="No key; tag + geo filters.", fallback="Remotive.", sync=sync_jobicy),
    SourceSpec("himalayas", "Himalayas remote jobs", D, "jobs", "snapshot", 360, ["all"], limits="No key; 20 jobs per page.", fallback="Remotive.", sync=sync_himalayas),
    SourceSpec("themuse", "The Muse", D, "jobs", "incremental", 360, ["all"], limits="No key (optional key raises the limit).", fallback="Adzuna.", sync=sync_themuse),
    SourceSpec("weworkremotely", "We Work Remotely (RSS)", D, "jobs", "feed", 180, ["all"], limits="RSS, no key.", fallback="Remotive.", sync=sync_wwr),
    # ---------------------------------------------------------------- news / press releases
    SourceSpec("google_news_topics", "Google News RSS: topic search (when:1h/1d, per country)", D, "news", "feed", 30, ["all"],
               limits="No key; ~100 items per query. hl/gl select the market's language edition.", fallback="Bing News RSS, NewsData.io.", sync=sync_google_news_topics),
    SourceSpec("prnewswire", "PR Newswire RSS", D, "news", "feed", 15, ["all"], limits="RSS, no key, ~20 latest per feed.", fallback="GlobeNewswire.", sync=sync_prnewswire),
    SourceSpec("globenewswire", "GlobeNewswire RSS", D, "news", "feed", 15, ["all"], limits="RSS, no key; organisation name in dc:contributor.", fallback="PR Newswire.", sync=sync_globenewswire),
    SourceSpec("bing_news", "Bing News RSS", D, "news", "feed", 60, ["all"], limits="RSS, no key, unofficial endpoint.", fallback="Google News RSS.", sync=sync_bing_news),
    SourceSpec("newsdata", "NewsData.io", D, "news", "incremental", 120, ["all"], requires=["newsdata_key"],
               limits="Free: 200 credits/day (~60-80 real requests), 206 countries.", fallback="Google News RSS per country.", sync=sync_newsdata),
    SourceSpec("currents", "Currents API", D, "news", "incremental", 120, ["all"], requires=["currents_key"],
               limits="Free: 250 requests/day, commercial use allowed.", fallback="Google News RSS.", sync=sync_currents),
    # ---------------------------------------------------------------- cyber
    SourceSpec("ransomware_live", "ransomware.live recent victims (API v2)", D, "cyber", "feed", 30, ["cyber"],
               limits="No key; victim, domain, country, sector.", fallback="RansomPosts JSON/Atom.", sync=sync_ransomware_live),
    SourceSpec("hibp", "Have I Been Pwned breach catalogue", D, "cyber", "feed", 360, ["cyber"],
               limits="Catalogue free, no key; domain/email search is paid (not used).", fallback="DataBreaches.net RSS.", sync=sync_hibp),
    SourceSpec("databreaches", "DataBreaches.net RSS", D, "cyber", "feed", 60, ["cyber"], limits="RSS, no key; free-text headlines.", fallback="HIBP.", sync=sync_databreaches),
    # ---------------------------------------------------------------- SEC (US-listed)
    SourceSpec("sec_8k_cyber", "SEC 8-K Item 1.05: material cyber incidents", D, "corporate", "incremental", 60, ["cyber"], requires=["sec_user_agent"],
               limits="No key; User-Agent with contact email mandatory; max 10 req/s.", fallback="ransomware.live / HIBP for non-US companies.", coverage="US-listed", sync=sync_sec_8k_cyber),
    SourceSpec("sec_8k_leadership", "SEC 8-K Item 5.02: officer changes", D, "corporate", "incremental", 60, ["all"], requires=["sec_user_agent"],
               limits="As above.", fallback="Press releases (GlobeNewswire 'Management Changes').", coverage="US-listed", sync=sync_sec_8k_leadership),
    SourceSpec("sec_form_d", "SEC Form D: new funding rounds", D, "corporate", "feed", 60, ["all"], requires=["sec_user_agent"],
               limits="As above; latest 100 filings per poll.", fallback="Press releases (funding).", coverage="US", sync=sync_sec_form_d),
    # ---------------------------------------------------------------- enrichment (per company; run by the orchestrator)
    SourceSpec("company_news", "Company news: Google News + Bing News (local editions) + GDELT + NewsAPI", E, "news", "incremental", 1440, ["all"],
               limits="Google News: 1 request / 2 s, answers 503 for hours if queried faster. Bing News RSS: no key, ~12 latest "
                      "articles, 1 request / 1.5 s. GDELT: 1 request / 5 s. NewsAPI: 100/day, dev-only, 24 h delay, 1 month history.",
               fallback="Google News and Bing News cover each other; GDELT and NewsAPI are supplements."),
    SourceSpec("business_press", "RO / MD business press RSS: ZF, Economica, Profit, StartupCafe, HotNews, G4Media, Biziday, "
               "NewsMaker, Ziarul de Garda, Bani.md, Diez", E, "news", "feed", 60, ["all"],
               limits="No key; one request per outlet (WordPress feeds paged for older articles) covers every company at once; "
                      "articles are matched to companies by name (one-word names only with exact capitalisation).",
               fallback="Google News / Bing News per company."),
    SourceSpec("company_website", "Company website crawl (newsroom, about, annual-report PDFs, tech stack)", E, "news", "daily", 1440, ["all"],
               limits="robots.txt respected, max 12 pages/domain, 1 s between requests.", fallback="Playwright for JS-rendered pages (USE_PLAYWRIGHT)."),
    SourceSpec("ats_boards", "Company ATS boards: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, Personio", E, "jobs", "snapshot", 360, ["all"],
               limits="No key; needs the company's board slug (guessed from domain/name or set in `companies.ats`).", fallback="Careers page parsing; SerpAPI Google Jobs."),
    SourceSpec("serpapi_jobs", "SerpAPI Google Jobs", E, "jobs", "incremental", 1440, ["all"], requires=["serpapi_key"],
               limits="Free: ~100-250 searches/month. Used only for the top-N scored companies (SERPAPI_TOP_N).", fallback="ATS boards + Arbeitnow/Adzuna."),
    SourceSpec("wikidata", "Wikidata: industry, country, employees, website", E, "registry", "daily", 1440, ["all"],
               limits="No key; good coverage for large companies, weak for SMEs.", fallback="GLEIF, CSV import (Crunchbase API is Enterprise-only in 2026)."),
    SourceSpec("gleif", "GLEIF LEI: legal entity, country, ultimate parent", E, "registry", "daily", 1440, ["all"],
               limits="No key; 60 requests/min.", fallback="Wikidata."),
    SourceSpec("cisa_kev", "CISA KEV x detected tech stack", E, "cyber", "daily", 1440, ["cyber"],
               limits="No key; single JSON file (~1.7k entries).", fallback="None needed."),
    SourceSpec("sec_10k", "SEC 10-K full-text: automation / cost / cyber language", E, "corporate", "daily", 1440, ["all"], requires=["sec_user_agent"],
               limits="As SEC above.", fallback="Annual-report PDFs from the company website.", coverage="US-listed"),
]

NOT_IMPLEMENTED = [
    ("LinkedIn / Sales Navigator", "The brief forbids depending on LinkedIn scraping/API. Manual validation fields only (GIG-24)."),
    ("Crunchbase API", "Free tier removed in 2026, API needs an Enterprise licence. CSV import + Wikidata/GLEIF instead."),
    ("Apollo.io API", "Free plan has no API access and blocks @gmail accounts."),
    ("BuiltWith / Wappalyzer API", "No free API (from $450/month). Tech stack is detected from the website HTML instead."),
    ("Reddit API", "New apps need manual approval since 2025."),
    ("rabota.md, delucru.md, ejobs.ro, bestjobs", "No public API; Playwright scraping only with ToS/robots.txt review (stretch)."),
    ("Companies House streaming, Wikimedia EventStreams, HN /v0/updates", "Real-time streams: stretch goal; the feeds above are polled every 15-60 min instead."),
    ("ANAF / DemoANAF, data.gov.ro (ONRC)", "Need the company's CUI or bulk CSV processing: next step for the RO market."),
    ("Jooble, GNews, TheNewsAPI, RTPR, SAM.gov, crt.sh, GitHub, Bluesky", "Low value or strict limits for the MVP; add as SourceSpec entries when needed."),
]

BY_NAME = {s.name: s for s in SOURCES}


def render_markdown() -> str:
    refresh_icon = {"stream": "stream", "feed": "feed (RSS/Atom)", "incremental": "incremental (since cursor)", "snapshot": "snapshot diff", "daily": "daily"}
    lines = [
        "# Data sources: limits, fallback, refresh (GIG-14)",
        "",
        "Generated from `pipeline/sales_pipeline/sources/catalog.py`; edit the catalogue, then run",
        "`python -m sales_pipeline.sources.catalog > docs/data-sources.md`. Live status per source: `GET /sources`.",
        "",
        "Keys go in `.env` only (never in Git, Jira or Notion). A source whose key is missing is skipped automatically.",
        "",
    ]
    for mode, title in (("discovery", "Discovery (signal → company)"), ("enrichment", "Enrichment (company → signals)")):
        lines += [f"## {title}", "", "| Source | Category | Refresh | Every | Key | Coverage | Limits | Fallback |", "|---|---|---|---|---|---|---|---|"]
        for s in SOURCES:
            if s.mode != mode:
                continue
            key = ", ".join(k.upper() for k in s.requires) or "none"
            every = f"{s.interval_minutes // 60} h" if s.interval_minutes >= 60 else f"{s.interval_minutes} min"
            lines.append(f"| **{s.label}** (`{s.name}`) | {s.category} | {refresh_icon[s.refresh]} | {every} | {key} | {s.coverage} | {s.limits} | {s.fallback} |")
        lines.append("")
    lines += ["## Evaluated and not used (yet)", "", "| Source | Why |", "|---|---|"]
    lines += [f"| {n} | {why} |" for n, why in NOT_IMPLEMENTED]
    lines += [
        "",
        "## Refresh rules",
        "",
        "1. Every source keeps a cursor (last date / seen IDs) in `source_cursors`, so a sync only fetches what is new.",
        "2. Documents are deduplicated by URL + content hash; only new documents reach the LLM.",
        "3. A new signal re-scores only the companies it touched.",
        "4. A lead is flagged `is_new` for 24 h after discovery, and `previous_score` shows the score movement.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_markdown())
