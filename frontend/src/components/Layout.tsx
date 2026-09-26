import { Activity, ChevronDown, CircleHelp, Kanban, LayoutDashboard, LogOut, RadioTower, RefreshCw, Search, ShieldCheck, SlidersHorizontal, UserPlus, UserRound, Users } from 'lucide-react'
import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { useSession } from '../auth/session'
import { dataLoadedAt, getCompanies, getSources, loadData, syncAssignments, timeAgo, useDataVersion } from '../data/api'
import Guide, { openGuide } from './Guide'
import { Avatar } from './ui'

function Logo() {
  return (
    <NavLink to="/" className="flex items-center gap-3" aria-label="LeadRadar — acasă">
      <span className="relative block size-10 bg-orange" aria-hidden>
        <span className="absolute bottom-[7px] left-[7px] h-[7px] w-[7px] bg-white" />
        <span className="absolute bottom-[7px] left-[16px] h-[14px] w-[7px] bg-white" />
        <span className="absolute bottom-[7px] left-[25px] h-[22px] w-[7px] bg-white" />
      </span>
      <span className="leading-none">
        <span className="block text-[19px] font-bold text-white">LeadRadar</span>
        <span className="mt-1 block text-[11px] font-bold text-orange">Orange Systems</span>
      </span>
    </NavLink>
  )
}

// Data is reloaded in the background so new leads from the daily run show up without a page refresh.
const REFRESH_MS = 5 * 60_000

function useAutoRefresh() {
  const [state, setState] = useState<{ busy: boolean; error: string | null }>({ busy: false, error: null })
  const busy = useRef(false)
  const refresh = useCallback(async () => {
    if (busy.current) return
    busy.current = true
    setState({ busy: true, error: null })
    try {
      await loadData()
      setState({ busy: false, error: null })
    } catch (err) {
      // Keep the data already on screen; the header shows that the update failed.
      setState({ busy: false, error: err instanceof Error ? err.message : String(err) })
    } finally {
      busy.current = false
    }
  }, [])
  useEffect(() => {
    const stale = () => Date.now() - new Date(dataLoadedAt() ?? 0).getTime() > REFRESH_MS
    const tick = () => {
      if (document.visibilityState === 'visible' && stale()) void refresh()
    }
    const timer = setInterval(tick, 60_000)
    document.addEventListener('visibilitychange', tick)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [refresh])
  return { ...state, refresh }
}

function TopBar() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const { busy, error, refresh } = useAutoRefresh()

  const submit = (e: FormEvent) => {
    e.preventDefault()
    navigate(`/leads${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''}`)
  }

  return (
    <header className="flex h-16 shrink-0 items-center gap-6 bg-ink pr-6">
      <div className="flex w-60 shrink-0 items-center pl-5">
        <Logo />
      </div>
      <form onSubmit={submit} className="flex max-w-xl flex-1" role="search">
        <div className="relative min-w-0 flex-1">
          <Search size={17} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Caută companie, domeniu sau industrie…"
            aria-label="Caută în lead-uri"
            className="h-10 w-full border-0 pl-10 focus:outline-2 focus:-outline-offset-2 focus:outline-orange"
          />
        </div>
        <button type="submit" className="h-10 shrink-0 bg-orange px-5 font-bold text-ink transition-colors hover:bg-white">
          Caută
        </button>
      </form>
      <div className="ml-auto flex items-center gap-5 text-white">
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={busy}
          className={`flex items-center gap-2 text-[12px] hover:text-white ${error ? 'text-orange' : 'text-faint'}`}
          title={error ? `Actualizarea a eșuat: ${error}. Click pentru a reîncerca.` : 'Datele se actualizează automat la 5 minute. Click pentru acum.'}
        >
          <RefreshCw size={14} className={busy ? 'animate-spin' : ''} aria-hidden />
          {busy ? 'Se actualizează…' : error ? 'Actualizare eșuată · reîncearcă' : `Date actualizate ${timeAgo(dataLoadedAt() ?? '')}`}
        </button>
        <button type="button" onClick={openGuide} className="p-1 hover:text-orange" aria-label="Ghid rapid" title="Ghid rapid">
          <CircleHelp size={20} />
        </button>
        <UserMenu />
      </div>
    </header>
  )
}

function UserMenu() {
  const { seller, signOut } = useSession()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])
  if (!seller) return <Avatar name={null} size={32} />
  const out = async () => {
    setOpen(false)
    await signOut()
    navigate('/', { replace: true })
  }
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-3 py-1 pl-1 hover:text-orange"
      >
        <span className="hidden text-right leading-tight md:block">
          <span className="block text-[13px] font-bold">{seller.full_name}</span>
          <span className="block text-[11px] text-faint">{seller.role === 'admin' ? 'Administrator' : 'Sales manager'}</span>
        </span>
        <Avatar name={seller.full_name} size={32} />
        <ChevronDown size={15} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-40 mt-2 w-60 border-2 border-ink bg-white text-ink shadow-[0_12px_40px_rgba(0,0,0,0.18)]">
          <div className="border-b border-line px-4 py-3">
            <p className="truncate font-bold">{seller.full_name}</p>
            <p className="truncate text-[13px] text-muted">{seller.email}</p>
          </div>
          <Link role="menuitem" to="/account" onClick={() => setOpen(false)} className="flex items-center gap-3 px-4 py-3 font-bold hover:bg-canvas">
            <UserRound size={17} aria-hidden /> Contul meu
          </Link>
          <button
            role="menuitem"
            type="button"
            onClick={() => {
              setOpen(false)
              openGuide()
            }}
            className="flex w-full items-center gap-3 px-4 py-3 text-left font-bold hover:bg-canvas"
          >
            <CircleHelp size={17} aria-hidden /> Ghid rapid
          </button>
          <button role="menuitem" type="button" onClick={() => void out()} className="flex w-full items-center gap-3 border-t border-line px-4 py-3 text-left font-bold hover:bg-canvas">
            <LogOut size={17} aria-hidden /> Ieșire din cont
          </button>
        </div>
      )}
    </div>
  )
}

