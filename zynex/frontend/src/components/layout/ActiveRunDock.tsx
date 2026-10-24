import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, CheckCircle2, Loader2, X } from 'lucide-react'
import { tenderApi, type TenderHistoryItem } from '../../features/tender/api'

const STEPS: Record<string, string> = {
  S1: 'Checking the file', S2A: 'Reading the text', S2B: 'Reading scanned pages', S3: 'Finding chapters', S4: 'Splitting into clauses',
  S5: 'Finding eligibility pages', S6: 'AI is listing the requirements', S7: 'Checking quotes', S8: 'Matching company records',
  S9: 'Comparing each requirement', S10: 'Writing explanations', S11: 'Reading the whole tender for the checklist',
}
const stepName = (s?: string) => (s ? STEPS[s.toUpperCase().replace('_REPORT_BUILDER', '')] ?? 'Working' : 'Starting')

/**
 * Follows the user across the app: while a tender analysis runs it shows a small card (file, step, open progress), and when one
 * finishes it says so with a link to the report. Read-only: it only asks for the run list, then the one running run's step.
 */
export default function ActiveRunDock() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [running, setRunning] = useState<TenderHistoryItem[]>([])
  const [step, setStep] = useState<string | undefined>()
  const [finished, setFinished] = useState<TenderHistoryItem | null>(null)
  const known = useRef<Map<string, TenderHistoryItem>>(new Map())
  const idle = useRef(true)

  useEffect(() => {
    let alive = true
    let timer: number | undefined
    const tick = async () => {
      try {
        const runs = await tenderApi.getHistory()
        if (!alive) return
        const now = runs.filter(r => r.status === 'processing')
        // a run that was running and is not any more: tell the user how it ended
        known.current.forEach((old, id) => {
          if (!now.some(r => r.run_id === id)) {
            const after = runs.find(r => r.run_id === id)
            if (after && after.status === 'completed') setFinished(after)
            known.current.delete(id)
          }
        })
        now.forEach(r => known.current.set(r.run_id, r))
        setRunning(now)
        idle.current = now.length === 0
        if (now[0]) tenderApi.getStatus(now[0].run_id).then(s => alive && setStep(s.progress_step)).catch(() => {})
      } catch { /* keep what is shown */ }
      if (alive) timer = window.setTimeout(tick, idle.current ? 15000 : 4000)
    }
    tick()
    return () => { alive = false; window.clearTimeout(timer) }
  }, [])

  // opening the report of a run clears its "finished" notice
  useEffect(() => { if (finished && pathname === `/tender/report/${finished.run_id}`) setFinished(null) }, [pathname, finished])

  const run = running[0]
  const onItsPage = run && pathname === `/tender/processing/${run.run_id}`

  return (
    <div className="zx-dock" aria-live="polite">
      {finished && (
        <div className="zx-dock-card is-done" role="status">
          <CheckCircle2 size={18} className="zx-dock-ic" />
          <div className="min-w-0 flex-1">
            <p className="zx-dock-title">Analysis finished</p>
            <p className="zx-dock-sub" title={finished.filename}>{finished.filename}</p>
          </div>
          <button type="button" className="zx-dock-go" onClick={() => { navigate(`/tender/report/${finished.run_id}`); setFinished(null) }}>View report <ArrowRight size={13} /></button>
          <button type="button" className="zx-dock-x" aria-label="Dismiss" onClick={() => setFinished(null)}><X size={14} /></button>
        </div>
      )}
      {run && !onItsPage && (
        <Link to={`/tender/processing/${run.run_id}`} className="zx-dock-card is-run">
          <Loader2 size={18} className="zx-dock-ic animate-spin" />
          <div className="min-w-0 flex-1">
            <p className="zx-dock-title">Analysing{running.length > 1 ? ` (${running.length} running)` : ''}</p>
            <p className="zx-dock-sub" title={run.filename}>{run.filename}</p>
            <p className="zx-dock-step">{step ? `${step.toUpperCase().replace('_REPORT_BUILDER', '')} · ` : ''}{stepName(step)}</p>
            <span className="zx-dock-bar" aria-hidden="true"><i /></span>
          </div>
          <span className="zx-dock-go">Open <ArrowRight size={13} /></span>
        </Link>
      )}
    </div>
  )
}
