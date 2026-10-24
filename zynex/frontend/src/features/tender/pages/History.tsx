import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { tenderApi, TenderHistoryItem } from '../api';
import { OUTCOME, outcomeOf } from '../outcome';
import { Clock, ArrowRight, FileCheck2, Inbox, FileUp, History, Search, Filter, Download, ChevronLeft, ChevronRight, Trash2, Square } from 'lucide-react';

function verdictColor(verdict: string | null): string {
  if (!verdict) return '#64748b';
  const v = verdict.toUpperCase();
  if (v.includes('PASS')) return '#10b981';
  if (v.includes('FAIL')) return '#f43f5e';
  if (v.includes('PARTIAL')) return '#f59e0b';
  return '#1A59BD';
}

function formatAuditDate(dateStr: string): string {
  if (!dateStr) return '—';
  let parseable = dateStr;
  if (!parseable.includes('Z') && !parseable.includes('+') && !parseable.includes('-')) {
    parseable = parseable.replace(' ', 'T') + 'Z';
  } else if (parseable.includes(' ') && !parseable.includes('T')) {
    parseable = parseable.replace(' ', 'T');
  }
  try {
    const d = new Date(parseable);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleString(undefined, {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
  } catch (e) {
    return dateStr;
  }
}

export const HistoryPage: React.FC = () => {
  const [history, setHistory] = useState<TenderHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [verdictFilter, setVerdictFilter] = useState<string>('ALL');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;
  const navigate = useNavigate();
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleStop = async (item: TenderHistoryItem) => {
    if (!window.confirm(`Stop the analysis of "${item.filename}"?`)) return;
    setDeleteError(null);
    try {
      await tenderApi.cancelRun(item.run_id);
      setHistory(await tenderApi.getHistory());
    } catch (err: any) {
      setDeleteError(err.message || 'Could not stop the analysis');
    }
  };

  const handleDelete = async (item: TenderHistoryItem) => {
    if (!window.confirm(`Delete the evaluation of "${item.filename}"? This removes its report and the uploaded file.`)) return;
    setDeleteError(null);
    try {
      await tenderApi.deleteRun(item.run_id);
      setHistory(h => h.filter(x => x.run_id !== item.run_id));
    } catch (err: any) {
      setDeleteError(err.message || 'Delete failed');
    }
  };

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const data = await tenderApi.getHistory();
        setHistory(data);
      } catch (err) {
        console.error('Failed to load tender history', err);
      } finally {
        setLoading(false);
      }
    };
    fetchHistory();
  }, []);

  const filteredHistory = history.filter(item => {
    const matchesSearch = item.filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.run_id.toLowerCase().includes(searchTerm.toLowerCase());

    if (verdictFilter === 'ALL') return matchesSearch;
    if (verdictFilter === 'PASS') return matchesSearch && (item.verdict?.toUpperCase().includes('PASS'));
    if (verdictFilter === 'FAIL') return matchesSearch && (item.verdict?.toUpperCase().includes('FAIL'));
    if (verdictFilter === 'PARTIAL') return matchesSearch && outcomeOf(item.verdict, item.met) === 'partial';
    if (verdictFilter === 'UNCONFIRMED') return matchesSearch && !!item.verdict && outcomeOf(item.verdict, item.met) === 'unconfirmed';
    if (verdictFilter === 'FAILED_RUNS') return matchesSearch && item.status === 'failed';
    return matchesSearch;
  });

  // Reset to page 1 on filter or search change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, verdictFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredHistory.length / itemsPerPage));
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = Math.min(startIndex + itemsPerPage, filteredHistory.length);
  const paginatedHistory = filteredHistory.slice(startIndex, endIndex);

  return (
    <div className="w-full max-w-[1700px] mx-auto py-2 px-4 sm:px-8 space-y-3 animate-fade-in hero-subtitle-custom">
      {/* Header */}
      <div className="zx-page-head">
        <div>
          <span className="zx-eyebrow-line">Tender Analysis</span>
          <h1 className="mt-1">Audit history</h1>
          <p>Every tender you have checked, with its verdict. Open one to see the full report, or download it as PDF.</p>
          {deleteError && (
            <p className="text-sm font-mono font-semibold text-rose-600 mt-2" role="alert">{deleteError}</p>
          )}

        </div>
        <button
          onClick={() => navigate('/tender')}
          className="zx-action primary flex-shrink-0 cursor-pointer"
        >
          <FileUp className="w-4 h-4" />
          Upload tender
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="zx-panel flex flex-col lg:flex-row lg:items-center gap-3" style={{ padding: '0.85rem 1rem', height: 'auto' }}>
        <label className="zx-search flex-1 lg:max-w-md">
          <Search className="w-4 h-4" aria-hidden="true" />
          <input
            type="text"
            placeholder="Search document or run number…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            aria-label="Search runs"
          />
        </label>
        <div className="flex items-center gap-1.5 overflow-x-auto lg:ml-auto" role="group" aria-label="Filter by verdict">
          {[
            { id: 'ALL', label: 'All runs', n: history.length },
            { id: 'PASS', label: 'Eligible', n: history.filter(h => h.verdict?.toUpperCase().includes('PASS')).length },
            { id: 'PARTIAL', label: 'Partially eligible', n: history.filter(h => outcomeOf(h.verdict, h.met) === 'partial').length },
            { id: 'UNCONFIRMED', label: 'Cannot confirm yet', n: history.filter(h => h.verdict && outcomeOf(h.verdict, h.met) === 'unconfirmed').length },
            { id: 'FAIL', label: 'Not eligible', n: history.filter(h => h.verdict?.toUpperCase().includes('FAIL')).length },
          ].map(filter => (
            <button
              key={filter.id}
              type="button"
              onClick={() => setVerdictFilter(filter.id)}
              className={`zx-pill ${verdictFilter === filter.id ? 'is-on' : ''}`}
              aria-pressed={verdictFilter === filter.id}
            >
              {filter.label} <b>{filter.n}</b>
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="glass-panel p-3 rounded-3xl space-y-2" role="status" aria-label="Loading audit history">
          {[0, 1, 2, 3].map(i => (
            <div key={i} className="flex items-center gap-4 p-4">
              <div className="skeleton w-14 h-14 rounded-2xl" />
              <div className="flex-1 space-y-2">
                <div className="skeleton h-4 w-1/3 rounded-md" />
                <div className="skeleton h-3 w-1/5 rounded-md" />
              </div>
              <div className="skeleton h-6 w-20 rounded-full hidden sm:block" />
            </div>
          ))}
        </div>
      ) : history.length === 0 ? (
        <div className="glass-panel p-20 rounded-3xl text-center space-y-5">
          <Inbox className="w-16 h-16 text-muted mx-auto" />
          <h3 className="text-xl font-semibold text-primary">No Qualification Runs Recorded</h3>
          <p className="text-base text-secondary max-w-md mx-auto">
            Upload your first tender document to evaluate company master eligibility.
          </p>
          <button onClick={() => navigate('/tender')} className="btn-primary mx-auto text-base py-3.5 px-7 min-h-[48px]">
            <FileUp className="w-5 h-5" />
            Upload Tender
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="glass-panel rounded-3xl overflow-hidden border border-mid shadow-sm">
            <div className="overflow-x-auto">
              <table className="data-table w-full border-collapse table-fixed min-w-[950px]">
                <colgroup>
                  <col style={{ width: '36%' }} />
                  <col style={{ width: '22%' }} />
                  <col style={{ width: '12%' }} />
                  <col style={{ width: '18%' }} />
                  <col style={{ width: '12%' }} />
                </colgroup>
                <thead>
                  <tr className="bg-raised border-b border-mid">
                    <th className="px-4 py-2 text-left hero-subtitle-custom text-xs font-semibold text-muted">Document</th>
                    <th className="px-4 py-2 text-left hero-subtitle-custom text-xs font-semibold text-muted">Evaluated Date & Time</th>
                    <th className="px-4 py-4 text-center hero-subtitle-custom text-xs font-semibold text-muted">Criteria</th>
                    <th className="px-4 py-4 text-center hero-subtitle-custom text-xs font-semibold text-muted">Verdict</th>
                    <th className="px-4 py-4 text-center hero-subtitle-custom text-xs font-semibold text-muted">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-mid">
                  {paginatedHistory.map((item, idx) => {
                    const color = verdictColor(item.verdict || null);

                    return (
                      <tr
                        key={item.run_id}
                        onClick={() => navigate(item.status === 'processing' ? `/tender/processing/${item.run_id}` : `/tender/report/${item.run_id}`)}
                        className="cursor-pointer transition-colors hover:bg-indigo-500/10 group"
                        style={{ animationDelay: `${idx * 30}ms` }}
                      >
                        <td className="px-4 py-2">
                          <div className="flex items-center gap-4">
                            <div
                              className="w-8 h-8 min-w-[32px] min-h-[32px] rounded-xl flex items-center justify-center flex-shrink-0 shadow-md border border-indigo-500/20 group-hover:scale-105 transition-transform"
                              style={{ background: `${color}20` }}
                            >
                              <FileCheck2 className="w-4 h-4" style={{ color }} />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="text-sm font-semibold text-primary group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors truncate">
                                {item.filename}
                              </div>
                              <div className="text-xs text-muted mt-0.5 hero-subtitle-custom">
                                {/^\d+$/.test(item.run_id) ? `Run ${item.run_id}` : `ID ${item.run_id.slice(0, 8)}…`}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-2">
                          <div className="flex items-center gap-2">
                            <Clock className="w-4 h-4 text-indigo-500 flex-shrink-0" />
                            <span className="text-sm text-secondary hero-subtitle-custom font-semibold">
                              {formatAuditDate(item.created_at)}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-2 text-center">
                          <div className="flex items-center justify-center">
                            <span className="inline-flex items-center justify-center w-9 h-9 bg-raised border border-mid rounded-xl text-sm font-semibold text-primary hero-subtitle-custom shadow-xs">
                              {item.criteria_count}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-2 text-center">
                          <div className="flex items-center justify-center">
                            {item.verdict ? (
                              (() => { const o = OUTCOME[outcomeOf(item.verdict, item.met)]; return (
                                <span className={`zx-chip ${o.chip} whitespace-nowrap`} title={item.total ? `${item.met ?? 0} of ${item.total} requirements met` : undefined}>
                                  {o.label}{item.total ? <span className="opacity-70 font-medium tabular-nums">{item.met ?? 0}/{item.total}</span> : null}
                                </span>) })()
                            ) : (
                              <span className="status-pending-pill">
                                <span className="status-pending-dot" aria-hidden="true" />
                                <span className="capitalize">{item.status}</span>
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-2 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); tenderApi.downloadPdf(item.run_id); }}
                              className="p-2 rounded-xl border border-mid hover:border-indigo-500/40 text-muted hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors min-w-[38px] min-h-[38px] flex items-center justify-center"
                              title="Download PDF Report"
                            >
                              <Download className="w-4.5 h-4.5" />
                            </button>
                            {item.status === 'processing' ? (
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); handleStop(item); }}
                                className="p-2 rounded-xl border border-rose-500/40 text-rose-600 hover:bg-rose-500/10 transition-all cursor-pointer"
                                title="Stop this analysis"
                              >
                                <Square className="w-4.5 h-4.5" />
                              </button>
                            ) : (
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); handleDelete(item); }}
                                className="p-2 rounded-xl border border-mid hover:border-rose-500/50 text-muted hover:text-rose-600 transition-all cursor-pointer"
                                title="Delete this evaluation"
                              >
                                <Trash2 className="w-4.5 h-4.5" />
                              </button>
                            )}
                            <ArrowRight className="w-5 h-5 text-muted group-hover:text-indigo-600 dark:group-hover:text-indigo-400 group-hover:translate-x-1 transition-all" />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-3 px-3">
              <div className="text-sm text-secondary font-semibold hero-subtitle-custom">
                Page <span className="font-semibold text-primary">{currentPage}</span> of{' '}
                <span className="font-semibold text-primary">{totalPages}</span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="px-4 py-2 rounded-xl border border-mid bg-surface hover:bg-raised text-primary text-sm font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 cursor-pointer shadow-sm"
                >
                  <ChevronLeft className="w-4.5 h-4.5" />
                  Previous
                </button>

                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter(page => page === 1 || page === totalPages || Math.abs(page - currentPage) <= 1)
                  .map((page, idx, arr) => {
                    const prev = arr[idx - 1];
                    const showEllipsis = prev && page - prev > 1;
                    return (
                      <React.Fragment key={page}>
                        {showEllipsis && <span className="px-1.5 text-muted text-sm font-semibold">…</span>}
                        <button
                          onClick={() => setCurrentPage(page)}
                          className={`w-10 h-10 rounded-xl text-sm font-semibold transition-all cursor-pointer ${currentPage === page
                              ? 'bg-indigo-600 text-white shadow-md scale-105'
                              : 'bg-surface hover:bg-raised text-secondary border border-mid'
                            }`}
                        >
                          {page}
                        </button>
                      </React.Fragment>
                    );
                  })}

                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="px-4 py-2 rounded-xl border border-mid bg-surface hover:bg-raised text-primary text-sm font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 cursor-pointer shadow-sm"
                >
                  Next
                  <ChevronRight className="w-4.5 h-4.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default HistoryPage;
