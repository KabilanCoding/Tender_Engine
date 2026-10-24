import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, FolderOpen, Search, X } from 'lucide-react'
import { Briefcase, CalendarBlank, CurrencyInr, Stack, Buildings, Files } from '@phosphor-icons/react'
import { kbApi, type Client, type Project } from '../../api/knowledgeBase'

/** Delivered work from the company knowledge base, as a searchable portfolio (read-only). */

function money(v: number | null | undefined): string {
  if (!v) return '—'
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(v >= 1e9 ? 0 : 2)} Cr`
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`
  return `₹${v.toLocaleString('en-IN')}`
}
function year(d?: string | null): string { return d ? String(new Date(d).getFullYear()) : '' }
function period(p: Project): string {
  const a = year(p.start_date || p.work_order_date), b = year(p.completion_date)
  return a && b ? (a === b ? a : `${a} – ${b}`) : a || b || '—'
}
const STATUS_CHIP: Record<string, string> = { completed: 'is-ok', ongoing: 'is-info', active: 'is-info' }

export default function PastProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [clients, setClients] = useState<Record<number, Client>>({})
  const [failed, setFailed] = useState(false)
  const [q, setQ] = useState('')
  const [domain, setDomain] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)

  useEffect(() => {
    kbApi.listProjects().then(r => setProjects(r.data)).catch(() => { setFailed(true); setProjects([]) })
    kbApi.listClients().then(r => setClients(Object.fromEntries(r.data.map(c => [c.id, c])))).catch(() => {})
  }, [])

  const domains = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of projects ?? []) if (p.domain) m.set(p.domain, (m.get(p.domain) ?? 0) + 1)
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [projects])

  const shown = useMemo(() => {
    const t = q.trim().toLowerCase()
    return (projects ?? [])
      .filter(p => !domain || p.domain === domain)
      .filter(p => !status || (p.status || '').toLowerCase() === status)
      .filter(p => !t || [p.name, p.description, p.domain, p.project_code, clients[p.client_id ?? -1]?.name, ...(p.technologies ?? [])]
        .some(v => v && String(v).toLowerCase().includes(t)))
      .sort((a, b) => (b.completion_date || b.start_date || '').localeCompare(a.completion_date || a.start_date || ''))
  }, [projects, q, domain, status, clients])

  const total = (projects ?? []).reduce((t, p) => t + (p.total_value || 0), 0)
  const completed = (projects ?? []).filter(p => (p.status || '').toLowerCase() === 'completed').length
  const techCount = new Set((projects ?? []).flatMap(p => p.technologies ?? [])).size
  const clientCount = new Set((projects ?? []).map(p => p.client_id).filter(Boolean)).size

  return (
    <div className="flex flex-col gap-6 max-w-[1400px]">
      <div className="zx-page-head">
        <div>
          <span className="zx-eyebrow-line">Library</span>
          <h1 className="mt-1">Past projects</h1>
          <p>Work your company has delivered. The tender check reads these as proof of experience, so keep values and dates complete.</p>
        </div>
        <Link to="/knowledge-base" className="zx-action">Manage in knowledge base <ArrowRight size={14} /></Link>
      </div>

      {projects === null ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">{[0, 1, 2, 3, 4, 5].map(i => <div key={i} className="zx-skel rounded-2xl" style={{ height: 210 }} />)}</div>
      ) : projects.length === 0 ? (
        <div className="zx-empty">
          <div className="zx-empty-icon"><FolderOpen size={28} strokeWidth={1.5} /></div>
          <h2>{failed ? 'Projects could not be loaded' : 'No projects recorded yet'}</h2>
          <p>{failed ? 'Your account may not have access to the company knowledge base. Ask an administrator.' : 'Add delivered projects in the knowledge base; they appear here and are used as proof of experience.'}</p>
          <div className="zx-actions"><Link to="/knowledge-base" className="zx-action primary">Open the knowledge base <ArrowRight size={14} /></Link></div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4 zx-stagger">
            {[
              { icon: Briefcase, label: 'Projects', value: String(projects.length), hint: `${completed} completed`, accent: 'var(--c-series-1)' },
              { icon: CurrencyInr, label: 'Total order value', value: money(total), hint: 'all recorded work orders', accent: 'var(--s-ok)' },
              { icon: Buildings, label: 'Clients', value: String(clientCount), hint: 'distinct organisations', accent: '#0f8a9d' },
              { icon: Stack, label: 'Technologies', value: String(techCount), hint: 'used across projects', accent: 'var(--s-warn)' },
            ].map(c => (
              <div key={c.label} className="zx-kpi" style={{ ['--accent' as string]: c.accent }}>
                <div className="zx-stat-icon"><c.icon size={22} /></div>
                <p className="zx-stat-value mt-4">{c.value}</p>
                <p className="zx-stat-label">{c.label}</p>
                <p className="zx-stat-hint">{c.hint}</p>
              </div>
            ))}
          </div>

          <div className="zx-panel" style={{ padding: '0.9rem 1rem' }}>
            <div className="flex flex-col lg:flex-row lg:items-center gap-3">
              <label className="zx-search flex-1">
                <Search size={15} aria-hidden="true" />
                <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search name, client, technology, code…" aria-label="Search projects" />
                {q && <button type="button" onClick={() => setQ('')} aria-label="Clear search"><X size={14} /></button>}
              </label>
              <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by status">
                {[
                  { id: null, label: 'All', n: projects.length },
                  { id: 'completed', label: 'Completed', n: completed },
                  { id: 'ongoing', label: 'Ongoing', n: projects.filter(p => (p.status || '').toLowerCase() === 'ongoing').length },
                ].map(f => (
                  <button key={f.label} type="button" className={`zx-pill ${status === f.id ? 'is-on' : ''}`} aria-pressed={status === f.id} onClick={() => setStatus(f.id)}>
                    {f.label} <b>{f.n}</b>
                  </button>
                ))}
                <select className="zx-select" value={domain ?? ''} onChange={e => setDomain(e.target.value || null)} aria-label="Domain">
                  <option value="">All domains</option>
                  {domains.map(([d, n]) => <option key={d} value={d}>{d} ({n})</option>)}
                </select>
              </div>
            </div>
          </div>

          {shown.length === 0 ? (
            <p className="text-sm text-center py-10" style={{ color: 'var(--ink-3)' }}>No project matches this search.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 zx-stagger">
              {shown.map(p => {
                const client = clients[p.client_id ?? -1]?.name
                const techs = p.technologies ?? []
                return (
                  <Link key={p.id} to={`/knowledge-base/projects/${p.id}`} className="zx-proj group">
                    <div className="flex items-start justify-between gap-3">
                      <span className="zx-proj-code">{p.project_code || `#${p.id}`}</span>
                      <span className={`zx-chip ${STATUS_CHIP[(p.status || '').toLowerCase()] ?? ''} capitalize`}>{p.status || '—'}</span>
                    </div>
                    <h3 className="zx-proj-title">{p.name}</h3>
                    {client && <p className="zx-proj-client"><Buildings size={13} /> {client}</p>}
                    {p.description && <p className="zx-proj-desc">{p.description}</p>}
                    <div className="zx-proj-meta">
                      <span><CurrencyInr size={14} /> {money(p.total_value)}</span>
                      <span><CalendarBlank size={14} /> {period(p)}</span>
                      {!!p.evidence_files?.length && <span><Files size={14} /> {p.evidence_files.length} file{p.evidence_files.length === 1 ? '' : 's'}</span>}
                    </div>
                    {techs.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-auto pt-3">
                        {techs.slice(0, 4).map(t => <span key={t} className="zx-tag">{t}</span>)}
                        {techs.length > 4 && <span className="zx-tag">+{techs.length - 4}</span>}
                      </div>
                    )}
                    <span className="zx-proj-go" aria-hidden="true"><ArrowRight size={15} /></span>
                  </Link>
                )
              })}
            </div>
          )}
        </>
      )}
    </div>
  )
}
