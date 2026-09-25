import { COMPANIES, QUESTIONS, SERVICES, SOURCES } from './mock'
import type { Company, Signal, Stage } from './types'

export const getCompanies = () => COMPANIES
export const getCompany = (id: string) => COMPANIES.find((c) => c.id === id)
export const getServices = () => SERVICES
export const getQuestions = () => QUESTIONS
export const getSources = () => SOURCES

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
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (min < 1) return 'acum'
  if (min < 60) return `acum ${min} min`
  const h = Math.round(min / 60)
  if (h < 24) return `acum ${h} h`
  const d = Math.round(h / 24)
  return d === 1 ? 'ieri' : `acum ${d} zile`
}
