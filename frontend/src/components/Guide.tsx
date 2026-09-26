import { ArrowLeft, ArrowRight, FileSearch, Filter, Hand, LayoutDashboard, Radar, Send, ShieldCheck, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { useSession } from '../auth/session'

// A short first-run guide for sales managers who are not AI experts. It opens once per account (remembered in this
// browser) and again from the "?" button in the header or the account menu.
const OPEN_EVENT = 'leadradar:guide'
const seenKey = (id: number) => `leadradar.guideSeen.${id}`

export const openGuide = () => window.dispatchEvent(new Event(OPEN_EVENT))

interface Step {
  icon: typeof Radar
  title: string
  text: string
  to?: string
  cta?: string
}

const STEPS: Step[] = [
  {
    icon: Radar,
    title: 'Bun venit în LeadRadar',
    text:
      'LeadRadar citește zilnic știri, presa de business și registre publice și îți arată companiile care au acum nevoie de serviciile Orange Systems. Tu decizi pe cine suni; aplicația îți spune de ce.',
  },
  {
    icon: LayoutDashboard,
    title: 'Acasă: ce e nou azi',
    text:
      'Vezi lead-urile noi, pe cele fierbinți (scor 75 sau mai mare), semnalele din ultimele 24 de ore și impactul adus echipei. Începe ziua de aici.',
    to: '/',
    cta: 'Deschide Acasă',
  },
  {
    icon: Filter,
    title: 'Lead-uri: găsește-i pe ai tăi',
    text:
      'Filtrează după serviciu, industrie, țară și stadiu (poți bifa mai multe), apoi apasă „Aplică filtrele”. Lista e ordonată după scor: cele de sus merită sunate primele.',
    to: '/leads',
    cta: 'Deschide Lead-uri',
  },
  {
    icon: FileSearch,
    title: 'Fișa companiei: de ce acum',
    text:
      'Scorul 0–100 are o explicație: „De ce acest lead, acum?” și fiecare semnal cu fraza din articol și linkul sursei. Deschide sursa înainte de a contacta compania.',
  },
  {
    icon: Hand,
    title: 'Preia lead-ul',
    text:
      'Apasă „Preia lead-ul” sau alege stadiul „Calificat” și devii responsabilul lui. Lead-ul apare în Pipeline, iar colegii văd schimbarea în câteva secunde.',
    to: '/pipeline',
    cta: 'Deschide Pipeline',
  },
  {
    icon: Send,
    title: 'Mesajul de contact',
    text:
      'În fișa companiei, tab-ul „Mesaj de contact” scrie un email sau un mesaj LinkedIn pornind de la semnalele companiei, în română, engleză sau germană. Verifică-l, copiază-l și trimite-l din contul tău.',
  },
]

const ADMIN_STEP: Step = {
  icon: ShieldCheck,
  title: 'Pentru administrator',
  text:
    'Din „Monitorizare echipă” vezi activitatea sales managerilor, din „Conturi sales manageri” creezi conturi, iar din „Configurare” schimbi întrebările-semnal, regulile și profilul clientului ideal.',
  to: '/admin',
  cta: 'Deschide Monitorizare',
}

export default function Guide() {
  const { seller } = useSession()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [i, setI] = useState(0)
  const next = useRef<HTMLButtonElement>(null)
  const steps = seller?.role === 'admin' ? [...STEPS, ADMIN_STEP] : STEPS

  const close = useCallback(() => {
    if (seller) {
      try {
        localStorage.setItem(seenKey(seller.id), '1')
      } catch {
        // ignore: it will simply open again next time
      }
    }
    setOpen(false)
  }, [seller])

  // First login of this account in this browser: open once.
  useEffect(() => {
    if (!seller) return
    try {
      if (!localStorage.getItem(seenKey(seller.id))) setOpen(true)
    } catch {
      // storage blocked: the guide stays available from the "?" button
    }
  }, [seller])

  useEffect(() => {
    const show = () => {
      setI(0)
      setOpen(true)
    }
    window.addEventListener(OPEN_EVENT, show)
    return () => window.removeEventListener(OPEN_EVENT, show)
  }, [])

  useEffect(() => {
    if (!open) return
    next.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, i, close])

  if (!open || !seller) return null

  const step = steps[i]
  const last = i === steps.length - 1
  const Icon = step.icon

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-6" role="dialog" aria-modal="true" aria-labelledby="guide-title">
      <div className="rise w-full max-w-[560px] border-2 border-ink bg-white shadow-[0_24px_80px_rgba(0,0,0,0.35)]">
        <div className="flex items-center justify-between border-b border-line px-6 py-3">
          <p className="text-[13px] font-bold text-muted">
            Ghid rapid · pasul {i + 1} din {steps.length}
          </p>
          <button type="button" onClick={close} className="p-1 text-muted hover:text-ink" aria-label="Închide ghidul">
            <X size={18} />
          </button>
        </div>
        <div className="flex gap-[3px] px-6 pt-4" aria-hidden>
          {steps.map((_, k) => (
            <span key={k} className={`h-1.5 flex-1 ${k <= i ? 'bg-orange' : 'bg-band'}`} />
          ))}
        </div>
        <div className="px-6 pb-6 pt-6">
          <span className="flex size-12 items-center justify-center bg-orange text-ink">
            <Icon size={24} strokeWidth={2.25} aria-hidden />
          </span>
          <h2 id="guide-title" className="mt-5 text-[24px] leading-tight">
            {step.title}
          </h2>
          <p className="mt-3 text-[16px] leading-relaxed text-ink-2">{step.text}</p>
          {step.to && (
            <button
              type="button"
              onClick={() => navigate(step.to!)}
              className="mt-4 text-[14px] font-bold underline underline-offset-4 hover:text-orange-ink"
            >
              {step.cta} →
            </button>
          )}
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-line px-6 py-4">
          <button type="button" onClick={close} className="text-[14px] font-bold text-muted hover:text-ink">
            Sari peste
          </button>
          <div className="flex gap-2">
            {i > 0 && (
              <button
                type="button"
                onClick={() => setI(i - 1)}
                className="inline-flex h-10 items-center gap-2 border-2 border-ink px-4 font-bold hover:bg-canvas"
              >
                <ArrowLeft size={16} aria-hidden /> Înapoi
              </button>
            )}
            <button
              ref={next}
              type="button"
              onClick={() => (last ? close() : setI(i + 1))}
              className="inline-flex h-10 items-center gap-2 border-2 border-orange bg-orange px-5 font-bold text-ink hover:border-ink"
            >
              {last ? 'Am înțeles' : 'Următorul'} {!last && <ArrowRight size={16} aria-hidden />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
