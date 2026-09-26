// Loads data from the FastAPI backend and maps it onto the UI types in ./types.
// Backend contract: /docs on the API (GIG-32). Used by ./api.ts at startup.
import { del, getJson, postJson, putJson } from './client'
import type { Company, Service, ServiceId, Signal, SignalQuestion, SourceStatus, SourceType, Stage, Weight } from './types'

// Backend service slugs -> UI service ids: the slug itself, except "apa", which keeps the id the demo data uses.
const SLUG_ALIAS: Record<string, ServiceId> = { apa: 'automation' }
// Romanian [name, short label] for the services we know; any other service shows the name configured on the server.
const SERVICE_NAMES: Record<ServiceId, [string, string]> = {
  automation: ['Automatizare cu agenți AI', 'Automatizare'],
  cyber: ['Securitate cibernetică', 'Cyber'],
  digital: ['Transformare digitală', 'Digital'],
  cloud: ['Cloud & infrastructură', 'Cloud'],
  data: ['Date & AI (BI)', 'Date & AI'],
  erp: ['ERP / CRM & integrare', 'ERP / CRM'],
  iot: ['IoT & telecom', 'IoT'],
}

// ------------------------------------------------------------------ API shapes (subset we read)
interface ApiService { id: number; name: string; slug: string; active: boolean }
interface ApiQuestion { id: number; service_id: number; text: string; weight: 'High' | 'Medium' | 'Low'; is_negative: boolean; active: boolean }
interface ApiRule { id: number; service_id: number | null; name: string; rule_type: string; question: string | null; active: boolean }
interface ApiEvidence { quote?: string; url?: string; date?: string }
interface ApiItem { kind: string; question_id?: number; event_type?: string; label: string; confidence: number; points: number; evidence: ApiEvidence[] }
interface ApiScore {
  lead_id: number; service_id: number; final_score: number; previous_score: number | null; score_changed_at: string | null; disqualified: boolean
  summary: string; computed_at: string; signals: ApiItem[]
}
// GET /dashboard/companies: every scored company with its per-service scores and evidence, in one call.
interface ApiDashboardCompany {
  company: { id: number; name: string; domain: string | null; industry: string | null; country: string | null; employee_count: number | null; created_at: string; origin: string }
  scores: ApiScore[]
  // PostgreSQL lead_assignments, joined in by the backend
  assignment: { stage: Stage | null; seller_id: number | null; owner: string | null; notes: number; updated_at: string | null }
}
interface ApiSource {
  name: string; label: string; category: string; refresh: string; last_run_at: string | null; last_status: string
  last_error: string | null; missing_keys: string[]; last_stats: { new_documents?: number }
}

// ------------------------------------------------------------------ mapping helpers
const serviceIdFor = (slug: string): ServiceId => SLUG_ALIAS[slug] ?? slug
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
  const status: SourceStatus['status'] =
    s.missing_keys.length > 0 ? 'warn' : s.last_status === 'ok' ? 'ok' : s.last_status === 'error' ? 'error' : s.last_status === 'never' ? 'idle' : 'warn'
  const note =
    s.missing_keys.length > 0
      ? `Lipsește cheia: ${s.missing_keys.map((k) => k.toUpperCase()).join(', ')}`
      : s.last_status === 'never'
        ? 'Nu a rulat încă. Pornește la următoarea rulare.'
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
        service, services: service ? [service] : [], title: item.label, quote: ev.quote ?? '', source: hostOf(ev.url),
        sourceType: sourceTypeOf(ev.url, item.kind), url: ev.url, date: toIso(ev.date, score.computed_at), confidence: item.confidence,
        points: Math.round(item.points),
      })
    }
  }
  return mergeByLink(out)
}

/**
 * The backend scores each service on its own, so one article can come back once per service. Show it once: signals
 * with the same link (and the same direction, so a negative is never hidden by a positive) merge into the one with
 * the most points, which lists every service the article counts for. Scores are untouched.
 */
