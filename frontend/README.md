# LeadRadar — frontend

CRM-style sales dashboard in the Orange (orange.md) visual style. React 19 + TypeScript + Vite + Tailwind CSS 4 + React Router.

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check + production build
```

Requires Node 22.22+.

## Pages

| Route | Page | Jira |
|---|---|---|
| `/` (logged out) | Login — the home page for visitors, with a Higgsfield-generated looping background and what the platform does (no company data before login). There is no sign-up: sales-manager accounts are created by an admin, admin accounts directly in the database (`python -m app.admin create`). Any app URL opened while logged out comes back here and returns to that URL after login | — |
| `/account` | Personal account — profile, password, my leads, my activity; for admins also **Sales-manager accounts** (create, deactivate, reset password; role is always `seller`) | — |
| `/admin` | Admin only (`role = admin`): team monitoring — KPIs, activity per day, per-seller table (last login, actions, leads, in progress, won, last action) and the filterable activity log | — |
| `/` (logged in) | Home — KPIs, for admins **Impactul LeadRadar** (research hours saved, qualified leads, conversion, pipeline value and gross profit weighted by stage from the server's deal estimates; formulas under "Cum calculăm"), fresh signals, top leads to contact. A short **Ghid rapid** opens on each account's first login and from the "?" in the header | — |
| `/leads` | Lead list — filters (service, industry sector, country, stage, new), sort, pagination, CSV export | GIG-34 |
| `/leads/:id` | Company record — score breakdown, "why now", evidence with sources, timeline, notes, **Valoare estimată pentru Orange** (deal value range, cost, gross profit, win chance and expected profit per service, from `GET /companies/{id}`), **Contacte** (decision makers and published contact details with their sources: company site, news, Hunter.io / Apollo.io, added by hand; "Nu contacta"), contact message (saved; "Generează din nou" asks for a fresh one; "Trimite către" opens the e-mail with recipient, subject and text filled in, or copies it and opens LinkedIn, and logs the send) | GIG-35 |
| `/pipeline` | Kanban by stage, drag & drop | — |
| `/config` | Signal questions + weights, negative rules, ICP, scoring (admins edit, sales managers read). Admins add a service category with "Serviciu nou" (`POST /services`, the shared ICP and an optional first question) and change the deal-estimate assumptions in "Valoare contracte" (`GET/PUT /deal-model`) | GIG-36 |
| `/runs` | Data sources, refresh tiers, run status (admins start runs) | GIG-37 |

## Data

At startup `src/data/api.ts` loads everything from the FastAPI backend (`VITE_API_URL`, default
`http://localhost:8000`) through `src/data/backend.ts`, which maps the API responses onto the shapes in
`src/data/types.ts`. There is no demo data: the app only ever shows what the server returns. The data reloads in the
background every 5 minutes while the tab is visible (and on demand from the header), so results of the daily cloud
run appear without a page refresh. "Rulează acum" on `/runs` (admins) starts a discovery run (`POST /discovery/runs`)
and reloads the data when it ends.

## Sessions

`src/auth/session.tsx` holds the session for every page and always uses the seller accounts on the server
(`/auth/login`, `/auth/me`, `POST /sellers`, `PUT /sellers/{id}`, `GET /activity`). At startup it waits up to two
minutes for `/auth/status`, because the free Render instance needs about a minute to wake up; if the server still does
not answer, the app says so and offers a retry instead of showing anything invented. The same goes for a failed data
load after login. The login background loop lives in `public/media/`. The app is built for desktop screens: below 1024 px wide (phones, small tablets) `src/components/DesktopOnly.tsx` shows a notice with the app address to open on a computer, and a "continue anyway" link.

## Design tokens

Defined in `src/index.css` (`@theme`): Orange `#FF7900` (brand, fills) / `#F16E00` (text on white), black header,
Helvetica Neue, square corners, 2px-border buttons, `#EEEEEE` bands. Service colours `#527EDB` / `#50BE87` / `#A885D8`
were checked for colour-blind separation and are always paired with a text label.
