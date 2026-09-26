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
  /** A failed login or another event an admin should notice. */
  alert: boolean
}

const STAGE_RO: Record<string, string> = {
  nou: 'Nou', calificat: 'Calificat', contactat: 'Contactat', negociere: 'În negociere', castigat: 'Câștigat', descalificat: 'Descalificat',
}
const CHANGE_RO: Record<string, string> = { name: 'nume', password: 'parolă resetată', activated: 'reactivat', deactivated: 'dezactivat' }
const str = (v: unknown) => (typeof v === 'string' && v ? v : null)

/** Explicit events with details, when the backend records them; the generic audit paths below cover the rest. */
const DETAILED: Record<string, (d: Record<string, unknown>) => { label: string; category: ActivityCategory; alert?: boolean }> = {
  lead_stage: (d) => ({ label: `A mutat lead-ul din ${STAGE_RO[str(d.stage_from) ?? ''] ?? '—'} în ${STAGE_RO[str(d.stage_to) ?? ''] ?? '—'}`, category: 'leaduri' }),
  lead_assign: (d) => ({ label: str(d.owner_to) ? `A asignat lead-ul lui ${d.owner_to}` : 'A scos responsabilul lead-ului', category: 'leaduri' }),
  lead_note: (d) => ({ label: str(d.excerpt) ? `A adăugat o notă: „${d.excerpt}”` : 'A adăugat o notă', category: 'leaduri' }),
  seller_create: (d) => ({ label: `A creat contul lui ${str(d.target) ?? 'un sales manager'}`, category: 'conturi' }),
  seller_update: (d) => ({
    label: `A modificat contul lui ${str(d.target) ?? 'un sales manager'}${Array.isArray(d.changes) && d.changes.length ? ` (${d.changes.map((c) => CHANGE_RO[String(c)] ?? String(c)).join(', ')})` : ''}`,
    category: 'conturi',
  }),
  seller_delete: (d) => ({ label: `A șters contul lui ${str(d.target) ?? 'un sales manager'}`, category: 'conturi' }),
  login_failed: (d) => ({ label: `Autentificare eșuată${str(d.email) ? ` pentru ${d.email}` : ''}`, category: 'acces', alert: true }),
  integrity_repair: () => ({ label: 'A reparat legăturile dintre baze de date', category: 'altele' }),
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

export function describe(action: string, details: Record<string, unknown> = {}): { label: string; category: ActivityCategory; alert: boolean } {
  const detailed = DETAILED[action]
  if (detailed) {
    const r = detailed(details)
    return { ...r, alert: r.alert ?? false }
  }
  for (const [re, label, category] of RULES) if (re.test(action)) return { label, category, alert: false }
  return { label: action, category: 'altele', alert: false }
}

const fromApi = (e: ActivityEntry): TeamEvent => ({
  t: e.t,
  sellerId: e.seller_id,
  seller: e.seller,
  action: e.action,
  ...describe(e.action, e.details ?? {}),
  companyId: e.company_id != null ? String(e.company_id) : null,
})

// ------------------------------------------------------------------ loaders
export const loadTeam = (): Promise<Seller[]> => listSellers()

export async function loadActivity(limit = 1000): Promise<TeamEvent[]> {
  const rows = await getJson<ActivityEntry[]>(`/activity?limit=${limit}`)
  return rows.map(fromApi)
}
