import { ChevronDown, Clock, Coins, Target, Trophy } from 'lucide-react'
import { useId, useState } from 'react'
import type { Company, Stage } from '../data/types'
import { Panel, PanelTitle } from './ui'

// What LeadRadar is worth to the team, computed from the data on screen plus two stated assumptions that anyone can
// change (kept in this browser only; they are illustration inputs, not business data).
const KEY = 'leadradar.impactAssumptions'
const DEFAULTS = { minutesPerCompany: 20, avgDeal: 20_000 }

// Usual B2B forecast weights: the chance a lead at this stage turns into a contract.
const STAGE_WEIGHT: Partial<Record<Stage, number>> = { calificat: 0.1, contactat: 0.25, negociere: 0.5, castigat: 1 }
const STAGE_RO: Record<string, string> = { calificat: 'Calificat', contactat: 'Contactat', negociere: 'În negociere', castigat: 'Câștigat' }

function readAssumptions() {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? { ...DEFAULTS, ...(JSON.parse(raw) as Partial<typeof DEFAULTS>) } : DEFAULTS
  } catch {
    return DEFAULTS
  }
}

const eur = (n: number) => new Intl.NumberFormat('ro-RO', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(n)
const int = (n: number) => new Intl.NumberFormat('ro-RO').format(Math.round(n))

function Metric({ icon: Icon, label, value, note }: { icon: typeof Clock; label: string; value: string; note: string }) {
  return (
    <div className="p-5">
      <p className="flex items-center gap-2 text-[13px] font-bold text-white/60">
        <Icon size={15} className="text-orange" aria-hidden /> {label}
      </p>
      <p className="num mt-3 text-[34px] font-bold leading-none text-white">{value}</p>
      <p className="mt-2 text-[13px] text-white/60">{note}</p>
    </div>
  )
}

export default function ImpactPanel({ companies }: { companies: Company[] }) {
  const uid = useId()
  const [a, setA] = useState(readAssumptions)
  const [open, setOpen] = useState(false)

  const save = (next: typeof DEFAULTS) => {
    setA(next)
    try {
      localStorage.setItem(KEY, JSON.stringify(next))
    } catch {
      // private mode: the change lasts for this page view
    }
  }

  const analysed = companies.length
  const hours = (analysed * a.minutesPerCompany) / 60
  const inPipeline = companies.filter((c) => STAGE_WEIGHT[c.stage] != null)
  const won = companies.filter((c) => c.stage === 'castigat').length
  const conversion = inPipeline.length ? Math.round((won / inPipeline.length) * 100) : 0
  const weighted = inPipeline.reduce((sum, c) => sum + (STAGE_WEIGHT[c.stage] ?? 0) * a.avgDeal, 0)
  const byStage = Object.keys(STAGE_WEIGHT).map((s) => ({ s, n: companies.filter((c) => c.stage === s).length }))

  return (
    <Panel className="mb-6 overflow-hidden">
      <PanelTitle
        action={
          <button
            type="button"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            className="flex items-center gap-1 text-[13px] font-bold underline underline-offset-4 hover:text-orange-ink"
          >
            Cum calculăm <ChevronDown size={14} className={open ? 'rotate-180' : ''} aria-hidden />
          </button>
        }
      >
        Impactul LeadRadar
      </PanelTitle>

      <div className="grid bg-ink sm:grid-cols-2 xl:grid-cols-4 [&>*]:border-white/10 [&>*:not(:last-child)]:border-r">
        <Metric
          icon={Clock}
          label="Timp de cercetare economisit"
          value={`${int(hours)} ore`}
          note={`${hours >= 8 ? `≈ ${int(hours / 8)} zile de lucru · ` : ''}${int(analysed)} companii analizate automat`}
        />
        <Metric
          icon={Target}
          label="Lead-uri calificate"
          value={int(inPipeline.length)}
          note="în pipeline, cu responsabil și stadiu"
        />
        <Metric
          icon={Trophy}
          label="Conversie"
          value={`${conversion}%`}
          note={`${int(won)} ${won === 1 ? 'contract câștigat' : 'contracte câștigate'} din lead-urile calificate`}
        />
        <Metric icon={Coins} label="Valoare pipeline ponderată" value={eur(weighted)} note="șansa pe stadiu × valoarea medie a contractului" />
      </div>

      {open && (
        <div className="grid gap-6 p-5 text-[14px] lg:grid-cols-[1fr_1fr]">
          <div className="space-y-3">
            <p>
              <b>Timp economisit</b> = companii analizate × minute de cercetare manuală per companie (știri, site, joburi, registre), pe care
              LeadRadar le face automat.
            </p>
            <p>
              <b>Conversie</b> = lead-uri câștigate ÷ lead-uri calificate (tot ce e în Pipeline).
            </p>
            <p>
              <b>Valoare ponderată</b> = pentru fiecare lead din Pipeline, valoarea medie a contractului × șansa stadiului:{' '}
              {byStage.map(({ s, n }, k) => (
                <span key={s}>
                  {STAGE_RO[s]} {Math.round((STAGE_WEIGHT[s as Stage] ?? 0) * 100)}% ({n}){k < byStage.length - 1 ? ', ' : '.'}
                </span>
              ))}
            </p>
          </div>
          <div className="space-y-4 border-l-4 border-orange bg-canvas p-4">
            <p className="text-[13px] font-bold text-muted">Ipoteze (le poți schimba; rămân doar în acest browser)</p>
            <label className="flex items-center justify-between gap-4" htmlFor={`${uid}-m`}>
              <span>Minute de cercetare manuală per companie</span>
              <input
                id={`${uid}-m`}
                type="number"
                min={1}
                max={240}
                value={a.minutesPerCompany}
                onChange={(e) => save({ ...a, minutesPerCompany: Math.max(1, Number(e.target.value) || DEFAULTS.minutesPerCompany) })}
                className="h-9 w-24 text-right"
              />
            </label>
            <label className="flex items-center justify-between gap-4" htmlFor={`${uid}-d`}>
              <span>Valoarea medie a unui contract (EUR)</span>
              <input
                id={`${uid}-d`}
                type="number"
                min={0}
                step={1000}
                value={a.avgDeal}
                onChange={(e) => save({ ...a, avgDeal: Math.max(0, Number(e.target.value) || 0) })}
                className="h-9 w-32 text-right"
              />
            </label>
            <button type="button" onClick={() => save(DEFAULTS)} className="text-[13px] font-bold underline underline-offset-4">
              Revino la valorile inițiale
            </button>
          </div>
        </div>
      )}
    </Panel>
  )
}
