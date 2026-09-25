import type { AuthMode } from '../auth/session'
import { COMPANIES } from './mock'
import { type ActivityEntry, getJson, listSellers, type Seller } from './client'

export type ActivityCategory = 'acces' | 'leaduri' | 'configurare' | 'rulari' | 'conturi' | 'altele'

export const CATEGORIES: { id: ActivityCategory; label: string }[] = [
  { id: 'leaduri', label: 'Lead-uri' },
  { id: 'acces', label: 'Autentificări' },
  { id: 'configurare', label: 'Configurare' },
  { id: 'rulari', label: 'Rulări' },
  { id: 'conturi', label: 'Conturi' },
  { id: 'altele', label: 'Altele' },
]

export interface TeamEvent {
  t: string
  sellerId: number | null
  seller: string | null
  action: string
  label: string
  category: ActivityCategory
  companyId: string | null
}

/** Backend audit actions ("PUT /companies/{company_id}/assignment", "login", …) as words a manager reads. */
const RULES: [RegExp, string, ActivityCategory][] = [
  [/^login$/, 'S-a autentificat', 'acces'],
  [/^logout$/, 'A ieșit din cont', 'acces'],
  [/\/companies\/\{company_id\}\/assignment$/, 'A actualizat stadiul sau responsabilul unui lead', 'leaduri'],
  [/\/companies\/\{company_id\}\/notes$/, 'A adăugat o notă', 'leaduri'],
  [/\/companies\/\{company_id\}\/outreach/, 'A generat un mesaj de contact', 'leaduri'],
  [/\/companies\/\{company_id\}\/linkedin$/, 'A validat compania pe LinkedIn', 'leaduri'],
  [/\/companies\/\{company_id\}\/manual-signal$/, 'A adăugat un semnal manual', 'leaduri'],
  [/\/companies\/\{company_id\}\/explain/, 'A regenerat explicația scorului', 'leaduri'],
  [/\/crm\/hubspot$/, 'A trimis lead-uri în HubSpot', 'leaduri'],
  [/^POST \/companies\/import$/, 'A importat companii', 'leaduri'],
  [/^POST \/companies$/, 'A adăugat o companie', 'leaduri'],
  [/\/(discovery|bootstrap)\/runs|^POST \/runs$|\/sources\/\{name\}\/sync$/, 'A pornit o rulare de date', 'rulari'],
  [/\/sources/, 'A modificat o sursă de date', 'rulari'],
  [/\/scoring-config|\/scores\/recompute/, 'A schimbat scorarea', 'configurare'],
  [/\/services|\/questions|\/rules|\/icp/, 'A modificat configurarea', 'configurare'],
  [/^POST \/sellers$/, 'A creat un cont', 'conturi'],
  [/\/sellers/, 'A modificat un cont', 'conturi'],
]

export function describe(action: string): { label: string; category: ActivityCategory } {
  for (const [re, label, category] of RULES) if (re.test(action)) return { label, category }
  return { label: action, category: 'altele' }
}

const fromApi = (e: ActivityEntry): TeamEvent => ({
  t: e.t,
  sellerId: e.seller_id,
  seller: e.seller,
  action: e.action,
  ...describe(e.action),
  companyId: e.company_id != null ? String(e.company_id) : null,
})

// ------------------------------------------------------------------ demo team (no server)
const ago = (hours: number) => new Date(Date.now() - hours * 3600_000).toISOString()

const DEMO_TEAM: Seller[] = [
  { id: 101, email: 'ana.rusu@orange.md', full_name: 'Ana Rusu', role: 'seller', active: true, created_at: ago(24 * 70), last_login_at: ago(1.5) },
  { id: 102, email: 'mihai.ceban@orange.md', full_name: 'Mihai Ceban', role: 'seller', active: true, created_at: ago(24 * 64), last_login_at: ago(5) },
  { id: 103, email: 'elena.munteanu@orange.md', full_name: 'Elena Munteanu', role: 'seller', active: true, created_at: ago(24 * 20), last_login_at: ago(24 * 3 + 4) },
  { id: 104, email: 'victor.lungu@orange.md', full_name: 'Victor Lungu', role: 'seller', active: false, created_at: ago(24 * 120), last_login_at: ago(24 * 21) },
  { id: 1, email: 'admin@orange.md', full_name: 'Admin Orange', role: 'admin', active: true, created_at: ago(24 * 150), last_login_at: ago(0.2) },
]

function demoActivity(): TeamEvent[] {
  let seed = 20260925
  const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648)
  const pick = <T,>(xs: T[]) => xs[Math.floor(rnd() * xs.length)]
  const out: TeamEvent[] = []
  const add = (h: number, s: Seller, action: string, companyId: string | null = null) =>
    out.push({ t: ago(h), sellerId: s.id, seller: s.full_name, action, ...describe(action), companyId })
  const intensity: Record<number, number> = { 101: 1, 102: 0.75, 103: 0.3 }
  const leadActions = [
    'PUT /companies/{company_id}/assignment',
    'PUT /companies/{company_id}/assignment',
    'POST /companies/{company_id}/notes',
    'POST /companies/{company_id}/outreach',
    'PUT /companies/{company_id}/linkedin',
  ]
  for (const s of DEMO_TEAM.filter((m) => m.role === 'seller' && m.active)) {
    const own = COMPANIES.filter((c) => c.owner === s.full_name).map((c) => c.id)
    const pool = own.length ? own : COMPANIES.filter((c) => c.stage !== 'descalificat').map((c) => c.id)
    for (let day = 13; day >= 0; day--) {
      if (rnd() > 0.35 + 0.6 * intensity[s.id] || (day % 7 === 5 || day % 7 === 6)) continue
      const start = day * 24 + 14 - rnd() * 2 // ~9:00 local
      add(start, s, 'login')
      const n = Math.round(1 + rnd() * 6 * intensity[s.id])
      for (let k = 0; k < n; k++) add(start - 0.3 - k * (0.4 + rnd()), s, pick(leadActions), pick(pool))
      if (rnd() < 0.25 * intensity[s.id]) add(start - 5, s, 'POST /crm/hubspot')
      if (rnd() < 0.5) add(start - 8, s, 'logout')
    }
  }
  const admin = DEMO_TEAM.find((m) => m.role === 'admin')!
  add(26, admin, 'POST /discovery/runs')
  add(50, admin, 'PUT /scoring-config')
  add(24 * 20, admin, 'POST /sellers')
  const victor = DEMO_TEAM.find((m) => m.id === 104)!
  add(24 * 21, victor, 'login')
  add(24 * 21 - 1, victor, 'POST /companies/{company_id}/notes', 'terranova')
  return out.filter((e) => new Date(e.t).getTime() <= Date.now()).sort((a, b) => b.t.localeCompare(a.t))
}

// ------------------------------------------------------------------ loaders
export async function loadTeam(mode: AuthMode): Promise<Seller[]> {
  if (mode === 'api') return listSellers()
  const events = demoActivity()
  return DEMO_TEAM.map((s) => ({ ...s, last_login_at: events.find((e) => e.sellerId === s.id && e.action === 'login')?.t ?? s.last_login_at }))
}

export async function loadActivity(mode: AuthMode, limit = 1000): Promise<TeamEvent[]> {
  if (mode !== 'api') return demoActivity()
  const rows = await getJson<ActivityEntry[]>(`/activity?limit=${limit}`)
  return rows.map(fromApi)
}

