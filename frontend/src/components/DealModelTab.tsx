import { CircleCheck, Lock, RotateCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { friendlyError } from '../auth/session'
import { type DealModel, getDealModel, saveDealModel } from '../data/backend'
import { Button, Panel, PanelTitle } from './ui'

const TIERS: [string, string][] = [
  ['Hot', 'Fierbinte'],
  ['Warm', 'Cald'],
  ['Cold', 'Rece'],
]

let regionName: (code: string) => string = (code) => code
try {
  const names = new Intl.DisplayNames(['ro'], { type: 'region' })
  regionName = (code) => names.of(code) ?? code
} catch {
  // older browsers: show the ISO code
}

/**
 * Assumptions of the deal estimate (value, cost, profit per lead; backend/app/deal_value.py). Admins change them
 * (PUT /deal-model), sales managers read them. Every default is a public benchmark listed under "Surse".
 */
export default function DealModelTab({ services, isAdmin }: { services: { slug: string; name: string }[]; isAdmin: boolean }) {
  const [model, setModel] = useState<DealModel | null>(null)
  const [draft, setDraft] = useState<DealModel | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getDealModel()
      .then((m) => {
        setModel(m)
        setDraft(structuredClone(m))
      })
      .catch((e) => setError(friendlyError(e)))
  }, [])

  if (error && !draft) return <p className="bg-danger-bg px-4 py-3 font-bold text-danger">Nu am putut încărca ipotezele: {error}</p>
  if (!draft || !model) return <p className="text-muted">Se încarcă ipotezele…</p>

  const svc = (slug: string) => draft.services[slug] ?? draft.default_service
  const setSvc = (slug: string, patch: Partial<DealModel['default_service']>) => {
    setSaved(false)
    setDraft({ ...draft, services: { ...draft.services, [slug]: { ...svc(slug), ...patch } } })
  }
  const dirty = JSON.stringify(draft) !== JSON.stringify(model)

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const next = await saveDealModel({ services: draft.services, market_price_level: draft.market_price_level, win_probability: draft.win_probability })
      setModel(next)
      setDraft(structuredClone(next))
      setSaved(true)
    } catch (e) {
      setError(friendlyError(e))
    } finally {
      setBusy(false)
    }
  }
  const restore = async () => {
    if (!window.confirm('Revii la valorile implicite (repere publice) pentru toate ipotezele?')) return
    setBusy(true)
    setError(null)
    try {
      const next = await saveDealModel({})
      setModel(next)
      setDraft(structuredClone(next))
      setSaved(true)
    } catch (e) {
      setError(friendlyError(e))
    } finally {
      setBusy(false)
    }
  }

  const markets = Object.entries(draft.market_price_level).sort((a, b) => b[1] - a[1])

  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-muted">
        Pe fișa fiecărei companii apare cât ar putea aduce proiectul pentru Orange Systems: valoarea în primul an, costul de livrare, profitul brut
        și profitul așteptat după șansa de câștig. Estimarea pornește de la ipotezele de mai jos; valorile implicite sunt repere publice.
      </p>
      {!isAdmin && (
        <p className="flex items-center gap-2 border-l-4 border-ink bg-band px-4 py-3 text-[14px]">
          <Lock size={16} aria-hidden /> Doar administratorul poate schimba ipotezele.
        </p>
      )}

      <fieldset disabled={!isAdmin} className="m-0 min-w-0 space-y-6 border-0 p-0">
        <Panel>
          <PanelTitle>Valoare și marjă pe serviciu</PanelTitle>
          <table className="w-full border-collapse text-[14px]">
            <thead className="whitespace-nowrap border-b-2 border-ink text-left text-[13px]">
              <tr>
                <th className="px-5 py-3">Serviciu</th>
                <th className="px-5 py-3">Valoare de bază (EUR, primul an)</th>
                <th className="px-5 py-3">Marjă brută</th>
              </tr>
            </thead>
            <tbody>
              {services.map((s) => (
                <tr key={s.slug} className="border-b border-line align-top last:border-0">
                  <td className="px-5 py-3.5">
                    <p className="font-bold">{s.name}</p>
                    <p className="mt-0.5 max-w-md text-[12px] text-muted">{svc(s.slug).basis || 'Valorile medii ale celorlalte servicii.'}</p>
                  </td>
                  <td className="px-5 py-3.5">
                    <input
                      type="number"
                      min={0}
                      step={5000}
                      value={svc(s.slug).base_value}
                      onChange={(e) => setSvc(s.slug, { base_value: Math.max(0, Number(e.target.value) || 0) })}
                      className="h-9 w-36 text-right"
                      aria-label={`Valoare de bază: ${s.name}`}
                    />
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="flex items-center gap-2">
                      <input
                        type="number"
                        min={0}
                        max={95}
                        value={Math.round(svc(s.slug).gross_margin * 100)}
                        onChange={(e) => setSvc(s.slug, { gross_margin: Math.min(95, Math.max(0, Number(e.target.value) || 0)) / 100 })}
                        className="h-9 w-20 text-right"
                        aria-label={`Marjă brută: ${s.name}`}
                      />
                      %
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-line px-5 py-3 text-[13px] text-muted">
            Valoarea de bază e pentru o companie de 150 de angajați dintr-o piață vest-europeană; o companie de 10 ori mai mare cumpără cam de 4 ori
            mai mult.
          </p>
        </Panel>

        <div className="grid gap-6 lg:grid-cols-2">
          <Panel>
            <PanelTitle>Nivel de preț pe piață</PanelTitle>
            <ul className="grid grid-cols-2 gap-x-6 gap-y-2 p-5 text-[14px]">
              {markets.map(([code, level]) => (
                <li key={code} className="flex items-center justify-between gap-3">
                  <span>{regionName(code)}</span>
                  <input
                    type="number"
                    min={0}
                    max={3}
                    step={0.05}
                    value={level}
                    onChange={(e) => {
                      setSaved(false)
                      setDraft({ ...draft, market_price_level: { ...draft.market_price_level, [code]: Math.max(0, Number(e.target.value) || 0) } })
                    }}
                    className="h-9 w-20 text-right"
                    aria-label={`Nivel de preț: ${regionName(code)}`}
                  />
                </li>
              ))}
            </ul>
            <p className="border-t border-line px-5 py-3 text-[13px] text-muted">
              Germania și Austria = 1. Alte țări: {draft.default_market_price_level}.
            </p>
          </Panel>

          <Panel>
            <PanelTitle>Șansa de câștig după scor</PanelTitle>
            <ul className="space-y-2 p-5 text-[14px]">
              {TIERS.map(([tier, label]) => (
                <li key={tier} className="flex items-center justify-between gap-3">
                  <span>Lead {label.toLowerCase()}</span>
                  <span className="flex items-center gap-2">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={Math.round((draft.win_probability[tier] ?? 0) * 100)}
                      onChange={(e) => {
                        setSaved(false)
                        setDraft({ ...draft, win_probability: { ...draft.win_probability, [tier]: Math.min(100, Math.max(0, Number(e.target.value) || 0)) / 100 } })
                      }}
                      className="h-9 w-20 text-right"
                      aria-label={`Șansa de câștig: lead ${label.toLowerCase()}`}
                    />
                    %
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </fieldset>

      <Panel>
        <PanelTitle>Surse pentru valorile implicite</PanelTitle>
        <ul className="list-disc space-y-1 py-4 pl-10 pr-5 text-[13px] text-ink-2">
          {draft.sources.map((src) => (
            <li key={src}>{src}</li>
          ))}
        </ul>
      </Panel>

      {isAdmin && (
        <div className="flex flex-wrap items-center gap-4">
          <Button variant="primary" onClick={() => void save()} disabled={!dirty || busy}>
            {busy ? 'Se salvează…' : 'Salvează ipotezele'}
          </Button>
          <button type="button" onClick={() => void restore()} disabled={busy} className="flex items-center gap-1.5 font-bold underline underline-offset-4 hover:text-orange-ink">
            <RotateCcw size={15} aria-hidden /> Revino la valorile implicite
          </button>
          {saved && !dirty && (
            <span className="flex items-center gap-2 font-bold text-ok">
              <CircleCheck size={17} aria-hidden /> Salvat. Estimările se actualizează la următoarea deschidere a fișelor.
            </span>
          )}
          {error && <span className="font-bold text-danger" role="alert">{error}</span>}
        </div>
      )}
    </div>
  )
}
