import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, BarChart2, Database, FileText, Loader2, CalendarClock, Building2 } from 'lucide-react'
import { Folders, SealCheck, Hourglass, WarningOctagon, Binoculars } from '@phosphor-icons/react'
import { TrendChart, RadialRings, Columns, HBars, Sparkline } from '../../components/dashboard/Charts'
import { RunBadge } from '../../features/tender/pages/TenderTiger'
import { outcomeOf } from '../../features/tender/outcome'
import { tigerApi, daysLeft, formatDate, type TigerList } from '../../features/tender/tigerApi'
import { useAuthStore } from '../../store/authStore'
import { documentsApi } from '../../api/documents'
import { tenderApi, type TenderHistoryItem } from '../../features/tender/api'

// ---------------------------------------------------------------------------
// Inline AI Chat widget (no persistence — for quick access on dashboard)
// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

// a missing or unreadable date shows a dash instead of "Invalid Date"
function shortDate(value: string | undefined): string {
  const d = value ? new Date(value) : null
  return d && !isNaN(d.getTime()) ? d.toLocaleDateString(undefined, { day: '2-digit', month: 'short' }) : '—'
}

function timeAgo(value: string | undefined): string {
  const t = value ? new Date(value).getTime() : NaN
  if (isNaN(t)) return '—'
  const m = Math.round((Date.now() - t) / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h} h ago`
  const d = Math.round(h / 24)
  return d < 7 ? `${d} day${d === 1 ? '' : 's'} ago` : shortDate(value)
}

// One result per tender run, read from the run itself (the document row is marked analysed at upload time,
// before the analysis has finished, so it cannot tell whether a run is still going).
type RunResult = 'running' | 'eligible' | 'partial' | 'unconfirmed' | 'not_eligible' | 'failed' | 'stopped'

function resultOf(r: TenderHistoryItem): RunResult {
  if (r.status === 'processing') return 'running'
  if (r.status === 'failed') return 'failed'
  if (r.status === 'cancelled') return 'stopped'
  return outcomeOf(r.verdict, r.met)
}

const RESULT_LOOK: Record<RunResult, { label: string; chip: string }> = {
  running:      { label: 'Analysing',          chip: 'is-info' },
  eligible:     { label: 'Eligible',           chip: 'is-ok' },
  partial:      { label: 'Partially eligible', chip: 'is-warn' },
  unconfirmed:  { label: 'Cannot confirm yet', chip: 'is-review' },
  not_eligible: { label: 'Not eligible',       chip: 'is-bad' },
  failed:       { label: 'Run failed',         chip: 'is-bad' },
  stopped:      { label: 'Stopped',            chip: '' },
}

function RunChip({ result }: { result: RunResult }) {
  const look = RESULT_LOOK[result]
  return (
    <span className={`zx-chip ${look.chip} whitespace-nowrap`}>
      {result === 'running' && <Loader2 size={11} className="animate-spin" />}
      {look.label}
    </span>
  )
}

function lastDays(n: number): Date[] {
  return Array.from({ length: n }, (_, i) => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - (n - 1 - i)); return d })
}
function perDay(runs: TenderHistoryItem[], days: Date[], keep: (r: TenderHistoryItem) => boolean): number[] {
  return days.map(d => {
    const next = new Date(d); next.setDate(d.getDate() + 1)
    return runs.filter(r => { const t = new Date(r.created_at); return t >= d && t < next && keep(r) }).length
  })
}

function Panel({ title, sub, action, children, className = '' }: {
  title: string; sub?: string; action?: React.ReactNode; children: React.ReactNode; className?: string
}) {
  return (
    <section className={`zx-panel ${className}`}>
      <header className="zx-panel-head">
        <div className="min-w-0">
          <h2>{title}</h2>
          {sub && <p>{sub}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  )
}

/** Runs started vs. completed per day, last 14 days. */
function ActivityPanel({ runs }: { runs: TenderHistoryItem[] }) {
  const days = lastDays(14)
  const started = perDay(runs, days, () => true)
  const completed = perDay(runs, days, r => r.status === 'completed')
  const series = [
    { key: 'started', label: 'Runs started', values: started, color: 'var(--c-series-1)' },
    { key: 'completed', label: 'Completed', values: completed, color: 'var(--c-series-2)' },
  ]
  const labels = days.map((d, i) => i === 13 ? 'Today' : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }))
  const sum = (v: number[]) => v.reduce((t, x) => t + x, 0)
  return (
    <Panel title="Analysis activity" sub="Last 14 days"
      action={
        <ul className="zx-legend" aria-label="Legend">
          {series.map(s => <li key={s.key}><i className="zx-swatch" style={{ background: s.color }} />{s.label} <b>{sum(s.values)}</b></li>)}
        </ul>
      }>
      <TrendChart labels={labels} series={series} height={292}
        ariaLabel={`Runs started and completed per day for the last 14 days. Started ${sum(started)}, completed ${sum(completed)}.`} />
    </Panel>
  )
}

/** Verdict share as concentric rings. */
function VerdictPanel({ runs }: { runs: TenderHistoryItem[] }) {
  const res = runs.map(resultOf)
  const items = [
    { key: 'eligible', label: 'Eligible', value: res.filter(r => r === 'eligible').length, color: 'var(--s-ok)' },
    { key: 'partial', label: 'Partially eligible', value: res.filter(r => r === 'partial').length, color: 'var(--s-warn)' },
    { key: 'unconfirmed', label: 'Cannot confirm yet', value: res.filter(r => r === 'unconfirmed').length, color: 'var(--s-review)' },
    { key: 'not_eligible', label: 'Not eligible', value: res.filter(r => r === 'not_eligible').length, color: 'var(--s-bad)' },
  ]
  const total = items.reduce((t, i) => t + i.value, 0)
  return (
    <Panel title="Verdicts" sub="Every completed analysis">
      {total === 0
        ? <p className="text-sm py-8 text-center" style={{ color: 'var(--ink-3)' }}>No completed analyses yet.</p>
        : <div className="py-2"><RadialRings items={items} total={total} centerLabel="checked" /></div>}
    </Panel>
  )
}

/** Open Tender Tiger notices: deadlines per week ahead, and who publishes most. */
function useTigerInsights() {
  const [weeks, setWeeks] = useState<{ label: string; value: number; hint: string }[] | null>(null)
  const [orgs, setOrgs] = useState<{ label: string; value: number }[] | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    tigerApi.list({ search: '', status: 'open', org: '', sort: 'due_asc', page: 1, page_size: 50 })
      .then(d => {
        const start = new Date(); start.setHours(0, 0, 0, 0)
        setWeeks(Array.from({ length: 5 }, (_, i) => {
          const from = new Date(start); from.setDate(start.getDate() + i * 7)
          const to = new Date(from); to.setDate(from.getDate() + 7)
          const value = d.items.filter(t => { const due = t.due_date ? new Date(t.due_date) : null; return due && due >= from && due < to }).length
          const f = (x: Date) => x.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
          return { label: i === 0 ? 'This week' : `+${i} wk`, value, hint: `${value} due ${f(from)} – ${f(new Date(to.getTime() - 864e5))}` }
        }))
      })
      .catch(() => setFailed(true))
    tigerApi.organizations()
      .then(o => setOrgs(o.sort((a, b) => b.count - a.count).slice(0, 6).map(x => ({ label: x.name, value: x.count }))))
      .catch(() => setFailed(true))
  }, [])
  return { weeks, orgs, failed }
}

function DeadlinesPanel({ weeks }: { weeks: { label: string; value: number; hint: string }[] | null }) {
  return (
    <Panel title="Deadlines ahead" sub="Open tenders due per week"
      action={<Link to="/tender/tiger?status=open&sort=due_asc" className="zx-panel-link">Open list <ArrowRight size={12} /></Link>}>
      {weeks ? <Columns items={weeks} highlight={0} height={170} /> : <div className="zx-skel rounded-xl" style={{ height: 170 }} />}
    </Panel>
  )
}

function OrgsPanel({ orgs }: { orgs: { label: string; value: number }[] | null }) {
  return (
    <Panel title="Most active organisations" sub="Tenders collected, top 6">
      {orgs ? <HBars items={orgs} /> : <div className="zx-skel rounded-xl" style={{ height: 150 }} />}
    </Panel>
  )
}

/** The latest notices Tender Tiger collected, with the result of the last eligibility check on any of their files. */
function TenderLog() {
  const navigate = useNavigate()
  const [data, setData] = useState<TigerList | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    tigerApi.list({ search: '', status: 'all', org: '', sort: 'published_desc', page: 1, page_size: 20 }).then(setData).catch(() => setFailed(true))
  }, [])
  return (
    <section className="zx-panel zx-log">
      <header className="zx-panel-head">
        <div className="min-w-0">
          <h2>Latest tenders from Tender Tiger</h2>
          <p>{data ? `${data.summary.total} collected · ${data.summary.open} open · ${data.summary.closing_soon} close within 7 days` : 'Newest notices first'}</p>
        </div>
        <Link to="/tender/tiger?sort=published_desc" className="zx-panel-link">All tenders <ArrowRight size={12} /></Link>
      </header>
      {failed ? <p className="text-sm py-6 text-center" style={{ color: 'var(--ink-3)' }}>Tender Tiger data is not available.</p>
        : !data ? <div className="space-y-2">{[0, 1, 2, 3, 4, 5].map(i => <div key={i} className="zx-skel" style={{ height: '3.2rem' }} />)}</div>
        : data.items.length === 0 ? <p className="text-sm py-6 text-center" style={{ color: 'var(--ink-3)' }}>No tenders collected yet.</p>
        : (
          <div className="zx-log-table" role="table" aria-label="Latest tenders">
            <div className="zx-log-row is-head" role="row">
              <span role="columnheader">Tender</span><span role="columnheader">Published</span><span role="columnheader">Due</span><span role="columnheader">Eligibility</span>
            </div>
            {data.items.map(t => {
              const d = daysLeft(t.due_date)
              const tone = d === null ? '' : d < 0 ? '' : d <= 3 ? 'is-bad' : d <= 7 ? 'is-warn' : 'is-ok'
              return (
                <div key={t.tid} role="row" className="zx-log-row" tabIndex={0}
                  onClick={() => navigate(`/tender/tiger/${t.tid}`)} onKeyDown={e => { if (e.key === 'Enter') navigate(`/tender/tiger/${t.tid}`) }}>
                  <span className="min-w-0" role="cell">
                    <b className="zx-log-title" title={t.tender_title || ''}>{t.tender_title || 'Untitled tender'}</b>
                    <small className="zx-log-sub"><Building2 size={11} />{t.organization || '—'}{t.key_location ? ` · ${t.key_location.split(',')[0]}` : ''}</small>
                  </span>
                  <span role="cell" className="zx-log-muted">{t.published_date ? formatDate(t.published_date) : '—'}</span>
                  <span role="cell">
                    <span className="zx-log-muted block">{formatDate(t.due_date)}</span>
                    {d !== null && <span className={`zx-chip ${tone}`}>{d < 0 ? 'Closed' : d === 0 ? 'Today' : `${d} day${d === 1 ? '' : 's'}`}</span>}
                  </span>
                  <span role="cell" onClick={e => e.stopPropagation()}>
                    <RunBadge run={t.last_run} onOpen={() => t.last_run && navigate(t.last_run.state === 'RUNNING' ? `/tender/processing/${t.last_run.run_id}` : `/tender/report/${t.last_run.run_id}`)} />
                  </span>
                </div>
              )
            })}
          </div>
        )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Closing soon: open Tender Tiger notices, soonest deadline first (read-only)
// ---------------------------------------------------------------------------

function ClosingSoon() {
  const [data, setData] = useState<TigerList | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    tigerApi.list({ search: '', status: 'open', org: '', sort: 'due_asc', page: 1, page_size: 5 })
      .then(setData)
      .catch(() => setFailed(true))
  }, [])

  if (failed) return null
  const s = data?.summary

  return (
    <div className="bg-white rounded-2xl border overflow-hidden min-w-0">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="zx-file" style={{ color: '#d97706', background: 'color-mix(in srgb, #d97706 12%, transparent)', borderColor: 'color-mix(in srgb, #d97706 25%, transparent)' }}><Binoculars size={17} /></span>
          <div className="min-w-0">
            <h2 className="font-semibold text-slate-800" style={{ fontFamily: 'var(--font-heading)' }}>Closing soon</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {s ? `${s.open} open tenders · ${s.closing_soon} close within 7 days` : 'Open Tender Tiger notices'}
            </p>
          </div>
        </div>
        <Link to="/tender/tiger?status=open&sort=due_asc" className="text-xs font-semibold inline-flex items-center gap-1 flex-shrink-0" style={{ color: 'var(--brand-blue-dark)' }}>All tenders <ArrowRight size={12} /></Link>
      </div>
      {!data ? (
        <div className="p-5 space-y-3">{[0, 1, 2].map(i => <div key={i} className="zx-skel" style={{ height: '3rem' }} />)}</div>
      ) : data.items.length === 0 ? (
        <p className="px-5 py-8 text-sm text-center text-slate-500">No open tenders right now.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {data.items.map(t => {
            const d = daysLeft(t.due_date)
            const tone = d !== null && d <= 3 ? 'is-bad' : d !== null && d <= 7 ? 'is-warn' : 'is-ok'
            return (
              <li key={t.tid}>
                <Link to={`/tender/tiger/${t.tid}`} className="flex items-center gap-4 px-5 py-3 hover:bg-slate-50 transition-colors group">
                  <div className="zx-due">
                    <span className="zx-due-day">{t.due_date ? new Date(t.due_date).getDate() : '—'}</span>
                    <span className="zx-due-mon">{t.due_date ? new Date(t.due_date).toLocaleString('en', { month: 'short' }) : ''}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-slate-800 truncate group-hover:text-[#014BAA] transition-colors" title={t.tender_title || ''}>{t.tender_title || 'Untitled tender'}</p>
                    <p className="text-xs text-slate-500 truncate flex items-center gap-1.5"><Building2 size={11} className="flex-shrink-0" />{t.organization || '—'}</p>
                  </div>
                  <span className={`zx-chip ${tone} whitespace-nowrap hidden sm:inline-flex`} title={`Due ${formatDate(t.due_date)}`}>
                    <CalendarClock size={11} /> {d === null ? '—' : d === 0 ? 'Today' : `${d} day${d === 1 ? '' : 's'}`}
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Dashboard page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const [runs, setRuns] = useState<TenderHistoryItem[]>([])
  const [docCount, setDocCount] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  // the run list is the source of truth for status; refresh it while anything is still running
  useEffect(() => {
    let alive = true
    let timer: number | undefined
    const load = () => tenderApi.getHistory()
      .then(r => { if (!alive) return; setRuns(r); if (r.some(x => x.status === 'processing')) timer = window.setTimeout(load, 5000) })
      .catch(() => { /* keep what is shown */ })
      .finally(() => alive && setLoading(false))
    load()
    documentsApi.list().then(r => alive && setDocCount(r.data.length)).catch(() => {})
    const onFocus = () => { window.clearTimeout(timer); load() }
    window.addEventListener('focus', onFocus)
    return () => { alive = false; window.clearTimeout(timer); window.removeEventListener('focus', onFocus) }
  }, [])

  const results = runs.map(resultOf)
  const running  = results.filter(r => r === 'running').length
  const done     = results.filter(r => r === 'eligible' || r === 'partial' || r === 'not_eligible').length
  const eligible = results.filter(r => r === 'eligible').length
  const attention = results.filter(r => r === 'partial' || r === 'not_eligible').length
  const failed   = results.filter(r => r === 'failed' || r === 'stopped').length
  const weekAgo = Date.now() - 7 * 864e5
  const thisWeek = runs.filter(r => new Date(r.created_at).getTime() >= weekAgo).length

  const tiger = useTigerInsights()
  const days14 = lastDays(14)
  const stats = [
    { label: 'Tenders analysed', value: done,      icon: Folders,        accent: 'var(--c-series-1)', hint: thisWeek ? `${thisWeek} run${thisWeek === 1 ? '' : 's'} this week` : 'none this week',
      spark: perDay(runs, days14, r => r.status === 'completed') },
    { label: 'Analysing now',    value: running,   icon: Hourglass,      accent: '#0f8a9d', hint: running ? 'updates on its own' : 'queue is empty', pulse: running > 0,
      spark: perDay(runs, days14, () => true) },
    { label: 'Eligible',         value: eligible,  icon: SealCheck,      accent: 'var(--s-ok)', hint: done ? `${Math.round((eligible / done) * 100)}% of completed` : 'no results yet',
      spark: perDay(runs, days14, r => r.verdict === 'PASS') },
    { label: 'Need a look',      value: attention, icon: WarningOctagon, accent: 'var(--s-warn)', hint: failed ? `plus ${failed} failed or stopped` : 'cannot confirm or not eligible',
      spark: perDay(runs, days14, r => r.verdict === 'PARTIAL' || r.verdict === 'FAIL') },
  ]
  const name = (useAuthStore.getState().fullName || 'there').split(' ')[0]
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="flex flex-col gap-6 max-w-[1500px]">
      <div className="zx-page-head">
        <div>
          <span className="zx-eyebrow-line">Overview</span>
          <h1 className="mt-1">{greeting}, {name}</h1>
          <p>
            {running > 0
              ? <>{running} analysis{running === 1 ? ' is' : 'es are'} running now. This page updates when {running === 1 ? 'it finishes' : 'they finish'}.</>
              : <>Your tender work at a glance{docCount !== null ? ` · ${docCount} documents in the library` : ''}. Everything runs on your own servers.</>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/tender" className="zx-action primary">Evaluate a tender <ArrowRight size={14} /></Link>
          <Link to="/estimation" className="zx-action"><BarChart2 size={14} /> New estimate</Link>
          <Link to="/knowledge-base" className="zx-action"><Database size={14} /> Company data</Link>
        </div>
      </div>

      {/* Stat tiles with a 14-day sparkline each */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4 zx-stagger">
        {stats.map(({ label, value, icon: Icon, accent, hint, pulse, spark }) => (
          <div key={label} className="zx-kpi" style={{ ['--accent' as string]: accent }}>
            <div className="flex items-start justify-between gap-3">
              <div className={`zx-stat-icon ${pulse ? 'is-pulsing' : ''}`}><Icon size={22} /></div>
              {!loading && <Sparkline values={spark} />}
            </div>
            {loading ? <div className="zx-skel mt-4" style={{ width: '3rem', height: '2rem' }} /> : <p className="zx-stat-value mt-4">{value}</p>}
            <p className="zx-stat-label">{label}</p>
            {!loading && <p className="zx-stat-hint">{hint}</p>}
          </div>
        ))}
      </div>

      {/* Latest tenders + deadlines column */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5 items-stretch">
        <div className="xl:col-span-2 min-w-0 zx-log-cell"><TenderLog /></div>
        <div className="flex flex-col gap-5 min-w-0 zx-side-col">
          <ClosingSoon />
          {!tiger.failed && <DeadlinesPanel weeks={tiger.weeks} />}
          {loading ? <div className="zx-skel rounded-2xl" style={{ height: 300 }} /> : <VerdictPanel runs={runs} />}
        </div>
      </div>

      {/* Activity + organisations */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5 items-start">
        <div className="xl:col-span-2 min-w-0">{loading ? <div className="zx-skel rounded-2xl" style={{ height: 300 }} /> : <ActivityPanel runs={runs} />}</div>
        {!tiger.failed && <div className="min-w-0"><OrgsPanel orgs={tiger.orgs} /></div>}
      </div>

      {/* Recent analyses */}
      <section className="zx-panel" style={{ padding: 0, overflow: 'hidden' }}>
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold text-slate-800" style={{ fontFamily: 'var(--font-heading)' }}>Recent analyses</h2>
            <p className="text-xs text-slate-500 mt-0.5">Status is read from each run and refreshes while one is running</p>
          </div>
          <Link to="/tender/history" className="zx-panel-link">Audit history <ArrowRight size={12} /></Link>
        </div>
        {loading ? (
          <div className="p-5 space-y-3" role="status" aria-label="Loading analyses">{[0, 1, 2].map(i => <div key={i} className="zx-skel" style={{ height: '2.6rem' }} />)}</div>
        ) : runs.length === 0 ? (
          <p className="px-5 py-10 text-sm text-center text-slate-500">No tenders analysed yet. <Link to="/tender" className="zx-panel-link">Evaluate a tender</Link></p>
        ) : (
          <ul className="zx-run-grid">
            {runs.slice(0, 6).map(r => {
              const res = resultOf(r)
              const to = res === 'running' ? `/tender/processing/${r.run_id}` : `/tender/report/${r.run_id}`
              return (
                <li key={r.run_id}>
                  <Link to={to} className="zx-run-row group">
                    <span className={`zx-file ${res === 'running' ? 'is-live' : ''}`}><FileText size={15} /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-slate-800 truncate group-hover:text-[#014BAA] transition-colors" title={r.filename}>{r.filename}</span>
                      <span className="block text-xs text-slate-500">Run {r.run_id} · {timeAgo(r.created_at)}{r.total ? ` · ${r.met ?? 0}/${r.total} met` : ''}</span>
                    </span>
                    <RunChip result={res} />
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}
