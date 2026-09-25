import { ChevronRight, ExternalLink, Globe, Send, Sparkles, UserSearch } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { STAGES, getCompany, getQuestions, getServices, isNew, timeAgo } from '../data/api'
import type { Company as CompanyT, Signal, Stage } from '../data/types'
import {
  Avatar,
  Button,
  NewBadge,
  Panel,
  PanelTitle,
  SERVICE_COLOR,
  ScoreDelta,
  ScoreMeter,
  ServiceTag,
  SourceIcon,
  StageTag,
  btn,
  sourceTypeLabel,
} from '../components/ui'

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

function SignalCard({ s }: { s: Signal }) {
  const question = getQuestions().find((q) => q.id === s.questionId)
  const negative = s.points < 0
  return (
    <article className={`border-l-4 bg-white p-5 ${negative ? 'border-danger' : 'border-orange'}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-1.5 flex items-center gap-3">
            {s.service ? (
              <ServiceTag id={s.service} />
            ) : (
              <span className="bg-danger-bg px-2 py-0.5 text-[12px] font-bold text-danger">Regulă negativă</span>
            )}
            <span className="text-[12px] text-muted">{sourceTypeLabel(s.sourceType)}</span>
          </div>
          <h3 className="text-[16px] leading-snug">{s.title}</h3>
        </div>
        <span
          className={`num shrink-0 px-2 py-1 text-[14px] font-bold ${negative ? 'bg-danger-bg text-danger' : 'bg-orange-wash text-ink'}`}
          title="Contribuția la scor"
        >
          {negative ? '' : '+'}
          {s.points} pct
        </span>
      </div>
      {question && (
        <p className="mt-2 text-[13px] text-muted">
          <span className="font-bold text-ink-2">Răspunde la:</span> {question.text}
        </p>
      )}
      <blockquote className="mt-3 bg-canvas px-4 py-3 text-[14px] leading-relaxed text-ink-2">„{s.quote}”</blockquote>
      <footer className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted">
        <span className="inline-flex items-center gap-1.5 font-bold text-ink-2">
          <SourceIcon type={s.sourceType} size={14} /> {s.source}
        </span>
        <span>{fmtDate(s.date)}</span>
        <span>Încredere AI: <span className="num font-bold text-ink-2">{Math.round(s.confidence * 100)}%</span></span>
        <a href={s.url} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 font-bold text-ink underline underline-offset-4 hover:text-orange-ink">
          Vezi sursa <ExternalLink size={13} aria-hidden />
        </a>
      </footer>
    </article>
  )
}

function Timeline({ c }: { c: CompanyT }) {
  const events = [
    ...c.signals.map((s) => ({ date: s.date, title: s.title, meta: s.source, negative: s.points < 0 })),
    { date: c.firstSeen, title: 'Companie descoperită automat', meta: 'LeadRadar', negative: false },
  ].sort((a, b) => b.date.localeCompare(a.date))
  return (
    <ol className="relative ml-2 border-l-2 border-line py-2">
      {events.map((e, i) => (
        <li key={i} className="relative mb-6 pl-6 last:mb-0">
          <span className={`absolute -left-[7px] top-1 size-3 ${e.negative ? 'bg-danger' : i === 0 ? 'bg-orange' : 'bg-ink'}`} aria-hidden />
          <p className="text-[12px] text-muted">{fmtDate(e.date)}</p>
          <p className="font-bold">{e.title}</p>
          <p className="text-[13px] text-muted">{e.meta}</p>
        </li>
      ))}
    </ol>
  )
}

function Notes() {
  const [notes, setNotes] = useState<{ text: string; at: string }[]>([])
  const [draft, setDraft] = useState('')
  const add = () => {
    if (!draft.trim()) return
    setNotes([{ text: draft.trim(), at: new Date().toISOString() }, ...notes])
    setDraft('')
  }
  return (
    <div>
      <label htmlFor="note" className="mb-2 block font-bold">
        Notă nouă
      </label>
      <textarea
        id="note"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={3}
        placeholder="Ex: Am vorbit cu directorul IT, revenim după 15 octombrie."
        className="w-full py-2"
      />
      <div className="mt-2 flex justify-end">
        <Button variant="dark" size="sm" onClick={add} disabled={!draft.trim()}>
          Salvează nota
        </Button>
      </div>
      <ul className="mt-4 space-y-3">
        {notes.map((n, i) => (
          <li key={i} className="border border-line p-4">
            <p className="text-[12px] text-muted">
              Ana Rusu · {timeAgo(n.at)}
            </p>
            <p className="mt-1">{n.text}</p>
          </li>
        ))}
        {notes.length === 0 && <li className="text-muted">Nicio notă încă.</li>}
      </ul>
    </div>
  )
}

type Tab = 'signals' | 'timeline' | 'notes' | 'message'

export default function Company() {
  const { id = '' } = useParams()
  const c = getCompany(id)
  const [stage, setStage] = useState<Stage | undefined>(c?.stage)
  const [tab, setTab] = useState<Tab>('signals')

  if (!c)
    return (
      <div className="py-20 text-center">
        <h1 className="text-[28px]">Compania nu a fost găsită</h1>
        <Link to="/leads" className={`${btn('secondary')} mt-6`}>
          Înapoi la lead-uri
        </Link>
      </div>
    )

  const positives = c.signals.filter((s) => s.points > 0)
  const negatives = c.signals.filter((s) => s.points < 0)
  const tabs: [Tab, string][] = [
    ['signals', `Semnale (${c.signals.length})`],
    ['timeline', 'Cronologie'],
    ['notes', 'Note'],
    ['message', 'Mesaj de contact'],
  ]

  return (
    <div className="rise">
      <nav className="mb-4 flex items-center gap-1 text-[13px] text-muted" aria-label="Breadcrumb">
        <Link to="/leads" className="font-bold hover:text-ink hover:underline">
          Lead-uri
        </Link>
        <ChevronRight size={14} aria-hidden />
        <span className="text-ink">{c.name}</span>
      </nav>

      <Panel className="mb-6">
        <div className="flex flex-wrap items-start gap-5 p-6">
          <span className="flex size-16 shrink-0 items-center justify-center bg-ink text-[24px] font-bold text-white" aria-hidden>
            {c.name[0]}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-[30px] leading-tight">{c.name}</h1>
              {isNew(c) && <NewBadge />}
              {stage && <StageTag stage={stage} />}
            </div>
            <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-muted">
              <span className="inline-flex items-center gap-1">
                <Globe size={14} aria-hidden /> {c.domain}
              </span>
              <span>{c.industry}</span>
              <span>{c.countryName}</span>
              <span>{c.employees} angajați</span>
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="stage">
              Stadiu
            </label>
            <select id="stage" value={stage} onChange={(e) => setStage(e.target.value as Stage)} className="h-10 font-bold">
              {STAGES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
            <a
              href={`https://www.linkedin.com/search/results/companies/?keywords=${encodeURIComponent(c.name)}`}
              target="_blank"
              rel="noreferrer"
              className={btn('ghost')}
              title="Validare manuală pe LinkedIn — fără extragere automată de date"
            >
              <UserSearch size={16} aria-hidden /> LinkedIn
            </a>
            <Button>Trimite în HubSpot</Button>
            <Button variant="primary" onClick={() => setTab('message')}>
              <Send size={16} aria-hidden /> Generează mesaj
            </Button>
          </div>
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        <div className="space-y-6">
          <Panel>
            <PanelTitle>Scor lead</PanelTitle>
            <div className="p-5">
              <div className="flex items-end gap-3">
                <span className="text-[56px] font-bold leading-[0.85]">{c.score}</span>
                <span className="pb-1 text-muted">/ 100</span>
                <span className="ml-auto pb-1">
                  <ScoreDelta score={c.score} prev={c.prevScore} />
                </span>
              </div>
              <div className="mt-4">
                <ScoreMeter score={c.score} size="lg" />
              </div>
              <h3 className="mb-3 mt-6 text-[13px] uppercase tracking-wider text-muted">Pe servicii</h3>
              <ul className="space-y-3">
                {getServices().map((s) => (
                  <li key={s.id}>
                    <div className="mb-1 flex items-center justify-between">
                      <ServiceTag id={s.id} />
                      <span className="num font-bold">{c.serviceScores[s.id]}</span>
                    </div>
                    <div className="h-2 bg-band" aria-hidden>
                      <div className={`h-full ${SERVICE_COLOR[s.id]}`} style={{ width: `${c.serviceScores[s.id]}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-5 border-t border-line pt-4 text-[13px] text-muted">
                <span className="num font-bold text-ink">{positives.length}</span> semnale pozitive
                {negatives.length > 0 && (
                  <>
                    {' '}
                    · <span className="num font-bold text-danger">{negatives.length}</span> reguli negative
                  </>
                )}
              </p>
            </div>
          </Panel>

          <Panel>
            <PanelTitle>Detalii</PanelTitle>
            <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-3 p-5 text-[14px]">
              <dt className="text-muted">Responsabil</dt>
              <dd className="flex items-center gap-2 font-bold">
                <Avatar name={c.owner} size={22} /> {c.owner ?? 'Neasignat'}
              </dd>
              <dt className="text-muted">Industrie</dt>
              <dd>{c.industry}</dd>
              <dt className="text-muted">Țară</dt>
              <dd>{c.countryName}</dd>
              <dt className="text-muted">Angajați</dt>
              <dd className="num">{c.employees}</dd>
              <dt className="text-muted">Descoperit</dt>
              <dd>{timeAgo(c.firstSeen)}</dd>
              <dt className="text-muted">Actualizat</dt>
              <dd>{timeAgo(c.updatedAt)}</dd>
            </dl>
          </Panel>
        </div>

        <div className="min-w-0 space-y-6">
          <section className="bg-ink p-6 text-white">
            <h2 className="flex items-center gap-2 text-[13px] uppercase tracking-wider text-orange">
              <Sparkles size={16} aria-hidden /> De ce acest lead, acum?
            </h2>
            <p className="mt-3 text-[17px] leading-relaxed">{c.whyNow}</p>
            <p className="mt-3 text-[12px] text-faint">Rezumat generat de AI din {c.signals.length} semnale cu surse verificabile.</p>
          </section>

          <div>
            <div className="flex border-b-2 border-ink" role="tablist">
              {tabs.map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={tab === id}
                  onClick={() => setTab(id)}
                  className={`-mb-[2px] px-5 py-3 font-bold transition-colors ${
                    tab === id ? 'bg-ink text-white' : 'text-ink-2 hover:bg-band'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="pt-5" role="tabpanel">
              {tab === 'signals' && (
                <div className="space-y-4">
                  {[...c.signals]
                    .sort((a, b) => Math.abs(b.points) - Math.abs(a.points))
                    .map((s) => (
                      <SignalCard key={s.id} s={s} />
                    ))}
                </div>
              )}
              {tab === 'timeline' && (
                <Panel className="p-6">
                  <Timeline c={c} />
                </Panel>
              )}
              {tab === 'notes' && (
                <Panel className="p-6">
                  <Notes />
                </Panel>
              )}
              {tab === 'message' && (
                <Panel className="p-8 text-center">
                  <Send size={28} className="mx-auto text-orange" aria-hidden />
                  <h3 className="mt-3 text-[18px]">Mesaj personalizat — în lucru</h3>
                  <p className="mx-auto mt-2 max-w-md text-muted">
                    AI-ul va scrie un email, un mesaj LinkedIn și un follow-up pe baza celor {positives.length} semnale ale companiei
                    (GIG-38).
                  </p>
                </Panel>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
