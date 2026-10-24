import { useCallback, useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Loader2, Lock, RotateCcw, Save } from 'lucide-react'
import { kbApi, type ProfileSection } from '../../../api/knowledgeBase'
import { Loading, Switch, Panel, apiError } from './ui'
import { AttachChip } from './KbFiles'

/** The company_profile facts, loaded once and shared by the tabs that edit different sections of them. */
export function useProfile() {
  const [sections, setSections] = useState<ProfileSection[] | null>(null)
  const [error, setError] = useState('')
  const reload = useCallback(() => {
    kbApi.getProfile().then(r => setSections(r.data.sections)).catch(() => setError('Could not load the company profile.'))
  }, [])
  useEffect(() => { reload() }, [reload])
  const value = useCallback((key: string) => {
    for (const s of sections ?? []) for (const f of s.fields) if (f.key === key) return f.value
    return ''
  }, [sections])
  return { sections, setSections, error, reload, value }
}
export type ProfileState = ReturnType<typeof useProfile>

const SWITCH_FIRST = new Set(['legal', 'bidding'])
const RISK = new Set(['blacklisted', 'debarred', 'insolvency', 'litigation_pending'])

/** Edits the given profile sections with one save bar. Values that were not changed are never sent. */
export function ProfileForm({ profile, ids, icons = {}, layout = 'grid' }: {
  profile: ProfileState
  ids: string[]
  icons?: Record<string, React.ReactNode>
  layout?: 'grid' | 'stack'
}) {
  const shown = useMemo(() => (profile.sections ?? []).filter(s => ids.includes(s.id)), [profile.sections, ids])
  const original = useMemo(() => Object.fromEntries(shown.flatMap(s => s.fields.map(f => [f.key, f.value]))), [shown])
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  const dirty = Object.keys(draft).filter(k => draft[k] !== original[k])
  const get = (k: string) => (k in draft ? draft[k] : original[k] ?? '')
  const set = (k: string, v: string) => { setDraft(d => ({ ...d, [k]: v })); setSaved(false) }

  async function save() {
    setBusy(true); setError('')
    try {
      const { data } = await kbApi.saveProfile(Object.fromEntries(dirty.map(k => [k, draft[k]])))
      profile.setSections(data.sections)
      setDraft({}); setSaved(true)
      setTimeout(() => setSaved(false), 3500)
    } catch (e) {
      setError(apiError(e))
    } finally {
      setBusy(false)
    }
  }

  if (!profile.sections) return profile.error ? <p className="kb-err">{profile.error}</p> : <Loading />

  return (
    <>
      <div className={layout === 'grid' ? 'kb-grid cols-2' : 'kb-grid'}>
        {shown.map(section => {
          const switches = section.fields.filter(f => f.kind === 'yesno')
          const inputs = section.fields.filter(f => f.kind !== 'yesno')
          return (
            <Panel key={section.id} title={section.title} icon={icons[section.id]}>
              {SWITCH_FIRST.has(section.id) ? <>
              {switches.length > 0 && (
                <div className="flex flex-col gap-2.5">
                  {switches.map(f => {
                    const v = get(f.key)
                    return (
                      <div key={f.key} className="kb-switch-row">
                        <div className="min-w-0">
                          <span className="block text-sm font-semibold" style={{ color: 'var(--ink)' }}>
                            {f.label}
                          </span>
                          <span className="kb-meta">
                            {v === '' ? 'Not recorded' : v === 'yes' ? 'Yes' : 'No'}{f.hint ? ` · ${f.hint}` : ''}
                          </span>
                          <div className="mt-1"><AttachChip ownerKey={f.key} label={f.label} inline /></div>
                        </div>
                        <Switch value={v === '' ? null : v === 'yes'} risk={RISK.has(f.key)} label={f.label} onChange={on => set(f.key, on ? 'yes' : 'no')} />
                      </div>
                    )
                  })}
                </div>
              )}
              {inputs.length > 0 && (
                <div className="kb-fields">
                  {inputs.map(f => (
                    <div key={f.key} className={`${f.kind === 'longtext' ? 'span-2' : ''} `}>
                      <div className="kb-label-row">
                        <label className="kb-label" htmlFor={`p-${f.key}`}>
                          {f.label} {f.sensitive && <Lock size={10} className="inline -mt-0.5" aria-label="hidden on screen" />}
                        </label>
                        <AttachChip ownerKey={f.key} label={f.label} inline />
                      </div>
                      {f.kind === 'longtext' ? (
                        <textarea id={`p-${f.key}`} className="kb-textarea" rows={2} value={get(f.key)} onChange={e => set(f.key, e.target.value)} />
                      ) : f.kind.startsWith('choice:') ? (
                        <select id={`p-${f.key}`} className="kb-select" value={get(f.key)} onChange={e => set(f.key, e.target.value)}>
                          <option value="">Not set</option>
                          {f.kind.slice(7).split('|').map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : (
                        <input id={`p-${f.key}`} className={`kb-input ${/^(cin|pan|tan|gstin|gem_seller_id|msme_registration|epf_registration|esi_registration|ifsc_code|bank_account_number)$/.test(f.key) ? 'is-mono' : ''}`}
                          type={f.kind === 'number' ? 'number' : 'text'} value={get(f.key)} onChange={e => set(f.key, e.target.value)} />
                      )}
                      {f.hint && <p className="kb-hint">{f.hint}</p>}
                    </div>
                  ))}
                </div>
              )}
              </> : <>
              {inputs.length > 0 && (
                <div className="kb-fields">
                  {inputs.map(f => (
                    <div key={f.key} className={`${f.kind === 'longtext' ? 'span-2' : ''} `}>
                      <div className="kb-label-row">
                        <label className="kb-label" htmlFor={`p-${f.key}`}>
                          {f.label} {f.sensitive && <Lock size={10} className="inline -mt-0.5" aria-label="hidden on screen" />}
                        </label>
                        <AttachChip ownerKey={f.key} label={f.label} inline />
                      </div>
                      {f.kind === 'longtext' ? (
                        <textarea id={`p-${f.key}`} className="kb-textarea" rows={2} value={get(f.key)} onChange={e => set(f.key, e.target.value)} />
                      ) : f.kind.startsWith('choice:') ? (
                        <select id={`p-${f.key}`} className="kb-select" value={get(f.key)} onChange={e => set(f.key, e.target.value)}>
                          <option value="">Not set</option>
                          {f.kind.slice(7).split('|').map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : (
                        <input id={`p-${f.key}`} className={`kb-input ${/^(cin|pan|tan|gstin|gem_seller_id|msme_registration|epf_registration|esi_registration|ifsc_code|bank_account_number)$/.test(f.key) ? 'is-mono' : ''}`}
                          type={f.kind === 'number' ? 'number' : 'text'} value={get(f.key)} onChange={e => set(f.key, e.target.value)} />
                      )}
                      {f.hint && <p className="kb-hint">{f.hint}</p>}
                    </div>
                  ))}
                </div>
              )}
              {switches.length > 0 && (
                <div className="flex flex-col gap-2.5">
                  {switches.map(f => {
                    const v = get(f.key)
                    return (
                      <div key={f.key} className="kb-switch-row">
                        <div className="min-w-0">
                          <span className="block text-sm font-semibold" style={{ color: 'var(--ink)' }}>
                            {f.label}
                          </span>
                          <span className="kb-meta">
                            {v === '' ? 'Not recorded' : v === 'yes' ? 'Yes' : 'No'}{f.hint ? ` · ${f.hint}` : ''}
                          </span>
                          <div className="mt-1"><AttachChip ownerKey={f.key} label={f.label} inline /></div>
                        </div>
                        <Switch value={v === '' ? null : v === 'yes'} risk={RISK.has(f.key)} label={f.label} onChange={on => set(f.key, on ? 'yes' : 'no')} />
                      </div>
                    )
                  })}
                </div>
              )}
              </>}
            </Panel>
          )
        })}
      </div>

      {(dirty.length > 0 || saved || error) && (
        <div className="kb-savebar" role="status">
          <span className={error ? 'kb-err' : saved ? 'kb-ok' : 'kb-meta'}>
            {error || (saved ? <><CheckCircle2 size={15} /> Saved</> : `${dirty.length} unsaved change${dirty.length === 1 ? '' : 's'}`)}
          </span>
          <div className="flex gap-2">
            <button className="kb-btn ghost" onClick={() => { setDraft({}); setError('') }} disabled={busy || !dirty.length}><RotateCcw size={14} /> Discard</button>
            <button className="kb-btn primary" onClick={save} disabled={busy || !dirty.length}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save changes
            </button>
          </div>
        </div>
      )}
    </>
  )
}
