import { ArrowDown, ChevronLeft, ChevronRight, Download, Kanban, Plus, Search } from 'lucide-react'
import { useMemo, useRef } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { STAGES, getCompanies, getServices, isNew, timeAgo, topSignal } from '../data/api'
import { OTHER_INDUSTRY, industryGroup } from '../data/industry'
import type { Company, ServiceId } from '../data/types'
import { Avatar, Button, NewBadge, PageHeader, ScoreDelta, ScoreMeter, ServiceTag, SourceIcon, StageTag, btn } from '../components/ui'

export const bestService = (c: Company) =>
  (Object.entries(c.serviceScores) as [ServiceId, number][]).sort((a, b) => b[1] - a[1])[0][0]

type SortKey = 'score' | 'updated' | 'name'

const PAGE_SIZES = [25, 50, 100]

const regionName = (() => {
  try {
    const names = new Intl.DisplayNames(['ro'], { type: 'region' })
    return (code: string) => names.of(code) ?? code
  } catch {
    return (code: string) => code
  }
})()

/** Page numbers around the current page, with gaps: 1 … 4 5 6 … 39. */
function pageList(current: number, total: number): (number | null)[] {
  const keep = new Set([1, total, current - 1, current, current + 1].filter((n) => n >= 1 && n <= total))
  const out: (number | null)[] = []
  let prev = 0
  for (const n of [...keep].sort((a, b) => a - b)) {
    if (n - prev === 2) out.push(n - 1)
    else if (n - prev > 2) out.push(null)
    out.push(n)
    prev = n
  }
  return out
}

export default function Leads() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const q = params.get('q') ?? ''
  const svc = params.get('svc') ?? ''
  const country = params.get('country') ?? ''
  const industry = params.get('ind') ?? ''
  const stage = params.get('stage') ?? ''
  const onlyNew = params.get('new') === '1'
  const showDisq = params.get('disq') === '1'
  const sort = (params.get('sort') as SortKey) ?? 'score'
  const size = PAGE_SIZES.includes(Number(params.get('size'))) ? Number(params.get('size')) : PAGE_SIZES[0]
  const tableTop = useRef<HTMLDivElement>(null)

  /** Any filter or sort change starts again from page 1. */
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next, { replace: true })
  }

  const all = getCompanies()

  const countries = useMemo(() => {
    const counts = new Map<string, { name: string; n: number }>()
    for (const c of all) {
      if (!c.country) continue
      const hit = counts.get(c.country)
      if (hit) hit.n++
      else counts.set(c.country, { name: c.countryName && c.countryName !== '—' ? c.countryName : regionName(c.country), n: 1 })
    }
    return [...counts.entries()].sort((a, b) => b[1].n - a[1].n || a[1].name.localeCompare(b[1].name, 'ro'))
  }, [all])

  const industries = useMemo(() => {
    const counts = new Map<string, number>()
    for (const c of all) {
      const group = industryGroup(c.industry)
      if (group) counts.set(group, (counts.get(group) ?? 0) + 1)
    }
    // Largest sectors first; "Altele" always last.
    return [...counts.entries()].sort((a, b) => Number(a[0] === OTHER_INDUSTRY) - Number(b[0] === OTHER_INDUSTRY) || b[1] - a[1])
  }, [all])

  const rows = useMemo(() => {
    const needle = q.toLowerCase()
    return all
      .filter((c) => showDisq || stage === 'descalificat' || c.stage !== 'descalificat')
      .filter((c) => !needle || [c.name, c.domain, c.industry].some((f) => f.toLowerCase().includes(needle)))
      .filter((c) => !svc || bestService(c) === svc)
      .filter((c) => !country || c.country === country)
      .filter((c) => !industry || industryGroup(c.industry) === industry)
      .filter((c) => !stage || c.stage === stage)
      .filter((c) => !onlyNew || isNew(c))
      .sort((a, b) =>
        sort === 'name' ? a.name.localeCompare(b.name) : sort === 'updated' ? b.updatedAt.localeCompare(a.updatedAt) : b.score - a.score,
      )
  }, [all, q, svc, country, industry, stage, onlyNew, showDisq, sort])

  const hot = rows.filter((c) => c.score >= 75).length
  const filtersOn = q || svc || country || industry || stage || onlyNew

  const pages = Math.max(1, Math.ceil(rows.length / size))
  const page = Math.min(Math.max(1, Number(params.get('page')) || 1), pages)
  const first = (page - 1) * size
  const shown = rows.slice(first, first + size)
  const goTo = (n: number) => {
    set('page', n > 1 ? String(n) : '')
    tableTop.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }

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
        <select value={industry} onChange={(e) => set('ind', e.target.value)} className="h-10 max-w-60" aria-label="Industrie">
          <option value="">Toate industriile</option>
          {industries.map(([name, n]) => (
            <option key={name} value={name}>
              {name} ({n})
            </option>
          ))}
        </select>
        <select value={country} onChange={(e) => set('country', e.target.value)} className="h-10 max-w-60" aria-label="Țară">
          <option value="">Toate țările</option>
          {countries.map(([code, { name, n }]) => (
            <option key={code} value={code}>
              {name} ({n})
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

      <div ref={tableTop} className="scroll-mt-4 overflow-x-auto border border-line bg-white">
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
            {shown.map((c) => {
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
                  <p className="mt-1 text-muted">Încearcă alt serviciu, altă industrie sau altă țară.</p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {rows.length > 0 && (
        <nav className="mt-4 flex flex-wrap items-center justify-between gap-4" aria-label="Paginare lead-uri">
          <p className="text-[14px] text-muted">
            <span className="num font-bold text-ink">
              {first + 1}–{first + shown.length}
            </span>{' '}
            din <span className="num font-bold text-ink">{rows.length}</span>
          </p>
          {pages > 1 && (
            <div className="flex items-center gap-1">
              <button type="button" onClick={() => goTo(page - 1)} disabled={page === 1} className={btn('secondary', 'sm')} aria-label="Pagina anterioară">
                <ChevronLeft size={16} aria-hidden />
              </button>
              {pageList(page, pages).map((n, i) =>
                n == null ? (
                  <span key={`gap-${i}`} className="px-1 text-muted" aria-hidden>
                    …
                  </span>
                ) : (
                  <button
                    key={n}
                    type="button"
                    onClick={() => goTo(n)}
                    aria-current={n === page ? 'page' : undefined}
                    className={`num h-8 min-w-8 border-2 px-2 text-[13px] font-bold transition-colors ${
                      n === page ? 'border-ink bg-ink text-white' : 'border-transparent hover:border-orange hover:text-orange-ink'
                    }`}
                  >
                    {n}
                  </button>
                ),
              )}
              <button type="button" onClick={() => goTo(page + 1)} disabled={page === pages} className={btn('secondary', 'sm')} aria-label="Pagina următoare">
                <ChevronRight size={16} aria-hidden />
              </button>
            </div>
          )}
          <label className="flex items-center gap-2 text-[14px] text-muted">
            Pe pagină
            <select value={size} onChange={(e) => set('size', e.target.value === String(PAGE_SIZES[0]) ? '' : e.target.value)} className="h-8 text-[13px] text-ink">
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </nav>
      )}
    </div>
  )
}
