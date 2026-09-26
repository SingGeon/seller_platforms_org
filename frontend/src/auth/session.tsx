import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { clearData, loadData, setSeller as setDataSeller } from '../data/api'
import {
  AuthError,
  authStatus,
  getToken,
  login as apiLogin,
  logout as apiLogout,
  me,
  type Seller,
  setOnAuthLost,
  updateSeller,
} from '../data/client'

/**
 * connecting — waiting for the API; the free Render instance sleeps and needs about a minute to wake up.
 * up         — the API answers: login and data come from it.
 * down       — no answer within WAKE_MS; the app says so and offers a retry (there is no offline/demo data).
 */
export type ServerState = 'connecting' | 'up' | 'down'

const WAKE_MS = 120_000
const ATTEMPT_MS = 15_000
const PAUSE_MS = 3_000

interface Session {
  server: ServerState
  seller: Seller | null
  dataReady: boolean
  dataError: string | null
  /** Reconnect to the server, or reload the data after an error. */
  retry: () => void
  signIn: (email: string, password: string) => Promise<void>
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

export const friendlyError = (err: unknown) => {
  const msg = err instanceof Error ? err.message : String(err)
  if (msg === 'Wrong email or password') return 'Email sau parolă greșită.'
  if (msg.startsWith('Only an admin') || msg === 'Admin only') return 'Doar un administrator poate face această acțiune.'
  if (msg.startsWith('Admin accounts are managed')) return 'Conturile de administrator se gestionează doar direct în baza de date.'
  if (msg.startsWith('You cannot activate or deactivate your own')) return 'Nu îți poți dezactiva propriul cont.'
  if (msg.startsWith('You can only change your own')) return 'Poți modifica doar numele și parola propriului cont.'
  if (msg.includes('already exists')) return 'Există deja un cont cu acest email.'
  if (msg.includes('abort')) return 'Serverul nu a răspuns la timp. Încearcă din nou.'
  if (msg === 'Failed to fetch' || msg.includes('NetworkError') || msg.includes('Load failed')) return 'Serverul nu poate fi contactat. Verifică conexiunea și încearcă din nou.'
  return msg
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** Polls /auth/status until the API answers or WAKE_MS passes. */
async function waitForServer(): Promise<boolean> {
  const deadline = Date.now() + WAKE_MS
  while (Date.now() < deadline) {
    try {
      await authStatus(ATTEMPT_MS)
      return true
    } catch {
      await sleep(PAUSE_MS)
    }
  }
  return false
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [server, setServer] = useState<ServerState>('connecting')
  const [seller, setSellerState] = useState<Seller | null>(null)
  const [dataReady, setDataReady] = useState(false)
  const [dataError, setDataError] = useState<string | null>(null)

  const reset = useCallback(() => {
    setDataSeller(null)
    clearData()
    setSellerState(null)
    setDataReady(false)
    setDataError(null)
  }, [])

  const enter = useCallback(async (s: Seller) => {
    setDataSeller(s)
    setSellerState(s)
    setDataReady(false)
    setDataError(null)
    try {
      await loadData()
      setDataReady(true)
    } catch (err) {
      // An expired token is handled by setOnAuthLost (back to the login page).
      if (!(err instanceof AuthError)) setDataError(friendlyError(err))
    }
  }, [])

  const connect = useCallback(async () => {
    setServer('connecting')
    if (!(await waitForServer())) {
      setServer('down')
      return
    }
    // Resolve a saved session before saying "up": otherwise the gate briefly sees no seller and a deep link
    // (/config, a refresh on /leads/12) is sent to the login page.
    let saved: Seller | null = null
    if (getToken()) {
      try {
        saved = await me()
      } catch {
        // expired or revoked token: stay logged out
      }
    }
    setServer('up')
    if (saved) await enter(saved)
  }, [enter])

  useEffect(() => {
    setOnAuthLost(reset)
    void connect()
  }, [connect, reset])

  const retry = useCallback(() => {
    if (server !== 'up') void connect()
    else if (seller) void enter(seller)
  }, [server, seller, connect, enter])

  const signIn = useCallback(async (email: string, password: string) => enter(await apiLogin(email, password)), [enter])

  const signOut = useCallback(async () => {
    try {
      await apiLogout()
    } catch (err) {
      if (!(err instanceof AuthError)) console.warn(err)
    }
    reset()
  }, [reset])

  const updateProfile = useCallback(
    async (full_name: string) => {
      if (!seller) return
      const next = await updateSeller(seller.id, { full_name })
      setDataSeller(next)
      setSellerState(next)
    },
    [seller],
  )

  const changePassword = useCallback(
    async (password: string) => {
      if (seller) await updateSeller(seller.id, { password })
    },
    [seller],
  )

  const value = useMemo(
    () => ({ server, seller, dataReady, dataError, retry, signIn, signOut, updateProfile, changePassword }),
    [server, seller, dataReady, dataError, retry, signIn, signOut, updateProfile, changePassword],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
