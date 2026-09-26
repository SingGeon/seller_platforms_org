import { Check, ChevronDown, Search } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'

export interface MultiOption {
  value: string
  label: string
  count?: number
}

/**
 * A dropdown where several options can be ticked. Nothing ticked means "all" (the placeholder).
 * Long lists get a search box; Escape or a click outside closes it.
 */
export default function MultiSelect({
  label,
  allLabel,
  noun,
  options,
  value,
  onChange,
  searchable = options.length > 8,
  className = '',
}: {
  /** Accessible name, e.g. "Serviciu". */
  label: string
  /** Shown when nothing is ticked, e.g. "Toate serviciile". */
  allLabel: string
  /** Plural used for 2+ ticked options, e.g. "servicii" → "3 servicii". */
  noun: string
  options: MultiOption[]
  value: string[]
  onChange: (next: string[]) => void
  searchable?: boolean
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [needle, setNeedle] = useState('')
  const root = useRef<HTMLDivElement>(null)
  const listId = useId()

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const chosen = options.filter((o) => value.includes(o.value))
  const summary = chosen.length === 0 ? allLabel : chosen.length === 1 ? chosen[0].label : `${chosen.length} ${noun}`
  const visible = needle ? options.filter((o) => o.label.toLowerCase().includes(needle.toLowerCase())) : options
  const toggle = (v: string) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v])

  return (
    <div ref={root} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={`${label}: ${summary}`}
        className={`flex h-10 w-full items-center gap-2 border-2 bg-white pl-3 pr-2.5 text-left ${
          open ? 'border-ink' : chosen.length ? 'border-ink' : 'border-line'
        }`}
      >
        <span className={`min-w-0 flex-1 truncate ${chosen.length ? 'font-bold' : ''}`}>{summary}</span>
        {chosen.length > 1 && <span className="num bg-orange px-1.5 text-[12px] font-bold text-ink">{chosen.length}</span>}
        <ChevronDown size={16} strokeWidth={2.5} className={`shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-max min-w-full max-w-[340px] border-2 border-ink bg-white shadow-[0_12px_40px_rgba(0,0,0,0.18)]">
          {searchable && (
            <div className="relative border-b border-line p-2">
              <Search size={15} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
              <input
                autoFocus
                value={needle}
                onChange={(e) => setNeedle(e.target.value)}
                placeholder="Caută în listă…"
                aria-label={`Caută ${noun}`}
                className="h-9 w-full pl-8 text-[14px]"
              />
            </div>
          )}
          <ul id={listId} role="listbox" aria-multiselectable="true" aria-label={label} className="max-h-72 overflow-y-auto py-1">
            {visible.map((o) => {
              const on = value.includes(o.value)
              return (
                <li key={o.value} role="option" aria-selected={on}>
                  <label className="flex cursor-pointer items-center gap-3 px-3 py-2 text-[14px] hover:bg-orange-wash">
                    <input type="checkbox" checked={on} onChange={() => toggle(o.value)} className="sr-only" />
                    <span
                      className={`flex size-[18px] shrink-0 items-center justify-center border-2 ${on ? 'border-ink bg-ink text-white' : 'border-faint bg-white'}`}
                      aria-hidden
                    >
                      {on && <Check size={13} strokeWidth={3.5} />}
                    </span>
                    <span className={`flex-1 ${on ? 'font-bold' : ''}`}>{o.label}</span>
                    {o.count != null && <span className="num text-[12px] text-muted">{o.count}</span>}
                  </label>
                </li>
              )
            })}
            {visible.length === 0 && <li className="px-3 py-3 text-[14px] text-muted">Nimic găsit.</li>}
          </ul>
          <div className="flex items-center justify-between gap-4 border-t border-line px-3 py-2 text-[13px]">
            <button type="button" onClick={() => onChange([])} disabled={!value.length} className="font-bold underline underline-offset-4 disabled:text-faint disabled:no-underline">
              Șterge selecția
            </button>
            <button type="button" onClick={() => setOpen(false)} className="font-bold hover:text-orange-ink">
              Gata
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
