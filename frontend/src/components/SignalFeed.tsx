import { useEffect, useMemo, useState } from 'react'
import { getRecentSignals, timeAgo } from '../data/api'
import { SourceIcon, serviceColor } from './ui'

const CARD_H = 88
const GAP = 12
const VISIBLE = 3
const STEP_MS = 2800
const SLIDE_MS = 650

/** A looping feed of signal cards: every few seconds a new one slides in at the top. */
export default function SignalFeed() {
  const items = useMemo(() => {
    const seen = new Set<string>()
    return getRecentSignals(40).filter((s) => !seen.has(s.company.id) && seen.add(s.company.id)).slice(0, 8)
  }, [])
  const reduce = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const [head, setHead] = useState(0)
  const [sliding, setSliding] = useState(false)

  useEffect(() => {
    if (reduce || items.length <= VISIBLE) return
    let settle: ReturnType<typeof setTimeout>
    const tick = setInterval(() => {
      setSliding(true)
      settle = setTimeout(() => {
        setHead((h) => (h - 1 + items.length) % items.length)
        setSliding(false)
      }, SLIDE_MS)
    }, STEP_MS)
    return () => {
      clearInterval(tick)
      clearTimeout(settle)
    }
  }, [items.length, reduce])

  if (!items.length) return null
  // one extra card above the window slides in; the last one slides out under the fade
  const shown = Array.from({ length: VISIBLE + 1 }, (_, i) => items[(head - 1 + i + items.length) % items.length])
  const step = CARD_H + GAP

  return (
    <div>
      <p className="mb-4 flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.18em] text-white/70">
        <span className="blip size-2 bg-orange" aria-hidden />
        Radar activ · semnale noi
      </p>
      <div
        className="relative overflow-hidden"
        style={{
          height: VISIBLE * CARD_H + (VISIBLE - 1) * GAP,
          maskImage: 'linear-gradient(180deg, #000 70%, transparent 100%)',
          WebkitMaskImage: 'linear-gradient(180deg, #000 70%, transparent 100%)',
        }}
        aria-live="off"
      >
        <ul
          style={{
            transform: `translateY(${sliding ? 0 : -step}px)`,
            transition: sliding ? `transform ${SLIDE_MS}ms cubic-bezier(0.22, 1, 0.36, 1)` : 'none',
          }}
        >
          {shown.map((s, i) => (
            <li
              key={`${s.id}-${head}-${i}`}
              className={`flex items-center gap-4 border px-4 backdrop-blur-md ${i === 1 && !sliding ? 'border-orange/70' : 'border-white/12'}`}
              style={{
                height: CARD_H,
                marginBottom: GAP,
                background: i === 1 && !sliding ? 'rgba(255,121,0,0.12)' : 'rgba(10,10,11,0.55)',
                opacity: i === 0 && !sliding ? 0 : 1,
                transition: 'opacity 400ms ease, background 600ms ease, border-color 600ms ease',
              }}
            >
              <span className="relative flex size-10 shrink-0 items-center justify-center bg-white/10 text-white">
                <SourceIcon type={s.sourceType} size={18} />
                {s.service && <span className="absolute -bottom-1 -right-1 size-3" style={{ background: serviceColor(s.service) }} aria-hidden />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[15px] font-bold text-white">{s.company.name}</p>
                <p className="truncate text-[14px] text-white/80">{s.title}</p>
                <p className="truncate text-[12px] text-white/50">
                  {s.source} · {timeAgo(s.date)}
                </p>
              </div>
              <span className="num shrink-0 bg-orange px-2 py-1 text-[13px] font-bold text-ink">+{s.points}</span>
            </li>
          ))}
        </ul>
      </div>
      <p className="mt-2 text-[11px] text-white/40">Exemple cu date demo.</p>
    </div>
  )
}
