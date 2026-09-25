import { Bell, ChevronDown, Kanban, LayoutDashboard, LogOut, RadioTower, Search, SlidersHorizontal, UserRound, Users } from 'lucide-react'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router'
import { useSession } from '../auth/session'
import { dataError, getCompanies, getSources, isLive, isNew, timeAgo } from '../data/api'
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

function TopBar() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const lastSync = getSources().reduce((a, s) => (s.lastRun > a ? s.lastRun : a), '')
  const newCount = getCompanies().filter(isNew).length

  const submit = (e: FormEvent) => {
    e.preventDefault()
    navigate(`/leads${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''}`)
  }

  return (
    <header className="flex h-16 shrink-0 items-center gap-6 bg-ink pr-6">
      <div className="flex w-60 shrink-0 items-center pl-5">
        <Logo />
      </div>
      <form onSubmit={submit} className="relative max-w-xl flex-1" role="search">
        <Search size={17} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Caută companie, domeniu sau industrie…"
          aria-label="Caută în lead-uri"
          className="h-10 w-full border-0 pl-10 focus:outline-2 focus:outline-orange"
        />
      </form>
      <div className="ml-auto flex items-center gap-5 text-white">
        <span className="hidden items-center gap-2 text-[12px] text-faint lg:flex" title="Ultima sincronizare a surselor">
          <span className="blip size-2 bg-orange" aria-hidden />
          Sincronizat {timeAgo(lastSync)}
        </span>
        {!isLive() && (
          <span
            className="hidden border border-faint px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-faint md:inline"
            title={dataError() ? `API indisponibil: ${dataError()}` : 'Date demo (VITE_USE_MOCK)'}
          >
            Date demo
          </span>
        )}
        <button type="button" className="relative p-1 hover:text-orange" aria-label={`Notificări: ${newCount} lead-uri noi`}>
          <Bell size={20} />
          {newCount > 0 && (
            <span className="num absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center bg-orange px-1 text-[10px] font-bold text-ink">
              {newCount}
            </span>
          )}
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
          <span className="block text-[11px] text-faint">{seller.role === 'admin' ? 'Administrator' : 'Vânzător'}</span>
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
  { to: '/account', label: 'Contul meu', icon: UserRound },
]

function NavItem({ to, label, icon: Icon, end, badge }: { to: string; label: string; icon: typeof Users; end?: boolean; badge?: number }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `relative flex h-11 items-center gap-3 px-5 text-[14px] transition-colors ${
          isActive ? 'bg-canvas font-bold text-ink' : 'text-ink-2 hover:bg-canvas'
        }`
      }
    >
      {({ isActive }) => (
        <>
          {isActive && <span className="absolute inset-y-0 left-0 w-1 bg-orange" aria-hidden />}
          <Icon size={18} aria-hidden />
          <span className="flex-1">{label}</span>
          {badge ? <span className="num bg-band px-1.5 text-[12px] font-bold">{badge}</span> : null}
        </>
      )}
    </NavLink>
  )
}

function Sidebar() {
  const sources = getSources()
  const ok = sources.filter((s) => s.status === 'ok').length
  const active = getCompanies().filter((c) => c.stage !== 'descalificat').length
  return (
    <nav className="flex w-60 shrink-0 flex-col border-r border-line bg-white" aria-label="Navigare principală">
      <p className="px-5 pb-2 pt-6 text-[11px] font-bold uppercase tracking-wider text-muted">Vânzări</p>
      {NAV.map((n) => (
        <NavItem key={n.to} {...n} badge={n.to === '/leads' ? active : undefined} />
      ))}
      <p className="px-5 pb-2 pt-6 text-[11px] font-bold uppercase tracking-wider text-muted">Sistem</p>
      {NAV_SYSTEM.map((n) => (
        <NavItem key={n.to} {...n} />
      ))}
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
              className={`h-2 flex-1 ${s.status === 'ok' ? 'bg-ink' : s.status === 'warn' ? 'bg-warn' : 'bg-danger'}`}
            />
          ))}
        </div>
      </NavLink>
    </nav>
  )
}

export default function Layout() {
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
    </div>
  )
}
