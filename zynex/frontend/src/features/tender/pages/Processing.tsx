import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ProgressStepper } from '../components/ProgressStepper';
import { tenderApi, TenderRunStatus } from '../api';
import {
  AlertTriangle, RefreshCw, Workflow, FileText, Scale,
  Clock, CheckCircle2, Activity, Square, History
} from 'lucide-react';

export const ProcessingPage: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [statusData, setStatusData] = useState<TenderRunStatus | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string | null>(null);
  const [elapsedS, setElapsedS] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setElapsedS(s => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const isDone = statusData?.status === 'done' || statusData?.status === 'completed';
  const isCancelled = statusData?.status === 'cancelled';

  useEffect(() => {
    if (!runId) return;
    const pollStatus = async () => {
      try {
        const data = await tenderApi.getStatus(runId);
        setStatusData(data);
        if (data.status === 'done' || data.status === 'completed') {
          // Redirect to report page automatically after 1.5 seconds
          setTimeout(() => {
            navigate(`/tender/report/${runId}`);
          }, 1500);
        } else if (data.status === 'failed') {
          setErrorMsg(data.error || 'Pipeline processing failed.');
        }
      } catch (err: any) {
        setErrorMsg('Failed to poll status from server.');
      }
    };
    pollStatus();
    const interval = setInterval(pollStatus, 2000);
    return () => clearInterval(interval);
  }, [runId, navigate]);

  const handleStop = async () => {
    if (!runId || !window.confirm('Stop this analysis? Work done so far will be discarded.')) return;
    setStopping(true);
    setStopError(null);
    try {
      await tenderApi.cancelRun(runId);
    } catch (err: any) {
      setStopError(err.message || 'Could not stop the analysis');
      setStopping(false);
    }
  };

  const formatElapsed = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
  };

  const metrics = statusData?.metrics || {};

  const metricCards = [
    {
      label: 'Parts of the tender read',
      value: metrics.chunks_started ?? metrics.total_chunks ?? 0,
      icon: FileText,
      color: '#1A59BD',
      glow: 'rgba(139,92,246,0.25)',
    },
    {
      label: 'Requirements found',
      value: metrics.raw_criteria_found ?? metrics.criteria_grounded ?? 0,
      icon: Scale,
      color: '#10b981',
      glow: 'rgba(16,185,129,0.20)',
    },
    {
      label: 'Questions asked to the AI',
      value: metrics.actual_llm_api_calls ?? metrics.successful_calls ?? 0,
      icon: Activity,
      color: '#06b6d4',
      glow: 'rgba(6,182,212,0.20)',
    },
    {
      label: 'Time taken',
      value: formatElapsed(elapsedS),
      icon: Clock,
      color: '#f59e0b',
      glow: 'rgba(245,158,11,0.20)',
    },
  ];

  return (
    <div className="w-full max-w-[1500px] mx-auto py-2 px-4 sm:px-8 space-y-3 animate-fade-up">
      {/* Header */}
      <div className="text-center space-y-1">
        <div className="section-tag mx-auto w-fit flex items-center gap-1.5 px-3 py-1 shadow-lg shadow-indigo-500/10 animate-pulse-glow">
          <Workflow className="w-3.5 h-3.5 text-indigo-500" />
          <span>{isCancelled ? 'Analysis Stopped' : 'Pipeline Active'}</span>
        </div>
        <h2 className="text-2xl font-semibold tracking-tight animated-gradient-text">
          {isCancelled ? 'Analysis Stopped' : 'Reading the tender'}
        </h2>
        <p className="text-sm font-mono text-secondary">
          Run ID: <span className="text-indigo-600 dark:text-indigo-400 font-semibold">{runId}</span>
        </p>
        {!isDone && !isCancelled && !errorMsg && (
          <div className="pt-1">
            <button
              type="button"
              onClick={handleStop}
              disabled={stopping}
              className="btn-danger mx-auto cursor-pointer disabled:opacity-60"
              id="stop-analysis-btn"
            >
              <Square className="w-3.5 h-3.5" />
              {stopping ? 'Stopping…' : 'Stop analysis'}
            </button>
            {stopError && <p className="text-xs font-mono text-rose-600 mt-1" role="alert">{stopError}</p>}
          </div>
        )}
      </div>

      {/* Live metric cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 stagger">
        {metricCards.map((card, idx) => {
          const Icon = card.icon;
          return (
            <div
              key={card.label}
              className="metric-card animated-card-lift animate-fade-up"
              style={{
                '--accent-color': `${card.color}18`,
                animationDelay: `${idx * 0.08}s`
              } as React.CSSProperties}
            >
              <div className="flex items-center justify-between mb-2">
                <div
                  className="w-8 h-8 rounded-xl flex items-center justify-center animate-pulse-glow"
                  style={{ background: `${card.color}22`, boxShadow: `0 0 16px ${card.glow}` }}
                >
                  <Icon className="w-4 h-4" style={{ color: card.color }} />
                </div>
              </div>
              <div className="metric-value font-mono font-semibold text-xl" style={{ color: card.color }}>
                {card.value}
              </div>
              <div className="metric-label text-xs sm:text-sm font-semibold">{card.label}</div>
            </div>
          );
        })}
      </div>

      {/* Main content: stepper + telemetry log */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
        {/* Pipeline Stepper */}
        <div className="md:col-span-3 glass-panel p-4 rounded-2xl animated-card-lift relative overflow-hidden">
          <div className="flex items-center justify-between mb-3 pb-2 border-b border-mid">
            <h3 className="text-sm font-semibold text-primary flex items-center gap-2">
              <Workflow className="w-6 h-6 text-indigo-500" />
              Step-by-step progress
            </h3>
            <span className="text-[10px] font-mono text-indigo-600 dark:text-indigo-400 font-semibold px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 animate-pulse">
              {statusData?.status?.toUpperCase() || 'INITIALIZING'}
            </span>
          </div>

          {isCancelled ? (
            <div className="p-5 rounded-xl border space-y-3 text-center animate-fade-up"
              style={{ background: 'rgba(245,158,11,0.08)', borderColor: 'rgba(245,158,11,0.3)' }}>
              <Square className="w-8 h-8 text-amber-500 mx-auto" />
              <div>
                <h4 className="font-semibold text-amber-700">Analysis stopped</h4>
                <p className="text-xs text-secondary mt-1">You stopped this run. No report was produced.</p>
              </div>
              <div className="flex items-center justify-center gap-2">
                <button onClick={() => navigate('/tender')} className="btn-primary text-xs py-2 px-4 cursor-pointer">New evaluation</button>
                <button onClick={() => navigate('/tender/history')} className="btn-ghost-pill cursor-pointer">
                  <History className="w-4 h-4 text-indigo-500" /><span>Audit history</span>
                </button>
              </div>
            </div>
          ) : errorMsg ? (
            <div
              className="p-5 rounded-xl border space-y-4 text-center animate-fade-up"
              style={{
                background: 'rgba(244,63,94,0.08)',
                borderColor: 'rgba(244,63,94,0.25)',
              }}
            >
              <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto" />
              <div>
                <h4 className="font-semibold text-rose-300">Stage Execution Failed</h4>
                <p className="text-xs text-rose-300/80 mt-1 font-mono">{errorMsg}</p>
              </div>
              <button
                onClick={() => window.location.reload()}
                className="btn-danger mx-auto"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Retry
              </button>
            </div>
          ) : (
            <ProgressStepper
              currentStep={statusData?.progress_step}
              isDone={isDone}
              metrics={metrics}
            />
          )}
        </div>

        {/* Right column: model info + live log */}
        <div className="md:col-span-2 space-y-4">
          {/* Model info */}
          <div className="glass-panel rounded-2xl p-5 space-y-4 terminal-scanline animated-card-lift">
            <h3 className="text-xs font-mono font-semibold text-secondary flex items-center justify-between">
              <span>Live details</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            </h3>
            <div className="space-y-3">
              {[
                { label: 'AI model', value: metrics.llm_model || '—' },
                { label: 'AI jobs at a time', value: `${metrics.concurrency ?? '—'}` },
                { label: 'Current step', value: statusData?.progress_step || (isDone ? 'Completed' : 'Waiting…') },
                { label: 'Quote match needed', value: `at least ${metrics.grounding_threshold || 92}%` },
              ].map(item => (
                <div key={item.label} className="flex justify-between items-center">
                  <span className="text-[11px] text-secondary font-mono">
                    {item.label}
                  </span>
                  <span className="text-xs font-mono text-indigo-600 dark:text-indigo-300 text-right max-w-[55%] truncate font-semibold">
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Criteria progress */}
          {((metrics.llm_candidate_chunks ?? 0) > 0 || (metrics.total_chunks ?? 0) > 0) && (
            <div className="glass-panel rounded-2xl p-5 space-y-3 animated-card-lift">
              <h3 className="text-xs font-mono font-semibold text-secondary">
                Extraction Progress
              </h3>
              <div className="space-y-2">
                <div className="flex justify-between text-xs font-mono">
                  <span className="text-secondary">LLM Chunks</span>
                  <span className="text-indigo-600 dark:text-indigo-300 font-semibold">
                    {metrics.chunks_started ?? metrics.chunks_successful ?? 0} / {metrics.llm_candidate_chunks ?? metrics.total_chunks ?? 0}
                  </span>
                </div>
                <div
                  className="h-2 rounded-full overflow-hidden p-0.5"
                  style={{ background: 'rgba(1, 75, 170,0.15)' }}
                >
                  <div
                    className="h-full rounded-full transition-all duration-500 relative"
                    style={{
                      width: `${Math.min(100, (((metrics.chunks_started ?? metrics.chunks_successful ?? 0)) / Math.max(1, metrics.llm_candidate_chunks ?? metrics.total_chunks ?? 1)) * 100)}%`,
                      background: '#014BAA'
                    }}
                  />
                </div>
              </div>
              <div className="flex justify-between text-xs font-mono">
                <span className="text-secondary">Criteria Extracted</span>
                <span className="text-emerald-600 dark:text-emerald-400 font-semibold text-sm">
                  {metrics.raw_criteria_found ?? metrics.criteria_grounded ?? 0}
                </span>
              </div>
            </div>
          )}

          {/* Done indicator */}
          {isDone && (
            <div
              className="glass-panel rounded-2xl p-5 text-center space-y-3 animate-fade-up shadow-xl shadow-emerald-500/10 cursor-pointer hover:border-emerald-500 transition-all"
              style={{ borderColor: 'rgba(16,185,129,0.35)' }}
              onClick={() => navigate(`/tender/report/${runId}`)}
            >
              <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto animate-bounce" />
              <div className="text-sm font-mono font-semibold text-emerald-700 dark:text-emerald-300">Analysis Complete</div>
              <div className="text-xs text-secondary">Redirecting to report page…</div>
              <button className="btn-primary text-xs py-2 px-4 mx-auto w-full">
                View Evaluation Report &rarr;
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
