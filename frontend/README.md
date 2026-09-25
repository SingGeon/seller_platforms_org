# LeadRadar — frontend

CRM-style sales dashboard in the Orange (orange.md) visual style. React 19 + TypeScript + Vite + Tailwind CSS 4 + React Router.

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check + production build
```

Requires Node 22.22+ (the Docker image uses Node 24).

## Pages

| Route | Page | Jira |
|---|---|---|
| `/` | Home — KPIs, fresh signals, top leads to contact | — |
| `/leads` | Lead list — filters (service, country, stage, new), sort, CSV export | GIG-34 |
| `/leads/:id` | Company record — score breakdown, "why now", evidence with sources, timeline, notes | GIG-35 |
| `/pipeline` | Kanban by stage, drag & drop | — |
| `/config` | Signal questions + weights, negative rules, ICP, scoring | GIG-36 |
| `/runs` | Data sources, refresh tiers, run status | GIG-37 |

## Data

All data currently comes from demo data in `src/data/mock.ts` (fictional companies on the reserved `.example` domain),
exposed through `src/data/api.ts`. Wiring to the FastAPI backend (`VITE_API_URL`) only needs changes in `api.ts`;
the shapes the UI expects are in `src/data/types.ts`.

## Design tokens

Defined in `src/index.css` (`@theme`): Orange `#FF7900` (brand, fills) / `#F16E00` (text on white), black header,
Helvetica Neue, square corners, 2px-border buttons, `#EEEEEE` bands. Service colours `#527EDB` / `#50BE87` / `#A885D8`
were checked for colour-blind separation and are always paired with a text label.
