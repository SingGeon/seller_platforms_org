import { ChevronDown, Clock, Coins, Target, Trophy } from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import { getCompanyDeals } from '../data/backend'
import type { Company, Stage } from '../data/types'
import { Panel, PanelTitle } from './ui'

// What LeadRadar is worth to the team: time saved (one stated assumption, kept in this browser only) and the value of
// the pipeline, from the server's deal estimate of every lead in it (backend/app/deal_value.py).
const KEY = 'leadradar.impactAssumptions'
const DEFAULTS = { minutesPerCompany: 20 }

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
  const pipelineKey = inPipeline.map((c) => `${c.id}:${c.stage}:${c.bestServiceApiId}`).join('|')
  const [value, setValue] = useState<{ key: string; weighted: number; profit: number; estimated: number } | null>(null)

  // The estimate of each pipeline lead's best service (a handful of leads, so one request each is fine).
  useEffect(() => {
    let alive = true
    Promise.all(
      inPipeline.map(async (c) => {
        const deals = await getCompanyDeals(c.id).catch(() => [])
        const best = deals.find((d) => d.service_id === c.bestServiceApiId) ?? [...deals].sort((x, y) => y.final_score - x.final_score)[0]
        return { w: STAGE_WEIGHT[c.stage] ?? 0, deal: best?.deal ?? null }
      }),
    ).then((rows) => {
      if (!alive) return
      const known = rows.filter((r) => r.deal)
      setValue({
        key: pipelineKey,
        weighted: known.reduce((sum, r) => sum + r.w * r.deal!.value, 0),
        profit: known.reduce((sum, r) => sum + r.w * r.deal!.profit, 0),
        estimated: known.length,
      })
    })
    return () => {
      alive = false
    }
    // pipelineKey stands for the leads, their stages and best services
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineKey])
  const current = value?.key === pipelineKey ? value : null
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
        <Metric
          icon={Coins}
          label="Valoare pipeline ponderată"
          value={current ? eur(current.weighted) : '…'}
          note={
            current
              ? `profit brut ponderat ${eur(current.profit)} · ${current.estimated === 1 ? 'un lead estimat' : `${int(current.estimated)} lead-uri estimate`}`
              : 'se calculează…'
          }
        />
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
              <b>Valoare ponderată</b> = pentru fiecare lead din Pipeline, valoarea estimată a proiectului (pe serviciul potrivit: mărimea
              companiei, piața și prețul serviciului) × șansa stadiului:{' '}
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
            <p className="text-[13px] text-muted">
              Valoarea fiecărui proiect vine din estimarea serverului; ipotezele ei (prețul pe serviciu, marja, nivelul de preț pe țară) le
              schimbă administratorul din Configurare → „Valoare contracte”.
            </p>
            <button type="button" onClick={() => save(DEFAULTS)} className="text-[13px] font-bold underline underline-offset-4">
              Revino la valorile inițiale
            </button>
          </div>
        </div>
      )}
    </Panel>
  )
}