function mergeByLink(signals: Signal[]): Signal[] {
  const groups = new Map<string, Signal[]>()
  for (const s of signals) {
    const key = `${s.url}|${s.points > 0 ? '+' : '-'}`
    groups.set(key, [...(groups.get(key) ?? []), s])
  }
  return [...groups.values()]
    .map((group) => {
      const ranked = [...group].sort((a, b) => Math.abs(b.points) - Math.abs(a.points))
      return { ...ranked[0], services: [...new Set(ranked.flatMap((s) => s.services))] }
    })
    .sort((a, b) => Math.abs(b.points) - Math.abs(a.points))
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
    getJson<ApiDashboardCompany[]>('/dashboard/companies', 120_000),
    getJson<ApiSource[]>('/sources'),
    getJson<ApiRule[]>('/rules'),
  ])
  const active = apiServices.filter((s) => s.active)
  const serviceById = new Map(active.map((s) => [s.id, serviceIdFor(s.slug)]))
  const services: Service[] = active.map((s) => {
    const id = serviceIdFor(s.slug)
    return { id, name: SERVICE_NAMES[id]?.[0] ?? s.name, short: SERVICE_NAMES[id]?.[1] ?? s.name, apiId: s.id }
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
    const serviceScores: Record<ServiceId, number> = Object.fromEntries(services.map((s) => [s.id, 0]))
    for (const l of own) {
      const sid = serviceById.get(l.service_id)
      if (sid) serviceScores[sid] = Math.round(l.final_score)
    }
    const stage: Stage = d.assignment?.stage ?? (eligible.length === 0 ? 'descalificat' : 'nou')
    const updated = [...own.map((l) => l.score_changed_at ?? l.computed_at), d.assignment?.updated_at ?? ''].sort().at(-1) || d.company.created_at
    const c = d.company
    return {
      id: String(c.id), name: c.name, domain: c.domain ?? '', industry: c.industry ?? '—', country: c.country ?? '',
      countryName: c.country ? (countryNames?.of(c.country) ?? c.country) : '—',
      employees: c.employee_count != null ? c.employee_count.toLocaleString('ro-RO') : '—',
      stage, owner: d.assignment?.owner ?? null, sellerId: d.assignment?.seller_id ?? null,
      leadIds: own.map((l) => l.lead_id), bestServiceApiId: best?.service_id ?? null, score: Math.round(best?.final_score ?? 0), prevScore: Math.round(best?.previous_score ?? best?.final_score ?? 0),
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

// ------------------------------------------------------------------ CRM state (PostgreSQL) and actions
export interface Note { t: string; seller_id: number; author: string; text: string }
export interface Assignment { company_id: number; seller_id: number | null; owner: string | null; stage: Stage; notes: Note[]; updated_at: string | null }

export const getAssignment = (companyId: string) => getJson<Assignment>(`/companies/${companyId}/assignment`)
/** Stage and owner of every lead that has one (a small payload, polled for live updates). */
export const listAssignments = () => getJson<Assignment[]>('/assignments', 10_000)

export const saveAssignment = (companyId: string, body: { stage?: Stage; seller_id?: number; unassign?: boolean }) =>
  putJson<Assignment>(`/companies/${companyId}/assignment`, body)
export const addNote = (companyId: string, text: string) => postJson<Assignment>(`/companies/${companyId}/notes`, { text })

export interface Activity { t: string; action: string; seller: string | null; details: Record<string, unknown> }
export const getActivity = (companyId: string) => getJson<Activity[]>(`/activity?company_id=${companyId}&limit=50`)

export interface Outreach { subject: string; body: string; grounded: boolean; sources: { url: string; date: string }[] }
/** The server keeps the last draft per company, service, channel and language; `fresh` asks the AI for a new one. */
export const generateOutreach = (
  companyId: string, serviceApiId: number, channel: 'email' | 'linkedin' | 'followup', language: 'RO' | 'EN' | 'DE', fresh = false,
) =>
  postJson<Outreach>(
    `/companies/${companyId}/outreach?service=${serviceApiId}&channel=${channel}&language=${language}&tone=consultative${fresh ? '&fresh=true' : ''}`,
    undefined,
    120_000,
  )

// ------------------------------------------------------------------ deal estimate (backend/app/deal_value.py)
/** What a lead could bring Orange Systems in the first year: value range, delivery cost, gross profit, win chance. */
export interface Deal {
  currency: string
  value: number; value_low: number; value_high: number
  cost: number; profit: number; profit_low: number; profit_high: number
  gross_margin: number; win_probability: number; expected_profit: number
  confidence: 'medium' | 'low'
  assumptions: {
    employees: number; size_basis: 'known' | 'registry' | 'listed' | 'guessed'; size_factor: number
    country: string | null; market_price_level: number; base_value: number; basis: string
  }
}
export interface ServiceDeal { service_id: number; service: string; tier: string; final_score: number; disqualified: boolean; deal: Deal | null }

/** Per-service scores with the deal estimate of one company (GET /companies/{id}). */
export const getCompanyDeals = (companyId: string) =>
  getJson<{ scores: ServiceDeal[]; best_service: string | null }>(`/companies/${companyId}`).then((d) => d.scores)

export interface DealModel {
  currency: string
  services: Record<string, { base_value: number; gross_margin: number; basis?: string }>
  default_service: { base_value: number; gross_margin: number; basis?: string }
  market_price_level: Record<string, number>
  default_market_price_level: number
  win_probability: Record<string, number>
  sources: string[]
  [key: string]: unknown
}
export const getDealModel = () => getJson<DealModel>('/deal-model')
/** Admin only; only the keys sent change, `{}` restores the defaults. */
export const saveDealModel = (changes: Partial<DealModel>) => putJson<DealModel>('/deal-model', changes)

export const sendToHubspot = (leadIds: number[]) => postJson<{ lead_id: number; ok: boolean; error?: string }[]>('/crm/hubspot', leadIds)

// ------------------------------------------------------------------ configuration (PostgreSQL)
export interface ApiQuestionFull {
  id: number; service_id: number; text: string; weight: 'High' | 'Medium' | 'Low'; source_hint: string; lookback_days: number
  is_negative: boolean; keywords: string[]; active: boolean
}
export interface ApiRuleFull {
  id: number; service_id: number | null; name: string; rule_type: 'field_rule' | 'llm_question'; field: string | null; operator: string | null
  value: unknown; question: string | null; keywords: string[]; min_confidence: number; active: boolean
}
export interface ApiIcp {
  id: number; service_id: number; markets: string[]; industries: string[]; countries: string[]; employee_min: number | null
  employee_max: number | null; revenue_min: number | null; revenue_max: number | null; min_fit: number
}
export interface ApiScoringConfig {
  icp_weight: number; signal_weight: number; hot_threshold: number; warm_threshold: number; weight_values: Record<'High' | 'Medium' | 'Low', number>
  recency_buckets: [number | null, number][]; undated_recency: number; discovery_countries: string[]
}
export interface ConfigData {
  services: (ApiService & { uiId: ServiceId })[]
  questions: ApiQuestionFull[]
  rules: ApiRuleFull[]
  icps: ApiIcp[]
  scoring: ApiScoringConfig
}

export async function loadConfig(): Promise<ConfigData> {
  const [services, rules, icps, scoring] = await Promise.all([
    getJson<ApiService[]>('/services'), getJson<ApiRuleFull[]>('/rules'), getJson<ApiIcp[]>('/icp'), getJson<ApiScoringConfig>('/scoring-config'),
  ])
  const active = services.filter((s) => s.active)
  const questions = (await Promise.all(active.map((s) => getJson<ApiQuestionFull[]>(`/services/${s.id}/questions`)))).flat()
  return { services: active.map((s) => ({ ...s, uiId: serviceIdFor(s.slug) })), questions, rules, icps, scoring }
}

const questionBody = (q: ApiQuestionFull) => ({
  text: q.text, weight: q.weight, source_hint: q.source_hint, lookback_days: q.lookback_days, is_negative: q.is_negative, keywords: q.keywords, active: q.active,
})
const ruleBody = (r: ApiRuleFull) => ({
  name: r.name, rule_type: r.rule_type, field: r.field, operator: r.operator, value: r.value, question: r.question, keywords: r.keywords,
  min_confidence: r.min_confidence, active: r.active,
})

export const configApi = {
  /** Admin only on the server (POST /services); a new service starts without ICP, so every company fits it until one is set. */
  createService: (body: { name: string; slug: string; description: string; value_proposition: string }) =>
    postJson<ApiService>('/services', body),
  createQuestion: (serviceId: number, text: string, weight: 'High' | 'Medium' | 'Low', isNegative: boolean) =>
    postJson(`/services/${serviceId}/questions`, { text, weight, is_negative: isNegative }),
  updateQuestion: (q: ApiQuestionFull) => putJson(`/services/${q.service_id}/questions/${q.id}`, questionBody(q)),
  deleteQuestion: (q: ApiQuestionFull) => del(`/services/${q.service_id}/questions/${q.id}`),
  createRule: (question: string) => postJson('/rules', { name: question.slice(0, 190), rule_type: 'llm_question', question }),
  updateRule: (r: ApiRuleFull) => putJson(`/rules/${r.id}`, ruleBody(r)),
  deleteRule: (r: ApiRuleFull) => del(`/rules/${r.id}`),
  saveIcp: (icp: ApiIcp) => {
    const { id: _id, service_id, ...body } = icp
    return putJson(`/icp/${service_id}`, body)
  },
  saveScoring: (cfg: ApiScoringConfig) => putJson('/scoring-config', cfg),
}
