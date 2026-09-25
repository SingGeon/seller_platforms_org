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
| `/` (logged out) | Login — the home page for visitors, with a Higgsfield-generated looping background and a live signal feed. There is no sign-up: sales-manager accounts are created by an admin, admin accounts directly in the database. Any app URL opened while logged out comes back here and returns to that URL after login | — |
| `/account` | Personal account — profile, password, my leads, my activity; for admins also **Sales-manager accounts** (create, deactivate, reset password; role is always `seller`) | — |
| `/admin` | Admin only (`role = admin`): team monitoring — KPIs, activity per day, per-seller table (last login, actions, leads, in progress, won, last action) and the filterable activity log | — |
| `/` (logged in) | Home — KPIs, fresh signals, top leads to contact | — |
| `/leads` | Lead list — filters (service, country, stage, new), sort, CSV export | GIG-34 |
| `/leads/:id` | Company record — score breakdown, "why now", evidence with sources, timeline, notes | GIG-35 |
| `/pipeline` | Kanban by stage, drag & drop | — |
| `/config` | Signal questions + weights, negative rules, ICP, scoring | GIG-36 |
| `/runs` | Data sources, refresh tiers, run status | GIG-37 |

## Data

At startup `src/data/api.ts` loads everything from the FastAPI backend (`VITE_API_URL`, default
`http://localhost:8000`) through `src/data/backend.ts`, which maps the API responses onto the shapes in
`src/data/types.ts`. If the API is unreachable, or `VITE_USE_MOCK=true`, the app falls back to the fictional demo
data in `src/data/mock.ts` and shows the "Date demo" badge in the header. "Rulează acum" on `/runs` starts a real
discovery run (`POST /discovery/runs`) and reloads the data when it ends.

## Sessions

`src/auth/session.tsx` holds the session for every page. With the API up and `auth_required`, it uses the seller
accounts (`/auth/login`, `/auth/me`, `POST /sellers`, `PUT /sellers/{id}`, `GET /activity`). With the API down,
`VITE_USE_MOCK=true` or auth switched off, login keeps a local demo session in the browser (no password is stored):
an email starting with `admin` enters as administrator, anything else as a sales manager, and the admin pages use a
fictional demo team (`src/data/team.ts`). The login background loop lives in `public/media/`.

## Design tokens

Defined in `src/index.css` (`@theme`): Orange `#FF7900` (brand, fills) / `#F16E00` (text on white), black header,
Helvetica Neue, square corners, 2px-border buttons, `#EEEEEE` bands. Service colours `#527EDB` / `#50BE87` / `#A885D8`
were checked for colour-blind separation and are always paired with a text label.
