# Orange Signals: AI B2B sales intelligence for Orange Systems

This platform turns public company information into scored, evidence-backed sales leads. It automates the
manual process described in Annex 1:

```
ICP → Accounts → Public data → Signals → Interpretation → Score → Prioritised accounts
```

Sales users configure an **Ideal Customer Profile**, **signal questions** with weights, **negative signals** and
**disqualification rules** for each service. The platform collects news, website, annual-report and job-posting
data, has an LLM answer every question *with verbatim evidence*, detects business events, then scores and
explains each company × service lead.

## Repository layout

| Path | What |
|---|---|
| `backend/` | FastAPI REST API, PostgreSQL models + Alembic migrations, scoring engine, run orchestration, outreach, CRM export |
| `pipeline/` | `sales_pipeline` package: collectors (news / web / jobs), LangGraph signal-extraction graph, LLM backends, prompts, calibration set |
| `frontend/` | React + Vite app (a minimal shell for now; the dashboard is GIG-33 to GIG-37) |
| `infra/` | Deployment notes / manifests |

## Quick start

```bash
cp .env.example .env          # optional: add ANTHROPIC_API_KEY, NEWSAPI_KEY, SERPAPI_KEY, HUBSPOT_TOKEN
docker compose up --build     # postgres + backend (migrates and seeds) + frontend
```

- API + Swagger: http://localhost:8000/docs
- Frontend: http://localhost:5173
- Start a run: `curl -X POST localhost:8000/runs -H 'content-type: application/json' -d '{}'`

**Offline mode:** without `ANTHROPIC_API_KEY` the pipeline uses a deterministic keyword backend. It never produces
a false "yes", but it misses a lot. With `OFFLINE_COLLECT=true` nothing is fetched from the internet and only stored
documents are analysed. `python -m app.seed --sample-docs` loads sample documents paraphrasing the Annex 1
Lufthansa / DHL examples (marked `meta.sample`, URLs on the reserved `.example` domain) so the demo works end to end
without keys.

### Local development (without Docker)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e pipeline -r backend/requirements.txt
cd backend
export DATABASE_URL=postgresql+psycopg://orange:orange@localhost:5432/orange_signals
alembic upgrade head && python -m app.seed --sample-docs
uvicorn app.main:app --reload
pytest -q                       # backend tests (SQLite, no network)
cd ../pipeline && pytest -q     # pipeline tests (mocked HTTP + mocked Anthropic transport)
python calibration/run_calibration.py --provider anthropic   # signal-answer precision (needs a key)
```

## Data sources: discovery and enrichment (GIG-14)

The platform works in two modes. Limits, keys and fallbacks for every source are listed in
[`docs/data-sources.md`](docs/data-sources.md), which is generated from `pipeline/sales_pipeline/sources/catalog.py`.

- **Discovery (signal → company)** builds the lead universe automatically. The platform searches for the signal
  (an IT tender, a ransomware victim, an RPA job posting, an 8-K cyber disclosure, a press release) and creates or
  matches the company it names. Companies are resolved by web domain, then by normalised name ("GitLab Inc." =
  "GITLAB INC (GTLB)" = "GitLab"). Headlines the parser can't read go to the small LLM for company extraction.
  Sources: TED, MTender, UK Contracts Finder, World Bank, Arbeitnow, Adzuna, HN "Who is hiring", Remotive,
  RemoteOK, Jobicy, Himalayas, The Muse, We Work Remotely, Google News topics (per country, `when:1h/1d`),
  PR Newswire, GlobeNewswire, Bing News, NewsData.io, Currents, ransomware.live, HIBP, DataBreaches.net,
  SEC 8-K Item 1.05 / 5.02 and SEC Form D.
- **Enrichment (company → signals)** runs per company inside enrichment runs: company news (local-language Google
  News, throttled GDELT, NewsAPI), website crawl and tech stack, ATS boards (Greenhouse, Lever, Ashby, Workable,
  SmartRecruiters, Recruitee, Personio), SerpAPI Google Jobs (top N only), Wikidata and GLEIF firmographics
  (Crunchbase replacement), CISA KEV matched against the detected tech stack, and SEC 10-K language for US companies.

A **discovery run** (`POST /discovery/runs`) syncs the selected sources and analyses every company they touched,
using the documents just found. It then fully enriches the `enrich_top_n` best new leads that pass the ICP and the
rules. Each source keeps a cursor in `source_state`, so a sync only fetches what is new. Documents are deduplicated
by content hash, so only new text reaches the LLM. With `SCHEDULER_ENABLED=true` the backend syncs every source
on its catalogue interval (15 min for press releases, hourly for tenders, 6 h for job boards).

**Target markets** ("change the country") are a config value: `PUT /scoring-config` with
`discovery_countries: ["RO", "MD"]`. They drive TED buyer countries, Adzuna countries, Google News editions and
job-location filters. **B2B only**: the global rule "Pure B2C business" disqualifies companies marked `business_model = b2c`.

Check every source live from a machine with internet access (nothing is written):

```bash
cd pipeline && SEC_USER_AGENT="Your Name you@example.com" COUNTRIES=RO,MD python -m sales_pipeline.sources.smoke
```

## Architecture

```mermaid
flowchart LR
  subgraph Sources
    N[GDELT / NewsAPI / Google News RSS]
    W[Company websites, newsrooms, annual-report PDFs]
    J[SerpAPI Google Jobs, Greenhouse / Lever / Workable / Personio, careers pages]
    M[Manual: CSV / Crunchbase import, LinkedIn validation, manual signals]
  end
  Sources --> C[Collectors → common Document, dedupe by URL + title, content hash]
  C --> DB[(PostgreSQL raw_documents)]
  DB --> G
  subgraph G[LangGraph]
    L[load_context] --> R[relevance_filter<br/>lexical, per question] --> A[answer_questions<br/>Claude, batched, JSON schema] --> E[detect_events<br/>small model] --> AG[aggregate]
  end
  A -. quotes verified against sources .-> A
  AG --> S[(signals, company_events)]
  S --> SC[Scoring engine<br/>ICP fit + weighted signals + rules]
  SC --> LS[(lead_scores + breakdown + why-now)]
  LS --> API[FastAPI] --> UI[React dashboard]
  API --> CRM[HubSpot / CSV]
