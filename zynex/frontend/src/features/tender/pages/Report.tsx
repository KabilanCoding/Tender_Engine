import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { tenderApi, ReportData, TenderHistoryItem } from '../api';
import { VerdictBanner } from '../components/VerdictBanner';
import { CriteriaTable } from '../components/CriteriaTable';
import { PipelineStageViewer } from '../components/PipelineStageViewer';
import { FullChecklistPanel } from '../components/FullChecklistPanel';

import { Download, ListChecks, Clock, Workflow, FileText, AlertCircle, CheckCircle2, XCircle, HelpCircle, AlertTriangle, ShieldCheck, History, Copy, Check, Printer, Share2 } from 'lucide-react';
import { Cpu } from '@phosphor-icons/react'

export const ReportPage: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const [report, setReport] = useState<ReportData | null>(null);
  const [allRuns, setAllRuns] = useState<TenderHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [tab, setTab] = useState<'criteria' | 'actions' | 'full' | 'pipeline' | 'run'>('criteria');
  const [groupKey, setGroupKey] = useState<string>('');

  const handleCopyLink = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2000);
  };

  const handlePrint = () => {
    window.print();
  };

  useEffect(() => {
    const loadHistory = async () => {
      try {
        const historyData = await tenderApi.getHistory();
        setAllRuns(historyData);
      } catch (e) {
        console.error('Failed to fetch run history', e);
      }
    };
    loadHistory();
  }, []);

  useEffect(() => {
    const fetchReport = async () => {
      try {
        setLoading(true);
        setErrorMsg(null);
        
        let targetRunId = runId;
        if (!targetRunId || targetRunId === 'latest') {
          const historyData = await tenderApi.getHistory();
          // the newest run that actually produced a report (a stopped or failed run has none)
          const latest = historyData?.find(r => r.status === 'completed') ?? historyData?.[0];
          if (latest) targetRunId = latest.run_id;
        }

        if (!targetRunId) {
          setErrorMsg('No evaluation reports found. Upload a tender document first.');
          return;
        }

        const data = await tenderApi.getReport(targetRunId);
        setReport(data);
      } catch (err: any) {
        let message = 'Failed to load the requested tender evaluation report.';
        if (err?.response?.status === 409) {
          // the run exists but has no report: say why instead of a generic failure
          const run = (await tenderApi.getHistory().catch(() => [] as TenderHistoryItem[])).find(r => r.run_id === runId);
          if (run?.status === 'cancelled') message = 'This analysis was stopped before it finished, so it has no report. Start a new evaluation to analyse the tender.';
          else if (run?.status === 'failed') message = 'This analysis failed before it finished, so it has no report. Check the AI model is running, then start a new evaluation.';
          else if (run?.status === 'processing') message = 'This analysis is still running. The report appears here when it finishes.';
        } else if (err?.response?.status === 404) {
          message = 'This evaluation report no longer exists.';
        }
        setErrorMsg(message);
      } finally {
        setLoading(false);
      }
    };
    fetchReport();
  }, [runId]);

  if (loading) {
    return (
      <div className="w-full max-w-[1850px] mx-auto py-12 px-6 sm:px-10 lg:px-16 space-y-8" role="status" aria-label="Loading evaluation report">
        <div className="space-y-3">
          <div className="skeleton h-5 w-40 rounded-full" />
          <div className="skeleton h-10 w-2/3 rounded-xl" />
        </div>
        <div className="skeleton h-28 w-full rounded-3xl" />
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          {[0, 1, 2, 3, 4].map(i => <div key={i} className="skeleton h-36 rounded-3xl" />)}
        </div>
        <div className="skeleton h-64 w-full rounded-3xl" />
      </div>
    );
  }

  if (errorMsg || !report) {
    return (
      <div className="max-w-3xl mx-auto py-16 text-center space-y-6 animate-fade-in">
        <AlertCircle className="w-14 h-14 text-rose-500 mx-auto" />
        <h3 className="text-xl font-semibold text-primary">Report Unavailable</h3>
        <p className="text-secondary text-sm max-w-md mx-auto">{errorMsg || 'The requested evaluation report could not be found.'}</p>
        
        {allRuns.length > 0 && (
          <div className="glass-panel p-6 rounded-2xl max-w-lg mx-auto border border-mid text-left space-y-3">
            <h4 className="text-xs font-mono font-semibold text-secondary flex items-center gap-1.5">
              <History className="w-4 h-4 text-indigo-500" />
              Select Available Past Audit Report
            </h4>
            <select
              value={runId || ''}
              onChange={(e) => navigate(`/tender/report/${e.target.value}`)}
              className="w-full bg-surface text-primary border border-mid rounded-xl p-3 text-xs font-mono font-semibold hover:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 cursor-pointer"
            >
              <option value="" disabled>-- Select a Tender Audit Report --</option>
              {allRuns.map(run => (
                <option key={run.run_id} value={run.run_id} disabled={run.status !== 'completed'}>
                  {run.filename} ({run.verdict || run.status}) — {new Date(run.created_at).toLocaleDateString()}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
    );
  }

  const summaryCards = [
    {
      label: 'All requirements',
      value: report.results.length,
      icon: FileText,
      color: 'var(--brand-blue)',
      glow: 'rgba(1, 75, 170,0.20)',
    },
    {
      label: 'Met',
      value: report.mandatory_pass,
      icon: CheckCircle2,
      color: 'var(--ok)',
      glow: 'rgba(16,185,129,0.18)',
    },
    {
      label: 'Not met',
      value: report.mandatory_fail,
      icon: XCircle,
      color: 'var(--bad)',
      glow: 'rgba(244,63,94,0.18)',
    },
    {
      label: 'No company data',
      value: report.mandatory_missing,
      icon: HelpCircle,
      color: 'var(--warn)',
      glow: 'rgba(245,158,11,0.18)',
    },
    {
      label: 'Check by hand',
      value: (report as any).mandatory_review_required ?? 0,
      icon: AlertTriangle,
      color: 'var(--review)',
      glow: 'rgba(168,85,247,0.18)',
    },
    {
      label: 'Documents to prepare',
      value: report.documents_to_prepare ?? 0,
      icon: FileText,
      color: 'var(--info)',
      glow: 'rgba(14,165,233,0.18)',
    },
  ];

  const checklist = report.action_checklist ?? [];
  const tabs = [
    { id: 'criteria' as const, label: `Requirements (${report.results.length})`, icon: FileText },
    { id: 'actions' as const, label: `What to do (${checklist.length})`, icon: ListChecks },
    { id: 'full' as const, label: `Full checklist${report.full_checklist ? ` (${report.full_checklist.items.length})` : ''}`, icon: ListChecks },
    { id: 'pipeline' as const, label: 'How it was checked', icon: Workflow },
    { id: 'run' as const, label: 'Run details', icon: Clock },
  ];
  const panelHeight = 'calc(100vh - 360px)';

  return (
    <div className="w-full max-w-[1700px] mx-auto py-2 px-4 sm:px-8 space-y-3 animate-fade-up">
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            {allRuns.length > 0 && (
              <div className="flex items-center gap-1.5 bg-surface border border-mid rounded-md px-2.5 py-0.5 text-xs">
                <History className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0" />
                <select
                  value={report.run_id}
                  onChange={(e) => navigate(`/tender/report/${e.target.value}`)}
                  className="bg-transparent text-primary font-semibold focus:outline-none cursor-pointer max-w-[260px] truncate"
                >
                  {allRuns.map(run => (
                    <option key={run.run_id} value={run.run_id} disabled={run.status !== 'completed'} className="bg-surface text-primary">
                      {run.filename} ({run.verdict || run.status})
                    </option>
                  ))}
                </select>
              </div>
            )}
            <span className="text-xs text-secondary">Run <span className="text-primary font-semibold tabular-nums">{report.run_id}</span></span>
          </div>
          <h2 className="text-lg font-semibold tracking-tight truncate">{report.filename}</h2>
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:flex-shrink-0">
          <button onClick={handleCopyLink} className="btn-ghost-pill cursor-pointer" title="Copy report link">
            {copiedLink ? (<><Check className="w-4 h-4 text-emerald-500" /><span className="text-emerald-600 font-semibold">Copied!</span></>)
              : (<><Share2 className="w-4 h-4 text-indigo-500" /><span>Share</span></>)}
          </button>
          <button onClick={handlePrint} className="btn-ghost-pill cursor-pointer" title="Print report">
            <Printer className="w-4 h-4 text-indigo-500" /><span>Print</span>
          </button>
          <button
            type="button"
            onClick={() => tenderApi.downloadPdf(report.run_id)}
            className="btn-primary flex-shrink-0 cursor-pointer text-xs py-2 px-4"
            id="download-pdf-btn"
          >
            <Download className="w-4 h-4 text-white" />
            <span>Download PDF</span>
          </button>
        </div>
      </div>

      {/* Verdict first, then the figures behind it */}
      {(() => {
        const must = report.mandatory_pass + report.mandatory_fail + report.mandatory_missing + (report.mandatory_review_required ?? 0);
        const pct = Math.round((report.mandatory_pass / Math.max(1, must)) * 100);
        const segs = summaryCards.slice(1, 5).filter(c => Number(c.value) > 0);
        const segTotal = segs.reduce((t, c) => t + Number(c.value), 0);
        const R = 34, C = 2 * Math.PI * R;
        // chart fills (validated for colour-blind separation), not the darker text colours
        const fill = (c: string) => ({ 'var(--ok)': 'var(--s-ok)', 'var(--warn)': 'var(--s-warn)', 'var(--bad)': 'var(--s-bad)', 'var(--review)': 'var(--s-review)' } as Record<string, string>)[c] ?? c;
        return (
          <div className="report-hero space-y-4">
            <div className="flex flex-col md:flex-row md:items-center gap-4">
              <div className="flex-1 min-w-0"><VerdictBanner verdict={report.verdict} /></div>
              {report.results.length > 0 && (
                <div className="report-ring" aria-label={`${pct}% of must-have requirements met`}>
                  <svg viewBox="0 0 80 80" width="84" height="84" aria-hidden="true">
                    <circle cx="40" cy="40" r={R} fill="none" stroke="var(--line)" strokeWidth="7" />
                    <circle cx="40" cy="40" r={R} fill="none" stroke="var(--s-ok)" strokeWidth="7" strokeLinecap="round"
                      strokeDasharray={`${(pct / 100) * C} ${C}`} transform="rotate(-90 40 40)" className="report-ring-arc" />
                  </svg>
                  <div>
                    <div className="report-ring-value">{pct}<span>%</span></div>
                    <div className="report-ring-label">must-haves met<br />{report.mandatory_pass} of {must}</div>
                  </div>
                </div>
              )}
            </div>

            {segTotal > 0 && (
              <div>
                <div className="report-bar" role="img" aria-label={segs.map(c => `${c.label} ${c.value}`).join(', ')}>
                  {segs.map(c => (
                    <span key={c.label} style={{ flexGrow: Number(c.value), background: fill(c.color) }} title={`${c.label}: ${c.value}`} />
                  ))}
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-secondary">
                  {segs.map(c => (
                    <span key={c.label} className="inline-flex items-center gap-1.5">
                      <i className="w-2 h-2 rounded-full inline-block" style={{ background: fill(c.color) }} />{c.label} <b className="text-primary tabular-nums">{c.value}</b>
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="summary-strip">
              {summaryCards.map((card) => {
                const Icon = card.icon;
                return (
                  <div key={card.label} className="summary-item" style={{ ['--accent' as string]: card.color }}>
                    <div className="summary-label">
                      <span className="summary-icon"><Icon className="w-3.5 h-3.5 shrink-0" /></span>
                      <span>{card.label}</span>
                    </div>
                    <div className="summary-value">{card.value}</div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}

      {report.deadline_warning && (
        <div role="alert" className="rounded-xl px-4 py-2.5 flex items-start gap-3 text-sm" style={{ background: 'var(--warn-bg)', border: '1px solid var(--warn-line)', color: 'var(--warn)' }}>
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span><strong className="font-semibold">Check the deadline first. </strong>{report.deadline_warning}</span>
        </div>
      )}
      {!!report.key_dates?.length && (
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-secondary px-1" aria-label="Key dates">
          {report.key_dates.map(k => (
            <span key={k.kind} title={`Page ${k.page}: ${k.quote}`}>
              <span className="text-muted capitalize">{k.kind}: </span>
              <strong className="text-primary font-semibold tabular-nums">{k.date}{k.time ? ` ${k.time}` : ''}</strong>
              {k.status === 'passed' && <span style={{ color: 'var(--bad)' }}> (passed)</span>}
            </span>
          ))}
        </div>
      )}

      {/* Tabs keep everything on one screen; the active panel scrolls inside itself */}
      <div className="flex items-center gap-1.5 border-b border-subtle overflow-x-auto no-scrollbar">
        {tabs.map(t => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium whitespace-nowrap shrink-0 cursor-pointer border-b-2 -mb-px transition-colors ${
                active ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-secondary hover:text-primary'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      <div className="tender-scroll pr-1" style={{ maxHeight: panelHeight }}>
        {tab === 'criteria' && (
          <>
            {report.groups && report.groups.length > 1 && (
              <div className="glass-panel p-3 rounded-2xl mb-3 space-y-2">
                <p className="text-xs text-secondary">
                  This tender has {report.groups.length} bidder categories. A bidder applies under only one, so each category is judged on its own
                  requirements plus the ones that apply to everybody.
                </p>
                <div className="flex flex-wrap gap-2">
                  {report.groups.map(g => {
                    const tone = g.status === 'ELIGIBLE' ? 'is-ok' : g.status === 'NOT_ELIGIBLE' ? 'is-bad' : 'is-warn';
                    const label = g.status === 'ELIGIBLE' ? 'Eligible' : g.status === 'NOT_ELIGIBLE' ? 'Not eligible' : 'Cannot confirm yet';
                    const active = (groupKey || report.best_group) === g.key;
                    return (
                      <button key={g.key} type="button" onClick={() => setGroupKey(g.key)} title={g.summary}
                        className={`px-3 py-1.5 rounded-xl border text-xs font-semibold cursor-pointer text-left ${active ? 'border-indigo-500 bg-indigo-600/10' : 'border-mid bg-surface'}`}>
                        <span className="block text-primary">{g.name}</span>
                        <span className={`zx-chip ${tone} mt-1`}>{label}{g.key === report.best_group ? ' · best fit' : ''}</span>
                      </button>
                    );
                  })}
                  <button type="button" onClick={() => setGroupKey('all')}
                    className={`px-3 py-1.5 rounded-xl border text-xs font-semibold cursor-pointer ${(groupKey || report.best_group) === 'all' ? 'border-indigo-500 bg-indigo-600/10' : 'border-mid bg-surface'}`}>
                    Show every category
                  </button>
                </div>
              </div>
            )}
            <CriteriaTable results={
              report.groups && report.groups.length > 1 && (groupKey || report.best_group) !== 'all'
                ? report.results.filter(r => !r.group || r.group.split(' \u2014 ')[0] === (groupKey || report.best_group))
                : report.results
            } />
          </>
        )}

        {tab === 'actions' && (
          checklist.length > 0 ? (
            <div className="glass-panel p-4 space-y-2">
              <h3 className="text-sm font-semibold text-primary flex items-center gap-2">
                <ListChecks className="w-4 h-4" /> Action checklist before bidding
              </h3>
              <ul className="space-y-1.5">
                {checklist.map((item, idx) => (
                  <li key={idx} className="flex items-start gap-3 py-2 border-t border-subtle first:border-t-0">
                    <span className="w-5 h-5 rounded flex items-center justify-center text-[11px] tabular-nums font-semibold flex-shrink-0 bg-raised text-secondary">
                      {idx + 1}
                    </span>
                    <span className="text-sm text-primary">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="glass-panel p-6 rounded-2xl text-center text-sm text-secondary">
              <CheckCircle2 className="w-6 h-6 text-emerald-500 mx-auto mb-2" />
              Nothing left to do: every must-have requirement is met.
            </div>
          )
        )}

        {tab === 'full' && <FullChecklistPanel data={report.full_checklist ?? null} filename={report.filename} />}

        {tab === 'pipeline' && <PipelineStageViewer runId={report.run_id} />}

        {tab === 'run' && (
          <div className="glass-panel p-4 rounded-2xl text-xs flex flex-wrap gap-x-8 gap-y-3">
            {[
              { icon: Clock, label: 'Execution time', value: report.metrics?.execution_time_ms
                  ? (report.metrics.execution_time_ms > 1000 ? `${(report.metrics.execution_time_ms / 1000).toFixed(1)}s` : `${report.metrics.execution_time_ms} ms`)
                  : '\u2014' },
              { icon: Workflow, label: 'Pages analysed', value: `${report.metrics?.chunks_processed ?? report.metrics?.total_chunks ?? '\u2014'}` },
              { icon: FileText, label: 'Pages sent to the AI', value: `${report.metrics?.llm_candidate_chunks ?? '\u2014'}` },
              { icon: ShieldCheck, label: 'Requirements found', value: `${report.results.length}` },
              { icon: Cpu, label: 'Model', value: `${report.metrics?.llm_model ?? '\u2014'}${report.metrics?.model_source ? ` (${report.metrics.model_source})` : ''}` },
              { icon: Workflow, label: 'Context window', value: `${report.metrics?.num_ctx ?? '\u2014'} tokens` },
            ].map(item => {
              const Icon = item.icon;
              return (
                <div key={item.label} className="flex items-center gap-2">
                  <Icon className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{item.label}: <strong className="text-primary font-semibold">{item.value}</strong></span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
