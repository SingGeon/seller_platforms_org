import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router'
import { useSession } from '../auth/session'
import { getCompanies, getRecentSignals, getServices, getSources, isNew, timeAgo } from '../data/api'
import type { ServiceId } from '../data/types'
import { Panel, PanelTitle, ScoreDelta, ScoreMeter, ServiceTag, SourceIcon, btn, serviceColor } from '../components/ui'
import { bestService } from './Leads'

function StatTile({ label, value, note, to }: { label: string; value: number | string; note: string; to: string }) {
  return (
    <Link to={to} className="group block border border-line bg-white p-5 transition-colors hover:border-ink">
      <p className="flex items-center gap-2 text-[13px] font-bold text-muted">
        <span className="size-2 bg-orange" aria-hidden />
        {label}
      </p>
      <p className="mt-3 text-[40px] font-bold leading-none">{value}</p>
      <p className="mt-2 flex items-center gap-1 text-[13px] text-muted group-hover:text-ink">
        {note} <ArrowRight size={13} aria-hidden />
      </p>
    </Link>
  )
}

export default function Home() {
  const { seller } = useSession()
  const firstName = seller?.full_name.split(' ')[0]
  const companies = getCompanies()
  const active = companies.filter((c) => c.stage !== 'descalificat')
  const hot = active.filter((c) => c.score >= 75)
  const fresh = companies.filter(isNew)
  const signals24 = companies.flatMap((c) => c.signals).filter((s) => Date.now() - new Date(s.date).getTime() < 24 * 3600_000)
  const sources = getSources()
  const recent = getRecentSignals(7)
  const top = [...active].sort((a, b) => b.score - a.score).slice(0, 5)
  const perService = getServices().map((s) => ({ ...s, count: active.filter((c) => bestService(c) === s.id).length }))
  const maxCount = Math.max(...perService.map((s) => s.count))
  const today = new Date().toLocaleDateString('ro-RO', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div className="rise">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[13px] font-bold text-muted first-letter:uppercase">{today}</p>
          <h1 className="mt-1 text-[32px] leading-none">Bună ziua{firstName ? `, ${firstName}` : ''}</h1>
          <p className="mt-2 text-muted">
            Ai <span className="font-bold text-ink">{hot.filter((c) => !c.owner).length} lead-uri fierbinți neasignate</span> de preluat azi.
          </p>
        </div>
        <Link to="/leads?new=1" className={btn('primary')}>
          Vezi lead-urile noi <ArrowRight size={16} aria-hidden />
        </Link>
      </div>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Lead-uri noi (72h)" value={fresh.length} note="descoperite automat" to="/leads?new=1" />
        <StatTile label="Lead-uri fierbinți" value={hot.length} note="scor 75 sau mai mare" to="/leads" />
        <StatTile label="Semnale noi (24h)" value={signals24.length} note="din toate sursele" to="/leads?sort=updated" />
        <StatTile
          label="Surse active"
          value={`${sources.filter((s) => s.status === 'ok').length}/${sources.length}`}
          note="vezi starea surselor"
          to="/runs"
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <Panel>
          <PanelTitle
            action={
              <Link to="/leads?sort=updated" className="text-[13px] font-bold underline underline-offset-4 hover:text-orange-ink">
                Toate
              </Link>
            }
          >
            Semnale proaspete
          </PanelTitle>
          <ul>
            {recent.map((s) => (
              <li key={s.id} className="border-b border-line last:border-0">
                <Link to={`/leads/${s.company.id}`} className="flex gap-4 px-5 py-4 transition-colors hover:bg-orange-wash">
                  <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center bg-canvas">
                    <SourceIcon type={s.sourceType} size={17} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-bold leading-snug">{s.title}</p>
                    <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
                      <span className="font-bold text-ink">{s.company.name}</span>
                      {s.service && <ServiceTag id={s.service as ServiceId} className="!text-[12px] !font-normal" />}
                      <span>
                        {s.source} · {timeAgo(s.date)}
                      </span>
                    </p>
                  </div>
                  <span className="num h-fit shrink-0 bg-orange-wash px-2 py-1 text-[13px] font-bold">+{s.points}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>

        <div className="space-y-6">
          <Panel>
            <PanelTitle>De contactat primele</PanelTitle>
            <ol>
              {top.map((c, i) => (
                <li key={c.id} className="border-b border-line last:border-0">
                  <Link to={`/leads/${c.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-orange-wash">
                    <span className="num w-4 text-[13px] font-bold text-muted">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-bold">{c.name}</p>
                      <div className="mt-1">
                        <ScoreMeter score={c.score} size="sm" />
                      </div>
                    </div>
                    <span className="text-right">
                      <span className="num block text-[20px] font-bold leading-none">{c.score}</span>
                      <ScoreDelta score={c.score} prev={c.prevScore} />
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          </Panel>

          <Panel>
            <PanelTitle>Lead-uri pe servicii</PanelTitle>
            <ul className="space-y-4 p-5">
              {perService.map((s) => (
                <li key={s.id}>
                  <Link to={`/leads?svc=${s.id}`} className="block hover:opacity-80">
                    <div className="mb-1.5 flex items-center justify-between">
                      <ServiceTag id={s.id} />
                      <span className="num font-bold">{s.count}</span>
                    </div>
                    <div className="h-2 bg-band" aria-hidden>
                      <div className="h-full" style={{ width: `${(s.count / maxCount) * 100}%`, background: serviceColor(s.id) }} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  )
}
