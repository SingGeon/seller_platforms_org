import { Plus, X } from 'lucide-react'
import { type FormEvent, useId, useState } from 'react'
import { friendlyError } from '../auth/session'
import { type ApiIcp, configApi } from '../data/backend'
import { Button, Panel, PanelTitle } from './ui'
import { Field } from './forms'

/** "Consultanță GDPR & DPO" -> "consultanta-gdpr-dpo"; the server needs a unique slug per service. */
function slugify(name: string, taken: string[]) {
  const base =
    name
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 40) || 'serviciu'
  let slug = base
  for (let n = 2; taken.includes(slug); n++) slug = `${base}-${n}`
  return slug
}

/**
 * Admin form for a new service category. It is created on the server (POST /services) with an optional first signal
 * question; more questions, rules and the ICP are then set on this page like for any other service.
 */
export default function NewServiceForm({
  takenSlugs,
  baseIcp,
  onCreated,
}: {
  takenSlugs: string[]
  /** The shared ideal-customer profile of the other services; the new service starts with the same one. */
  baseIcp: ApiIcp | null
  onCreated: (slug: string) => Promise<void>
}) {
  const uid = useId()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', description: '', value: '', question: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const reset = () => {
    setForm({ name: '', description: '', value: '', question: '' })
    setError(null)
    setOpen(false)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (form.name.trim().length < 3) return setError('Scrie numele serviciului (minim 3 caractere).')
    setBusy(true)
    setError(null)
    try {
      const slug = slugify(form.name, takenSlugs)
      const svc = await configApi.createService({
        name: form.name.trim(), slug, description: form.description.trim(), value_proposition: form.value.trim(),
      })
      if (baseIcp) await configApi.saveIcp({ ...baseIcp, service_id: svc.id })
      if (form.question.trim()) await configApi.createQuestion(svc.id, form.question.trim(), 'Medium', false)
      await onCreated(svc.slug)
      reset()
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg.includes('already exists') ? 'Există deja un serviciu cu acest nume.' : friendlyError(err))
    } finally {
      setBusy(false)
    }
  }

  if (!open)
    return (
      <Button variant="primary" onClick={() => setOpen(true)}>
        <Plus size={16} aria-hidden /> Serviciu nou
      </Button>
    )

  return (
    <Panel className="w-full border-2 border-ink">
      <PanelTitle
        action={
          <button type="button" onClick={reset} className="p-1 text-muted hover:text-ink" aria-label="Închide formularul">
            <X size={18} />
          </button>
        }
      >
        Serviciu nou
      </PanelTitle>
      <form onSubmit={submit} className="grid gap-4 p-5 md:grid-cols-2" noValidate>
        <Field label="Numele serviciului" id={`${uid}-n`} hint="Apare în filtre, pe fișa companiei și în scoruri.">
          <input
            id={`${uid}-n`}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="ex. Consultanță GDPR & DPO"
            className="h-11 w-full"
            autoFocus
          />
        </Field>
        <Field label="Ce acoperă (descriere scurtă)" id={`${uid}-d`}>
          <input
            id={`${uid}-d`}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="ex. Audit GDPR, DPO externalizat, registre de prelucrare"
            className="h-11 w-full"
          />
        </Field>
        <Field label="Propunerea de valoare" id={`${uid}-v`} hint="Folosită de AI când scrie mesajele de contact pentru acest serviciu.">
          <textarea
            id={`${uid}-v`}
            value={form.value}
            onChange={(e) => setForm({ ...form, value: e.target.value })}
            rows={3}
            placeholder="ex. Orange Systems aduce compania în conformitate GDPR în 60 de zile: audit, documentație și DPO dedicat."
            className="w-full py-2"
          />
        </Field>
        <Field label="Prima întrebare-semnal (opțional)" id={`${uid}-q`} hint="Poți adăuga mai multe întrebări după ce serviciul e creat.">
          <textarea
            id={`${uid}-q`}
            value={form.question}
            onChange={(e) => setForm({ ...form, question: e.target.value })}
            rows={3}
            placeholder="ex. Compania a primit o amendă GDPR sau caută un DPO?"
            className="w-full py-2"
          />
        </Field>
        {error && (
          <p className="bg-danger-bg px-3 py-2 text-[13px] font-bold text-danger md:col-span-2" role="alert">
            {error}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-4 md:col-span-2">
          <Button type="submit" variant="primary" disabled={busy}>
            <Plus size={16} aria-hidden /> {busy ? 'Se creează…' : 'Creează serviciul'}
          </Button>
          <button type="button" onClick={reset} className="font-bold underline underline-offset-4 hover:text-orange-ink">
            Renunță
          </button>
          <p className="text-[13px] text-muted">
            Primește profilul clientului ideal comun (tab-ul „Profil client ideal”) și un scor după următoarea analiză.
          </p>
        </div>
      </form>
    </Panel>
  )
}
