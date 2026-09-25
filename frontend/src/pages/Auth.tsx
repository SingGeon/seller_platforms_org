import { ArrowLeft, Eye, EyeOff, Info } from 'lucide-react'
import { type FormEvent, type ReactNode, useId, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'
import { friendlyError, useSession } from '../auth/session'
import { LogoMark, LoopVideo, Wordmark } from '../components/Brand'
import SignalFeed from '../components/SignalFeed'
import { btn } from '../components/ui'

export function passwordStrength(pw: string) {
  let score = 0
  if (pw.length >= 8) score++
  if (pw.length >= 12) score++
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) score++
  const labels = ['Prea scurtă', 'Slabă', 'Acceptabilă', 'Bună', 'Puternică']
  return { score: pw.length < 8 ? 0 : Math.max(1, score), label: labels[pw.length < 8 ? 0 : Math.max(1, score)] }
}

export function StrengthMeter({ password }: { password: string }) {
  const { score, label } = passwordStrength(password)
  if (!password) return null
  return (
    <div className="mt-2" aria-live="polite">
      <div className="flex gap-1" aria-hidden>
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className={`h-1.5 flex-1 ${i <= score ? (score >= 3 ? 'bg-ok' : 'bg-orange') : 'bg-band'}`} />
        ))}
      </div>
      <p className="mt-1 text-[12px] text-muted">
        Parolă: <span className="font-bold text-ink">{label}</span>
      </p>
    </div>
  )
}

export function Field({
  label,
  error,
  hint,
  children,
  id,
}: {
  label: string
  error?: string | null
  hint?: ReactNode
  children: ReactNode
  id: string
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-[14px] font-bold">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-err`} className="mt-1.5 text-[13px] font-bold text-danger">
          {error}
        </p>
      ) : (
        hint && <p className="mt-1.5 text-[12px] text-muted">{hint}</p>
      )}
    </div>
  )
}

export function PasswordInput({
  id,
  value,
  onChange,
  autoComplete,
  invalid,
}: {
  id: string
  value: string
  onChange: (v: string) => void
  autoComplete: string
  invalid?: boolean
}) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <input
        id={id}
        type={show ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        aria-invalid={invalid || undefined}
        aria-describedby={invalid ? `${id}-err` : undefined}
        className={`h-12 w-full pr-12 ${invalid ? '!border-danger' : ''}`}
      />
      <button
        type="button"
        onClick={() => setShow(!show)}
        className="absolute right-1 top-1/2 flex size-10 -translate-y-1/2 items-center justify-center text-muted hover:text-ink"
        aria-label={show ? 'Ascunde parola' : 'Arată parola'}
      >
        {show ? <EyeOff size={18} /> : <Eye size={18} />}
      </button>
    </div>
  )
}

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

