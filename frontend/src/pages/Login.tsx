import { Gauge, Newspaper, Send } from 'lucide-react'
import { type FormEvent, useId, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { friendlyError, useSession } from '../auth/session'
import { LogoMark, LoopVideo, Wordmark } from '../components/Brand'
import { EMAIL_RE, Field, PasswordInput } from '../components/forms'
import { btn } from '../components/ui'

// What the platform does, without showing any company data before login.
const FEATURES = [
  { icon: Newspaper, title: 'Semnale din surse publice', text: 'Știri, presa de business și registre, citite zilnic pentru fiecare companie.' },
  { icon: Gauge, title: 'Scor 0–100 pe fiecare serviciu', text: 'Fiecare punct are o dovadă: articolul și fraza din care vine.' },
  { icon: Send, title: 'Mesaj de contact gata de trimis', text: 'Generat din semnalele companiei, în română, engleză sau germană.' },
]

/** The home page for visitors. Accounts are created by an admin, so there is no sign-up here. */
export default function Login() {
  const session = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  const uid = useId()
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [forgot, setForgot] = useState(false)

  if (session.seller) return <Navigate to={from} replace />

  const submit = async (ev: FormEvent) => {
    ev.preventDefault()
    setFormError(null)
    const e: Record<string, string> = {}
    if (!EMAIL_RE.test(email.trim())) e.email = 'Scrie o adresă de email validă.'
    if (!password) e.password = 'Scrie parola.'
    setErrors(e)
    if (Object.keys(e).length) return
    setBusy(true)
    try {
      await session.signIn(email.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      setFormError(friendlyError(err))
    } finally {
      setBusy(false)
    }
  }

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
            <ul className="mt-10 space-y-2">
              {FEATURES.map(({ icon: Icon, title, text }) => (
                <li key={title} className="flex items-start gap-4 border border-white/10 bg-[rgba(10,10,11,0.55)] p-4 backdrop-blur-sm">
                  <span className="flex size-10 shrink-0 items-center justify-center bg-white/10 text-orange">
                    <Icon size={18} aria-hidden />
                  </span>
                  <span>
                    <span className="block text-[15px] font-bold">{title}</span>
                    <span className="block text-[14px] text-white/70">{text}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <p className="text-[12px] text-white/45">© 2026 Orange Systems · Gigahack</p>
        </div>
      </aside>

      <main className="flex flex-col bg-white">
        <div className="flex justify-end px-6 py-5 sm:px-10 lg:hidden">
          <LogoMark size={32} />
        </div>
        <div className="flex flex-1 items-center justify-center px-6 pb-12 sm:px-10">
          <form onSubmit={submit} noValidate className="rise w-full max-w-[420px]">
            <h1 className="text-[34px] leading-tight tracking-[-0.02em]">Bine ai revenit</h1>
            <p className="mt-2 text-muted">Intră în cont ca să vezi lead-urile de azi.</p>

            <div className="mt-7 space-y-5">
              <Field label="Email" id={`${uid}-email`} error={errors.email}>
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
              <Field label="Parolă" id={`${uid}-pw`} error={errors.password}>
                <PasswordInput id={`${uid}-pw`} value={password} onChange={setPassword} autoComplete="current-password" invalid={!!errors.password} />
              </Field>
              <div className="text-right">
                <button type="button" onClick={() => setForgot(!forgot)} className="text-[13px] font-bold underline underline-offset-4 hover:text-orange-ink">
                  Ai uitat parola?
                </button>
                {forgot && (
                  <p className="mt-2 bg-band px-3 py-2 text-left text-[13px]">
                    Parola se resetează de administratorul echipei. Îți va trimite o parolă nouă temporară, pe care o poți schimba din Contul meu.
                  </p>
                )}
              </div>
            </div>

            {formError && (
              <p className="mt-5 bg-danger-bg px-3 py-2.5 text-[13px] font-bold text-danger" role="alert">
                {formError}
              </p>
            )}

            <button type="submit" disabled={busy} className={`${btn('primary')} mt-7 h-12 w-full text-[15px]`}>
              {busy ? 'Se verifică…' : 'Autentificare'}
            </button>

            <p className="mt-6 text-center text-[13px] text-muted">Nu ai cont? Conturile sunt create de administratorul echipei.</p>
          </form>
        </div>
      </main>
    </div>
  )
}
