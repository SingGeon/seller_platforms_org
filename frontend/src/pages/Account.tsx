import { CircleCheck, KeyRound, LogOut, Plus, UserRound } from 'lucide-react'
import { type FormEvent, useEffect, useId, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { friendlyError, useSession } from '../auth/session'
import { STAGES, getCompanies, timeAgo } from '../data/api'
import { type ActivityEntry, createSeller, listActivity, listSellers, type Seller, updateSeller } from '../data/client'
import type { Company } from '../data/types'
import { Avatar, Button, PageHeader, Panel, PanelTitle, ScoreMeter, StageTag, btn } from '../components/ui'
import { Field, PasswordInput, StrengthMeter } from './Auth'

type Tab = 'profile' | 'security' | 'leads' | 'activity' | 'team'

const fmtDate = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString('ro-RO', { day: 'numeric', month: 'long', year: 'numeric' }) : '—'

const ACTIONS: Record<string, string> = {
  login: 'Autentificare',
  logout: 'Ieșire din cont',
  stage_change: 'A schimbat stadiul unui lead',
  assign: 'A asignat un lead',
  note: 'A adăugat o notă',
}
const actionLabel = (a: string) => ACTIONS[a] ?? a.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())

function Saved({ text }: { text: string }) {
  return (
    <p className="flex items-center gap-2 text-[14px] font-bold text-ok" role="status">
      <CircleCheck size={17} aria-hidden /> {text}
    </p>
  )
}

function ProfileTab() {
  const { seller, updateProfile, mode } = useSession()
  const uid = useId()
  const [name, setName] = useState(seller?.full_name ?? '')
  const [state, setState] = useState<'idle' | 'busy' | 'saved'>('idle')
  const [error, setError] = useState<string | null>(null)
  if (!seller) return null
  const save = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return setError('Numele nu poate fi gol.')
    setState('busy')
    setError(null)
    try {
      await updateProfile(name.trim())
      setState('saved')
    } catch (err) {
      setError(friendlyError(err))
      setState('idle')
    }
  }
  return (
    <form onSubmit={save} className="max-w-[560px] space-y-5">
      <Field label="Nume complet" id={`${uid}-n`} error={error}>
        <input id={`${uid}-n`} value={name} onChange={(e) => { setName(e.target.value); setState('idle') }} className="h-11 w-full" autoComplete="name" />
      </Field>
      <Field label="Email" id={`${uid}-e`} hint="Emailul este identificatorul contului și nu poate fi schimbat.">
        <input id={`${uid}-e`} value={seller.email} readOnly className="h-11 w-full bg-canvas text-muted" />
      </Field>
      <Field label="Rol" id={`${uid}-r`} hint={seller.role === 'admin' ? 'Poți gestiona echipa și configurarea.' : 'Rolul îl schimbă un administrator.'}>
        <input id={`${uid}-r`} value={seller.role === 'admin' ? 'Administrator' : 'Vânzător'} readOnly className="h-11 w-full bg-canvas text-muted" />
      </Field>
      <div className="flex items-center gap-4">
        <Button type="submit" variant="primary" disabled={state === 'busy' || name.trim() === seller.full_name}>
          {state === 'busy' ? 'Se salvează…' : 'Salvează'}
        </Button>
        {state === 'saved' && <Saved text={mode === 'api' ? 'Profil actualizat.' : 'Profil actualizat în acest browser.'} />}
      </div>
    </form>
  )
}

function SecurityTab() {
  const { changePassword, mode } = useSession()
  const uid = useId()
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [state, setState] = useState<'idle' | 'busy' | 'saved'>('idle')
  const save = async (e: FormEvent) => {
    e.preventDefault()
    const errs: Record<string, string> = {}
    if (pw.length < 8) errs.pw = 'Parola trebuie să aibă cel puțin 8 caractere.'
    if (pw2 !== pw) errs.pw2 = 'Parolele nu coincid.'
    setErrors(errs)
    if (Object.keys(errs).length) return
    setState('busy')
    try {
      await changePassword(pw)
      setPw('')
      setPw2('')
      setState('saved')
    } catch (err) {
      setErrors({ pw: friendlyError(err) })
      setState('idle')
    }
  }
  if (mode !== 'api')
    return <p className="max-w-[560px] bg-band px-4 py-3">În modul demo nu există parolă salvată. Schimbarea parolei funcționează când serverul cere autentificare.</p>
  return (
    <form onSubmit={save} className="max-w-[560px] space-y-5" noValidate>
      <Field label="Parolă nouă" id={`${uid}-p`} error={errors.pw}>
        <PasswordInput id={`${uid}-p`} value={pw} onChange={(v) => { setPw(v); setState('idle') }} autoComplete="new-password" invalid={!!errors.pw} />
        <StrengthMeter password={pw} />
      </Field>
      <Field label="Confirmă parola nouă" id={`${uid}-p2`} error={errors.pw2}>
        <PasswordInput id={`${uid}-p2`} value={pw2} onChange={setPw2} autoComplete="new-password" invalid={!!errors.pw2} />
      </Field>
      <div className="flex items-center gap-4">
        <Button type="submit" variant="primary" disabled={state === 'busy' || !pw}>
          <KeyRound size={16} aria-hidden /> {state === 'busy' ? 'Se salvează…' : 'Schimbă parola'}
        </Button>
        {state === 'saved' && <Saved text="Parola a fost schimbată." />}
      </div>
    </form>
  )
}

