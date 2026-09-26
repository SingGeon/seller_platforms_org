import { ChevronDown } from 'lucide-react'
import { useEffect, useState } from 'react'
import { friendlyError } from '../auth/session'
import { getServices } from '../data/api'
import { type ServiceDeal, getCompanyDeals } from '../data/backend'
import { Panel, PanelTitle } from './ui'

const money = (n: number, currency = 'EUR') =>
  new Intl.NumberFormat('ro-RO', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n)
const pct = (x: number) => `${Math.round(x * 100)}%`
const TIER_RO: Record<string, string> = { Hot: 'lead fierbinte', Warm: 'lead cald', Cold: 'lead rece', Disqualified: 'descalificat' }
const serviceName = (d: ServiceDeal) => getServices().find((s) => s.apiId === d.service_id)?.name ?? d.service

const SIZE_BASIS: Record<string, string> = {
  known: 'numărul de angajați cunoscut',
  registry: 'numărul de angajați din registru',
  listed: 'estimat: companie listată la bursă',
  guessed: 'estimat: mărimea nu e cunoscută',
}

/**
 * What this lead could bring Orange Systems (backend/app/deal_value.py): first-year project value with a range,
 * delivery cost, gross profit and the profit weighted by the chance to win. One service at a time, the best by default.
 */
export default function DealPanel({ companyId, bestServiceApiId }: { companyId: string; bestServiceApiId: number | null }) {
  const [deals, setDeals] = useState<ServiceDeal[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pick, setPick] = useState<number | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let alive = true
    getCompanyDeals(companyId)
      .then((d) => alive && setDeals(d.filter((s) => s.deal && !s.disqualified)))
      .catch((e) => alive && setError(friendlyError(e)))
    return () => {
      alive = false
    }
  }, [companyId])

  if (error) return null // the rest of the page still works; the estimate is a bonus
  if (!deals) return null
  if (!deals.length) return null

  const chosen = deals.find((d) => d.service_id === (pick ?? bestServiceApiId)) ?? [...deals].sort((a, b) => b.final_score - a.final_score)[0]
  const deal = chosen.deal!
  const a = deal.assumptions

  return (
    <Panel>
      <PanelTitle
        action={
          deal.confidence === 'low' ? (
            <span className="bg-warn-bg px-1.5 py-0.5 text-[11px] font-bold" title="Numărul de angajați nu e cunoscut, deci intervalul e mai larg">
              Estimare aproximativă
            </span>
          ) : undefined
        }
      >
        Valoare estimată pentru Orange
      </PanelTitle>
      <div className="p-5">
        {deals.length > 1 && (
          <select
            value={chosen.service_id}
            onChange={(e) => setPick(Number(e.target.value))}
            className="mb-4 h-9 w-full text-[13px] font-bold"
            aria-label="Serviciul pentru estimare"
          >
            {deals.map((d) => (
              <option key={d.service_id} value={d.service_id}>
                {serviceName(d)}
              </option>
            ))}
          </select>
        )}
        <p className="text-[13px] text-muted">Valoarea proiectului (primul an)</p>
        <p className="num mt-1 text-[30px] font-bold leading-none">{money(deal.value, deal.currency)}</p>
        <p className="num mt-1 text-[13px] text-muted">
          interval {money(deal.value_low, deal.currency)} – {money(deal.value_high, deal.currency)}
        </p>

        <dl className="mt-5 grid grid-cols-[1fr_auto] gap-y-2 border-t border-line pt-4 text-[14px]">
          <dt className="text-muted">Cost de livrare</dt>
          <dd className="num text-right">{money(deal.cost, deal.currency)}</dd>
          <dt className="text-muted">Profit brut ({pct(deal.gross_margin)} marjă)</dt>
          <dd className="num text-right font-bold">{money(deal.profit, deal.currency)}</dd>
          <dt className="text-muted">Șansa de câștig ({TIER_RO[chosen.tier] ?? chosen.tier})</dt>
          <dd className="num text-right">{pct(deal.win_probability)}</dd>
          <dt className="font-bold">Profit așteptat</dt>
          <dd className="num text-right font-bold text-orange-ink">{money(deal.expected_profit, deal.currency)}</dd>
        </dl>

        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="mt-4 flex items-center gap-1 text-[13px] font-bold underline underline-offset-4 hover:text-orange-ink"
        >
          Cum am estimat <ChevronDown size={14} className={open ? 'rotate-180' : ''} aria-hidden />
        </button>
        {open && (
          <ul className="mt-3 space-y-1.5 text-[13px] text-ink-2">
            <li>
              Valoare de bază a serviciului: <b className="num">{money(a.base_value, deal.currency)}</b> pentru o companie de 150 de angajați.
            </li>
            <li>
              Mărime: <b className="num">{a.employees.toLocaleString('ro-RO')}</b> angajați ({SIZE_BASIS[a.size_basis] ?? a.size_basis}), factor{' '}
              <b className="num">×{a.size_factor}</b>.
            </li>
            <li>
              Nivel de preț în {a.country ?? 'piața companiei'}: <b className="num">×{a.market_price_level}</b> (Germania și Austria = 1).
            </li>
            {a.basis && <li className="text-muted">Reper: {a.basis}</li>}
            <li className="text-muted">Ipotezele le poate ajusta administratorul din Configurare → „Valoare contracte”.</li>
          </ul>
        )}
      </div>
    </Panel>
  )
}
