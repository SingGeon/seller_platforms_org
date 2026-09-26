import { ArrowRight, TriangleAlert, UserPlus } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { getCompanies, timeAgo, useDataVersion } from '../data/api'
import type { Seller } from '../data/client'
import { CATEGORIES, type ActivityCategory, loadActivity, loadTeam, type TeamEvent } from '../data/team'
import { Avatar, PageHeader, Panel, PanelTitle, btn } from '../components/ui'

const PERIODS = [
  { id: '1', label: 'Ultimele 24 de ore', hours: 24 },
  { id: '7', label: 'Ultimele 7 zile', hours: 24 * 7 },
  { id: '30', label: 'Ultimele 30 de zile', hours: 24 * 30 },
]

const dayKey = (iso: string) => new Date(iso).toLocaleDateString('sv-SE')
const dayLabel = (iso: string) => {
  const key = dayKey(iso)
  if (key === dayKey(new Date().toISOString())) return 'Azi'
  if (key === dayKey(new Date(Date.now() - 86400000).toISOString())) return 'Ieri'
  return new Date(iso).toLocaleDateString('ro-RO', { weekday: 'long', day: 'numeric', month: 'long' })
}
const hhmm = (iso: string) => new Date(iso).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })

function Tile({ label, value, note, warn }: { label: string; value: string | number; note: string; warn?: boolean }) {
  return (
    <div className="border border-line bg-white p-5">
      <p className="flex items-center gap-2 text-[13px] font-bold text-muted">
        <span className="size-2 bg-orange" aria-hidden />
        {label}
      </p>
      <p className="num mt-3 text-[36px] font-bold leading-none">{value}</p>
      <p className={`mt-2 text-[13px] ${warn ? 'font-bold text-danger' : 'text-muted'}`}>{note}</p>
    </div>
  )
}

function DailyChart({ events, now }: { events: TeamEvent[]; now: number }) {
  const days = Array.from({ length: 14 }, (_, i) => {
    const d = new Date(now - (13 - i) * 86400000)
    const key = dayKey(d.toISOString())
    return { key, date: d, n: events.filter((e) => dayKey(e.t) === key && e.category !== 'acces').length }
  })
  const max = Math.max(1, ...days.map((d) => d.n))
  const total = days.reduce((a, d) => a + d.n, 0)
  return (
    <Panel>
      <PanelTitle action={<span className="num text-[13px] text-muted">{total} acțiuni în 14 zile</span>}>Activitate pe zile</PanelTitle>
      <div className="px-5 pb-4 pt-6">
        <div className="flex h-40 items-end gap-[3px] border-b border-line" role="img" aria-label={`Acțiuni pe zi în ultimele 14 zile, maximum ${max}`}>
          {days.map((d) => (
            <div key={d.key} className="group relative flex h-full flex-1 items-end">
              <div className="w-full bg-orange transition-colors group-hover:bg-ink" style={{ height: `${(d.n / max) * 100}%`, minHeight: d.n ? 3 : 0, borderRadius: '3px 3px 0 0' }} />
              <span className="num pointer-events-none absolute -top-7 left-1/2 hidden -translate-x-1/2 whitespace-nowrap bg-ink px-2 py-1 text-[12px] font-bold text-white group-hover:block">
                {d.n} · {d.date.toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })}
              </span>
            </div>
          ))}
        </div>
        <div className="mt-2 flex gap-[3px] text-[11px] text-muted">
          {days.map((d, i) => (
            <span key={d.key} className="flex-1 text-center">
              {i % 2 === 1 || i === 13 ? d.date.toLocaleDateString('ro-RO', { day: 'numeric' }) : ''}
            </span>
          ))}
        </div>
        <p className="mt-3 text-[12px] text-muted">Acțiunile sales managerilor pe lead-uri și conturi (fără autentificări și fără acțiunile administratorilor). Treci cu mouse-ul peste o bară pentru valoare.</p>
      </div>
    </Panel>
  )
}


