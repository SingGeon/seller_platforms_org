import { ArrowRight, Check, Gavel, LayoutDashboard, Newspaper, RadioTower, ShieldAlert, SlidersHorizontal, Sparkles, Briefcase } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { LoopVideo, Wordmark } from '../components/Brand'
import { btn } from '../components/ui'

const STEPS = [
  { n: '01', title: 'Colectează', text: 'Joburi, știri, licitații, registre și incidente cyber din zeci de surse publice, actualizate automat.' },
  { n: '02', title: 'Înțelege', text: 'AI-ul răspunde la întrebările voastre de vânzări și citează exact sursa fiecărui răspuns.' },
  { n: '03', title: 'Scorează', text: 'Un scor de la 0 la 100 pe fiecare serviciu, explicat punct cu punct.' },
  { n: '04', title: 'Acționează', text: 'Pipeline, notițe, mesaj personalizat și export în HubSpot.' },
]

const FEATURES = [
  { icon: Sparkles, title: '„De ce acest lead, acum?”', text: 'Fiecare companie vine cu un rezumat și cu dovezile din spatele scorului.' },
  { icon: SlidersHorizontal, title: 'Configurabil fără cod', text: 'Întrebări în limbaj natural, ponderi, reguli de descalificare, profilul clientului ideal.' },
  { icon: LayoutDashboard, title: 'Un CRM, nu un raport', text: 'Lead-uri, pipeline pe stadii, responsabili și istoric, într-un singur loc.' },
]

const SOURCES: [typeof Gavel, string][] = [
  [Gavel, 'TED — licitații UE'],
  [Gavel, 'MTender'],
  [Briefcase, 'Greenhouse · Lever · Ashby'],
  [Briefcase, 'Arbeitnow · The Muse'],
  [Newspaper, 'Google News'],
  [Newspaper, 'PR Newswire'],
  [RadioTower, 'SEC EDGAR'],
  [ShieldAlert, 'ransomware.live'],
  [ShieldAlert, 'Have I Been Pwned'],
  [RadioTower, 'GLEIF · Wikidata'],
]

