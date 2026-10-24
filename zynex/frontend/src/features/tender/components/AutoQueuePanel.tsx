import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowClockwise, CaretDown, CaretRight, Robot } from '@phosphor-icons/react'
import { tigerApi, type AutoQueue, type AutoQueueItem } from '../tigerApi'

/** The automatic-analysis queue: what n8n sent, what is running, each outcome, and "Analyse again". */
const LABEL: Record<AutoQueueItem['status'], string> = {
  waiting: 'Waiting', running: 'Analysing…', done: 'Done', failed: 'Failed', stopped: 'Stopped',
  no_documents: 'No tender document', skipped: 'Skipped',
}
const VERDICT: Record<string, string> = {
  ELIGIBLE: '✅ Eligible', PARTIAL: '⚠️ Partially eligible', PENDING: '⚠️ Cannot confirm yet', NOT_ELIGIBLE: '❌ Not eligible',
}

export function AutoQueuePanel() {
  const navigate = useNavigate()
  const [q, setQ] = useState<AutoQueue | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(() => { tigerApi.queue().then(setQ).catch(() => setQ(null)) }, [])
  useEffect(() => {
    load()
    const t = window.setInterval(load, 15000)
    return () => window.clearInterval(t)
  }, [load])

  if (!q || (!q.enabled && q.items.length === 0)) return null
  const running = q.items.find(i => i.status === 'running')
  const waiting = q.counts.waiting || 0

  const again = async (tid: string) => {
    setBusy(tid)
    try { await tigerApi.requeue(tid); load() } finally { setBusy(null) }
  }

  return (
    <div className="zx-panel" style={{ padding: '0.75rem 1rem', height: 'auto' }}>
      <button type="button" className="flex items-center gap-2 w-full text-left" onClick={() => setOpen(o => !o)}>
        {open ? <CaretDown size={14} /> : <CaretRight size={14} />}
        <Robot size={18} />
        <b>Automatic analysis</b>
        <span className="text-sm text-gray-500">
          {!q.enabled ? 'switched off (Settings > Tender Analysis)'
            : running ? `analysing TID ${running.tid}${waiting ? `, ${waiting} waiting` : ''}`
            : waiting ? `${waiting} waiting` : 'idle'}
          {' · '}{q.counts.done || 0} done{q.counts.stopped ? ` · ${q.counts.stopped} stopped` : ''}{q.counts.failed ? ` · ${q.counts.failed} failed` : ''}
        </span>
      </button>
      {open && (
        <div className="mt-3 overflow-x-auto">
          <table className="data-table w-full text-sm">
            <thead><tr><th>Tender</th><th>Status</th><th>Documents analysed</th><th>Teams</th><th></th></tr></thead>
            <tbody>
              {q.items.map(i => (
                <tr key={i.tid}>
                  <td>
                    <button type="button" className="text-left hover:underline" onClick={() => navigate(`/tender/tiger/${encodeURIComponent(i.tid)}`)}>
                      <b>{(i.tender_title || 'Untitled tender').slice(0, 80)}</b>
                    </button>
                    <div className="text-xs text-gray-500">TID {i.tid}{i.organization ? ` · ${i.organization}` : ''}{i.due_date ? ` · due ${i.due_date}` : ''}</div>
                  </td>
                  <td>
                    {i.status === 'done' && i.verdict ? VERDICT[i.verdict] || i.verdict : LABEL[i.status]}
                    {i.reason && i.status !== 'done' && <div className="text-xs text-gray-500">{i.reason}{i.stage ? ` (step ${i.stage})` : ''}</div>}
                  </td>
                  <td className="text-xs">{(i.documents?.analyse || []).map(d => `${d.name} (${d.pages}p)`).join(', ') || '—'}</td>
                  <td className="text-xs">{i.teams_sent_at ? 'sent' : i.teams_error ? <span title={i.teams_error}>not sent</span> : '—'}</td>
                  <td className="whitespace-nowrap text-right">
                    {i.status === 'done' && i.report_id && (
                      <button type="button" className="btn-secondary text-xs mr-2" onClick={() => navigate(`/tender/report/${i.report_id}`)}>Report</button>
                    )}
                    {i.status !== 'running' && i.status !== 'waiting' && (
                      <button type="button" className="btn-secondary text-xs" disabled={busy === i.tid} onClick={() => again(i.tid)}>
                        <ArrowClockwise size={12} className="inline mr-1" />Analyse again
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
