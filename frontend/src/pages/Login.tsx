import { type FormEvent, useState } from 'react'
import { createSeller, login, type Seller } from '../data/client'
import { btn } from '../components/ui'

/** Seller login (PostgreSQL accounts). When no account exists yet, it creates the first one, which becomes admin. */
export default function Login({ firstRun, onDone }: { firstRun: boolean; onDone: (seller: Seller) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (firstRun) await createSeller({ email, full_name: fullName, password })
      onDone(await login(email, password))
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg === 'Wrong email or password' ? 'Email sau parolă greșită.' : msg)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-ink px-4 py-10">
      <form onSubmit={submit} className="w-full max-w-sm bg-white p-8">
        <div className="mb-6 flex items-center gap-3">
          <span className="relative block size-10 bg-orange" aria-hidden>
            <span className="absolute bottom-[7px] left-[7px] h-[7px] w-[7px] bg-white" />
            <span className="absolute bottom-[7px] left-[16px] h-[14px] w-[7px] bg-white" />
            <span className="absolute bottom-[7px] left-[25px] h-[22px] w-[7px] bg-white" />
          </span>
          <span className="leading-none">
            <span className="block text-[19px] font-bold">LeadRadar</span>
            <span className="mt-1 block text-[11px] font-bold text-orange-ink">Orange Systems</span>
          </span>
        </div>
        <h1 className="text-[24px]">{firstRun ? 'Creează contul de administrator' : 'Autentificare'}</h1>
        {firstRun && <p className="mt-2 text-[13px] text-muted">Nu există încă niciun cont. Primul cont devine administrator și poate adăuga ceilalți vânzători.</p>}

        <div className="mt-6 space-y-4">
          {firstRun && (
            <label className="block">
              <span className="mb-1 block font-bold">Nume complet</span>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} required className="h-10 w-full" autoComplete="name" />
            </label>
          )}
          <label className="block">
            <span className="mb-1 block font-bold">Email</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="h-10 w-full" autoComplete="username" />
          </label>
          <label className="block">
            <span className="mb-1 block font-bold">Parolă</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={firstRun ? 8 : undefined}
              className="h-10 w-full"
              autoComplete={firstRun ? 'new-password' : 'current-password'}
            />
          </label>
        </div>
        {error && <p className="mt-4 bg-danger-bg px-3 py-2 text-[13px] font-bold text-danger" role="alert">{error}</p>}
        <button type="submit" disabled={busy} className={`${btn('primary')} mt-6 w-full`}>
          {busy ? 'Se verifică…' : firstRun ? 'Creează contul' : 'Intră'}
        </button>
      </form>
    </div>
  )
}
