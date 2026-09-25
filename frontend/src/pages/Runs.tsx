import { CircleCheck, CircleX, RefreshCw, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { getSources, timeAgo } from '../data/api'
import type { RefreshTier, SourceStatus } from '../data/types'
import { Button, PageHeader } from '../components/ui'

const TIERS: Record<RefreshTier, [string, string]> = {
  stream: ['Stream', 'în timp real'],
  rss: ['Feed RSS', 'la 5–15 min'],
  incremental: ['Incremental', 'la fiecare oră'],
  snapshot: ['Comparare liste', 'la 1–6 ore'],
  daily: ['Zilnic', 'o dată pe zi'],
}

const STATUS: Record<SourceStatus['status'], [typeof CircleCheck, string, string]> = {
  ok: [CircleCheck, 'Funcționează', 'text-ok'],
  warn: [TriangleAlert, 'Atenție', 'text-ink'],
  error: [CircleX, 'Eroare', 'text-danger'],
}

export default function Runs() {
  const [sources, setSources] = useState(getSources)
  const [running, setRunning] = useState(false)

  const runNow = () => {
    setRunning(true)
    setTimeout(() => {
      const now = new Date().toISOString()
      setSources((list) => list.map((s) => (s.status === 'error' ? s : { ...s, lastRun: now })))
      setRunning(false)
    }, 2200)
  }

  const totalNew = sources.reduce((a, s) => a + s.newItems, 0)

  return (
    <div className="rise">
      <PageHeader
        title="Surse și rulări"
        subtitle={
          <>
            <span className="num font-bold text-ink">{sources.length}</span> surse publice ·{' '}
            <span className="num font-bold text-ink">{totalNew}</span> documente noi la ultima rulare · doar documentele noi ajung la AI
          </>
        }
        actions={
          <Button variant="primary" onClick={runNow} disabled={running}>
            <RefreshCw size={16} className={running ? 'animate-spin' : ''} aria-hidden />
            {running ? 'Se rulează…' : 'Rulează acum'}
          </Button>
        }
      />

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
        {(Object.keys(TIERS) as RefreshTier[]).map((t) => (
          <div key={t} className="border border-line bg-white p-4">
            <p className="font-bold">{TIERS[t][0]}</p>
            <p className="text-[13px] text-muted">{TIERS[t][1]}</p>
            <p className="num mt-2 text-[24px] font-bold leading-none">{sources.filter((s) => s.tier === t).length}</p>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto border border-line bg-white">
        <table className="w-full min-w-[800px] border-collapse">
          <thead className="border-b-2 border-ink text-left text-[13px]">
            <tr>
              <th className="px-4 py-3">Sursă</th>
              <th className="px-4 py-3">Categorie</th>
              <th className="px-4 py-3">Actualizare</th>
              <th className="px-4 py-3">Ultima rulare</th>
              <th className="px-4 py-3 text-right">Noi</th>
              <th className="px-4 py-3">Stare</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => {
              const [Icon, label, color] = STATUS[s.status]
              return (
                <tr key={s.id} className="border-b border-line align-top last:border-0">
                  <td className="px-4 py-3.5 font-bold">{s.name}</td>
                  <td className="px-4 py-3.5 text-muted">{s.category}</td>
                  <td className="px-4 py-3.5">
                    {TIERS[s.tier][0]} <span className="text-[13px] text-muted">· {TIERS[s.tier][1]}</span>
                  </td>
                  <td className="num px-4 py-3.5 text-muted">{running && s.status !== 'error' ? 'se rulează…' : timeAgo(s.lastRun)}</td>
                  <td className="num px-4 py-3.5 text-right font-bold">{s.newItems}</td>
                  <td className="px-4 py-3.5">
                    <span className={`inline-flex items-center gap-1.5 font-bold ${color}`}>
                      <Icon size={16} aria-hidden className={s.status === 'warn' ? 'fill-warn' : ''} /> {label}
                    </span>
                    {s.note && <p className="mt-0.5 text-[12px] text-muted">{s.note}</p>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
