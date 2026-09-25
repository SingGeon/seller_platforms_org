import { ArrowDown, Download, Kanban, Plus, Search } from 'lucide-react'
import { useMemo } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { STAGES, getCompanies, getServices, isNew, timeAgo, topSignal } from '../data/api'
import type { Company, ServiceId } from '../data/types'
import { Avatar, Button, NewBadge, PageHeader, ScoreDelta, ScoreMeter, ServiceTag, SourceIcon, StageTag, btn } from '../components/ui'

export const bestService = (c: Company) =>
  (Object.entries(c.serviceScores) as [ServiceId, number][]).sort((a, b) => b[1] - a[1])[0][0]

type SortKey = 'score' | 'updated' | 'name'

export default function Leads() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const q = params.get('q') ?? ''
  const svc = params.get('svc') ?? ''
  const country = params.get('country') ?? ''
  const stage = params.get('stage') ?? ''
  const onlyNew = params.get('new') === '1'
  const showDisq = params.get('disq') === '1'
  const sort = (params.get('sort') as SortKey) ?? 'score'

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  const all = getCompanies()
  const countries = [...new Map(all.map((c) => [c.country, c.countryName])).entries()]

  const rows = useMemo(() => {
    const needle = q.toLowerCase()
    return all
      .filter((c) => showDisq || stage === 'descalificat' || c.stage !== 'descalificat')
      .filter((c) => !needle || [c.name, c.domain, c.industry].some((f) => f.toLowerCase().includes(needle)))
      .filter((c) => !svc || bestService(c) === svc)
      .filter((c) => !country || c.country === country)
      .filter((c) => !stage || c.stage === stage)
      .filter((c) => !onlyNew || isNew(c))
      .sort((a, b) =>
        sort === 'name' ? a.name.localeCompare(b.name) : sort === 'updated' ? b.updatedAt.localeCompare(a.updatedAt) : b.score - a.score,
      )
  }, [all, q, svc, country, stage, onlyNew, showDisq, sort])

  const hot = rows.filter((c) => c.score >= 75).length
  const filtersOn = q || svc || country || stage || onlyNew

  const exportCsv = () => {
    const head = 'Companie,Domeniu,Industrie,Țară,Scor,Stadiu,Serviciu potrivit,Semnal principal'
    const body = rows.map((c) =>
      [c.name, c.domain, c.industry, c.countryName, c.score, c.stage, bestService(c), topSignal(c)?.title ?? '']
        .map((v) => `"${String(v).replace(/"/g, '""')}"`)
        .join(','),
    )
    const blob = new Blob(['﻿' + [head, ...body].join('\n')], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'leadradar-leaduri.csv'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const sortHead = (k: SortKey, children: string, className = '') => (
    <th key={k} className={`px-4 py-3 text-left ${className}`} aria-sort={sort === k ? 'descending' : 'none'}>
      <button type="button" onClick={() => set('sort', k === 'score' ? '' : k)} className="inline-flex items-center gap-1 font-bold hover:text-orange-ink">
        {children}
        {sort === k && <ArrowDown size={13} strokeWidth={3} aria-hidden />}
      </button>
    </th>
  )

  return (
    <div className="rise">
      <PageHeader
        title="Lead-uri"
        subtitle={
          <>
            <span className="num font-bold text-ink">{rows.length}</span> companii · <span className="num font-bold text-ink">{hot}</span> fierbinți
            (scor ≥ 75)
          </>
        }
        actions={
          <>
            <Link to="/pipeline" className={btn('ghost')}>
              <Kanban size={16} aria-hidden /> Pipeline
            </Link>
            <Button onClick={exportCsv}>
              <Download size={16} aria-hidden /> Export CSV
            </Button>
            <Button variant="primary">
              <Plus size={16} aria-hidden /> Adaugă companie
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3 bg-band p-3">
        <div className="relative min-w-60 flex-1">
          <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
          <input
            value={q}
            onChange={(e) => set('q', e.target.value)}
            placeholder="Filtrează după nume, domeniu, industrie"
            aria-label="Filtrează lead-urile"
            className="h-10 w-full pl-9"
          />
        </div>
        <select value={svc} onChange={(e) => set('svc', e.target.value)} className="h-10" aria-label="Serviciu">
          <option value="">Toate serviciile</option>
          {getServices().map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <select value={country} onChange={(e) => set('country', e.target.value)} className="h-10" aria-label="Țară">
          <option value="">Toate țările</option>
          {countries.map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </select>
        <select value={stage} onChange={(e) => set('stage', e.target.value)} className="h-10" aria-label="Stadiu">
          <option value="">Toate stadiile</option>
          {STAGES.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
        <label className="flex h-10 cursor-pointer items-center gap-2 border-2 border-line bg-white px-3 font-bold">
          <input type="checkbox" checked={onlyNew} onChange={(e) => set('new', e.target.checked ? '1' : '')} className="size-4 accent-orange" />
          Doar noi (72h)
        </label>
        <label className="flex h-10 cursor-pointer items-center gap-2 px-1 text-muted">
          <input type="checkbox" checked={showDisq} onChange={(e) => set('disq', e.target.checked ? '1' : '')} className="size-4 accent-orange" />
          Arată descalificați
        </label>
        {filtersOn && (
          <button type="button" onClick={() => setParams({}, { replace: true })} className="ml-auto font-bold underline underline-offset-4 hover:text-orange-ink">
            Resetează filtrele
          </button>
        )}
      </div>

      <div className="overflow-x-auto border border-line bg-white">
        <table className="w-full min-w-[1000px] border-collapse text-[14px]">
          <thead className="sticky top-0 border-b-2 border-ink bg-white text-[13px]">
            <tr>
              {sortHead('name', 'Companie', 'w-[26%]')}
              {sortHead('score', 'Scor', 'w-[150px]')}
              <th className="px-4 py-3 text-left font-bold">Potrivire</th>
              <th className="px-4 py-3 text-left font-bold">Semnal principal</th>
              <th className="px-4 py-3 text-left font-bold">Stadiu</th>
              <th className="px-4 py-3 text-left font-bold">Resp.</th>
              {sortHead('updated', 'Actualizat')}
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => {
              const sig = topSignal(c)
              const disq = c.stage === 'descalificat'
              return (
                <tr
                  key={c.id}
                  onClick={() => navigate(`/leads/${c.id}`)}
                  className={`cursor-pointer border-b border-line align-top transition-colors hover:bg-orange-wash ${disq ? 'text-muted' : ''}`}
                >
                  <td className="px-4 py-3.5">
                    <div className="flex items-center gap-2">
                      <Link to={`/leads/${c.id}`} onClick={(e) => e.stopPropagation()} className="font-bold text-ink hover:underline">
                        {c.name}
                      </Link>
                      {isNew(c) && <NewBadge />}
                    </div>
                    <div className="mt-0.5 text-[12px] text-muted">
                      {c.industry} · {c.countryName} · {c.employees} ang.
                    </div>
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center gap-2">
                      <span className="num w-7 text-[18px] font-bold leading-none text-ink">{c.score}</span>
                      <ScoreDelta score={c.score} prev={c.prevScore} />
                    </div>
                    <div className="mt-1.5">
                      <ScoreMeter score={c.score} size="sm" />
                    </div>
                  </td>
                  <td className="px-4 py-3.5">{disq ? <span className="text-[13px]">—</span> : <ServiceTag id={bestService(c)} />}</td>
                  <td className="max-w-[340px] px-4 py-3.5">
                    {sig && (
                      <div className="flex gap-2">
                        <span className="mt-0.5 text-muted">
                          <SourceIcon type={sig.sourceType} />
                        </span>
                        <div className="min-w-0">
                          <p className="line-clamp-2 leading-snug">{sig.title}</p>
                          <p className="mt-0.5 text-[12px] text-muted">
                            {sig.source} · {timeAgo(sig.date)}
                            {c.signals.length > 1 && ` · +${c.signals.length - 1} semnale`}
                          </p>
                        </div>
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3.5">
                    <StageTag stage={c.stage} />
                  </td>
                  <td className="px-4 py-3.5">
                    <Avatar name={c.owner} />
                  </td>
                  <td className="num whitespace-nowrap px-4 py-3.5 text-[13px] text-muted">{timeAgo(c.updatedAt)}</td>
                </tr>
              )
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-16 text-center">
                  <p className="text-[18px] font-bold">Niciun lead pentru filtrele alese</p>
                  <p className="mt-1 text-muted">Încearcă alt serviciu sau altă țară.</p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
