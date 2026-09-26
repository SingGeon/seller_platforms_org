import {
  ArrowDown,
  ArrowUp,
  Briefcase,
  Database,
  FileText,
  Gavel,
  Globe,
  Megaphone,
  Minus,
  Newspaper,
  ShieldAlert,
  type LucideIcon,
} from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { getServices, stageLabel } from '../data/api'
import type { ServiceId, SourceType, Stage } from '../data/types'

type Variant = 'primary' | 'secondary' | 'dark' | 'ghost'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-orange border-orange text-ink hover:bg-ink hover:border-ink hover:text-white',
  secondary: 'bg-white border-ink text-ink hover:bg-ink hover:text-white',
  dark: 'bg-ink border-ink text-white hover:bg-white hover:text-ink',
  ghost: 'bg-transparent border-transparent text-ink hover:border-ink',
}

export const btn = (variant: Variant = 'secondary', size: 'sm' | 'md' = 'md') =>
  `inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap border-2 font-bold transition-colors disabled:opacity-40 disabled:pointer-events-none ${
    size === 'sm' ? 'h-8 px-3 text-[13px]' : 'h-10 px-5'
  } ${VARIANTS[variant]}`

export function Button({
  variant = 'secondary',
  size = 'md',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md' }) {
  return <button type="button" className={`${btn(variant, size)} ${className}`} {...props} />
}

// Each known service keeps its colour whatever else is configured (colour follows the service, not its position).
// Palette checked for colour-blind separation; a colour never appears without the service name next to it.
const SERVICE_SLOT: Record<string, number> = { automation: 1, cyber: 2, digital: 3, cloud: 4, data: 5, erp: 6, iot: 7 }
const SLOTS = 7

export function serviceColor(id: ServiceId): string {
  let slot = SERVICE_SLOT[id]
  if (!slot) {
    // A service added later takes the first colour no configured service uses, so it never repeats a neighbour's.
    const services = getServices().map((s) => s.id)
    const taken = new Set(services.map((s) => SERVICE_SLOT[s]).filter(Boolean))
    const free = Array.from({ length: SLOTS }, (_, k) => k + 1).filter((n) => !taken.has(n))
    const extra = services.filter((s) => !SERVICE_SLOT[s]).indexOf(id)
    slot = free.length ? free[Math.max(0, extra) % free.length] : (Math.max(0, extra) % SLOTS) + 1
  }
  return `var(--color-svc-${slot})`
}

export const serviceShort = (id: ServiceId) => getServices().find((s) => s.id === id)?.short ?? id

export function ServiceTag({ id, className = '' }: { id: ServiceId; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap text-[13px] font-bold ${className}`}>
      <span className="size-2.5 shrink-0" style={{ background: serviceColor(id) }} aria-hidden />
      {serviceShort(id)}
    </span>
  )
}

export function ScoreMeter({ score, size = 'md' }: { score: number; size?: 'sm' | 'md' | 'lg' }) {
  const filled = Math.round(score / 10)
  const block = size === 'lg' ? 'h-5 w-full' : size === 'md' ? 'h-3 w-2.5' : 'h-2.5 w-1.5'
  return (
    <div
      className={`flex ${size === 'lg' ? 'gap-1' : 'gap-[2px]'}`}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={score}
      aria-label={`Scor ${score} din 100`}
    >
      {Array.from({ length: 10 }, (_, i) => (
        <span key={i} className={`${block} ${i < filled ? 'bg-orange' : 'bg-orange-soft'}`} />
      ))}
    </div>
  )
}

export function ScoreDelta({ score, prev }: { score: number; prev: number }) {
  const d = score - prev
  if (d === 0)
    return (
      <span className="inline-flex items-center text-faint" title="Fără schimbare">
        <Minus size={14} aria-label="Fără schimbare" />
      </span>
    )
  const up = d > 0
  const Icon = up ? ArrowUp : ArrowDown
  return (
    <span
      className={`num inline-flex items-center gap-0.5 text-[12px] font-bold ${up ? 'text-ok' : 'text-danger'}`}
      title={`${up ? '+' : ''}${d} puncte față de rularea anterioară`}
    >
      <Icon size={13} strokeWidth={3} aria-hidden />
      {Math.abs(d)}
    </span>
  )
}

const SOURCE_ICON: Record<SourceType, [LucideIcon, string]> = {
  job: [Briefcase, 'Anunț de angajare'],
  news: [Newspaper, 'Știre'],
  press: [Megaphone, 'Comunicat de presă'],
  tender: [Gavel, 'Licitație'],
  filing: [FileText, 'Raportare oficială'],
  breach: [ShieldAlert, 'Incident de securitate'],
  website: [Globe, 'Site companie'],
  registry: [Database, 'Registru'],
}

export function SourceIcon({ type, size = 15 }: { type: SourceType; size?: number }) {
  const [Icon, label] = SOURCE_ICON[type]
  return <Icon size={size} aria-label={label} className="shrink-0" />
}

export const sourceTypeLabel = (t: SourceType) => SOURCE_ICON[t][1]

const STAGE_STYLE: Record<Stage, string> = {
  nou: 'bg-orange text-ink',
  calificat: 'bg-ink text-white',
  contactat: 'bg-band text-ink',
  negociere: 'bg-band text-ink',
  castigat: 'bg-ok-bg text-ok',
  descalificat: 'bg-danger-bg text-danger',
}

export function StageTag({ stage }: { stage: Stage }) {
  return (
    <span className={`inline-block whitespace-nowrap px-2 py-0.5 text-[12px] font-bold ${STAGE_STYLE[stage]}`}>
      {stageLabel(stage)}
    </span>
  )
}

export function Avatar({ name, size = 28 }: { name: string | null; size?: number }) {
  if (!name)
    return (
      <span
        className="inline-flex shrink-0 items-center justify-center border-2 border-dashed border-line text-[11px] text-faint"
        style={{ width: size, height: size }}
        title="Neasignat"
      >
        —
      </span>
    )
  const initials = name
    .split(' ')
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center bg-ink text-[11px] font-bold text-white"
      style={{ width: size, height: size }}
      title={name}
    >
      {initials}
    </span>
  )
}

export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`border border-line bg-white ${className}`}>{children}</section>
}

export function PanelTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-line px-5 py-3">
      <h2 className="text-[16px]">{children}</h2>
      {action}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[32px] leading-none">{title}</h1>
        {subtitle && <p className="mt-2 text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function NewBadge() {
  return <span className="border border-orange-ink px-1.5 py-px text-[10px] font-bold uppercase tracking-wide text-orange-ink" title="Descoperit în ultimele 72 de ore">Recent</span>
}
