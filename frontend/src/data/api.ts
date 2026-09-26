import { useSyncExternalStore } from 'react'
import { listAssignments, loadBackendData, runDiscovery, type BackendData } from './backend'
import type { Seller } from './client'
import type { Company, ServiceId, Signal, Stage } from './types'

// Everything on screen comes from the FastAPI backend (VITE_API_URL). There is no demo fallback: when the server
// cannot be reached the app says so instead of showing invented companies.
let store: BackendData = { companies: [], services: [], questions: [], sources: [] }
let loadedAt: string | null = null
let seller: Seller | null = null

/** The logged-in seller (PostgreSQL account). */
export const getSeller = () => seller
export const setSeller = (s: Seller | null) => {
  seller = s
}

// Pages read the store synchronously; useDataVersion() re-renders them after a reload.
let version = 0
const listeners = new Set<() => void>()
const bump = () => {
  version++
  for (const fn of listeners) fn()
}
const subscribe = (fn: () => void) => {
  listeners.add(fn)
  return () => listeners.delete(fn)
}
export const useDataVersion = () => useSyncExternalStore(subscribe, () => version)

/** Loads everything from the backend. Throws when the server does not answer; the caller shows the error. */
export async function loadData(): Promise<void> {
  store = await loadBackendData()
  loadedAt = new Date().toISOString()
  bump()
}

export function clearData() {
  store = { companies: [], services: [], questions: [], sources: [] }
  loadedAt = null
  bump()
}

// Leads whose stage or owner was just changed by someone else, so the UI can highlight them once.
let changedByOthers = new Set<string>()
export const recentlyChanged = (id: string) => changedByOthers.has(id)

/**
 * Pulls the stage and owner of every lead (GET /assignments) and applies what changed since the last look.
 * Polled every few seconds, so a card moved by a colleague moves on everyone's screen without a full reload.
 */
export async function syncAssignments(): Promise<void> {
  const rows = await listAssignments()
  const byId = new Map(rows.map((a) => [String(a.company_id), a]))
  const changed = new Set<string>()
  const companies = store.companies.map((c) => {
    const a = byId.get(c.id)
    if (!a) return c
    const stage = a.stage ?? c.stage
    if (stage === c.stage && a.seller_id === c.sellerId && a.owner === c.owner) return c
    changed.add(c.id)
    return { ...c, stage, sellerId: a.seller_id, owner: a.owner, updatedAt: a.updated_at ?? c.updatedAt }
  })
  if (!changed.size) return
  store = { ...store, companies }
  changedByOthers = changed
  bump()
}

/** When the data on screen was fetched from the server. */
export const dataLoadedAt = () => loadedAt

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

/** Apply a saved change (stage, owner) to the in-memory copy so every page shows it without a reload. */
export function patchCompany(id: string, patch: Partial<Company>) {
  store = { ...store, companies: store.companies.map((c) => (c.id === id ? { ...c, ...patch } : c)) }
  bump()
}

export const getRecentSignals = (limit = 8) =>
  store.companies.filter((c) => c.stage !== 'descalificat').flatMap((c) => c.signals.filter((s) => s.points > 0).map((s) => ({ ...s, company: c })))
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

/** Stages that put a lead on the pipeline board ("Nou" and "Descalificat" stay in the list only). */
export const inPipeline = (s: Stage) => s !== 'nou' && s !== 'descalificat'

/**
 * Body for a stage change. A sales manager who moves a lead without an owner into the pipeline becomes its owner in
 * the same request (the server lets a seller take a free lead); admins only change the stage.
 */
export function stageChange(c: Company, next: Stage, by: Seller | null): { stage: Stage; seller_id?: number } {
  const takes = by != null && by.role !== 'admin' && c.sellerId == null && inPipeline(next)
  return takes ? { stage: next, seller_id: by.id } : { stage: next }
}

export const stageLabel = (s: Stage) => STAGES.find((x) => x.id === s)!.label

export const isNew = (c: Company) => Date.now() - new Date(c.firstSeen).getTime() < 72 * 3600_000

/**
 * One line for a signal in lists. For an answered question the backend label is the question itself
 * ("Does the company mention…?"), so the first sentence of the evidence reads better.
 */
export function signalHeadline(s: Signal): string {
  const q = store.questions.find((x) => x.id === s.questionId)
  const isQuestion = q ? s.title.trim() === q.text.trim() : /\?\s*$/.test(s.title)
  const quote = s.quote.trim()
  if (!isQuestion || !quote) return s.title
  const first = quote.split(/(?<=[.!?])\s/)[0].trim()
  return first.length > 160 ? `${first.slice(0, 157).trimEnd()}…` : first
}

/**
 * The service a lead fits: the highest-scoring service among those with at least one positive signal.
 * null when no service has evidence yet: the score then comes only from the ICP fit, which does not point at a service.
 */
export function bestService(c: Company): ServiceId | null {
  const withEvidence = new Set(c.signals.filter((s) => s.points > 0 && s.service).map((s) => s.service as ServiceId))
  const ranked = Object.entries(c.serviceScores).filter(([id]) => withEvidence.has(id)).sort((a, b) => b[1] - a[1])
  return ranked[0]?.[0] ?? null
}

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
