/** UI id of a service: the backend slug ("apa" keeps the older id "automation"). Services are configured on the server. */
export type ServiceId = string

export type Stage = 'nou' | 'calificat' | 'contactat' | 'negociere' | 'castigat' | 'descalificat'

export type SourceType = 'job' | 'news' | 'press' | 'tender' | 'filing' | 'breach' | 'website' | 'registry'

export type Weight = 'high' | 'medium' | 'low'

export interface Service {
  id: ServiceId
  name: string
  short: string
}

export interface SignalQuestion {
  id: string
  service: ServiceId | null
  text: string
  weight: Weight
  polarity: 'positive' | 'negative'
  active: boolean
}

export interface Signal {
  id: string
  questionId: string
  service: ServiceId | null
  title: string
  quote: string
  source: string
  sourceType: SourceType
  url: string
  date: string
  confidence: number
  points: number
}

export interface Company {
  id: string
  name: string
  domain: string
  industry: string
  country: string
  countryName: string
  employees: string
  stage: Stage
  owner: string | null
  /** PostgreSQL sellers.id of the owner (lead_assignments) */
  sellerId: number | null
  /** MongoDB lead_scores ids per service, for HubSpot */
  leadIds: number[]
  /** Backend service id of the best-scoring service (outreach) */
  bestServiceApiId: number | null
  score: number
  prevScore: number
  /** 0-100 per service id; a service without a score is missing from the map. */
  serviceScores: Record<ServiceId, number>
  whyNow: string
  firstSeen: string
  updatedAt: string
  signals: Signal[]
}

export type RefreshTier = 'stream' | 'rss' | 'incremental' | 'snapshot' | 'daily'

export interface SourceStatus {
  id: string
  name: string
  category: string
  tier: RefreshTier
  lastRun: string
  status: 'ok' | 'warn' | 'error'
  newItems: number
  note?: string
}