function LeadRow({ c }: { c: Company }) {
  return (
    <li className="border-b border-line last:border-0">
      <Link to={`/leads/${c.id}`} className="flex items-center gap-4 px-5 py-3.5 hover:bg-orange-wash">
        <div className="min-w-0 flex-1">
          <p className="truncate font-bold">{c.name}</p>
          <p className="text-[12px] text-muted">
            {c.industry} · {c.countryName}
          </p>
        </div>
        <StageTag stage={c.stage} />
        <div className="w-24 text-right">
          <span className="num block text-[18px] font-bold leading-none">{c.score}</span>
          <span className="mt-1 flex justify-end">
            <ScoreMeter score={c.score} size="sm" />
          </span>
        </div>
      </Link>
    </li>
  )
}

function LeadsTab() {
  const { seller, mode } = useSession()
  const all = getCompanies()
  const mine = all.filter((c) => (mode === 'api' ? c.sellerId === seller?.id : c.owner === seller?.full_name))
  const open = all.filter((c) => !c.owner && c.stage !== 'descalificat' && c.score >= 75).sort((a, b) => b.score - a.score).slice(0, 6)
  const byStage = STAGES.filter((s) => s.id !== 'descalificat').map((s) => ({ ...s, n: mine.filter((c) => c.stage === s.id).length }))
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {byStage.map((s) => (
          <div key={s.id} className="border border-line bg-white p-4">
            <p className="text-[13px] font-bold text-muted">{s.label}</p>
            <p className="num mt-2 text-[28px] font-bold leading-none">{s.n}</p>
          </div>
        ))}
      </div>
      <Panel>
        <PanelTitle action={<Link to="/pipeline" className="text-[13px] font-bold underline underline-offset-4">Pipeline</Link>}>Asignate ție ({mine.length})</PanelTitle>
        {mine.length ? (
          <ul>{mine.sort((a, b) => b.score - a.score).map((c) => <LeadRow key={c.id} c={c} />)}</ul>
        ) : (
          <p className="px-5 py-6 text-muted">Nu ai încă lead-uri asignate. Preia unul dintre cele de mai jos din fișa companiei.</p>
        )}
      </Panel>
      <Panel>
        <PanelTitle>Fierbinți și neasignate: de preluat</PanelTitle>
        {open.length ? <ul>{open.map((c) => <LeadRow key={c.id} c={c} />)}</ul> : <p className="px-5 py-6 text-muted">Toate lead-urile fierbinți au un responsabil.</p>}
      </Panel>
    </div>
  )
}

function ActivityTab() {
  const { seller, mode } = useSession()
  const [rows, setRows] = useState<ActivityEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (mode !== 'api' || !seller) return
    listActivity(seller.id).then(setRows).catch((e) => setError(friendlyError(e)))
  }, [mode, seller])
  if (mode !== 'api') return <p className="max-w-[560px] bg-band px-4 py-3">Istoricul activității se citește din jurnalul serverului și apare când serverul cere autentificare.</p>
  if (error) return <p className="bg-danger-bg px-4 py-3 font-bold text-danger">{error}</p>
  if (!rows) return <p className="text-muted">Se încarcă…</p>
  if (!rows.length) return <p className="text-muted">Nicio activitate încă.</p>
  return (
    <Panel>
      <ol className="relative ml-6 border-l-2 border-line py-4">
        {rows.map((r, i) => (
          <li key={i} className="relative mb-5 pl-6 pr-5 last:mb-0">
            <span className={`absolute -left-[7px] top-1 size-3 ${i === 0 ? 'bg-orange' : 'bg-ink'}`} aria-hidden />
            <p className="font-bold">{actionLabel(r.action)}</p>
            <p className="text-[13px] text-muted">
              {timeAgo(r.t)}
              {r.company_id != null && (
                <>
                  {' · '}
                  <Link to={`/leads/${r.company_id}`} className="underline underline-offset-2 hover:text-ink">
                    compania #{r.company_id}
                  </Link>
                </>
              )}
            </p>
          </li>
        ))}
      </ol>
    </Panel>
  )
}