const NAV = [
  { to: '/', label: 'Acasă', icon: LayoutDashboard, end: true },
  { to: '/leads', label: 'Lead-uri', icon: Users },
  { to: '/pipeline', label: 'Pipeline', icon: Kanban },
]
const NAV_SYSTEM = [
  { to: '/config', label: 'Configurare', icon: SlidersHorizontal },
  { to: '/runs', label: 'Surse și rulări', icon: RadioTower },
]

function NavItem({ to, label, icon: Icon, end, badge, active }: { to: string; label: string; icon: typeof Users; end?: boolean; badge?: number; active?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive: routeActive }) => {
        const isActive = active ?? routeActive
        return `relative flex h-11 items-center gap-3 px-5 text-[14px] transition-colors ${
          isActive ? 'bg-canvas font-bold text-ink' : 'text-ink-2 hover:bg-canvas'
        }`
      }}
    >
      {({ isActive: routeActive }) => (
        <>
          {(active ?? routeActive) && <span className="absolute inset-y-0 left-0 w-1 bg-orange" aria-hidden />}
          <Icon size={18} aria-hidden />
          <span className="flex-1">{label}</span>
          {badge ? <span className="num bg-band px-1.5 text-[12px] font-bold">{badge}</span> : null}
        </>
      )}
    </NavLink>
  )
}

function Sidebar() {
  const { seller } = useSession()
  useDataVersion()
  const { pathname, search } = useLocation()
  const accountsTab = pathname === '/account' && new URLSearchParams(search).get('tab') === 'accounts'
  const sources = getSources()
  const ok = sources.filter((s) => s.status === 'ok').length
  const active = getCompanies().filter((c) => c.stage !== 'descalificat').length
  return (
    <nav className="flex w-60 shrink-0 flex-col border-r border-line bg-white" aria-label="Navigare principală">
      <p className="px-5 pb-2 pt-6 text-[11px] font-bold uppercase tracking-wider text-muted">Vânzări</p>
      {NAV.map((n) => (
        <NavItem key={n.to} {...n} badge={n.to === '/leads' ? active : undefined} />
      ))}
      {seller?.role === 'admin' && (
        <>
          <p className="flex items-center gap-1.5 px-5 pb-2 pt-6 text-[11px] font-bold uppercase tracking-wider text-orange-ink">
            <ShieldCheck size={13} aria-hidden /> Administrare
          </p>
          <NavItem to="/admin" label="Monitorizare echipă" icon={Activity} />
          <NavItem to="/account?tab=accounts" label="Conturi sales manageri" icon={UserPlus} active={accountsTab} />
        </>
      )}
      <p className="px-5 pb-2 pt-6 text-[11px] font-bold uppercase tracking-wider text-muted">Sistem</p>
      {NAV_SYSTEM.map((n) => (
        <NavItem key={n.to} {...n} />
      ))}
      <NavItem to="/account" label="Contul meu" icon={UserRound} active={pathname === '/account' && !accountsTab} />
      <NavLink to="/runs" className="mx-4 mb-4 mt-auto block border-2 border-ink p-3 hover:bg-canvas">
        <p className="text-[11px] font-bold uppercase tracking-wider text-muted">Surse de date</p>
        <p className="mt-1 text-[22px] font-bold leading-none">
          {ok}
          <span className="text-[14px] text-muted">/{sources.length} active</span>
        </p>
        <div className="mt-2 flex gap-[2px]" aria-hidden>
          {sources.map((s) => (
            <span
              key={s.id}
              className={`h-2 flex-1 ${s.status === 'ok' ? 'bg-ink' : s.status === 'warn' ? 'bg-warn' : s.status === 'error' ? 'bg-danger' : 'bg-line'}`}
            />
          ))}
        </div>
      </NavLink>
    </nav>
  )
}

// Stage and owner changes by colleagues (drag & drop, "Preia lead-ul") reach every open screen within this delay.
const LIVE_MS = 10_000

function useLiveAssignments() {
  useEffect(() => {
    let busy = false
    const tick = async () => {
      if (busy || document.visibilityState !== 'visible') return
      busy = true
      try {
        await syncAssignments()
      } catch {
        // a missed poll is retried on the next tick; the full refresh reports lasting errors
      } finally {
        busy = false
      }
    }
    const timer = setInterval(() => void tick(), LIVE_MS)
    document.addEventListener('visibilitychange', tick)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [])
}

export default function Layout() {
  useDataVersion()
  useLiveAssignments()
  // Re-render once a minute so "acum X min" labels stay true.
  const [, setTick] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 60_000)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1400px] px-8 py-7">
            <Outlet />
          </div>
        </main>
      </div>
      <Guide />
    </div>
  )
}
