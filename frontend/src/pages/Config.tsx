import { CircleCheck, Lock, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSession } from '../auth/session'
import { getQuestions, getServices, loadData, useDataVersion } from '../data/api'
import { type ApiQuestionFull, type ConfigData, configApi, loadConfig } from '../data/backend'
import type { ServiceId, SignalQuestion, Weight } from '../data/types'
import NewServiceForm from '../components/NewServiceForm'
import { Button, Panel, PanelTitle, PageHeader, ServiceTag } from '../components/ui'

const WEIGHTS: [Weight, string][] = [
  ['high', 'Mare'],
  ['medium', 'Medie'],
  ['low', 'Mică'],
]

function WeightPicker({ value, onChange, label }: { value: Weight; onChange: (w: Weight) => void; label: string }) {
  return (
    <div className="flex shrink-0 border-2 border-ink" role="radiogroup" aria-label={label}>
      {WEIGHTS.map(([w, text]) => (
        <button
          key={w}
          type="button"
          role="radio"
          aria-checked={value === w}
          onClick={() => onChange(w)}
          className={`h-8 px-3 text-[13px] font-bold transition-colors ${value === w ? 'bg-ink text-white' : 'bg-white hover:bg-band'}`}
        >
          {text}
        </button>
      ))}
    </div>
  )
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 shrink-0 border-2 border-ink transition-colors ${checked ? 'bg-orange' : 'bg-white'}`}
    >
      <span className={`absolute top-0.5 size-4 bg-ink transition-all ${checked ? 'left-[22px]' : 'left-0.5'}`} />
    </button>
  )
}

function Chips({ options, value, onChange, label }: { options: string[]; value: string[]; onChange: (v: string[]) => void; label: string }) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={label}>
      {options.map((o) => {
        const on = value.includes(o)
        return (
          <button
            key={o}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((x) => x !== o) : [...value, o])}
            className={`h-9 border-2 px-3 font-bold transition-colors ${on ? 'border-ink bg-ink text-white' : 'border-line bg-white hover:border-ink'}`}
          >
            {o}
          </button>
        )
      })}
    </div>
  )
}

type Tab = 'questions' | 'negative' | 'icp' | 'scoring'

// UI labels <-> backend values (ISO-2 markets, ICP industry vocabulary).
const MARKETS: [string, string][] = [
  ['Moldova', 'MD'], ['România', 'RO'], ['Polonia', 'PL'], ['Germania', 'DE'], ['Ucraina', 'UA'], ['Regatul Unit', 'GB'], ['SUA', 'US'],
]
const INDUSTRIES: [string, string][] = [
  ['Servicii bancare', 'Banking'], ['Asigurări', 'Insurance'], ['Fintech', 'Financial Services'], ['Logistică', 'Logistics'],
  ['Energie', 'Energy'], ['Sănătate privată', 'Healthcare'], ['Retail B2B', 'Retail'], ['Agribusiness', 'Agriculture'],
  ['Construcții', 'Construction'], ['Farmaceutic', 'Pharmaceuticals'],
]
const API_WEIGHT = { high: 'High', medium: 'Medium', low: 'Low' } as const
const DECAYS = ['30', '60', '90', '180']
const toCodes = (names: string[], table: [string, string][]) => table.filter(([n]) => names.includes(n)).map(([, v]) => v)
const toNames = (codes: string[], table: [string, string][]) => table.filter(([, v]) => codes.map((c) => c.toLowerCase()).includes(v.toLowerCase())).map(([n]) => n)

export default function Config() {
  // Sales managers see the current setup; only an admin changes it (it re-scores every company for everyone).
  const isAdmin = useSession().seller?.role === 'admin'
  useDataVersion()
  const [tab, setTab] = useState<Tab>('questions')
  const [questions, setQuestions] = useState<SignalQuestion[]>(getQuestions)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [dirty, setDirty] = useState(false)
  const [saved, setSaved] = useState(false)
  const [markets, setMarkets] = useState(['Moldova', 'România', 'Polonia'])
  const [industries, setIndustries] = useState(['Servicii bancare', 'Asigurări', 'Logistică', 'Energie', 'Sănătate privată'])
  const [minEmployees, setMinEmployees] = useState(50)
  const [b2bOnly, setB2bOnly] = useState(true)
  const [hot, setHot] = useState(75)
  const [decay, setDecay] = useState('90')
  const [points, setPoints] = useState({ high: 3, medium: 2, low: 1 })

  const [config, setConfig] = useState<ConfigData | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Start from what is stored in PostgreSQL (questions, rules, ICP, scoring config).
  useEffect(() => {
    loadConfig()
      .then((cfg) => {
        setConfig(cfg)
        const countries = cfg.scoring.discovery_countries
        if (countries.length) setMarkets(toNames(countries, MARKETS))
        const inds = [...new Set(cfg.icps.flatMap((i) => i.industries))]
        if (inds.length) setIndustries(toNames(inds, INDUSTRIES))
        const mins = cfg.icps.map((i) => i.employee_min).filter((m): m is number => m != null)
        if (mins.length) setMinEmployees(Math.min(...mins))
        const b2c = cfg.rules.find((r) => r.field === 'business_model')
        if (b2c) setB2bOnly(b2c.active)
        setHot(Math.round(cfg.scoring.hot_threshold))
        const wv = cfg.scoring.weight_values
        setPoints({ high: wv.High, medium: wv.Medium, low: wv.Low })
        const third = cfg.scoring.recency_buckets[2]?.[0]
        if (third != null) setDecay(DECAYS.reduce((best, d) => (Math.abs(+d - third) < Math.abs(+best - third) ? d : best), '90'))
      })
      .catch((err: unknown) => setError(`Nu am putut încărca configurarea: ${err instanceof Error ? err.message : String(err)}`))
  }, [])

  const save = async () => {
    if (!config) {
      setError('Configurarea nu s-a încărcat de pe server, așa că nu poate fi salvată. Reîncarcă pagina.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const byId = new Map(questions.map((q) => [q.id, q]))
      const apiService = new Map(config.services.map((s) => [s.uiId, s.id]))
      for (const q of config.questions) {
        const ui = byId.get(`q:${q.id}`)
        if (!ui) await configApi.deleteQuestion(q)
        else if (ui.active !== q.active || API_WEIGHT[ui.weight] !== q.weight)
          await configApi.updateQuestion({ ...q, active: ui.active, weight: API_WEIGHT[ui.weight] } as ApiQuestionFull)
      }
      for (const r of config.rules.filter((r) => r.rule_type === 'llm_question')) {
        const ui = byId.get(`rule:${r.id}`)
        if (!ui) await configApi.deleteRule(r)
        else if (ui.active !== r.active) await configApi.updateRule({ ...r, active: ui.active })
      }
      for (const q of questions.filter((q) => q.id.startsWith('custom-'))) {
        const sid = q.service ? apiService.get(q.service) : undefined
        if (sid != null) await configApi.createQuestion(sid, q.text, API_WEIGHT[q.weight], q.polarity === 'negative')
        else await configApi.createRule(q.text)
      }
      const b2c = config.rules.find((r) => r.field === 'business_model')
      if (b2c && b2c.active !== b2bOnly) await configApi.updateRule({ ...b2c, active: b2bOnly })
      const countries = toCodes(markets, MARKETS)
      const inds = toCodes(industries, INDUSTRIES)
      for (const icp of config.icps) {
        if (icp.employee_min !== minEmployees || JSON.stringify(icp.industries) !== JSON.stringify(inds) || JSON.stringify(icp.countries) !== JSON.stringify(countries))
          await configApi.saveIcp({ ...icp, industries: inds, countries, employee_min: minEmployees })
      }
      const d = +decay
      await configApi.saveScoring({
        ...config.scoring,
        hot_threshold: hot,
        warm_threshold: Math.min(config.scoring.warm_threshold, hot),
        weight_values: { High: points.high, Medium: points.medium, Low: points.low },
        recency_buckets: [[Math.round(d / 3), 1.0], [Math.round((2 * d) / 3), 0.7], [d, 0.4], [null, 0.1]],
        discovery_countries: countries.length ? countries : config.scoring.discovery_countries,
      })
      await loadData()
      const fresh = await loadConfig()
      setConfig(fresh)
      setQuestions(getQuestions())
      setDirty(false)
      setSaved(true)
    } catch (err) {
      setError(`Salvarea a eșuat: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setSaving(false)
    }
  }

  // A new service came from the form: reload services and questions, keep the unsaved edits made on this page.
  const addedService = async (slug: string) => {
    await loadData()
    setConfig(await loadConfig())
    const known = new Set(questions.map((q) => q.id))
    setQuestions((qs) => [...qs, ...getQuestions().filter((q) => !known.has(q.id))])
    setSaved(false)
    requestAnimationFrame(() => document.getElementById(`service-${slug}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  }

  const touch = () => {
    setDirty(true)
    setSaved(false)
  }
  const update = (id: string, patch: Partial<SignalQuestion>) => {
    setQuestions((qs) => qs.map((q) => (q.id === id ? { ...q, ...patch } : q)))
    touch()
  }
  const remove = (id: string) => {
    setQuestions((qs) => qs.filter((q) => q.id !== id))
    touch()
  }
  const add = (service: ServiceId | null, key: string) => {
    const text = drafts[key]?.trim()
    if (!text) return
    setQuestions((qs) => [
      ...qs,
      { id: `custom-${Date.now()}`, service, text, weight: 'medium', polarity: service ? 'positive' : 'negative', active: true },
    ])
    setDrafts((d) => ({ ...d, [key]: '' }))
    touch()
  }

  const questionRow = (q: SignalQuestion) => (
    <li key={q.id} className={`flex flex-wrap items-center gap-4 border-b border-line px-5 py-4 last:border-0 ${q.active ? '' : 'opacity-50'}`}>
      <Toggle checked={q.active} onChange={(v) => update(q.id, { active: v })} label={`Activează: ${q.text}`} />
      <p className="min-w-60 flex-1 leading-snug">{q.text}</p>
      {q.id.startsWith('rule:') ? (
        <span className="shrink-0 bg-danger-bg px-2 py-1 text-[12px] font-bold text-danger">Descalifică</span>
      ) : (
        <WeightPicker value={q.weight} onChange={(w) => update(q.id, { weight: w })} label={`Importanță: ${q.text}`} />
      )}
      {isAdmin && (
        <button type="button" onClick={() => remove(q.id)} className="p-1 text-muted hover:text-danger" aria-label={`Șterge: ${q.text}`}>
          <Trash2 size={17} />
        </button>
      )}
    </li>
  )

  const addRow = (k: string, service: ServiceId | null, placeholder: string) =>
    isAdmin && (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        add(service, k)
      }}
      className="flex gap-2 bg-canvas px-5 py-3"
    >
      <input
        value={drafts[k] ?? ''}
        onChange={(e) => setDrafts((d) => ({ ...d, [k]: e.target.value }))}
        placeholder={placeholder}
        aria-label={placeholder}
        className="h-9 flex-1"
      />
      <Button type="submit" size="sm" variant="dark" disabled={!drafts[k]?.trim()}>
        <Plus size={15} aria-hidden /> Adaugă
      </Button>
    </form>
  )

  const tabs: [Tab, string][] = [
    ['questions', 'Întrebări de semnal'],
    ['negative', 'Reguli negative'],
    ['icp', 'Profil client ideal'],
    ['scoring', 'Scorare'],
  ]

  return (
    <div className="rise pb-24">
      <PageHeader
        title="Configurare"
        subtitle="Definește ce înseamnă un lead bun. Orice schimbare recalculează scorurile tuturor companiilor."
      />

      {!isAdmin && (
        <p className="mb-6 flex items-center gap-2 border-l-4 border-ink bg-band px-4 py-3 text-[14px]">
          <Lock size={16} aria-hidden /> Doar administratorul poate modifica configurarea. Aici vezi setările după care se calculează scorurile.
        </p>
      )}

      <div className="mb-6 flex border-b-2 border-ink" role="tablist">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`-mb-[2px] border-b-2 px-5 py-3 font-bold transition-colors ${tab === id ? 'border-ink bg-ink text-white' : 'border-transparent text-ink-2 hover:border-orange hover:text-orange-ink'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* A disabled fieldset makes every control inside read-only for sales managers. */}
      <fieldset disabled={!isAdmin} className="m-0 min-w-0 border-0 p-0">
      {tab === 'questions' && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <p className="max-w-3xl text-muted">
              Scrie întrebările în limbaj natural. AI-ul le caută răspunsul în știri, joburi, licitații și rapoarte, și citează sursa pentru fiecare
              răspuns. Importanța decide cât contează răspunsul în scor.
            </p>
            {isAdmin && (
              <NewServiceForm
                takenSlugs={config?.services.map((s) => s.slug) ?? []}
                baseIcp={config?.icps[0] ?? null}
                onCreated={addedService}
              />
            )}
          </div>
          {getServices().map((s) => {
            const list = questions.filter((q) => q.service === s.id)
            return (
              <div key={s.id} id={`service-${s.id}`} className="scroll-mt-6">
              <Panel>
                <PanelTitle action={<span className="text-[13px] text-muted">{list.filter((q) => q.active).length} active</span>}>
                  <span className="flex items-center gap-3">
                    <ServiceTag id={s.id} className="!text-[16px]" />
                    <span className="font-normal text-muted">{s.name}</span>
                  </span>
                </PanelTitle>
                <ul>
                  {list.map(questionRow)}
                </ul>
                {addRow(s.id, s.id, `Întrebare nouă pentru ${s.short}…`)}
              </Panel>
              </div>
            )
          })}
        </div>
      )}

      {tab === 'negative' && (
        <Panel>
          <PanelTitle>Reguli care scad scorul sau descalifică</PanelTitle>
          <p className="border-b border-line px-5 py-3 text-[13px] text-muted">
            Importanță <span className="font-bold text-ink">Mare</span> = compania e descalificată automat. Medie sau Mică = penalizare de scor.
          </p>
          <ul>
            {questions
              .filter((q) => q.polarity === 'negative')
              .map(questionRow)}
          </ul>
          {addRow('negative', null, 'Regulă nouă, ex: Compania este în insolvență?')}
        </Panel>
      )}

      {tab === 'icp' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Panel>
            <PanelTitle>Piețe țintă</PanelTitle>
            <div className="p-5">
              <Chips
                label="Piețe țintă"
                options={['Moldova', 'România', 'Polonia', 'Germania', 'Ucraina', 'Regatul Unit', 'SUA']}
                value={markets}
                onChange={(v) => {
                  setMarkets(v)
                  touch()
                }}
              />
              <p className="mt-4 text-[13px] text-muted">Sursele de știri și licitații se filtrează automat pe țările alese.</p>
            </div>
          </Panel>
          <Panel>
            <PanelTitle>Industrii</PanelTitle>
            <div className="p-5">
              <Chips
                label="Industrii"
                options={['Servicii bancare', 'Asigurări', 'Fintech', 'Logistică', 'Energie', 'Sănătate privată', 'Retail B2B', 'Agribusiness', 'Construcții', 'Farmaceutic']}
                value={industries}
                onChange={(v) => {
                  setIndustries(v)
                  touch()
                }}
              />
            </div>
          </Panel>
          <Panel>
            <PanelTitle>Mărimea companiei</PanelTitle>
            <div className="p-5">
              <label htmlFor="min-emp" className="font-bold">
                Minim angajați
              </label>
              <div className="mt-2 flex items-center gap-4">
                <input
                  id="min-emp"
                  type="range"
                  min={0}
                  max={1000}
                  step={10}
                  value={minEmployees}
                  onChange={(e) => {
                    setMinEmployees(+e.target.value)
                    touch()
                  }}
                  className="flex-1 border-0 px-0 accent-orange"
                />
                <span className="num w-16 text-right text-[20px] font-bold">{minEmployees}</span>
              </div>
            </div>
          </Panel>
          <Panel>
            <PanelTitle>Tip de client</PanelTitle>
            <div className="flex items-start gap-4 p-5">
              <Toggle
                checked={b2bOnly}
                onChange={(v) => {
                  setB2bOnly(v)
                  touch()
                }}
                label="Doar companii B2B"
              />
              <div>
                <p className="font-bold">Doar companii B2B</p>
                <p className="text-[13px] text-muted">Companiile care vând exclusiv către consumatori sunt descalificate automat.</p>
              </div>
            </div>
          </Panel>
        </div>
      )}

      {tab === 'scoring' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Panel className="lg:col-span-2">
            <div className="bg-ink p-6 text-white">
              <p className="text-[13px] font-bold uppercase tracking-wider text-orange">Formula de scor</p>
              <p className="mt-2 text-[20px] font-bold">Scor = Σ (importanță × încredere AI × actualitate) − penalizări</p>
              <p className="mt-1 text-faint">Rezultatul se normalizează între 0 și 100. Fiecare punct poate fi urmărit până la sursa lui.</p>
            </div>
          </Panel>
          <Panel>
            <PanelTitle>Puncte pe importanță</PanelTitle>
            <div className="space-y-4 p-5">
              {WEIGHTS.map(([w, label]) => (
                <label key={w} className="flex items-center justify-between gap-4">
                  <span className="font-bold">{label}</span>
                  <input
                    type="number"
                    min={0}
                    max={10}
                    value={points[w]}
                    onChange={(e) => {
                      setPoints((p) => ({ ...p, [w]: +e.target.value }))
                      touch()
                    }}
                    className="num h-10 w-24 text-right font-bold"
                  />
                </label>
              ))}
            </div>
          </Panel>
          <Panel>
            <PanelTitle>Praguri</PanelTitle>
            <div className="space-y-6 p-5">
              <div>
                <label htmlFor="hot" className="font-bold">
                  Lead fierbinte de la scorul
                </label>
                <div className="mt-2 flex items-center gap-4">
                  <input
                    id="hot"
                    type="range"
                    min={50}
                    max={95}
                    value={hot}
                    onChange={(e) => {
                      setHot(+e.target.value)
                      touch()
                    }}
                    className="flex-1 border-0 px-0 accent-orange"
                  />
                  <span className="num w-12 text-right text-[20px] font-bold">{hot}</span>
                </div>
              </div>
              <div>
                <label htmlFor="decay" className="font-bold">
                  Un semnal își pierde valoarea după
                </label>
                <select
                  id="decay"
                  value={decay}
                  onChange={(e) => {
                    setDecay(e.target.value)
                    touch()
                  }}
                  className="mt-2 h-10 w-full"
                >
                  <option value="30">30 de zile</option>
                  <option value="60">60 de zile</option>
                  <option value="90">90 de zile</option>
                  <option value="180">180 de zile</option>
                </select>
              </div>
            </div>
          </Panel>
        </div>
      )}

      </fieldset>

      {isAdmin && (dirty || saved || error) && (
        <div className="fixed bottom-0 left-60 right-0 z-10 border-t-2 border-ink bg-white px-8 py-3">
          <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-4">
            {error ? (
              <p className="font-bold text-danger" role="alert">{error}</p>
            ) : saved ? (
              <p className="flex items-center gap-2 font-bold text-ok">
                <CircleCheck size={18} aria-hidden /> Salvat. Scorurile au fost recalculate.
              </p>
            ) : (
              <p className="font-bold">Ai modificări nesalvate</p>
            )}
            {!saved && (
              <Button variant="primary" onClick={() => void save()} disabled={saving}>
                {saving ? 'Se salvează…' : 'Salvează și recalculează'}
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
