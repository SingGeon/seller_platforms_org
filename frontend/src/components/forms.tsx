import { Eye, EyeOff } from 'lucide-react'
import { type ReactNode, useState } from 'react'

export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

export function passwordStrength(pw: string) {
  let score = 0
  if (pw.length >= 8) score++
  if (pw.length >= 12) score++
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) score++
  const labels = ['Prea scurtă', 'Slabă', 'Acceptabilă', 'Bună', 'Puternică']
  const s = pw.length < 8 ? 0 : Math.max(1, score)
  return { score: s, label: labels[s] }
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

export function Field({ label, error, hint, children, id }: { label: string; error?: string | null; hint?: ReactNode; children: ReactNode; id: string }) {
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
