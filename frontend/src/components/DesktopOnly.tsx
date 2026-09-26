import { Check, Copy, Monitor } from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'
import { LogoMark } from './Brand'

// The CRM is built for desktop screens (wide tables, pipeline board). Below this width a phone or a small tablet
// gets a notice instead of a broken layout.
const QUERY = '(max-width: 1023px)'
const SKIP_KEY = 'leadradar.mobileContinue'

function readSkip() {
  try {
    return sessionStorage.getItem(SKIP_KEY) === '1'
  } catch {
    return false
  }
}

export default function DesktopOnly({ children }: { children: ReactNode }) {
  const [small, setSmall] = useState(() => window.matchMedia(QUERY).matches)
  const [skip, setSkip] = useState(readSkip)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const mq = window.matchMedia(QUERY)
    const onChange = () => setSmall(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  if (!small || skip) return children

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.origin)
      setCopied(true)
    } catch {
      // clipboard blocked: the address is shown on screen anyway
    }
  }
  const proceed = () => {
    try {
      sessionStorage.setItem(SKIP_KEY, '1')
    } catch {
      // private mode: continue for this page view only
    }
    setSkip(true)
  }

  return (
    <div className="flex min-h-full flex-col bg-ink px-6 py-8 text-white">
      <div className="flex items-center gap-3">
        <LogoMark size={36} />
        <span className="leading-none">
          <span className="block text-[18px] font-bold">LeadRadar</span>
          <span className="mt-1 block text-[11px] font-bold text-orange">Orange Systems</span>
        </span>
      </div>

      <main className="flex flex-1 flex-col justify-center py-10">
        <span className="flex size-16 items-center justify-center bg-orange text-ink">
          <Monitor size={32} strokeWidth={2.25} aria-hidden />
        </span>
        <h1 className="mt-8 text-[34px] leading-[1.08] tracking-[-0.02em]">
          LeadRadar se folosește <span className="text-orange">pe computer.</span>
        </h1>
        <p className="mt-4 max-w-md text-[17px] leading-relaxed text-white/75">
          Aplicația este gândită pentru ecrane de desktop: tabele largi cu lead-uri, pipeline-ul pe coloane și fișele companiilor
          cu toate semnalele. Deschide-o de pe un laptop sau un calculator.
        </p>

        <div className="mt-8 max-w-md border border-white/15 bg-white/5 p-4">
          <p className="text-[12px] font-bold uppercase tracking-wider text-white/50">Adresa aplicației</p>
          <p className="mt-1 break-all text-[16px] font-bold">{window.location.host}</p>
          <button
            type="button"
            onClick={() => void copy()}
            className="mt-4 flex h-11 w-full items-center justify-center gap-2 border-2 border-orange bg-orange font-bold text-ink"
          >
            {copied ? <Check size={17} aria-hidden /> : <Copy size={17} aria-hidden />}
            {copied ? 'Link copiat' : 'Copiază linkul'}
          </button>
        </div>
      </main>

      <footer className="flex flex-col gap-3 text-[13px] text-white/50">
        <button type="button" onClick={proceed} className="self-start underline underline-offset-4 hover:text-white">
          Continuă oricum pe acest ecran
        </button>
        <p>© 2026 Orange Systems · Gigahack</p>
      </footer>
    </div>
  )
}
