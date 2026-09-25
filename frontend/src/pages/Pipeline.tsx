import { Table2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { STAGES, getCompanies, topSignal } from '../data/api'
import type { Stage } from '../data/types'
import { Avatar, PageHeader, ScoreMeter, ServiceTag, btn } from '../components/ui'
import { bestService } from './Leads'

const COLUMNS = STAGES.filter((s) => s.id !== 'descalificat')

export default function Pipeline() {
  const [stages, setStages] = useState<Record<string, Stage>>(() =>
    Object.fromEntries(getCompanies().map((c) => [c.id, c.stage])),
  )
  const [dragId, setDragId] = useState<string | null>(null)
  const [over, setOver] = useState<Stage | null>(null)
  const companies = getCompanies().filter((c) => stages[c.id] !== 'descalificat')

  const drop = (stage: Stage) => {
    if (dragId) setStages((s) => ({ ...s, [dragId]: stage }))
    setDragId(null)
    setOver(null)
  }

  return (
    <div className="rise">
      <PageHeader
        title="Pipeline"
        subtitle="Trage cardurile între coloane pentru a schimba stadiul."
        actions={
          <Link to="/leads" className={btn('ghost')}>
            <Table2 size={16} aria-hidden /> Vizualizare tabel
          </Link>
        }
      />
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
                      {sig && <p className="mt-2 line-clamp-2 text-[12px] leading-snug text-muted">{sig.title}</p>}
                      <div className="mt-3 flex items-center justify-between">
                        <ServiceTag id={bestService(c)} className="!text-[12px]" />
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
