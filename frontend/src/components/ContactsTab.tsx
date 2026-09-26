import { BadgeCheck, Ban, Copy, ExternalLink, Mail, Phone, Plus, Search, Trash2, UserRound } from 'lucide-react'
import { type FormEvent, useId, useState } from 'react'
import { friendlyError, useSession } from '../auth/session'
import { type Contact, type DiscoverStats, addContact, deleteContact, discoverContacts, setDoNotContact } from '../data/backend'
import { Button, Panel } from './ui'
import { EMAIL_RE, Field } from './forms'

export const LEVEL_RO: Record<Contact['level'], string> = {
  c_level: 'Decident C-level',
  director: 'Director',
  manager: 'Manager',
  other: 'Alt rol',
  unknown: 'Contact general',
}
const SOURCE_RO: Record<string, string> = {
  website: 'Site-ul companiei',
  news: 'Presă',
  hunter: 'Hunter.io',
  apollo: 'Apollo.io',
  manual: 'Adăugat manual',
}

const fmtDay = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short', year: 'numeric' }) : '')

function statsLine(stats: DiscoverStats): string {
  const part = (key: string, label: string) => {
    const s = stats[key] as { found?: number; error?: string } | undefined
    if (!s) return null
    return s.error ? `${label}: indisponibil` : `${label}: ${s.found}`
  }
  const parts = [part('website', 'site'), part('news', 'presă'), part('hunter', 'Hunter.io'), part('apollo', 'Apollo.io')].filter(Boolean)
  if (!stats.keys.hunter) parts.push('Hunter.io: fără cheie API')
  if (!stats.keys.apollo) parts.push('Apollo.io: fără cheie API')
  return `${stats.new === 1 ? 'Un contact nou' : `${stats.new} contacte noi`} · ${parts.join(' · ')}`
}

