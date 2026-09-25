import { CircleCheck, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { getQuestions, getServices } from '../data/api'
import type { ServiceId, SignalQuestion, Weight } from '../data/types'
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

export default function Config() {
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
      <WeightPicker value={q.weight} onChange={(w) => update(q.id, { weight: w })} label={`Importanță: ${q.text}`} />
      <button type="button" onClick={() => remove(q.id)} className="p-1 text-muted hover:text-danger" aria-label={`Șterge: ${q.text}`}>
        <Trash2 size={17} />
      </button>
    </li>
  )

  const addRow = (k: string, service: ServiceId | null, placeholder: string) => (
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

      <div className="mb-6 flex border-b-2 border-ink" role="tablist">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`-mb-[2px] px-5 py-3 font-bold transition-colors ${tab === id ? 'bg-ink text-white' : 'text-ink-2 hover:bg-band'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'questions' && (
        <div className="space-y-6">
          <p className="max-w-3xl text-muted">
            Scrie întrebările în limbaj natural. AI-ul le caută răspunsul în știri, joburi, licitații și rapoarte, și citează sursa pentru fiecare
            răspuns. Importanța decide cât contează răspunsul în scor.
          </p>
          {getServices().map((s) => {
            const list = questions.filter((q) => q.service === s.id)
            return (
              <Panel key={s.id}>
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

      {(dirty || saved) && (
        <div className="fixed bottom-0 left-60 right-0 z-10 border-t-2 border-ink bg-white px-8 py-3">
          <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-4">
            {saved ? (
              <p className="flex items-center gap-2 font-bold text-ok">
                <CircleCheck size={18} aria-hidden /> Salvat. Scorurile au fost recalculate.
              </p>
            ) : (
              <p className="font-bold">Ai modificări nesalvate</p>
            )}
            {!saved && (
              <Button
                variant="primary"
                onClick={() => {
                  setDirty(false)
                  setSaved(true)
                }}
              >
                Salvează și recalculează
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