function TeamTab() {
  const { seller, mode } = useSession()
  const uid = useId()
  const [team, setTeam] = useState<Seller[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ full_name: '', email: '', password: '', role: 'seller' as 'seller' | 'admin' })
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const reload = () => listSellers().then(setTeam).catch((e) => setError(friendlyError(e)))
  useEffect(() => {
    if (mode === 'api') void reload()
  }, [mode])
  if (mode !== 'api') return <p className="max-w-[560px] bg-band px-4 py-3">Gestionarea echipei (conturi, roluri, resetare parolă) funcționează când serverul cere autentificare.</p>

  const add = async (e: FormEvent) => {
    e.preventDefault()
    setMsg(null)
    setError(null)
    if (!form.full_name.trim() || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email) || form.password.length < 8)
      return setError('Completează numele, un email valid și o parolă temporară de minim 8 caractere.')
    setBusy(true)
    try {
      await createSeller({ ...form, full_name: form.full_name.trim(), email: form.email.trim() })
      setMsg(`Cont creat pentru ${form.email.trim()}. Trimite-i parola temporară pe un canal sigur.`)
      setForm({ full_name: '', email: '', password: '', role: 'seller' })
      await reload()
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setBusy(false)
    }
  }

  const patch = async (s: Seller, body: Parameters<typeof updateSeller>[1], done: string) => {
    setMsg(null)
    setError(null)
    try {
      await updateSeller(s.id, body)
      setMsg(done)
      await reload()
    } catch (err) {
      setError(friendlyError(err))
    }
  }

  const resetPassword = (s: Seller) => {
    const pw = window.prompt(`Parolă temporară nouă pentru ${s.full_name} (minim 8 caractere):`)
    if (pw == null) return
    if (pw.length < 8) return setError('Parola temporară trebuie să aibă cel puțin 8 caractere.')
    void patch(s, { password: pw }, `Parola lui ${s.full_name} a fost resetată.`)
  }

  return (
    <div className="space-y-6">
      {msg && <Saved text={msg} />}
      {error && <p className="bg-danger-bg px-4 py-3 text-[14px] font-bold text-danger" role="alert">{error}</p>}
      <Panel>
        <PanelTitle>Membrii echipei</PanelTitle>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse">
            <thead className="border-b-2 border-ink text-left text-[13px]">
              <tr>
                <th className="px-5 py-3">Nume</th>
                <th className="px-5 py-3">Rol</th>
                <th className="px-5 py-3">Ultima autentificare</th>
                <th className="px-5 py-3">Stare</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {(team ?? []).map((s) => {
                const self = s.id === seller?.id
                return (
                  <tr key={s.id} className="border-b border-line last:border-0">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <Avatar name={s.full_name} />
                        <div>
                          <p className="font-bold">{s.full_name}{self && <span className="ml-2 text-[12px] font-normal text-muted">(tu)</span>}</p>
                          <p className="text-[13px] text-muted">{s.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      <select
                        value={s.role}
                        disabled={self}
                        onChange={(e) => void patch(s, { role: e.target.value as 'seller' | 'admin' }, `Rolul lui ${s.full_name} a fost schimbat.`)}
                        className="h-9"
                        aria-label={`Rolul lui ${s.full_name}`}
                      >
                        <option value="seller">Vânzător</option>
                        <option value="admin">Administrator</option>
                      </select>
                    </td>
                    <td className="px-5 py-3.5 text-[14px] text-muted">{s.last_login_at ? timeAgo(s.last_login_at) : 'niciodată'}</td>
                    <td className="px-5 py-3.5">
                      <span className={`px-2 py-0.5 text-[12px] font-bold ${s.active ? 'bg-ok-bg text-ok' : 'bg-band text-muted'}`}>{s.active ? 'Activ' : 'Dezactivat'}</span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {!self && (
                        <div className="flex justify-end gap-2">
                          <Button size="sm" onClick={() => resetPassword(s)}>Resetează parola</Button>
                          <Button size="sm" variant="ghost" onClick={() => void patch(s, { active: !s.active }, s.active ? `${s.full_name} a fost dezactivat.` : `${s.full_name} a fost reactivat.`)}>
                            {s.active ? 'Dezactivează' : 'Reactivează'}
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>
      <Panel>
        <PanelTitle>Adaugă un coleg</PanelTitle>
        <form onSubmit={add} className="grid gap-4 p-5 md:grid-cols-2" noValidate>
          <Field label="Nume complet" id={`${uid}-tn`}>
            <input id={`${uid}-tn`} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className="h-11 w-full" />
          </Field>
          <Field label="Email" id={`${uid}-te`}>
            <input id={`${uid}-te`} type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="h-11 w-full" />
          </Field>
          <Field label="Parolă temporară" id={`${uid}-tp`} hint="Colegul o poate schimba din Contul meu → Securitate.">
            <PasswordInput id={`${uid}-tp`} value={form.password} onChange={(v) => setForm({ ...form, password: v })} autoComplete="new-password" />
          </Field>
          <Field label="Rol" id={`${uid}-tr`}>
            <select id={`${uid}-tr`} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as 'seller' | 'admin' })} className="h-11 w-full">
              <option value="seller">Vânzător</option>
              <option value="admin">Administrator</option>
            </select>
          </Field>
          <div className="md:col-span-2">
            <Button type="submit" variant="primary" disabled={busy}>
              <Plus size={16} aria-hidden /> {busy ? 'Se creează…' : 'Creează contul'}
            </Button>
          </div>
        </form>
      </Panel>
    </div>
  )
}

export default function Account() {
  const { seller, mode, signOut } = useSession()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('profile')
  if (!seller) return null
  const isAdmin = seller.role === 'admin'
  const tabs: [Tab, string][] = [
    ['profile', 'Profil'],
    ['security', 'Securitate'],
    ['leads', 'Lead-urile mele'],
    ['activity', 'Activitate'],
    ...(isAdmin ? ([['team', 'Echipa']] as [Tab, string][]) : []),
  ]
  const initials = seller.full_name.split(' ').map((p) => p[0]).join('').slice(0, 2).toUpperCase()
  const mineCount = getCompanies().filter((c) => (mode === 'api' ? c.sellerId === seller.id : c.owner === seller.full_name)).length

  const out = async () => {
    await signOut()
    navigate('/', { replace: true })
  }

  return (
    <div className="rise">
      <PageHeader title="Contul meu" subtitle="Profilul, securitatea și lead-urile tale." />
      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <aside className="space-y-6">
          <Panel>
            <div className="p-6">
              <span className="flex size-20 items-center justify-center bg-orange text-[30px] font-bold text-ink" aria-hidden>
                {initials || <UserRound size={32} />}
              </span>
              <h2 className="mt-4 text-[22px] leading-tight">{seller.full_name}</h2>
              <p className="mt-1 break-all text-muted">{seller.email}</p>
              <span className={`mt-3 inline-block px-2 py-0.5 text-[12px] font-bold ${isAdmin ? 'bg-ink text-white' : 'bg-band'}`}>
                {isAdmin ? 'Administrator' : 'Vânzător'}
              </span>
              <dl className="mt-6 grid grid-cols-[1fr_auto] gap-y-2.5 border-t border-line pt-5 text-[14px]">
                <dt className="text-muted">Membru din</dt>
                <dd className="text-right">{fmtDate(seller.created_at)}</dd>
                <dt className="text-muted">Ultima autentificare</dt>
                <dd className="text-right">{seller.last_login_at ? timeAgo(seller.last_login_at) : '—'}</dd>
                <dt className="text-muted">Lead-uri asignate</dt>
                <dd className="num text-right font-bold">{mineCount}</dd>
                <dt className="text-muted">Mod</dt>
                <dd className="text-right">{mode === 'api' ? 'Cont pe server' : 'Demo (local)'}</dd>
              </dl>
              <button type="button" onClick={() => void out()} className={`${btn('secondary')} mt-6 w-full`}>
                <LogOut size={16} aria-hidden /> Ieșire din cont
              </button>
            </div>
          </Panel>
        </aside>
        <div className="min-w-0">
          <div className="mb-6 flex overflow-x-auto border-b-2 border-ink" role="tablist">
            {tabs.map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={`-mb-[2px] whitespace-nowrap px-5 py-3 font-bold transition-colors ${tab === id ? 'bg-ink text-white' : 'text-ink-2 hover:bg-band'}`}
              >
                {label}
              </button>
            ))}
          </div>
          <div role="tabpanel">
            {tab === 'profile' && <ProfileTab />}
            {tab === 'security' && <SecurityTab />}
            {tab === 'leads' && <LeadsTab />}
            {tab === 'activity' && <ActivityTab />}
            {tab === 'team' && isAdmin && <TeamTab />}
          </div>
        </div>
      </div>
    </div>
  )
}