```

### AI pipeline (`pipeline/sales_pipeline/graph.py`)

1. **load_context**: company documents plus the active questions of every selected service, and `llm_question` disqualification rules.
2. **relevance_filter**: splits documents into passages and scores them against each question's keywords. It respects `source_hint` (news/web/jobs) and `lookback_days`. Only the top passages reach the LLM.
3. **answer_questions**: questions for the same company are **batched** into one structured-output call (`claude-opus-5` by default, server-side refusal fallback enabled). Output is strict JSON: `answer yes|no|unknown`, `confidence`, `evidence[{quote, doc_id}]` and `reasoning`.
   **Anti-hallucination:** each quote must fuzzy-match (≥85) the text of a passage selected *for that question*. Otherwise the answer becomes `unknown` with confidence 0.
4. **detect_events**: `claude-haiku-4-5` classifies news and web passages into `security_incident`, `leadership_change`, `tech_stack`, `compliance_event` and `corporate_event` (with polarity), which builds the company timeline.
5. **aggregate**: hands results to the backend, which stores only new or changed signals. Manual signals from reps are never overwritten.

Cost and speed (GIG-28): responses are cached in `llm_cache` by (task, model, company, question, passages), so re-runs cost nothing unless the data changed. Companies run in parallel behind a semaphore, and LLM calls share a concurrency limit. Tokens and estimated USD cost are recorded on each `pipeline_runs` row.

### Scoring (`backend/app/scoring/engine.py`)

```
signal_score = ( Σ w·c·r  over positive "yes" signals
               + event bonus (service.event_weights)
               − Σ w·c·r  over negative "yes" signals ) / Σ w(positive questions) × 100     (clamped 0–100)