export default function Admin() {
  useDataVersion()
  // Fixed when the page opens: periods and the chart count back from this moment.
  const [now] = useState(() => Date.now())
  const [team, setTeam] = useState<Seller[] | null>(null)
  const [events, setEvents] = useState<TeamEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [period, setPeriod] = useState('7')
  const [who, setWho] = useState<string>('')
  const [cat, setCat] = useState<ActivityCategory | ''>('')
  const [limit, setLimit] = useState(40)
  const feedRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    Promise.all([loadTeam(), loadActivity()])
      .then(([t, e]) => {
        setTeam(t)
        setEvents(e)
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  const hours = PERIODS.find((p) => p.id === period)!.hours
  const since = now - hours * 3600_000
  const inPeriod = useMemo(() => events.filter((e) => new Date(e.t).getTime() >= since), [events, since])
  const companies = getCompanies()
  const companyName = useMemo(() => new Map(companies.map((c) => [c.id, c.name])), [companies])

  if (error) return <p className="bg-danger-bg px-4 py-3 font-bold text-danger">Nu am putut încărca activitatea: {error}</p>
  if (!team) return <p className="text-muted">Se încarcă activitatea echipei…</p>

  const sellers = team.filter((s) => s.role !== 'admin')
  const activeSellers = sellers.filter((s) => s.active)
  // Team figures count only sales managers; the journal below still shows everyone, admins included.
  const sellerIds = new Set(sellers.map((s) => s.id))
  const teamEvents = events.filter((e) => e.sellerId != null && sellerIds.has(e.sellerId))
  const teamInPeriod = inPeriod.filter((e) => e.sellerId != null && sellerIds.has(e.sellerId))
  const workedIds = new Set(teamInPeriod.filter((e) => e.category !== 'acces').map((e) => e.sellerId))
  const idle = activeSellers.filter((s) => !workedIds.has(s.id))
  const leadActions = teamInPeriod.filter((e) => e.category === 'leaduri').length
  const won = companies.filter((c) => c.stage === 'castigat' && c.sellerId != null && sellerIds.has(c.sellerId)).length
  const alerts = inPeriod.filter((e) => e.alert)

  const rows = sellers
    .map((s) => {
      const mine = companies.filter((c) => c.sellerId === s.id)
      const acts = inPeriod.filter((e) => e.sellerId === s.id && e.category !== 'acces')
      const last = events.find((e) => e.sellerId === s.id && e.category !== 'acces')
      return {
        s,
        acts: acts.length,
        leads: mine.length,
        working: mine.filter((c) => c.stage === 'contactat' || c.stage === 'negociere').length,
        won: mine.filter((c) => c.stage === 'castigat').length,
        last,
      }
    })
    .sort((a, b) => Number(b.s.active) - Number(a.s.active) || b.acts - a.acts)
  const maxActs = Math.max(1, ...rows.map((r) => r.acts))

  const feed = inPeriod.filter((e) => (!who || String(e.sellerId) === who) && (!cat || e.category === cat))
  const shown = feed.slice(0, limit)
  const focus = (id: number) => {
    setWho(String(id))
    setLimit(40)
    feedRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="rise">
      <PageHeader
        title="Monitorizare echipă"
        subtitle={
          <>
            Activitatea sales managerilor, din jurnalul serverului.
          </>
        }
        actions={
          <>
            <select value={period} onChange={(e) => setPeriod(e.target.value)} className="h-10 font-bold" aria-label="Perioada">
              {PERIODS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
            <Link to="/account?tab=accounts" className={btn('primary')}>
              <UserPlus size={16} aria-hidden /> Cont nou de sales manager
            </Link>
          </>
        }
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="Sales manageri activi" value={`${activeSellers.length}/${sellers.length}`} note={`${sellers.length - activeSellers.length} conturi dezactivate`} />
        <Tile
          label="Au lucrat în perioadă"
          value={`${activeSellers.length - idle.length}/${activeSellers.length}`}
          note={idle.length ? `${idle.length} fără nicio acțiune` : 'toți au activitate'}
          warn={idle.length > 0}
        />
        <Tile label="Acțiuni pe lead-uri" value={leadActions} note={`sales manageri, ${PERIODS.find((p) => p.id === period)!.label.toLowerCase()}`} />
        <Tile label="Lead-uri câștigate" value={won} note="de sales manageri, total" />
      </div>

      {alerts.length > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-3 border-l-4 border-danger bg-danger-bg px-5 py-3" role="status">
          <TriangleAlert size={18} className="text-danger" aria-hidden />
          <p className="font-bold text-danger">
            {alerts.length} {alerts.length === 1 ? 'autentificare eșuată' : 'autentificări eșuate'} în perioada aleasă
          </p>
          <button
            type="button"
            onClick={() => {
              setWho('')
              setCat('acces')
              feedRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
            }}
            className="ml-auto text-[14px] font-bold underline underline-offset-4"
          >
            Vezi în jurnal
          </button>
        </div>
      )}

      <div className="mb-6">
        <DailyChart events={teamEvents} now={now} />
      </div>

      <Panel className="mb-6">
        <PanelTitle>Sales manageri</PanelTitle>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead className="whitespace-nowrap border-b-2 border-ink text-left text-[13px]">
              <tr>
                <th className="px-4 py-3">Sales manager</th>
                <th className="px-4 py-3">Ultima autentificare</th>
                <th className="px-4 py-3">Acțiuni în perioadă</th>
                <th className="px-4 py-3 text-right">Lead-uri</th>
                <th className="px-4 py-3 text-right">În lucru</th>
                <th className="px-4 py-3 text-right">Câștigate</th>
                <th className="px-4 py-3">Ultima acțiune</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ s, acts, leads, working, won: w, last }) => (
                <tr
                  key={s.id}
                  onClick={() => focus(s.id)}
                  className={`cursor-pointer border-b border-line align-middle last:border-0 hover:bg-orange-wash ${s.active ? '' : 'text-muted'}`}
                  title="Arată activitatea în jurnal"
                >
                  <td className="min-w-[200px] px-4 py-3.5">
                    <div className="flex items-center gap-3">
                      <Avatar name={s.full_name} />
                      <div className="min-w-0">
                        <p className="font-bold text-ink">
                          {s.full_name}
                          {!s.active && <span className="ml-2 bg-band px-1.5 py-0.5 text-[11px] font-bold text-muted">Dezactivat</span>}
                        </p>
                        <p className="text-[13px] text-muted">{s.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3.5 text-[14px]">{s.last_login_at ? timeAgo(s.last_login_at) : 'niciodată'}</td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center gap-3">
                      <span className="num w-8 text-right font-bold text-ink">{acts}</span>
                      <span className="h-2 w-20 shrink-0 bg-band" aria-hidden>
                        <span className="block h-full bg-orange" style={{ width: `${(acts / maxActs) * 100}%` }} />
                      </span>
                      {s.active && acts === 0 && (
                        <span className="inline-flex items-center gap-1 whitespace-nowrap text-[12px] font-bold text-danger">
                          <TriangleAlert size={13} aria-hidden /> Fără activitate
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="num px-4 py-3.5 text-right font-bold text-ink">{leads}</td>
                  <td className="num px-4 py-3.5 text-right">{working}</td>
                  <td className="num px-4 py-3.5 text-right">{w}</td>
                  <td className="min-w-[170px] px-4 py-3.5 text-[13px]">
                    {last ? (
                      <>
                        <p className="line-clamp-2 text-ink" title={last.label}>{last.label}</p>
                        <p className="text-muted">{timeAgo(last.t)}</p>
                      </>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-10 text-center text-muted">
                    Niciun sales manager încă.{' '}
                    <Link to="/account?tab=accounts" className="font-bold text-ink underline underline-offset-4">
                      Creează primul cont
                    </Link>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      <div ref={feedRef} className="scroll-mt-6">
        <Panel>
          <PanelTitle action={<span className="num text-[13px] text-muted">{feed.length} înregistrări</span>}>Jurnal de activitate</PanelTitle>
          <div className="flex flex-wrap gap-3 border-b border-line bg-canvas px-5 py-3">
            <select value={who} onChange={(e) => { setWho(e.target.value); setLimit(40) }} className="h-10" aria-label="Filtrează după persoană">
              <option value="">Toată echipa</option>
              {team.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.full_name}
                </option>
              ))}
            </select>
            <select value={cat} onChange={(e) => { setCat(e.target.value as ActivityCategory | ''); setLimit(40) }} className="h-10" aria-label="Filtrează după tip">
              <option value="">Toate acțiunile</option>
              {CATEGORIES.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
            {(who || cat) && (
              <button type="button" onClick={() => { setWho(''); setCat('') }} className="ml-auto font-bold underline underline-offset-4 hover:text-orange-ink">
                Resetează filtrele
              </button>
            )}
          </div>
          {shown.length === 0 ? (
            <p className="px-5 py-10 text-center text-muted">Nicio activitate pentru filtrele alese în această perioadă.</p>
          ) : (
            <ol>
              {shown.map((e, i) => {
                const newDay = i === 0 || dayKey(shown[i - 1].t) !== dayKey(e.t)
                const name = e.companyId ? companyName.get(e.companyId) : null
                return (
                  <li key={`${e.t}-${i}`}>
                    {newDay && <p className="bg-canvas px-5 py-2 text-[12px] font-bold uppercase tracking-wider text-muted first-letter:uppercase">{dayLabel(e.t)}</p>}
                    <div className="flex items-center gap-4 border-b border-line px-5 py-3">
                      <span className="num w-12 shrink-0 text-[13px] text-muted">{hhmm(e.t)}</span>
                      <Avatar name={e.seller} size={28} />
                      <p className="min-w-0 flex-1 text-[14px]">
                        {e.seller ? (
                          <>
                            <span className="font-bold">{e.seller}</span> <span className="text-ink-2">{e.label.charAt(0).toLowerCase() + e.label.slice(1)}</span>
                          </>
                        ) : (
                          <span className={e.alert ? 'font-bold text-danger' : 'text-ink-2'}>{e.label}</span>
                        )}
                        {e.companyId && (
                          <>
                            {' · '}
                            <Link to={`/leads/${e.companyId}`} className="font-bold underline underline-offset-2 hover:text-orange-ink">
                              {name ?? `compania #${e.companyId}`}
                            </Link>
                          </>
                        )}
                      </p>
                      <span className={`shrink-0 px-2 py-0.5 text-[11px] font-bold ${e.alert ? 'bg-danger-bg text-danger' : 'bg-band'}`}>
                        {e.alert ? 'Atenție' : CATEGORIES.find((c) => c.id === e.category)?.label}
                      </span>
                    </div>
                  </li>
                )
              })}
            </ol>
          )}
          {feed.length > limit && (
            <div className="p-4 text-center">
              <button type="button" onClick={() => setLimit(limit + 40)} className={btn('secondary', 'sm')}>
                Arată mai multe <ArrowRight size={14} aria-hidden />
              </button>
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