function Nav() {
  const [solid, setSolid] = useState(false)
  useEffect(() => {
    const onScroll = () => setSolid(window.scrollY > 40)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  return (
    <header className={`fixed inset-x-0 top-0 z-30 transition-colors duration-300 ${solid ? 'bg-ink' : 'bg-transparent'}`}>
      <div className="mx-auto flex h-16 max-w-[1280px] items-center gap-8 px-4 sm:px-6">
        <Wordmark />
        <nav className="hidden items-center gap-7 text-[14px] font-bold text-white/85 md:flex" aria-label="Secțiuni">
          <a href="#cum" className="hover:text-orange">Cum funcționează</a>
          <a href="#produs" className="hover:text-orange">Produsul</a>
          <a href="#surse" className="hover:text-orange">Surse</a>
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <Link to="/login" className="hidden px-2 text-[14px] font-bold text-white hover:text-orange sm:inline">
            Autentificare
          </Link>
          <Link to="/signup" className={btn('primary', 'sm')}>
            Creează cont
          </Link>
        </div>
      </div>
    </header>
  )
}

export default function Landing() {
  return (
    <div className="min-h-full bg-ink text-white">
      <Nav />

      <section className="relative flex min-h-[100svh] items-center overflow-hidden">
        <LoopVideo src="/media/hero-loop.mp4" poster="/media/hero-poster.jpg" className="absolute inset-0 h-full w-full" />
        <div className="absolute inset-0" style={{ background: 'linear-gradient(90deg, rgba(10,10,11,0.95) 0%, rgba(10,10,11,0.8) 38%, rgba(10,10,11,0.15) 72%, rgba(10,10,11,0) 100%)' }} />
        <div className="absolute inset-x-0 bottom-0 h-40" style={{ background: 'linear-gradient(0deg, #000 0%, rgba(0,0,0,0) 100%)' }} />
        <div className="relative mx-auto w-full max-w-[1280px] px-6 pb-20 pt-32">
          <div className="max-w-[720px]">
            <p className="rise text-[13px] font-bold uppercase tracking-[0.2em] text-orange">Orange Systems · Sales intelligence B2B</p>
            <h1 className="rise mt-5 text-[46px] leading-[1.02] tracking-[-0.03em] sm:text-[72px] lg:text-[88px]" style={{ animationDelay: '80ms' }}>
              Clienții potriviți. La momentul <span className="text-orange">potrivit.</span>
            </h1>
            <p className="rise mt-6 max-w-[560px] text-[18px] leading-relaxed text-white/75" style={{ animationDelay: '160ms' }}>
              LeadRadar ascultă zeci de surse publice — joburi, licitații, știri, raportări oficiale — și îți arată ce companie are
              nevoie de serviciile tale, de ce și de ce acum.
            </p>
            <div className="rise mt-9 flex flex-wrap gap-3" style={{ animationDelay: '240ms' }}>
              <Link to="/signup" className={`${btn('primary')} h-12 px-7 text-[15px]`}>
                Creează cont <ArrowRight size={17} aria-hidden />
              </Link>
              <Link to="/login" className={`${btn('ghost')} h-12 border-white/70 px-7 text-[15px] text-white hover:border-white`}>
                Am deja cont
              </Link>
            </div>
          </div>
          <dl className="rise mt-16 grid max-w-[820px] grid-cols-1 gap-6 border-t border-white/15 pt-8 sm:grid-cols-3" style={{ animationDelay: '320ms' }}>
            {[
              ['4.924', 'licitații IT publicate în UE în 30 de zile'],
              ['826', 'schimbări de conducere raportate în 30 de zile'],
              ['45', 'surse publice, actualizate automat'],
            ].map(([n, label]) => (
              <div key={n}>
                <dt className="sr-only">{label}</dt>
                <dd className="text-[40px] font-bold leading-none">{n}</dd>
                <dd className="mt-2 text-[14px] text-white/65">{label}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-[12px] text-white/40">Cifre măsurate live prin API-urile publice ale surselor, 25 septembrie 2026.</p>
        </div>
      </section>

      <section id="cum" className="bg-canvas py-24 text-ink">
        <div className="mx-auto max-w-[1280px] px-6">
          <p className="text-[13px] font-bold uppercase tracking-[0.2em] text-orange-ink">Cum funcționează</p>
          <h2 className="mt-3 max-w-[760px] text-[40px] leading-tight tracking-[-0.02em] sm:text-[52px]">Patru pași. Zero căutări de mână.</h2>
          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s) => (
              <article key={s.n} className="border border-line bg-white p-7">
                <p className="text-[52px] font-bold leading-none text-orange">{s.n}</p>
                <h3 className="mt-5 text-[22px]">{s.title}</h3>
                <p className="mt-2 leading-relaxed text-muted">{s.text}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="produs" className="relative overflow-hidden py-24">
        <div className="mx-auto grid max-w-[1280px] items-center gap-14 px-6 lg:grid-cols-[1fr_1.35fr]">
          <div>
            <p className="text-[13px] font-bold uppercase tracking-[0.2em] text-orange">Produsul</p>
            <h2 className="mt-3 text-[40px] leading-tight tracking-[-0.02em] sm:text-[52px]">Un CRM care își găsește singur clienții.</h2>
            <ul className="mt-10 space-y-7">
              {FEATURES.map(({ icon: Icon, title, text }) => (
                <li key={title} className="flex gap-4">
                  <span className="flex size-11 shrink-0 items-center justify-center bg-orange text-ink">
                    <Icon size={20} aria-hidden />
                  </span>
                  <div>
                    <h3 className="text-[18px]">{title}</h3>
                    <p className="mt-1 leading-relaxed text-white/65">{text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <div className="relative">
            <div className="absolute -inset-10" style={{ background: 'radial-gradient(ellipse at 50% 55%, rgba(255,121,0,0.28) 0%, rgba(255,121,0,0.05) 45%, rgba(0,0,0,0) 70%)' }} />
            <div className="relative border-[10px] border-[#1d1d1f] bg-[#1d1d1f] shadow-[0_40px_120px_rgba(255,121,0,0.18)]">
              <img src="/media/app-home.jpg" alt="Ecranul Acasă din LeadRadar: lead-uri noi, lead-uri fierbinți, semnale proaspete și top lead-uri" className="block w-full" loading="lazy" />
            </div>
          </div>
        </div>
      </section>

      <section id="surse" className="bg-canvas py-24 text-ink">
        <div className="mx-auto max-w-[1280px] px-6">
          <div className="grid gap-10 lg:grid-cols-[1fr_1.4fr]">
            <div>
              <p className="text-[13px] font-bold uppercase tracking-[0.2em] text-orange-ink">Surse</p>
              <h2 className="mt-3 text-[40px] leading-tight tracking-[-0.02em] sm:text-[52px]">Doar date publice. Fiecare cu sursa ei.</h2>
              <ul className="mt-8 space-y-3 text-[16px]">
                {['Citat exact pentru fiecare răspuns al AI-ului', 'Fără scraping pe LinkedIn — doar validare manuală', 'Doar documentele noi ajung la AI, deci costul rămâne mic'].map((t) => (
                  <li key={t} className="flex gap-3">
                    <Check size={20} className="mt-0.5 shrink-0 text-ok" aria-hidden /> {t}
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex flex-wrap content-start gap-3">
              {SOURCES.map(([Icon, name]) => (
                <span key={name} className="flex h-12 items-center gap-2.5 border-2 border-line bg-white px-4 font-bold">
                  <Icon size={17} className="text-orange-ink" aria-hidden /> {name}
                </span>
              ))}
              <span className="flex h-12 items-center px-2 text-muted">și încă ~35</span>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-orange py-20 text-ink">
        <div className="mx-auto flex max-w-[1280px] flex-wrap items-center justify-between gap-8 px-6">
          <h2 className="max-w-[760px] text-[34px] leading-tight tracking-[-0.02em] sm:text-[44px]">Găsește următorul client înaintea concurenței.</h2>
          <Link to="/signup" className={`${btn('dark')} h-12 px-7 text-[15px]`}>
            Creează cont <ArrowRight size={17} aria-hidden />
          </Link>
        </div>
      </section>

      <footer className="bg-ink py-10">
        <div className="mx-auto flex max-w-[1280px] flex-wrap items-center justify-between gap-6 px-6 text-[13px] text-white/55">
          <Wordmark />
          <p>© 2026 Orange Systems · Gigahack. Construit de echipa LeadRadar.</p>
          <div className="flex gap-5 font-bold">
            <Link to="/login" className="hover:text-white">Autentificare</Link>
            <Link to="/signup" className="hover:text-white">Creează cont</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
