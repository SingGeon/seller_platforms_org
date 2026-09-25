import { loadBackendData, runDiscovery, type BackendData } from './backend'
import { COMPANIES, QUESTIONS, SERVICES, SOURCES } from './mock'
import type { Company, Signal, Stage } from './types'

// Data comes from the FastAPI backend (VITE_API_URL). If it is unreachable, or VITE_USE_MOCK=true,
// the app falls back to the fictional demo data in ./mock so it always renders.
let store: BackendData = { companies: COMPANIES, services: SERVICES, questions: QUESTIONS, sources: SOURCES }
let live = false
let loadError: string | null = null

export async function loadData(): Promise<void> {
  if (import.meta.env.VITE_USE_MOCK === 'true') return
  try {
    store = await loadBackendData()
    live = true
    loadError = null
  } catch (err) {
    live = false
    loadError = err instanceof Error ? err.message : String(err)
    console.warn('Backend unreachable, showing demo data:', loadError)
  }
}

/** True when the data on screen comes from the backend, false for demo data. */
export const isLive = () => live
export const dataError = () => loadError

/** Run discovery on the backend, then reload everything. Returns the final run status. */
export async function runNowAndReload(): Promise<string> {
  const run = await runDiscovery()
  await loadData()
  return run.status
}

export const getCompanies = () => store.companies
export const getCompany = (id: string) => store.companies.find((c) => c.id === id)
export const getServices = () => store.services
export const getQuestions = () => store.questions
export const getSources = () => store.sources

export const getRecentSignals = (limit = 8) =>
  COMPANIES.filter((c) => c.stage !== 'descalificat').flatMap((c) => c.signals.filter((s) => s.points > 0).map((s) => ({ ...s, company: c })))
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, limit) as (Signal & { company: Company })[]

export const STAGES: { id: Stage; label: string }[] = [
  { id: 'nou', label: 'Nou' },
  { id: 'calificat', label: 'Calificat' },
  { id: 'contactat', label: 'Contactat' },
  { id: 'negociere', label: 'În negociere' },
  { id: 'castigat', label: 'Câștigat' },
  { id: 'descalificat', label: 'Descalificat' },
]

export const stageLabel = (s: Stage) => STAGES.find((x) => x.id === s)!.label

export const isNew = (c: Company) => Date.now() - new Date(c.firstSeen).getTime() < 72 * 3600_000

export const topSignal = (c: Company) =>
  [...c.signals].sort((a, b) => Math.abs(b.points) - Math.abs(a.points))[0]

export function timeAgo(iso: string) {
  if (!iso || Number.isNaN(new Date(iso).getTime())) return '—'
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (min < 1) return 'acum'
  if (min < 60) return `acum ${min} min`
  const h = Math.round(min / 60)
  if (h < 24) return `acum ${h} h`
  const d = Math.round(h / 24)
  return d === 1 ? 'ieri' : `acum ${d} zile`
}