function ContactCard({ c, onChange, onDelete }: { c: Contact; onChange: (c: Contact) => void; onDelete: (id: number) => void }) {
  const { seller } = useSession()
  const [error, setError] = useState<string | null>(null)
  const canDelete = seller?.role === 'admin' || (c.added_by != null && c.added_by === seller?.full_name)
  const toggle = () =>
    setDoNotContact(c.id, !c.do_not_contact)
      .then(onChange)
      .catch((e) => setError(friendlyError(e)))
  const remove = () => {
    if (!window.confirm(`Ștergi contactul ${c.name ?? c.email ?? c.phone}?`)) return
    deleteContact(c.id)
      .then(() => onDelete(c.id))
      .catch((e) => setError(friendlyError(e)))
  }

  return (
    <article className={`border bg-white p-5 ${c.do_not_contact ? 'border-danger/40 opacity-70' : 'border-line'}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center bg-canvas text-muted" aria-hidden>
            <UserRound size={18} />
          </span>
          <div className="min-w-0">
            <p className="font-bold">
              {c.name ?? 'Contact general al companiei'}
              {c.verified && <BadgeCheck size={15} className="ml-1.5 inline text-ok" aria-label="Adresă verificată de furnizor" />}
            </p>
            {c.role && <p className="text-[14px] text-ink-2">{c.role}</p>}
            <span className={`mt-1 inline-block px-1.5 py-0.5 text-[11px] font-bold ${c.level === 'c_level' ? 'bg-orange text-ink' : 'bg-band'}`}>
              {LEVEL_RO[c.level]}
            </span>
            {c.do_not_contact && (
              <span className="ml-2 inline-flex items-center gap-1 bg-danger-bg px-1.5 py-0.5 text-[11px] font-bold text-danger">
                <Ban size={11} aria-hidden /> Nu contacta
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 text-[13px]">
          <button type="button" onClick={() => void toggle()} className="font-bold underline underline-offset-4 hover:text-orange-ink">
            {c.do_not_contact ? 'Permite contactarea' : 'Nu contacta'}
          </button>
          {canDelete && (
            <button type="button" onClick={remove} className="p-1 text-muted hover:text-danger" aria-label="Șterge contactul">
              <Trash2 size={16} />
            </button>
          )}
        </div>
      </div>

      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-[14px]">
        {c.email && (
          <li className="flex items-center gap-1.5">
            <Mail size={15} className="text-muted" aria-hidden />
            {c.do_not_contact ? <span>{c.email}</span> : <a href={`mailto:${c.email}`} className="underline underline-offset-2">{c.email}</a>}
            <button type="button" onClick={() => void navigator.clipboard?.writeText(c.email!)} className="p-0.5 text-muted hover:text-ink" aria-label="Copiază emailul">
              <Copy size={13} />
            </button>
          </li>
        )}
        {c.phone && (
          <li className="flex items-center gap-1.5">
            <Phone size={15} className="text-muted" aria-hidden />
            {c.do_not_contact ? <span>{c.phone}</span> : <a href={`tel:${c.phone.replace(/[^\d+]/g, '')}`} className="underline underline-offset-2">{c.phone}</a>}
          </li>
        )}
        {c.linkedin && (
          <li className="flex items-center gap-1.5">
            <ExternalLink size={15} className="text-muted" aria-hidden />
            <a href={c.linkedin} target="_blank" rel="noreferrer" className="underline underline-offset-2">Profil LinkedIn</a>
          </li>
        )}
      </ul>

      <ul className="mt-3 space-y-1 border-t border-line pt-3 text-[12px] text-muted">
        {c.sources.map((s, k) => (
          <li key={k}>
            <span className="font-bold text-ink-2">{SOURCE_RO[s.source] ?? s.source}</span>
            {s.found_at && ` · ${fmtDay(s.found_at)}`}
            {s.url && (
              <>
                {' · '}
                <a href={s.url} target="_blank" rel="noreferrer" className="underline">
                  sursa
                </a>
              </>
            )}
            {s.evidence && <span className="block italic">„{s.evidence}”</span>}
          </li>
        ))}
      </ul>
      {error && <p className="mt-2 text-[13px] font-bold text-danger" role="alert">{error}</p>}
    </article>
  )
}

function AddContact({ companyId, onAdded }: { companyId: string; onAdded: (c: Contact) => void }) {
  const uid = useId()
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ name: '', role: '', email: '', phone: '', linkedin: '', note: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (f.name.trim().length < 2) return setError('Scrie numele persoanei.')
    if (!f.email.trim() && !f.phone.trim() && !f.linkedin.trim()) return setError('Adaugă cel puțin un email, un telefon sau un profil LinkedIn.')
    if (f.email.trim() && !EMAIL_RE.test(f.email.trim())) return setError('Emailul nu pare valid.')
    if (f.linkedin.trim() && !/^https:\/\/([a-z]+\.)?linkedin\.com\//.test(f.linkedin.trim())) return setError('Linkul LinkedIn trebuie să înceapă cu https://www.linkedin.com/')
    setBusy(true)
    setError(null)
    try {
      const clean = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.trim() || undefined])) as typeof f
      onAdded(await addContact(companyId, { ...clean, name: f.name.trim() }))
      setF({ name: '', role: '', email: '', phone: '', linkedin: '', note: '' })
      setOpen(false)
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setBusy(false)
    }
  }
  if (!open)
    return (
      <Button onClick={() => setOpen(true)}>
        <Plus size={16} aria-hidden /> Adaugă manual
      </Button>
    )
  return (
    <Panel className="w-full border-2 border-ink">
      <form onSubmit={submit} className="grid gap-4 p-5 md:grid-cols-2" noValidate>
        <Field label="Nume" id={`${uid}-n`}>
          <input id={`${uid}-n`} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} className="h-10 w-full" autoFocus />
        </Field>
        <Field label="Funcție" id={`${uid}-r`}>
          <input id={`${uid}-r`} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} placeholder="ex. Director IT" className="h-10 w-full" />
        </Field>
        <Field label="Email de serviciu" id={`${uid}-e`}>
          <input id={`${uid}-e`} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} className="h-10 w-full" />
        </Field>
        <Field label="Telefon de serviciu" id={`${uid}-p`}>
          <input id={`${uid}-p`} value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} className="h-10 w-full" />
        </Field>
        <Field label="Profil LinkedIn" id={`${uid}-l`}>
          <input id={`${uid}-l`} value={f.linkedin} onChange={(e) => setF({ ...f, linkedin: e.target.value })} placeholder="https://www.linkedin.com/in/…" className="h-10 w-full" />
        </Field>
        <Field label="De unde îl ai" id={`${uid}-o`} hint="Apare la sursă, ca echipa să știe cât e de sigur.">
          <input id={`${uid}-o`} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="ex. convorbire cu recepția, cartea de vizită" className="h-10 w-full" />
        </Field>
        {error && <p className="bg-danger-bg px-3 py-2 text-[13px] font-bold text-danger md:col-span-2" role="alert">{error}</p>}
        <div className="flex items-center gap-4 md:col-span-2">
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? 'Se salvează…' : 'Salvează contactul'}
          </Button>
          <button type="button" onClick={() => setOpen(false)} className="font-bold underline underline-offset-4">
            Renunță
          </button>
        </div>
      </form>
    </Panel>
  )
}

/**
 * Decision makers and published contact details of a company, each with its source. Only real data: the company's
 * site, its news, Hunter.io / Apollo.io (with API keys) or a colleague who added it by hand. Nothing is guessed.
 */
export default function ContactsTab({
  companyId,
  companyName,
  contacts,
  onContacts,
}: {
  companyId: string
  companyName: string
  contacts: Contact[] | null
  onContacts: (c: Contact[]) => void
}) {
  const [busy, setBusy] = useState(false)
  const [stats, setStats] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const discover = async () => {
    setBusy(true)
    setError(null)
    try {
      const out = await discoverContacts(companyId)
      onContacts(out.contacts)
      setStats(statsLine(out.stats))
    } catch (e) {
      setError(friendlyError(e))
    } finally {
      setBusy(false)
    }
  }
  const replace = (c: Contact) => onContacts((contacts ?? []).map((x) => (x.id === c.id ? c : x)))
  const linkedInSearch = `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(`${companyName} CEO OR CIO OR CTO OR "Director General"`)}`

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" onClick={() => void discover()} disabled={busy}>
          <Search size={16} aria-hidden /> {busy ? 'Se caută…' : 'Caută contacte'}
        </Button>
        <AddContact companyId={companyId} onAdded={(c) => onContacts([...(contacts ?? []).filter((x) => x.id !== c.id), c])} />
        <a href={linkedInSearch} target="_blank" rel="noreferrer" className="text-[14px] font-bold underline underline-offset-4 hover:text-orange-ink">
          Caută decidenți pe LinkedIn →
        </a>
      </div>
      <p className="text-[13px] text-muted">
        Doar date publicate: site-ul companiei, presa, Hunter.io și Apollo.io (cu cheie API) sau ce adaugă un coleg. Nu generăm și nu ghicim
        adrese. Folosește datele doar pentru contact profesional; „Nu contacta” blochează trimiterea către persoana respectivă.
      </p>
      {stats && <p className="border-l-4 border-orange bg-white px-4 py-2 text-[13px] font-bold">{stats}</p>}
      {error && <p className="bg-danger-bg px-4 py-2 text-[13px] font-bold text-danger" role="alert">{error}</p>}
      {contacts === null && <p className="text-muted">Se încarcă…</p>}
      {contacts?.length === 0 && (
        <p className="border border-line bg-white px-5 py-8 text-center text-muted">
          Niciun contact încă. Apasă „Caută contacte” ca să verificăm site-ul companiei și celelalte surse.
        </p>
      )}
      {contacts?.map((c) => (
        <ContactCard key={c.id} c={c} onChange={replace} onDelete={(id) => onContacts(contacts.filter((x) => x.id !== id))} />
      ))}
    </div>
  )
}
