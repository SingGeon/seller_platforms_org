// Loads data from the FastAPI backend and maps it onto the UI types in ./types.
// Backend contract: /docs on the API (GIG-32). Used by ./api.ts at startup.
import type { Company, Service, ServiceId, Signal, SignalQuestion, SourceStatus, SourceType, Stage, Weight } from './types'

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

// Backend service slugs -> UI service ids (the UI colours and labels are keyed on these).
const SLUG_TO_SERVICE: Record<string, ServiceId> = { apa: 'automation', automation: 'automation', cyber: 'cyber', digital: 'digital' }
const SERVICE_NAMES: Record<ServiceId, [string, string]> = {
  automation: ['Automatizare cu agenți AI', 'Automatizare'],
  cyber: ['Securitate cibernetică', 'Cyber'],
  digital: ['Transformare digitală', 'Digital'],
}

// ------------------------------------------------------------------ API shapes (subset we read)
interface ApiService { id: number; name: string; slug: string; active: boolean }
interface ApiQuestion { id: number; service_id: number; text: string; weight: 'High' | 'Medium' | 'Low'; is_negative: boolean; active: boolean }
interface ApiRule { id: number; service_id: number | null; name: string; rule_type: string; question: string | null; active: boolean }
interface ApiEvidence { quote?: string; url?: string; date?: string }
interface ApiItem { kind: string; question_id?: number; event_type?: string; label: string; confidence: number; points: number; evidence: ApiEvidence[] }
interface ApiScore {
  service_id: number; final_score: number; previous_score: number | null; score_changed_at: string | null; disqualified: boolean
  summary: string; computed_at: string; signals: ApiItem[]
}
// GET /dashboard/companies: every scored company with its per-service scores and evidence, in one call.
interface ApiDashboardCompany {
  company: { id: number; name: string; domain: string | null; industry: string | null; country: string | null; employee_count: number | null; created_at: string; origin: string }
  scores: ApiScore[]
}
interface ApiSource {
  name: string; label: string; category: string; refresh: string; last_run_at: string | null; last_status: string
  last_error: string | null; missing_keys: string[]; last_stats: { new_documents?: number }
}

async function getJson<T>(path: string, timeoutMs = 8000): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const resp = await fetch(`${API_URL}${path}`, { signal: ctrl.signal })
    if (!resp.ok) throw new Error(`${path}: HTTP ${resp.status}`)
    return (await resp.json()) as T
  } finally {
    clearTimeout(timer)
  }
}

export async function postJson<T>(path: string, body: unknown = {}): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!resp.ok) throw new Error(`${path}: HTTP ${resp.status} ${await resp.text()}`)
  return (await resp.json()) as T
}

// ------------------------------------------------------------------ mapping helpers
const serviceIdFor = (slug: string): ServiceId => SLUG_TO_SERVICE[slug] ?? 'digital'
const weightOf = (w: string): Weight => (w.toLowerCase() as Weight)

const countryNames = (() => {
  try {
    return new Intl.DisplayNames(['ro'], { type: 'region' })
  } catch {
    return null
  }
})()

function sourceTypeOf(url: string, kind: string): SourceType {
  const u = url.toLowerCase()
  if (kind === 'event' && /ransomware|haveibeenpwned|databreaches/.test(u)) return 'breach'
  if (/greenhouse|lever\.co|ashbyhq|workable|smartrecruiters|recruitee|personio|arbeitnow|adzuna|remotive|remoteok|jobicy|himalayas|themuse|weworkremotely|ycombinator|\/jobs?\//.test(u)) return 'job'
  if (/ted\.europa|mtender|contractsfinder|worldbank/.test(u)) return 'tender'
  if (/sec\.gov/.test(u)) return 'filing'
  if (/ransomware|haveibeenpwned|databreaches/.test(u)) return 'breach'
  if (/prnewswire|globenewswire|businesswire/.test(u)) return 'press'
  if (/wikidata|gleif|nvd\.nist/.test(u)) return 'registry'
  if (/news|gdelt|bing\.com/.test(u)) return 'news'
  return 'website'
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return 'sursă'
  }
}

function toIso(date: string | undefined, fallback: string): string {
  if (!date || date === 'unknown') return fallback
  const d = new Date(date)
  return Number.isNaN(d.getTime()) ? fallback : d.toISOString()
}

const CATEGORY_RO: Record<string, string> = {
  jobs: 'Joburi', news: 'Știri', tenders: 'Licitații', cyber: 'Cyber', corporate: 'Raportări oficiale', registry: 'Registre',
}
const TIER_OF: Record<string, SourceStatus['tier']> = { stream: 'stream', feed: 'rss', incremental: 'incremental', snapshot: 'snapshot', daily: 'daily' }