export default function Auth({ mode }: { mode: 'login' | 'signup' }) {
  const session = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  const uid = useId()
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [agree, setAgree] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [forgot, setForgot] = useState(false)

  if (session.loading) return <div className="flex h-full items-center justify-center bg-ink text-white/60">Se încarcă…</div>
  if (session.seller) return <Navigate to={from} replace />

  const isSignup = mode === 'signup'
  const adminSetup = session.mode === 'api' && session.firstRun
  const closedSignup = isSignup && session.mode === 'api' && !session.firstRun

  const validate = () => {
    const e: Record<string, string> = {}
    if (isSignup && !fullName.trim()) e.fullName = 'Scrie numele complet.'
    if (!EMAIL_RE.test(email.trim())) e.email = 'Scrie o adresă de email validă.'
    if (!password) e.password = 'Scrie parola.'
    else if (isSignup && password.length < 8) e.password = 'Parola trebuie să aibă cel puțin 8 caractere.'
    if (isSignup && confirm !== password) e.confirm = 'Parolele nu coincid.'
    if (isSignup && !agree) e.agree = 'Bifează acordul ca să continui.'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const submit = async (ev: FormEvent) => {
    ev.preventDefault()
    setFormError(null)
    if (!validate()) return
    setBusy(true)
    try {
      if (isSignup) await session.signUp({ full_name: fullName.trim(), email: email.trim(), password })
      else await session.signIn(email.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      setFormError(friendlyError(err))
    } finally {
      setBusy(false)
    }
  }

  const title = isSignup ? (adminSetup ? 'Creează contul de administrator' : 'Creează-ți contul') : 'Bine ai revenit'
  const subtitle = isSignup
    ? adminSetup
      ? 'Nu există încă niciun cont. Primul cont devine administrator și îi poate adăuga pe ceilalți vânzători.'
      : 'Găsește clienții potriviți, la momentul potrivit.'
    : 'Intră în cont ca să vezi lead-urile de azi.'

  return (
    <div className="grid min-h-full lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-ink text-white lg:block">
        <LoopVideo src="/media/auth-loop.mp4" poster="/media/auth-poster.jpg" className="absolute inset-0 h-full w-full" />
        <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, rgba(10,10,11,0.75) 0%, rgba(10,10,11,0.35) 45%, rgba(10,10,11,0.92) 100%)' }} />
        <div className="relative flex h-full flex-col justify-between p-12">
          <Wordmark />
          <div className="max-w-[560px]">
            <h2 className="max-w-[520px] text-[52px] leading-[1.03] tracking-[-0.03em]">
              Fiecare companie lasă <span className="text-orange">semnale.</span>
            </h2>
            <p className="mt-4 text-[18px] text-white/70">LeadRadar le aude primul și îți spune pe cine să suni azi.</p>
            <div className="mt-10">
              <SignalFeed />
            </div>
          </div>
          <p className="text-[12px] text-white/45">© 2026 Orange Systems · Gigahack</p>
        </div>
      </aside>

      <main className="flex flex-col bg-white">
        <div className="flex items-center justify-between px-6 py-5 sm:px-10">
          {isSignup ? (
            <Link to="/" state={location.state} className="inline-flex items-center gap-2 text-[14px] font-bold text-muted hover:text-ink">
              <ArrowLeft size={16} aria-hidden /> Înapoi la autentificare
            </Link>
          ) : (
            <span />
          )}
          <span className="lg:hidden">
            <LogoMark size={32} />
          </span>
        </div>
        <div className="flex flex-1 items-center justify-center px-6 pb-12 sm:px-10">
          <form onSubmit={submit} noValidate className="rise w-full max-w-[420px]">
            <h1 className="text-[34px] leading-tight tracking-[-0.02em]">{title}</h1>
            <p className="mt-2 text-muted">{subtitle}</p>

            {session.mode !== 'api' && (
              <p className="mt-5 flex gap-2 bg-band px-3 py-2.5 text-[13px]">
                <Info size={16} className="mt-0.5 shrink-0" aria-hidden />
                {session.mode === 'demo'
                  ? 'Mod demo: serverul nu e disponibil, așa că sesiunea rămâne doar în acest browser. Parola nu este salvată.'
                  : 'Serverul rulează fără autentificare: sesiunea rămâne doar în acest browser. Parola nu este salvată.'}
              </p>
            )}
            {closedSignup && (
              <p className="mt-5 flex gap-2 bg-warn-bg px-3 py-2.5 text-[13px]">
                <Info size={16} className="mt-0.5 shrink-0" aria-hidden />
                Conturile noi sunt create de administratorul echipei. Dacă nu ai primit încă acces, cere-i să te adauge din Contul meu → Echipa.
              </p>
            )}

            <div className="mt-7 space-y-5">
              {isSignup && (
                <Field label="Nume complet" id={`${uid}-name`} error={errors.fullName}>
                  <input
                    id={`${uid}-name`}
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    autoComplete="name"
                    aria-invalid={!!errors.fullName || undefined}
                    className={`h-12 w-full ${errors.fullName ? '!border-danger' : ''}`}
                  />
                </Field>
              )}
              <Field label={isSignup ? 'Email de serviciu' : 'Email'} id={`${uid}-email`} error={errors.email}>
                <input
                  id={`${uid}-email`}
                  type="email"
                  inputMode="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="username"
                  placeholder="nume@companie.md"
                  aria-invalid={!!errors.email || undefined}
                  className={`h-12 w-full ${errors.email ? '!border-danger' : ''}`}
                />
              </Field>
              <Field
                label="Parolă"
                id={`${uid}-pw`}
                error={errors.password}
                hint={isSignup ? 'Minim 8 caractere. Recomandat: litere mari și mici, cifre și un simbol.' : undefined}
              >
                <PasswordInput
                  id={`${uid}-pw`}
                  value={password}
                  onChange={setPassword}
                  autoComplete={isSignup ? 'new-password' : 'current-password'}
                  invalid={!!errors.password}
                />
                {isSignup && <StrengthMeter password={password} />}
              </Field>
              {isSignup && (
                <Field label="Confirmă parola" id={`${uid}-pw2`} error={errors.confirm}>
                  <PasswordInput id={`${uid}-pw2`} value={confirm} onChange={setConfirm} autoComplete="new-password" invalid={!!errors.confirm} />
                </Field>
              )}
              {isSignup && (
                <div>
                  <label className="flex cursor-pointer items-start gap-3 text-[14px]">
                    <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-0.5 size-5 shrink-0 accent-orange" />
                    <span>Sunt de acord ca datele contului meu să fie folosite pentru accesul la LeadRadar.</span>
                  </label>
                  {errors.agree && <p className="mt-1.5 text-[13px] font-bold text-danger">{errors.agree}</p>}
                </div>
              )}
              {!isSignup && (
                <div className="text-right">
                  <button type="button" onClick={() => setForgot(!forgot)} className="text-[13px] font-bold underline underline-offset-4 hover:text-orange-ink">
                    Ai uitat parola?
                  </button>
                  {forgot && (
                    <p className="mt-2 bg-band px-3 py-2 text-left text-[13px]">
                      Parola se resetează de administratorul echipei, din Contul meu → Echipa. Îți va trimite o parolă nouă temporară.
                    </p>
                  )}
                </div>
              )}
            </div>

            {formError && (
              <p className="mt-5 bg-danger-bg px-3 py-2.5 text-[13px] font-bold text-danger" role="alert">
                {formError}
              </p>
            )}

            <button type="submit" disabled={busy} className={`${btn('primary')} mt-7 h-12 w-full text-[15px]`}>
              {busy ? 'Se verifică…' : isSignup ? (adminSetup ? 'Creează contul de administrator' : 'Creează contul') : 'Autentificare'}
            </button>

            <p className="mt-6 text-center text-[14px] text-muted">
              {isSignup ? 'Ai deja cont? ' : 'Nu ai cont? '}
              <Link to={isSignup ? '/' : '/signup'} state={location.state} className="font-bold text-ink underline underline-offset-4 hover:text-orange-ink">
                {isSignup ? 'Autentifică-te' : 'Creează unul'}
              </Link>
            </p>
          </form>
        </div>
      </main>
    </div>
  )
}
