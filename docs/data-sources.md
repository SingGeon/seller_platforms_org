# Data sources: limits, fallback, refresh (GIG-14)

Generated from `pipeline/sales_pipeline/sources/catalog.py`; edit the catalogue, then run
`python -m sales_pipeline.sources.catalog > docs/data-sources.md`. Live status per source: `GET /sources`.

Keys go in `.env` only (never in Git, Jira or Notion). A source whose key is missing is skipped automatically.

## Discovery (signal → company)

| Source | Category | Refresh | Every | Key | Coverage | Limits | Fallback |
|---|---|---|---|---|---|---|---|
| **TED: EU public tenders (API v3)** (`ted`) | tenders | incremental (since cursor) | 1 h | none | EU/EEA | No key. Filter by CPV (72*/48* IT), buyer country, publication date. | Country-specific portals (MTender, Contracts Finder). |
| **MTender: Moldova public tenders (OCDS)** (`mtender`) | tenders | incremental (since cursor) | 1 h | none | MD | No key. Slow (~10 s per call), paged by `offset` timestamp; one detail call per tender. | TED does not cover MD; World Bank notices for donor-funded projects. |
| **UK Contracts Finder (OCDS)** (`uk_contracts_finder`) | tenders | incremental (since cursor) | 1 h | none | GB | No key. `publishedFrom` incremental search. | Find a Tender (UK, above-threshold notices); TED no longer covers the UK. |
| **World Bank procurement notices** (`world_bank`) | tenders | incremental (since cursor) | 6 h | none | global | No key. Full-text `qterm` search, 100+ countries incl. MD/RO neighbours. | TED / MTender. |
| **Arbeitnow: EU job board API** (`arbeitnow`) | jobs | snapshot diff | 3 h | none | EU (DE-heavy) | No key, 100 jobs per page, aggregates ATS boards. | Adzuna (key), remote boards. |
| **Adzuna job search** (`adzuna`) | jobs | incremental (since cursor) | 6 h | ADZUNA_APP_ID, ADZUNA_APP_KEY | GB DE FR NL AT BE CH IT ES PL US CA | Free: 250 requests/day, 2,500/month; commercial use = 14-day trial. | Arbeitnow + ATS boards. |
| **Hacker News 'Who is hiring' (Algolia)** (`hn_who_is_hiring`) | jobs | snapshot diff | 12 h | none | global | No key. One thread per month; free text, company = text before the first '|'. | Remote job boards. |
| **Remotive remote jobs** (`remotive`) | jobs | snapshot diff | 6 h | none | global | No key; please keep to a few calls per day. | RemoteOK / Jobicy. |
| **RemoteOK** (`remoteok`) | jobs | snapshot diff | 6 h | none | global | No key; attribution link required when displaying jobs. | Remotive. |
| **Jobicy remote jobs** (`jobicy`) | jobs | snapshot diff | 6 h | none | global | No key; tag + geo filters. | Remotive. |
| **Himalayas remote jobs** (`himalayas`) | jobs | snapshot diff | 6 h | none | global | No key; 20 jobs per page. | Remotive. |
| **The Muse** (`themuse`) | jobs | incremental (since cursor) | 6 h | none | global | No key (optional key raises the limit). | Adzuna. |
| **We Work Remotely (RSS)** (`weworkremotely`) | jobs | feed (RSS/Atom) | 3 h | none | global | RSS, no key. | Remotive. |
| **Google News RSS: topic search (when:1h/1d, per country)** (`google_news_topics`) | news | feed (RSS/Atom) | 30 min | none | global | No key; ~100 items per query. hl/gl select the market's language edition. | Bing News RSS, NewsData.io. |
| **PR Newswire RSS** (`prnewswire`) | news | feed (RSS/Atom) | 15 min | none | global | RSS, no key, ~20 latest per feed. | GlobeNewswire. |
| **GlobeNewswire RSS** (`globenewswire`) | news | feed (RSS/Atom) | 15 min | none | global | RSS, no key; organisation name in dc:contributor. | PR Newswire. |
| **Bing News RSS** (`bing_news`) | news | feed (RSS/Atom) | 1 h | none | global | RSS, no key, unofficial endpoint. | Google News RSS. |
| **NewsData.io** (`newsdata`) | news | incremental (since cursor) | 2 h | NEWSDATA_KEY | global | Free: 200 credits/day (~60-80 real requests), 206 countries. | Google News RSS per country. |
| **Currents API** (`currents`) | news | incremental (since cursor) | 2 h | CURRENTS_KEY | global | Free: 250 requests/day, commercial use allowed. | Google News RSS. |
| **ransomware.live recent victims (API v2)** (`ransomware_live`) | cyber | feed (RSS/Atom) | 30 min | none | global | No key; victim, domain, country, sector. | RansomPosts JSON/Atom. |
| **Have I Been Pwned breach catalogue** (`hibp`) | cyber | feed (RSS/Atom) | 6 h | none | global | Catalogue free, no key; domain/email search is paid (not used). | DataBreaches.net RSS. |
| **DataBreaches.net RSS** (`databreaches`) | cyber | feed (RSS/Atom) | 1 h | none | global | RSS, no key; free-text headlines. | HIBP. |
| **SEC 8-K Item 1.05: material cyber incidents** (`sec_8k_cyber`) | corporate | incremental (since cursor) | 1 h | SEC_USER_AGENT | US-listed | No key; User-Agent with contact email mandatory; max 10 req/s. | ransomware.live / HIBP for non-US companies. |
| **SEC 8-K Item 5.02: officer changes** (`sec_8k_leadership`) | corporate | incremental (since cursor) | 1 h | SEC_USER_AGENT | US-listed | As above. | Press releases (GlobeNewswire 'Management Changes'). |
| **SEC Form D: new funding rounds** (`sec_form_d`) | corporate | feed (RSS/Atom) | 1 h | SEC_USER_AGENT | US | As above; latest 100 filings per poll. | Press releases (funding). |