function mapSource(s: ApiSource): SourceStatus {
  const status: SourceStatus['status'] = s.last_status === 'ok' ? 'ok' : s.last_status === 'error' ? 'error' : 'warn'
  const note =
    s.missing_keys.length > 0
      ? `Lipsește cheia: ${s.missing_keys.map((k) => k.toUpperCase()).join(', ')}`
      : s.last_status === 'never'
        ? 'Nu a rulat încă'
        : (s.last_error?.split(' For more information')[0].replace(/ for url '[^']*'/, '') ?? undefined)
  return {
    id: s.name, name: s.label, category: CATEGORY_RO[s.category] ?? s.category, tier: TIER_OF[s.refresh] ?? 'daily',
    lastRun: s.last_run_at ?? '', status, newItems: s.last_stats?.new_documents ?? 0, note,
  }
}

function signalsFrom(detail: ApiDashboardCompany, services: Map<number, ServiceId>): Signal[] {
  const out: Signal[] = []
  for (const score of detail.scores) {
    const service = services.get(score.service_id) ?? null
    for (const [i, item] of score.signals.entries()) {
      const ev = item.evidence?.[0]
      if (!ev?.url || item.points === 0) continue
      out.push({
        id: `${score.service_id}-${i}`,
        questionId: item.question_id != null ? `q:${item.question_id}` : `event:${item.event_type ?? i}`,
        service, title: item.label, quote: ev.quote ?? '', source: hostOf(ev.url), sourceType: sourceTypeOf(ev.url, item.kind),
        url: ev.url, date: toIso(ev.date, score.computed_at), confidence: item.confidence, points: Math.round(item.points),
      })
    }
  }
  return out.sort((a, b) => Math.abs(b.points) - Math.abs(a.points))
}

// ------------------------------------------------------------------ load everything
export interface BackendData {
  services: Service[]
  questions: SignalQuestion[]
  companies: Company[]
  sources: SourceStatus[]
}

export async function loadBackendData(): Promise<BackendData> {
  const [apiServices, dashboard, apiSources, rules] = await Promise.all([
    getJson<ApiService[]>('/services'),
    getJson<ApiDashboardCompany[]>('/dashboard/companies', 60_000),
    getJson<ApiSource[]>('/sources'),
    getJson<ApiRule[]>('/rules'),
  ])
  const active = apiServices.filter((s) => s.active)
  const serviceById = new Map(active.map((s) => [s.id, serviceIdFor(s.slug)]))
  const services: Service[] = active.map((s) => {
    const id = serviceIdFor(s.slug)
    return { id, name: SERVICE_NAMES[id]?.[0] ?? s.name, short: SERVICE_NAMES[id]?.[1] ?? s.name }
  })

  const questionLists = await Promise.all(active.map((s) => getJson<ApiQuestion[]>(`/services/${s.id}/questions`)))
  const questions: SignalQuestion[] = [
    ...questionLists.flat().map((q) => ({
      id: `q:${q.id}`, service: serviceById.get(q.service_id) ?? null, text: q.text, weight: weightOf(q.weight),
      polarity: (q.is_negative ? 'negative' : 'positive') as SignalQuestion['polarity'], active: q.active,
    })),
    ...rules.map((r) => ({
      id: `rule:${r.id}`, service: r.service_id != null ? (serviceById.get(r.service_id) ?? null) : null, text: r.question ?? r.name,
      weight: 'high' as Weight, polarity: 'negative' as const, active: r.active,
    })),
  ]

  const companies: Company[] = dashboard.map((d) => {
    const own = d.scores
    const eligible = own.filter((l) => !l.disqualified)
    const best = [...(eligible.length ? eligible : own)].sort((a, b) => b.final_score - a.final_score)[0]
    const serviceScores = { automation: 0, cyber: 0, digital: 0 } as Record<ServiceId, number>
    for (const l of own) {
      const sid = serviceById.get(l.service_id)
      if (sid) serviceScores[sid] = Math.round(l.final_score)
    }
    const stage: Stage = eligible.length === 0 ? 'descalificat' : 'nou'
    const updated = own.map((l) => l.score_changed_at ?? l.computed_at).sort().at(-1) ?? d.company.created_at
    const c = d.company
    return {
      id: String(c.id), name: c.name, domain: c.domain ?? '', industry: c.industry ?? '—', country: c.country ?? '',
      countryName: c.country ? (countryNames?.of(c.country) ?? c.country) : '—',
      employees: c.employee_count != null ? c.employee_count.toLocaleString('ro-RO') : '—',
      stage, owner: null, score: Math.round(best?.final_score ?? 0), prevScore: Math.round(best?.previous_score ?? best?.final_score ?? 0),
      serviceScores, whyNow: best?.summary ?? '', firstSeen: c.created_at, updatedAt: updated, signals: signalsFrom(d, serviceById),
    }
  })

  return { services, questions, companies, sources: apiSources.map(mapSource) }
}

interface ApiRun { id: number; status: string }

/** Start a discovery run (all configured sources) and wait until it ends. */
export async function runDiscovery(pollMs = 2000, maxWaitMs = 10 * 60_000): Promise<ApiRun> {
  const run = await postJson<ApiRun>('/discovery/runs', {})
  const started = Date.now()
  let current = run
  while (current.status === 'queued' || current.status === 'running') {
    if (Date.now() - started > maxWaitMs) break
    await new Promise((r) => setTimeout(r, pollMs))
    current = await getJson<ApiRun>(`/runs/${run.id}`)
  }
  return current
}