final_score  = 0.3 × icp_fit + 0.7 × signal_score                                          (weights configurable)
w: High=3 Medium=2 Low=1    c: confidence    r: recency 1.0 (<30d) 0.7 (<90d) 0.4 (<180d) 0.1 (older) 0.5 (undated)
tier: Hot ≥70, Warm 40–69, Cold <40, Disqualified if a hard rule matches
```

- **ICP fit (0–100)**: industry 30, geography 30 (countries or markets such as DACH/EU/Nordics), size 30, revenue 10. Only configured criteria count. Partial credit is given near the range, and unknown data gets half credit. Leads under `min_fit` are hidden by default (`include_outside_icp=true` shows them).
- **Disqualification**: `field_rule` (existing client, competitor, insolvent, < 50 employees, sanctioned country) or `llm_question` (e.g. insolvency reported, with a confidence threshold). The reasons are returned on the lead.
- Every score has a **breakdown**: points per signal and event (for the bar chart), ICP components, top 3 signals with source links, a recommendation (`contact now` / `nurture` / `monitor` / `exclude`) and a 2–3 sentence "why now" summary generated only from the evidence-backed signals.
- Scores are pure functions of stored data. Every configuration change (ICP, questions, rules, weights) recomputes them instantly, with no LLM call.

## Database (ERD)

```mermaid
erDiagram
  services ||--o| icp_criteria : has
  services ||--o{ signal_questions : has
  services ||--o{ disqualification_rules : "has (NULL = global)"
  companies ||--o{ raw_documents : collected
  companies ||--o{ signals : answered
  companies ||--o{ company_events : timeline
  companies ||--o{ lead_scores : scored
  services ||--o{ lead_scores : for
  signal_questions ||--o{ signals : answers
  disqualification_rules ||--o{ signals : "llm_question answers"
  pipeline_runs ||--o{ signals : produced

  services {
    int id PK
    string name
    string slug
    text value_proposition
    jsonb event_weights
  }
  icp_criteria {
    int id PK
    int service_id FK
    jsonb markets
    jsonb industries
    jsonb countries
    int employee_min
    int employee_max
    float revenue_min
    float revenue_max
    int min_fit
  }
  signal_questions {
    int id PK
    int service_id FK
    text text
    string weight
    string source_hint
    int lookback_days
    bool is_negative
    jsonb keywords
  }
  disqualification_rules {
    int id PK
    int service_id FK
    string rule_type
    string field
    string operator
    jsonb value
    text question
    float min_confidence
  }
  companies {
    int id PK
    string name
    string domain
    string industry
    int employee_count
    string country
    string market
    string crunchbase_url
    string linkedin_url
    jsonb ats
    bool is_existing_client
    bool is_competitor
    jsonb linkedin_validation
  }
  raw_documents {
    int id PK
    int company_id FK
    string source_type
    string url
    text content
    timestamptz published_at
    string content_hash
    jsonb meta
  }
  signals {
    int id PK
    int company_id FK
    int question_id FK
    int rule_id FK
    string origin
    string answer
    float confidence
    jsonb evidence
    timestamptz signal_date
  }
  company_events {
    int id PK
    int company_id FK
    string event_type
    string title
    timestamptz event_date
    string url
    string polarity
  }
  lead_scores {
    int id PK
    int company_id FK
    int service_id FK
    float icp_score
    float signal_score
    float final_score
    string tier
    jsonb breakdown
    jsonb explanation
  }
  scoring_config {
    int id PK
    float icp_weight
    float signal_weight
    float hot_threshold
    float warm_threshold
    jsonb weight_values
    jsonb recency_buckets
  }
  pipeline_runs {
    int id PK
    string status
    jsonb params
    jsonb progress
    jsonb stats
    jsonb log
  }
  llm_cache {
    string key PK
    jsonb value
  }
```

## API (full contract at `/docs`)

| Area | Endpoints |
|---|---|
| Services | `GET/POST /services`, `GET/PUT/DELETE /services/{id}` |
| ICP | `GET /icp`, `GET/PUT/DELETE /icp/{service_id}` |
| Signal questions | `GET/POST /services/{id}/questions`, `PUT/DELETE /services/{id}/questions/{qid}` |
| Rules | `GET/POST /services/{id}/rules`, `GET/POST /rules` (global), `PUT/DELETE /rules/{id}` |
| Scoring | `GET/PUT /scoring-config`, `POST /scores/recompute` |
| Leads | `GET /leads?service=apa&tier=Hot,Warm&country=DE&industry=bank&min_score=&sort=score&include_outside_icp=` |
| Companies | `GET/POST /companies`, `POST /companies/import` (CSV / Crunchbase export), `GET/PUT/DELETE /companies/{id}`, `GET /companies/{id}/events`, `GET /companies/{id}/documents`, `PUT /companies/{id}/linkedin`, `POST /companies/{id}/manual-signal`, `POST /companies/{id}/explain?service=` |
| Sources | `GET /sources` (catalogue + last sync, status, errors, missing keys), `GET/PUT /sources/{name}` (enable, interval, reset cursor), `POST /sources/{name}/sync`, `GET /sources/not-used` |
| Discovery | `POST /discovery/runs` (`{sources?, enrich_top_n?}`); leads carry `is_new`, `previous_score`, `origin`, `discovered_via`; `GET /leads?origin=ted&changed_since_hours=24` |
| Runs | `POST /runs` (`{company_ids?, service_ids?, sources?, explain?}`), `GET /runs`, `GET /runs/{id}` (status, progress, log, per-source stats, tokens, cost) |
| Outreach | `POST /companies/{id}/outreach?service=&channel=email\|linkedin\|followup&tone=formal\|consultative&language=EN\|RO\|DE` |
| CRM | `GET /export/leads.csv`, `GET /export/leads.json`, `POST /crm/hubspot` (body: lead ids) |

LinkedIn is used **only** for manual validation fields entered by reps. Nothing is scraped from LinkedIn.

## Jira mapping (backend / data / AI: Gheorghe Singereanu)

| Task | Status in code |
|---|---|
| GIG-14 Sources, keys, limits | Source catalogue with limits/fallback (`docs/data-sources.md`), 25 discovery + 8 enrichment sources, cursors, throttling (GDELT ≥ 5 s, SEC 10 req/s), 429 backoff, `/sources` status API, scheduler, live smoke script |
| GIG-12 Repo + Docker Compose | Structure, Dockerfiles, `docker-compose.yml` (config validated; full `up` not yet run, see below), `.env.example` |
| GIG-13 PostgreSQL schema | `backend/app/models.py`, Alembic `0001` (applied and round-tripped on Postgres 16), ERD above |
| GIG-15 ICP | `/icp` CRUD, fit score 0–100 with partial matches, `min_fit` filter |
| GIG-16 Signal questions | CRUD with weight / source_hint / lookback_days; APA + Cyber examples seeded; new questions are picked up by the next run (tested) |
| GIG-17 Negative signals + disqualifiers | `is_negative` questions subtract; `field_rule` / `llm_question` rules; reasons shown on the lead |
| GIG-20 News | GDELT + NewsAPI + Google News RSS, company-mention filter, URL + title dedupe |
| GIG-21 Websites | Polite crawler (robots.txt, page cap, rate limit), trafilatura, PDF reports, tech-stack detection, optional Playwright |
| GIG-22 Jobs | SerpAPI Google Jobs, Greenhouse / Lever / Workable / Personio, careers page; roles mapped to RPA / AI-ML / Process Excellence / BA / Security / Digital Transformation |
| GIG-23 Orchestration | Async runner, content-hash dedupe, LLM cache, `pipeline_runs` progress/log, `POST /runs`, idempotent re-runs (tested) |
| GIG-25 LangGraph | 5-node typed graph, retries, end-to-end tested |
| GIG-26 Prompts + evidence | Strict JSON, verbatim quotes verified, few-shot from Annex 1, 12-case calibration set in `pipeline/calibration/` |
| GIG-27 Events | Event classifier + `company_events` timeline, mapped to services via `event_weights` |
| GIG-28 Cost / speed | Batching, cache, small model for classification, concurrency limits, token + cost tracking |
| GIG-29 Scoring | Formula above, configurable, instant recompute |
| GIG-30 Explanation | Breakdown, top 3 signals + links, recommendation, AI "why now" for Hot/Warm |
| GIG-32 REST API | All endpoints above, OpenAPI at `/docs` |
| GIG-38 Outreach | Email / LinkedIn / follow-up drafts grounded in real signals, length limits enforced, `grounded` flag |
| GIG-40 CRM | CSV / JSON export; HubSpot company upsert + note |

### Not yet verified in this environment

- **Live collectors and discovery sources**: the build sandbox's network policy blocks every external data host, so collectors and all 25 discovery sources are covered by mocked-HTTP tests built from each API's documented response format. Run `python -m sales_pipeline.sources.smoke` on a machine with internet access to confirm them live.
- **Claude answers**: no API key was available. The Anthropic backend is tested through the real SDK with a mocked transport (request shape and parsing). The GIG-26 ≥80% precision target still has to be measured with `calibration/run_calibration.py --provider anthropic`. The offline keyword backend scores 58% accuracy / 100% yes-precision on that set.
- **`docker compose up`**: Docker Hub rate-limited image pulls here. The compose file validates, and the same startup sequence (migrate, seed, serve) was run directly against Postgres 16.
