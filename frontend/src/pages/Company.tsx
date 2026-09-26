import { ChevronRight, Copy, ExternalLink, Globe, Hand, Send, Sparkles, UserSearch } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { friendlyError, useSession } from '../auth/session'
import { STAGES, getCompany, getQuestions, getServices, isNew, patchCompany, signalHeadline, timeAgo, useDataVersion } from '../data/api'
import { describe } from '../data/team'
import { type Activity, type Note, type Outreach, addNote, generateOutreach, getActivity, getAssignment, saveAssignment, sendToHubspot } from '../data/backend'
import { listSellers, type Seller } from '../data/client'
import type { Company as CompanyT, Signal, Stage } from '../data/types'
import {
  Avatar,
  Button,
  NewBadge,
  Panel,
  PanelTitle,
  ScoreDelta,
  ScoreMeter,
  ServiceTag,
  SourceIcon,
  serviceColor,
  StageTag,
  btn,
  sourceTypeLabel,
} from '../components/ui'

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

function SignalCard({ s }: { s: Signal }) {
  const question = getQuestions().find((q) => q.id === s.questionId)
  const negative = s.points < 0
  const headline = signalHeadline(s)
  // When the headline already is the whole quote, do not repeat it below.
  const showQuote = !!s.quote.trim() && s.quote.trim() !== headline
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
          <h3 className="text-[16px] leading-snug">{headline}</h3>
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
      {showQuote && <blockquote className="mt-3 bg-canvas px-4 py-3 text-[14px] leading-relaxed text-ink-2">„{s.quote}”</blockquote>}
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


function Timeline({ c, activity }: { c: CompanyT; activity: Activity[] }) {
  const events = [
    ...c.signals.map((s) => ({ date: s.date, title: signalHeadline(s), meta: s.source, negative: s.points < 0 })),
    ...activity.map((a) => ({ date: a.t, title: describe(a.action, a.details ?? {}).label, meta: a.seller ?? 'Sistem', negative: false })),
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

function Notes({ companyId, notes, onChange }: { companyId: string; notes: Note[]; onChange: (n: Note[]) => void }) {
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const add = () => {
    if (!draft.trim()) return
    addNote(companyId, draft.trim())
      .then((a) => {
        onChange(a.notes)
        setDraft('')
        setError(null)
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
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
      {error && <p className="mt-2 font-bold text-danger" role="alert">{error}</p>}
      <ul className="mt-4 space-y-3">
        {[...notes].reverse().map((n, i) => (
          <li key={i} className="border border-line p-4">
            <p className="text-[12px] text-muted">
              {n.author} · {timeAgo(n.t)}
            </p>
            <p className="mt-1">{n.text}</p>
          </li>
        ))}
        {notes.length === 0 && <li className="text-muted">Nicio notă încă.</li>}
      </ul>
    </div>
  )
}

function Message({ c }: { c: CompanyT }) {
  const [channel, setChannel] = useState<'email' | 'linkedin' | 'followup'>('email')
  const [language, setLanguage] = useState<'RO' | 'EN' | 'DE'>('RO')
  const [draft, setDraft] = useState<Outreach | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canGenerate = c.bestServiceApiId != null

  const generate = () => {
    if (c.bestServiceApiId == null) return
    setBusy(true)
    setError(null)
    generateOutreach(c.id, c.bestServiceApiId, channel, language)
      .then(setDraft)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setBusy(false))
  }

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3">
        <label>
          <span className="mb-1 block text-[13px] font-bold">Canal</span>
          <select value={channel} onChange={(e) => setChannel(e.target.value as typeof channel)} className="h-10">
            <option value="email">Email</option>
            <option value="linkedin">Mesaj LinkedIn</option>
            <option value="followup">Follow-up</option>
          </select>
        </label>
        <label>
          <span className="mb-1 block text-[13px] font-bold">Limba</span>
          <select value={language} onChange={(e) => setLanguage(e.target.value as typeof language)} className="h-10">
            <option value="RO">Română</option>
            <option value="EN">Engleză</option>
            <option value="DE">Germană</option>
          </select>
        </label>
        <Button variant="primary" onClick={generate} disabled={!canGenerate || busy}>
          <Send size={16} aria-hidden /> {busy ? 'Se scrie…' : 'Generează'}
        </Button>
      </div>
      {!canGenerate && <p className="mt-3 text-muted">Disponibil când datele vin din backend și compania are un scor.</p>}
      {error && <p className="mt-3 font-bold text-danger" role="alert">{error}</p>}
      {draft && (
        <div className="mt-5 border border-line p-5">
          {draft.subject && <p className="mb-3 font-bold">Subiect: {draft.subject}</p>}
          <p className="whitespace-pre-wrap leading-relaxed">{draft.body || '(AI-ul nu a scris niciun text: fără cheie Anthropic se folosește modul offline.)'}</p>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-[12px] text-muted">
            <span className={draft.grounded ? 'font-bold text-ok' : 'font-bold text-warn'}>
              {draft.grounded ? 'Bazat pe semnale reale' : 'Nu citează niciun semnal: verifică înainte de trimitere'}
            </span>
            {draft.sources.map((s) => (
              <a key={s.url} href={s.url} target="_blank" rel="noreferrer" className="underline">
                sursă
              </a>
            ))}
            <Button size="sm" className="ml-auto" onClick={() => void navigator.clipboard?.writeText(`${draft.subject ? `${draft.subject}\n\n` : ''}${draft.body}`)}>
              <Copy size={14} aria-hidden /> Copiază
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

type Tab = 'signals' | 'timeline' | 'notes' | 'message'

export default function Company() {
  const { id = '' } = useParams()
  useDataVersion()
  const c = getCompany(id)
  const [stage, setStage] = useState<Stage | undefined>(c?.stage)
  const [sellerId, setSellerId] = useState<number | null>(c?.sellerId ?? null)
  const [owner, setOwner] = useState<string | null>(c?.owner ?? null)
  const { seller: me } = useSession()
  // Only an admin hands a lead to anyone; a sales manager can only take an unassigned lead or give back their own.
  const isAdmin = me?.role === 'admin'
  const [tab, setTab] = useState<Tab>('signals')
  const [sellers, setSellers] = useState<Seller[]>([])
  const [notes, setNotes] = useState<Note[]>([])
  const [activity, setActivity] = useState<Activity[]>([])
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null)

  const cid = c?.id
  useEffect(() => {
    if (!cid) return
    if (isAdmin) listSellers().then(setSellers).catch(() => setSellers([]))
    getAssignment(cid).then((a) => setNotes(a.notes)).catch(() => setNotes([]))
    getActivity(cid).then(setActivity).catch(() => setActivity([]))
  }, [cid, isAdmin])

  const fail = (err: unknown) => setStatus({ ok: false, text: friendlyError(err) })

  const changeStage = (next: Stage) => {
    if (!c) return
    const prev = stage
    setStage(next)
    saveAssignment(c.id, { stage: next })
      .then(() => {
        patchCompany(c.id, { stage: next })
        setStatus({ ok: true, text: 'Stadiu salvat.' })
      })
      .catch((err) => {
        setStage(prev)
        fail(err)
      })
  }

  const changeOwner = (value: string) => {
    if (!c) return
    const next = value ? Number(value) : null
    const prev = { sellerId, owner }
    const name = next == null ? null : next === me?.id ? me.full_name : sellers.find((s) => s.id === next)?.full_name ?? null
    setSellerId(next)
    setOwner(name)
    const self = next != null && next === me?.id
    saveAssignment(c.id, next == null ? { unassign: true } : { seller_id: next })
      .then((a) => {
        patchCompany(c.id, { sellerId: a.seller_id, owner: a.owner })
        setOwner(a.owner)
        setStatus({ ok: true, text: self ? 'Lead-ul este acum al tău.' : a.owner ? `Asignat lui ${a.owner}.` : 'Lead neasignat.' })
      })
      .catch((err) => {
        setSellerId(prev.sellerId)
        setOwner(prev.owner)
        fail(err)
      })
  }
  const mine = me != null && sellerId === me.id

  const hubspot = () => {
    if (!c || c.leadIds.length === 0) return
    sendToHubspot(c.leadIds)
      .then((res) => {
        const ok = res.filter((r) => r.ok).length
        setStatus(ok ? { ok: true, text: `Trimis în HubSpot (${ok} lead-uri).` } : { ok: false, text: res[0]?.error ?? 'HubSpot a refuzat cererea.' })
      })
      .catch(fail)
  }

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
    ['notes', `Note (${notes.length})`],
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
            <select id="stage" value={stage} onChange={(e) => changeStage(e.target.value as Stage)} className="h-10 font-bold">
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
            <Button onClick={hubspot} disabled={c.leadIds.length === 0} title="Creează / actualizează compania în HubSpot, cu o notă">
              Trimite în HubSpot
            </Button>
            <Button variant="primary" onClick={() => setTab('message')}>
              <Send size={16} aria-hidden /> Generează mesaj
            </Button>
          </div>
        </div>
        {status && (
          <p className={`border-t border-line px-6 py-2 text-[13px] font-bold ${status.ok ? 'text-ok' : 'text-danger'}`} role="status">
            {status.text}
          </p>
        )}
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
                      <span className="num font-bold">{c.serviceScores[s.id] ?? 0}</span>
                    </div>
                    <div className="h-2 bg-band" aria-hidden>
                      <div className="h-full" style={{ width: `${c.serviceScores[s.id] ?? 0}%`, background: serviceColor(s.id) }} />
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
            <dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-3 p-5 text-[14px]">
              <dt className="text-muted">Responsabil</dt>
              <dd className="flex min-w-0 items-center gap-2 font-bold">
                <Avatar name={owner} size={22} />
                {isAdmin ? (
                  <select value={sellerId ?? ''} onChange={(e) => changeOwner(e.target.value)} className="h-8 w-full min-w-0 flex-1 truncate text-[13px]" aria-label="Responsabil">
                    <option value="">Neasignat</option>
                    {sellers.filter((s) => s.active && s.role !== 'admin').map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.full_name}
                      </option>
                    ))}
                  </select>
                ) : owner == null && me && !isAdmin ? (
                  <Button size="sm" variant="primary" onClick={() => changeOwner(String(me.id))}>
                    <Hand size={14} aria-hidden /> Preia lead-ul
                  </Button>
                ) : (
                  <span className="flex min-w-0 flex-wrap items-center gap-x-3">
                    <span className="truncate">{owner ? (mine ? `${owner} (tu)` : owner) : 'Neasignat'}</span>
                    {mine && !isAdmin && (
                      <button type="button" onClick={() => changeOwner('')} className="text-[13px] font-normal text-muted underline underline-offset-4 hover:text-ink">
                        Renunță
                      </button>
                    )}
                  </span>
                )}
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
            {c.whyNow ? (
              <>
                <p className="mt-3 text-[17px] leading-relaxed">{c.whyNow}</p>
                <p className="mt-3 text-[12px] text-faint">Rezumat generat de AI din {c.signals.length} semnale cu surse verificabile.</p>
              </>
            ) : (
              <p className="mt-3 text-[15px] leading-relaxed text-white/75">
                {c.signals.length
                  ? 'Rezumatul se generează la următoarea analiză. Până atunci, vezi semnalele de mai jos.'
                  : 'Încă nu avem semnale pentru această companie. Scorul vine doar din potrivirea cu profilul de client ideal (industrie, țară, mărime).'}
              </p>
            )}
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
                  className={`-mb-[2px] border-b-2 px-5 py-3 font-bold transition-colors ${
                    tab === id ? 'border-ink bg-ink text-white' : 'border-transparent text-ink-2 hover:border-orange hover:text-orange-ink'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="pt-5" role="tabpanel">
              {tab === 'signals' && (
                <div className="space-y-4">
                  {c.signals.length === 0 && (
                    <p className="border border-line bg-white px-5 py-8 text-center text-muted">
                      Niciun semnal găsit încă. Apar automat când sursele publică ceva relevant despre companie.
                    </p>
                  )}
                  {[...c.signals]
                    .sort((a, b) => Math.abs(b.points) - Math.abs(a.points))
                    .map((s) => (
                      <SignalCard key={s.id} s={s} />
                    ))}
                </div>
              )}
              {tab === 'timeline' && (
                <Panel className="p-6">
                  <Timeline c={c} activity={activity} />
                </Panel>
              )}
              {tab === 'notes' && (
                <Panel className="p-6">
                  <Notes companyId={c.id} notes={notes} onChange={setNotes} />
                </Panel>
              )}
              {tab === 'message' && (
                <Panel className="p-6">
                  <Message c={c} />
                </Panel>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
