import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { loadData, setSeller as setDataSeller } from '../data/api'
import {
  AuthError,
  authStatus,
  createSeller,
  getToken,
  login as apiLogin,
  logout as apiLogout,
  me,
  type Seller,
  setOnAuthLost,
  updateSeller,
} from '../data/client'

/**
 * api  — backend reachable and login required: real seller accounts (PostgreSQL).
 * open — backend reachable, login switched off: a local session only gates the UI.
 * demo — backend unreachable or VITE_USE_MOCK: a local session so the flow can be shown offline.
 */
export type AuthMode = 'api' | 'open' | 'demo'

const DEMO_KEY = 'leadradar.demoUser'

interface Session {
  loading: boolean
  mode: AuthMode
  firstRun: boolean
  seller: Seller | null
  dataReady: boolean
  signIn: (email: string, password: string) => Promise<void>
  signUp: (body: { full_name: string; email: string; password: string }) => Promise<void>
  signOut: () => Promise<void>
  updateProfile: (full_name: string) => Promise<void>
  changePassword: (password: string) => Promise<void>
}

const Ctx = createContext<Session | null>(null)

export const useSession = () => {
  const s = useContext(Ctx)
  if (!s) throw new Error('useSession outside SessionProvider')
  return s
}

function readDemo(): Seller | null {
  try {
    const raw = localStorage.getItem(DEMO_KEY)
    return raw ? (JSON.parse(raw) as Seller) : null
  } catch {
    return null
  }
}

function writeDemo(s: Seller | null) {
  try {
    if (s) localStorage.setItem(DEMO_KEY, JSON.stringify(s))
    else localStorage.removeItem(DEMO_KEY)
  } catch {
    // private mode: the demo session lasts until the tab closes
  }
}

const nameFromEmail = (email: string) =>
  email
    .split('@')[0]
    .split(/[._-]+/)
    .filter(Boolean)
    .map((p) => p[0].toUpperCase() + p.slice(1))
    .join(' ') || 'Utilizator'

function demoSeller(email: string, full_name?: string): Seller {
  const now = new Date().toISOString()
  return { id: 0, email: email.trim().toLowerCase(), full_name: full_name?.trim() || nameFromEmail(email), role: 'admin', active: true, created_at: now, last_login_at: now }
}

export const friendlyError = (err: unknown) => {
  const msg = err instanceof Error ? err.message : String(err)
  if (msg === 'Wrong email or password') return 'Email sau parolă greșită.'
  if (msg.startsWith('Only an admin')) return 'Înregistrarea publică e închisă. Cere administratorului echipei să-ți creeze contul (Contul meu → Echipa).'
  if (msg.includes('already exists')) return 'Există deja un cont cu acest email.'
  if (msg.includes('abort')) return 'Serverul nu a răspuns la timp. Încearcă din nou.'
  return msg
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState<AuthMode>('demo')
  const [firstRun, setFirstRun] = useState(false)
  const [seller, setSellerState] = useState<Seller | null>(null)
  const [dataReady, setDataReady] = useState(false)

  const enter = useCallback(async (s: Seller, m: AuthMode) => {
    setDataSeller(m === 'api' ? s : null)
    setSellerState(s)
    setDataReady(false)
    await loadData()
    setDataReady(true)
  }, [])

  useEffect(() => {
    setOnAuthLost(() => {
      setDataSeller(null)
      setSellerState(null)
      setDataReady(false)
    })
    const start = async () => {
      let m: AuthMode = 'demo'
      if (import.meta.env.VITE_USE_MOCK !== 'true') {
        try {
          const status = await authStatus()
          m = status.auth_required ? 'api' : 'open'
          setFirstRun(status.auth_required && !status.has_sellers)
        } catch {
          m = 'demo'
        }
      }
      setMode(m)
      try {
        if (m === 'api' && getToken()) await enter(await me(), m)
        else if (m !== 'api') {
          const local = readDemo()
          if (local) await enter(local, m)
        }
      } catch {
        // expired or revoked token: stay logged out
      }
      setLoading(false)
    }
    void start()
  }, [enter])

  const signIn = useCallback(
    async (email: string, password: string) => {
      if (mode === 'api') return enter(await apiLogin(email, password), mode)
      const local = readDemo()
      const s = local && local.email === email.trim().toLowerCase() ? { ...local, last_login_at: new Date().toISOString() } : demoSeller(email)
      writeDemo(s)
      await enter(s, mode)
    },
    [mode, enter],
  )

  const signUp = useCallback(
    async (body: { full_name: string; email: string; password: string }) => {
      if (mode === 'api') {
        await createSeller(body)
        setFirstRun(false)
        return enter(await apiLogin(body.email, body.password), mode)
      }
      const s = demoSeller(body.email, body.full_name)
      writeDemo(s)
      await enter(s, mode)
    },
    [mode, enter],
  )

  const signOut = useCallback(async () => {
    if (mode === 'api') {
      try {
        await apiLogout()
      } catch (err) {
        if (!(err instanceof AuthError)) console.warn(err)
      }
    } else writeDemo(null)
    setDataSeller(null)
    setSellerState(null)
    setDataReady(false)
  }, [mode])

  const updateProfile = useCallback(
    async (full_name: string) => {
      if (!seller) return
      const next = mode === 'api' ? await updateSeller(seller.id, { full_name }) : { ...seller, full_name }
      if (mode !== 'api') writeDemo(next)
      else setDataSeller(next)
      setSellerState(next)
    },
    [mode, seller],
  )

  const changePassword = useCallback(
    async (password: string) => {
      if (seller && mode === 'api') await updateSeller(seller.id, { password })
    },
    [mode, seller],
  )

  const value = useMemo(
    () => ({ loading, mode, firstRun, seller, dataReady, signIn, signUp, signOut, updateProfile, changePassword }),
    [loading, mode, firstRun, seller, dataReady, signIn, signUp, signOut, updateProfile, changePassword],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
