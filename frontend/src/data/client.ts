// HTTP client for the FastAPI backend: base URL, bearer token of the logged-in seller, JSON helpers.
export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

const TOKEN_KEY = 'leadradar.token'

export interface Seller {
  id: number
  email: string
  full_name: string
  /** 'admin' or a sales-manager role, as stored in the database. */
  role: string
  active: boolean
  created_at?: string
  last_login_at?: string | null
}

let token: string | null = (() => {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
})()

export const getToken = () => token

export function setToken(value: string | null) {
  token = value
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // private mode: the session lasts until the tab closes
  }
}

/** Thrown when the API answers 401: the app shows the login screen. */
export class AuthError extends Error {}

let onAuthLost: () => void = () => {}
export const setOnAuthLost = (fn: () => void) => {
  onAuthLost = fn
}

export async function request<T>(method: string, path: string, body?: unknown, timeoutMs = 15_000): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  try {
    const resp = await fetch(`${API_URL}${path}`, {
      method, headers, signal: ctrl.signal, body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    if (resp.status === 401) {
      if (token) {
        setToken(null)
        onAuthLost()
      }
      throw new AuthError('Autentificare necesară')
    }
    if (!resp.ok) {
      let detail = await resp.text()
      try {
        detail = JSON.parse(detail).detail ?? detail
      } catch {
        // plain text error
      }
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    }
    if (resp.status === 204) return undefined as T
    return (await resp.json()) as T
  } finally {
    clearTimeout(timer)
  }
}

export const getJson = <T>(path: string, timeoutMs?: number) => request<T>('GET', path, undefined, timeoutMs)
export const postJson = <T>(path: string, body: unknown = {}, timeoutMs?: number) => request<T>('POST', path, body, timeoutMs)
export const putJson = <T>(path: string, body: unknown) => request<T>('PUT', path, body)
export const del = (path: string) => request<void>('DELETE', path)

// ------------------------------------------------------------------ auth
export interface AuthStatus {
  auth_required: boolean
  has_sellers: boolean
}

export const authStatus = () => getJson<AuthStatus>('/auth/status', 5000)

export async function login(email: string, password: string): Promise<Seller> {
  const out = await postJson<{ access_token: string; seller: Seller }>('/auth/login', { email, password })
  setToken(out.access_token)
  return out.seller
}

export async function logout(): Promise<void> {
  try {
    await postJson('/auth/logout')
  } finally {
    setToken(null)
  }
}

export const me = () => getJson<Seller>('/auth/me', 5000)

export const createSeller = (body: { email: string; full_name: string; password: string; role?: 'seller' | 'admin' }) =>
  postJson<Seller>('/sellers', body)

export const listSellers = () => getJson<Seller[]>('/sellers')

export const updateSeller = (id: number, body: { full_name?: string; password?: string; role?: 'seller' | 'admin'; active?: boolean }) =>
  putJson<Seller>(`/sellers/${id}`, body)

export interface ActivityEntry {
  t: string
  action: string
  seller_id: number | null
  seller: string | null
  company_id: number | null
  details: Record<string, unknown>
}

