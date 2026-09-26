import { Table2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { friendlyError } from '../auth/session'
import { STAGES, bestService, getCompanies, patchCompany, signalHeadline, topSignal, useDataVersion } from '../data/api'
import { saveAssignment } from '../data/backend'
import type { Stage } from '../data/types'
import { Avatar, PageHeader, ScoreMeter, ServiceTag, btn } from '../components/ui'

const COLUMNS = STAGES.filter((s) => s.id !== 'descalificat')

/** Drops a pending move once the server has answered (saved or refused). */
const forget = (id: string) => (moved: Record<string, Stage>) => {
  const next = { ...moved }
  delete next[id]
  return next
}

export default function Pipeline() {
  useDataVersion()
  // Stages moved here and not yet confirmed by the server; everything else comes from the (auto-refreshed) data.
  const [moved, setMoved] = useState<Record<string, Stage>>({})
  const all = getCompanies()
  const stages: Record<string, Stage> = Object.fromEntries(all.map((c) => [c.id, moved[c.id] ?? c.stage]))
  const [dragId, setDragId] = useState<string | null>(null)
  const [over, setOver] = useState<Stage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const companies = all.filter((c) => stages[c.id] !== 'descalificat')

  const drop = (stage: Stage) => {
    const id = dragId
    setDragId(null)
    setOver(null)
    if (!id || stages[id] === stage) return
    setMoved((s) => ({ ...s, [id]: stage }))
    saveAssignment(id, { stage })
      .then(() => {
        patchCompany(id, { stage })
        setMoved(forget(id))
        setError(null)
      })
      .catch((err: unknown) => {
        setMoved(forget(id))
        setError(`Nu am putut salva stadiul: ${friendlyError(err)}`)
      })
  }

  return (
    <div className="rise">
      <PageHeader
        title="Pipeline"
        subtitle="Trage cardurile între coloane pentru a schimba stadiul. Se salvează pentru toată echipa."
        actions={
          <Link to="/leads" className={btn('ghost')}>
            <Table2 size={16} aria-hidden /> Vizualizare tabel
          </Link>
        }
      />
      {error && <p className="mb-3 bg-danger-bg px-3 py-2 font-bold text-danger" role="alert">{error}</p>}
      <div className="grid min-w-[1000px] grid-cols-5 gap-3 overflow-x-auto pb-4">
        {COLUMNS.map((col) => {
          const items = companies.filter((c) => stages[c.id] === col.id).sort((a, b) => b.score - a.score)
          return (
            <section
              key={col.id}
              onDragOver={(e) => {
                e.preventDefault()
                setOver(col.id)
              }}
              onDragLeave={() => setOver(null)}
              onDrop={() => drop(col.id)}
              className={`flex min-h-[60vh] flex-col bg-band transition-colors ${over === col.id ? 'outline-2 outline-dashed outline-orange' : ''}`}
              aria-label={col.label}
            >
              <header className={`flex items-center justify-between border-b-4 px-3 py-3 ${col.id === 'nou' ? 'border-orange' : 'border-ink'}`}>
                <h2 className="text-[14px]">{col.label}</h2>
                <span className="num bg-white px-1.5 text-[12px] font-bold">{items.length}</span>
              </header>
              <div className="flex-1 space-y-2 p-2">
                {items.map((c) => {
                  const sig = topSignal(c)
                  return (
                    <Link
                      key={c.id}
                      to={`/leads/${c.id}`}
                      draggable
                      onDragStart={() => setDragId(c.id)}
                      onDragEnd={() => setDragId(null)}
                      className={`block border border-line bg-white p-3 transition-shadow hover:border-ink ${dragId === c.id ? 'opacity-40' : ''}`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="font-bold leading-snug">{c.name}</p>
                        <span className="num text-[18px] font-bold leading-none">{c.score}</span>
                      </div>
                      <div className="mt-2">
                        <ScoreMeter score={c.score} size="sm" />
                      </div>
                      {sig && <p className="mt-2 line-clamp-2 text-[12px] leading-snug text-muted">{signalHeadline(sig)}</p>}
                      <div className="mt-3 flex items-center justify-between">
                        {(() => {
                          const b = bestService(c)
                          return b ? <ServiceTag id={b} className="!text-[12px]" /> : <span />
                        })()}
                        <Avatar name={c.owner} size={22} />
                      </div>
                    </Link>
                  )
                })}
                {items.length === 0 && <p className="p-3 text-center text-[13px] text-muted">Niciun lead</p>}
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