## Enrichment (company → signals)

| Source | Category | Refresh | Every | Key | Coverage | Limits | Fallback |
|---|---|---|---|---|---|---|---|
| **Company news: Google News + Bing News (local editions) + GDELT + NewsAPI** (`company_news`) | news | incremental (since cursor) | 24 h | none | global | Google News: 1 request / 2 s, answers 503 for hours if queried faster. Bing News RSS: no key, ~12 latest articles, 1 request / 1.5 s. GDELT: 1 request / 5 s. NewsAPI: 100/day, dev-only, 24 h delay, 1 month history. | Google News and Bing News cover each other; GDELT and NewsAPI are supplements. |
| **RO / MD business press RSS: ZF, Economica, Profit, StartupCafe, HotNews, G4Media, Biziday, NewsMaker, Ziarul de Garda, Bani.md, Diez** (`business_press`) | news | feed (RSS/Atom) | 1 h | none | global | No key; one request per outlet (WordPress feeds paged for older articles) covers every company at once; articles are matched to companies by name (one-word names only with exact capitalisation). | Google News / Bing News per company. |
| **Company website crawl (newsroom, about, annual-report PDFs, tech stack)** (`company_website`) | news | daily | 24 h | none | global | robots.txt respected, max 12 pages/domain, 1 s between requests. | Playwright for JS-rendered pages (USE_PLAYWRIGHT). |
| **Company ATS boards: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, Personio** (`ats_boards`) | jobs | snapshot diff | 6 h | none | global | No key; needs the company's board slug (guessed from domain/name or set in `companies.ats`). | Careers page parsing; SerpAPI Google Jobs. |
| **SerpAPI Google Jobs** (`serpapi_jobs`) | jobs | incremental (since cursor) | 24 h | SERPAPI_KEY | global | Free: ~100-250 searches/month. Used only for the top-N scored companies (SERPAPI_TOP_N). | ATS boards + Arbeitnow/Adzuna. |
| **Wikidata: industry, country, employees, website** (`wikidata`) | registry | daily | 24 h | none | global | No key; good coverage for large companies, weak for SMEs. | GLEIF, CSV import (Crunchbase API is Enterprise-only in 2026). |
| **GLEIF LEI: legal entity, country, ultimate parent** (`gleif`) | registry | daily | 24 h | none | global | No key; 60 requests/min. | Wikidata. |
| **CISA KEV x detected tech stack** (`cisa_kev`) | cyber | daily | 24 h | none | global | No key; single JSON file (~1.7k entries). | None needed. |
| **SEC 10-K full-text: automation / cost / cyber language** (`sec_10k`) | corporate | daily | 24 h | SEC_USER_AGENT | US-listed | As SEC above. | Annual-report PDFs from the company website. |

## Evaluated and not used (yet)

| Source | Why |
|---|---|
| LinkedIn / Sales Navigator | The brief forbids depending on LinkedIn scraping/API. Manual validation fields only (GIG-24). |
| Crunchbase API | Free tier removed in 2026, API needs an Enterprise licence. CSV import + Wikidata/GLEIF instead. |
| Apollo.io API | Free plan has no API access and blocks @gmail accounts. |
| BuiltWith / Wappalyzer API | No free API (from $450/month). Tech stack is detected from the website HTML instead. |
| Reddit API | New apps need manual approval since 2025. |
| rabota.md, delucru.md, ejobs.ro, bestjobs | No public API; Playwright scraping only with ToS/robots.txt review (stretch). |
| Companies House streaming, Wikimedia EventStreams, HN /v0/updates | Real-time streams: stretch goal; the feeds above are polled every 15-60 min instead. |
| ANAF / DemoANAF, data.gov.ro (ONRC) | Need the company's CUI or bulk CSV processing: next step for the RO market. |
| Jooble, GNews, TheNewsAPI, RTPR, SAM.gov, crt.sh, GitHub, Bluesky | Low value or strict limits for the MVP; add as SourceSpec entries when needed. |

## Refresh rules

1. Every source keeps a cursor (last date / seen IDs) in `source_cursors`, so a sync only fetches what is new.
2. Documents are deduplicated by URL + content hash; only new documents reach the LLM.
3. A new signal re-scores only the companies it touched.
4. A lead is flagged `is_new` for 24 h after discovery, and `previous_score` shows the score movement.

