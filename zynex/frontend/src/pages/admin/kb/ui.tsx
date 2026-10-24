import React, { useEffect, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import './kb.css'

// ── formatting ────────────────────────────────────────────────────────────────

/** 12345678 -> "₹1.23 Cr" (the knowledge base stores rupees; tenders talk in crore and lakh). */
export function inrShort(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—'
  const v = Number(n)
  if (Math.abs(v) >= 1e7) return `₹${(v / 1e7).toLocaleString('en-IN', { maximumFractionDigits: 2 })} Cr`
  if (Math.abs(v) >= 1e5) return `₹${(v / 1e5).toLocaleString('en-IN', { maximumFractionDigits: 2 })} L`
  return `₹${v.toLocaleString('en-IN')}`
}

export function inrFull(n: number | null | undefined): string {
  return n === null || n === undefined ? '—' : `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

/** 2024 -> "FY 2023-24" */
export const fyLabel = (end: number) => `FY ${end - 1}-${String(end).slice(2)}`

export function dateText(d: string | null | undefined): string {
  if (!d) return '—'
  const t = new Date(d)
  return Number.isNaN(t.getTime()) ? d : t.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function apiError(e: unknown, fallback = 'Could not save. Check the values and try again.'): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d) && d[0]?.msg) return `${d[0].loc?.slice(-1)?.[0] ?? 'Value'}: ${d[0].msg}`
  return fallback
}

// ── small pieces ──────────────────────────────────────────────────────────────

export function SampleMark({ title = 'A placeholder value. Confirm or replace it with the real one.' }: { title?: string }) {
  return <span className="kb-sample" title={title}>Sample</span>
}

export function Panel({ icon, title, sub, action, children, className = '' }: {
  icon?: React.ReactNode; title?: string; sub?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; className?: string
}) {
  return (
    <section className={`kb-panel ${className}`}>
      {(title || action) && (
        <div className="kb-panel-head">
          <div>
            {title && <h3 className="kb-h">{icon}{title}</h3>}
            {sub && <p className="kb-sub">{sub}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <div className="kb-empty" role="status"><Loader2 size={16} className="animate-spin inline mr-2" />{label}</div>
}

export function Switch({ value, onChange, risk = false, label }: { value: boolean | null; onChange: (v: boolean) => void; risk?: boolean; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={value === true} aria-label={label}
      onClick={() => onChange(!(value === true))}
      className={`kb-switch ${value === true ? 'on' : ''} ${risk ? 'risk' : ''} ${value === null ? 'unset' : ''}`} />
  )
}

// ── generic record editor (one modal for every entity) ───────────────────────

export type FieldType = 'text' | 'number' | 'date' | 'select' | 'textarea' | 'list' | 'bool'
export interface FieldDef {
  key: string
  label: string
  type?: FieldType
  options?: ({ value: string | number; label: string } | string)[]
  span2?: boolean
  required?: boolean
  mono?: boolean
  hint?: string
  placeholder?: string
}

function toForm(v: any, t: FieldType | undefined): any {
  if (t === 'list') return Array.isArray(v) ? v.join(', ') : (v ?? '')
  if (t === 'bool') return v === true
  return v ?? ''
}

function fromForm(v: any, t: FieldType | undefined): any {
  if (t === 'bool') return v === true
  if (t === 'number') return v === '' || v === null ? null : Number(v)
  if (t === 'list') return String(v).split(/[,;\n]/).map(x => x.trim()).filter(Boolean)
  const s = typeof v === 'string' ? v.trim() : v
  return s === '' ? null : s
}

export function RecordModal<T extends Record<string, any>>({ title, fields, initial, onSave, onClose, wide = false }: {
  title: string
  fields: FieldDef[]
  initial: Partial<T>
  onSave: (values: Record<string, any>) => Promise<void>
  onClose: () => void
  wide?: boolean
}) {
  const [form, setForm] = useState<Record<string, any>>(() => Object.fromEntries(fields.map(f => [f.key, toForm((initial as any)[f.key], f.type)])))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const missing = fields.find(f => f.required && !String(form[f.key] ?? '').trim())
    if (missing) { setError(`${missing.label} is required.`); return }
    setBusy(true); setError('')
    try {
      await onSave(Object.fromEntries(fields.map(f => [f.key, fromForm(form[f.key], f.type)])))
      onClose()
    } catch (err) {
      setError(apiError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="kb-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <form className={`kb-modal ${wide ? 'wide' : ''}`} onSubmit={submit} role="dialog" aria-modal="true" aria-label={title}>
        <div className="flex items-start justify-between gap-3">
          <h3 className="kb-h" style={{ fontSize: '1.2rem' }}>{title}</h3>
          <button type="button" className="kb-icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="kb-fields">
          {fields.map(f => (
            <div key={f.key} className={f.span2 || f.type === 'textarea' ? 'span-2' : ''}>
              {f.type === 'bool' ? (
                <div className="kb-switch-row" style={{ padding: '0.6rem 0.9rem' }}>
                  <span className="kb-label" style={{ margin: 0 }}>{f.label}</span>
                  <Switch value={form[f.key] === true} onChange={v => setForm({ ...form, [f.key]: v })} label={f.label} />
                </div>
              ) : (
                <>
                  <label className="kb-label" htmlFor={`f-${f.key}`}>{f.label}{f.required && ' *'}</label>
                  {f.type === 'textarea' ? (
                    <textarea id={`f-${f.key}`} className="kb-textarea" rows={3} value={form[f.key]} placeholder={f.placeholder}
                      onChange={e => setForm({ ...form, [f.key]: e.target.value })} />
                  ) : f.type === 'select' ? (
                    <select id={`f-${f.key}`} className="kb-select" value={form[f.key]} onChange={e => setForm({ ...form, [f.key]: e.target.value })}>
                      <option value="">Not set</option>
                      {(f.options ?? []).map(o => typeof o === 'string'
                        ? <option key={o} value={o}>{o}</option>
                        : <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  ) : (
                    <input id={`f-${f.key}`} className={`kb-input ${f.mono ? 'is-mono' : ''}`} value={form[f.key]} placeholder={f.placeholder}
                      type={f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text'} step={f.type === 'number' ? 'any' : undefined}
                      onChange={e => setForm({ ...form, [f.key]: e.target.value })} />
                  )}
                  {f.hint && <p className="kb-hint">{f.hint}</p>}
                </>
              )}
            </div>
          ))}
        </div>
        {error && <p className="kb-err" role="alert">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="kb-btn ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="kb-btn primary" disabled={busy}>
            {busy && <Loader2 size={14} className="animate-spin" />} Save
          </button>
        </div>
      </form>
    </div>
  )
}

// ── confirm-before-delete ─────────────────────────────────────────────────────

export function useConfirm() {
  return (what: string) => window.confirm(`Delete ${what}? This cannot be undone.`)
}
