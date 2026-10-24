import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { OUTCOME, outcomeOf } from '../outcome';
import { downloadedText, tigerApi, TigerList, TigerRun, daysLeft, formatDate, formatMoney } from '../tigerApi';
import { Eye, Check, CheckCheck, Building2, ChevronLeft, ChevronRight, Clock, Download, ExternalLink, FileText, Filter, Inbox, Loader2, MapPin, Radar, Search, ArrowRight, X, RefreshCw, Info } from 'lucide-react';
import { AutoQueuePanel } from '../components/AutoQueuePanel';

const PAGE_SIZE = 10;

function DueBadge({ iso }: { iso: string | null }) {
  const days = daysLeft(iso);
  if (days === null) return <span className="text-sm text-muted">—</span>;
  const closed = days < 0;
  const color = closed ? '#64748b' : days <= 3 ? '#f43f5e' : days <= 10 ? '#f59e0b' : '#10b981';
  return (
    <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold" style={{ background: `${color}20`, color }}>
      {closed ? 'Closed' : days === 0 ? 'Due today' : `${days} day${days === 1 ? '' : 's'} left`}
    </span>
  );
}

const SORTS = [
  { id: 'downloaded_desc', label: 'Newest downloaded first' },
  { id: 'downloaded_asc', label: 'Oldest downloaded first' },
  { id: 'due_asc', label: 'Due date: soonest first' },
  { id: 'due_desc', label: 'Due date: latest first' },
  { id: 'published_desc', label: 'Newest published first' },
  { id: 'published_asc', label: 'Oldest published first' },
  { id: 'value_desc', label: 'Value: highest first' },
  { id: 'value_asc', label: 'Value: lowest first' },
  { id: 'emd_desc', label: 'EMD: highest first' },
  { id: 'title_asc', label: 'Title A to Z' },
  { id: 'title_desc', label: 'Title Z to A' },
];
const AUTO_REFRESH_MS = 60_000;

/** "₹ 2.23 Cr" on screen, the full rupee figure on hover. */
function money(amount: number | null | undefined, raw: string | null) {
  const short = formatMoney(amount ?? null, raw);
  return { short, full: amount ? `₹ ${Math.round(amount).toLocaleString('en-IN')}` : raw || 'Not stated' };
}

/** Column header that sorts: first click uses the column's natural order, the next click reverses it. */
function SortTh({ label, field, sort, onSort, align = 'left', first = 'desc', hint }: {
  label: string; field: string; sort: string; onSort: (s: string) => void; align?: 'left' | 'center'; first?: 'asc' | 'desc'; hint?: string
}) {
  const on = sort.startsWith(field + '_');
  const dir = on ? sort.slice(field.length + 1) : null;
  const next = on ? `${field}_${dir === 'asc' ? 'desc' : 'asc'}` : `${field}_${first}`;
  return (
    <th className={`px-4 py-2 text-${align} hero-subtitle-custom text-xs font-semibold text-muted`} aria-sort={on ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button type="button" onClick={() => onSort(next)} className={`tt-sort ${on ? 'is-on' : ''}`} title={hint ? `${hint} · click to sort` : 'Click to sort'}>
        {label}<span className="tt-sort-arrow" aria-hidden="true">{on ? (dir === 'asc' ? '▲' : '▼') : '↕'}</span>
      </button>
    </th>
  );
}

/** What happened the last time a file of this tender was checked, if ever. */
export function RunBadge({ run, onOpen }: { run?: TigerRun | null; onOpen?: () => void }) {
  if (!run) return <span className="text-xs text-muted">Not checked yet</span>;
  const running = run.state === 'RUNNING';
  const done = run.state === 'DONE' && run.verdict;
  const o = done ? OUTCOME[outcomeOf(run.verdict, run.met)] : null;
  const label = o?.label ?? (running ? 'Checking…' : run.state === 'FAILED' ? 'Check failed' : run.state === 'CANCELLED' ? 'Check stopped' : 'Checked');
  const chip = o?.chip ?? (running ? 'is-info' : '');
  const detail = done && run.total ? ` · ${run.met ?? 0} of ${run.total} requirements met` : '';
  return (
    <button type="button" onClick={(e) => { e.stopPropagation(); onOpen?.(); }}
      className={`zx-chip ${chip} whitespace-nowrap cursor-pointer hover:opacity-85 transition-opacity`}
      title={`Open the eligibility report${detail}`}>
      {running && <Loader2 className="w-3 h-3 animate-spin" />}{label}
      {done && run.total ? <span className="opacity-70 font-medium tabular-nums">{run.met ?? 0}/{run.total}</span> : null}
    </button>
  );
}

export const TenderTigerPage: React.FC = () => {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();      // the filters live in the address, so Back from a tender keeps them
  const query = params.get('q') ?? '';
  const status = params.get('status') ?? 'all';
  const read = params.get('read') ?? 'all';
  const org = params.get('org') ?? '';
  const sort = params.get('sort') ?? 'downloaded_desc';   // newest from the downloader first
  const page = Math.max(1, Number(params.get('page')) || 1);

  const [data, setData] = useState<TigerList | null>(null);
  const [orgs, setOrgs] = useState<{ name: string; count: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState(query);
  const [reloadKey, setReloadKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [arrived, setArrived] = useState(0);               // tenders added by the downloader since the page was opened
  const lastTotal = React.useRef<number | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const refresh = () => { setRefreshing(true); setReloadKey(k => k + 1); tigerApi.organizations().then(setOrgs).catch(() => {}); };

  const update = (changes: Record<string, string | null>, keepPage = false) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) { if (v) next.set(k, v); else next.delete(k); }
    if (!keepPage) next.delete('page');
    setParams(next, { replace: true });
  };

  useEffect(() => {                       // wait for the person to stop typing before asking the server
    if (search.trim() === query) return;
    const t = setTimeout(() => update({ q: search.trim() || null }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  useEffect(() => { tigerApi.organizations().then(setOrgs).catch(() => setOrgs([])); }, []);

  useEffect(() => {
    let live = true;
    setLoading(true);
    tigerApi.list({ search: query, status, org, sort, read, page, page_size: PAGE_SIZE })
      .then(d => {
        if (!live) return;
        if (lastTotal.current !== null && d.summary.total > lastTotal.current) setArrived(n => n + d.summary.total - lastTotal.current!);
        lastTotal.current = d.summary.total;
        setData(d); setError(null); setUpdatedAt(new Date());
      })
      .catch(e => { if (live) setError(e?.message || 'Could not load the tenders'); })
      .finally(() => { if (live) { setLoading(false); setRefreshing(false); } });
    return () => { live = false; };
  }, [query, status, org, sort, read, page, reloadKey]);

  // the n8n downloader adds tenders several times a day: check again every minute while the page is open and visible
  useEffect(() => {
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') setReloadKey(k => k + 1); }, AUTO_REFRESH_MS);
    return () => window.clearInterval(t);
  }, []);

  const filtered = !!(query || org || status !== 'all' || read !== 'all');
  const setSeen = async (tid: string, makeRead: boolean) => {
    const r = await tigerApi.markRead(tid, makeRead);
    setData(d => d && ({ ...d, items: d.items.map(i => i.tid === tid ? { ...i, seen: r.seen as 'viewed' | 'read' } : i),
      summary: { ...d.summary, read: Math.max(0, (d.summary.read ?? 0) + (makeRead ? 1 : -1)) } }));
  };
  const exportCsv = async () => {
    setExporting(true);
    try { await tigerApi.exportCsv({ search: query, status, org, sort }); }
    catch (e: any) { setError(e?.message || 'Could not export'); }
    finally { setExporting(false); }
  };

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));
  const items = data?.items ?? [];
  const summary = data?.summary;

  return (
    <div className="w-full max-w-[1700px] mx-auto py-2 px-4 sm:px-8 space-y-3 animate-fade-in hero-subtitle-custom">
      <div className="zx-page-head" style={{ alignItems: 'center' }}>
        <div>
          <span className="zx-eyebrow-line">Tender Analysis</span>
          <h1 className="mt-1">Tender Tiger</h1>
          <p>Tenders collected from Tender Tiger. Open one to see its details and files, or run the eligibility check on a file.</p>
        </div>
        {summary && (
          <div className="summary-strip" style={{ gridTemplateColumns: 'repeat(4, minmax(5.5rem, 1fr))' }}>
            {[
              { label: 'Tenders', value: summary.total, filter: 'all' },
              { label: 'Still open', value: summary.open, filter: 'open' },
              { label: 'Closing in 7 days', value: summary.closing_soon, filter: 'soon' },
              { label: 'Organizations', value: summary.organizations, filter: null },
            ].map(t => {
              const active = t.filter !== null && status === t.filter;
              const body = (
                <>
                  <div className="summary-label">{t.label}</div>
                  <div className="summary-value">{Number(t.value).toLocaleString('en-IN')}</div>
                </>
              );
              return t.filter === null ? (
                <div key={t.label} className="summary-item">{body}</div>
              ) : (
                <button key={t.label} type="button" onClick={() => update({ status: t.filter === 'all' ? null : t.filter })}
                  className={`summary-item text-left cursor-pointer ${active ? 'is-active' : ''}`}>
                  {body}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <AutoQueuePanel />

      <div className="zx-panel flex flex-col gap-3" style={{ padding: '0.85rem 1rem', height: 'auto' }}>
        <div className="flex flex-col lg:flex-row lg:items-center gap-3">
          <label className="zx-search flex-1 lg:max-w-md">
            <Search className="w-4 h-4" aria-hidden="true" />
            <input type="text" placeholder="Search title, organisation, location or ID…" value={search}
              onChange={(e) => setSearch(e.target.value)} aria-label="Search tenders" />
          </label>
          <div className="flex items-center gap-2 flex-wrap lg:ml-auto">
            <select value={sort} onChange={(e) => update({ sort: e.target.value === 'downloaded_desc' ? null : e.target.value })} aria-label="Sort by" className="zx-select sm:w-72">
              {SORTS.map(o => <option key={o.id} value={o.id}>Sort: {o.label}</option>)}
            </select>
            <button type="button" onClick={() => setShowFilters(v => !v)} aria-expanded={showFilters}
              className={`zx-pill ${showFilters || (status !== 'all' ? 1 : 0) + (read !== 'all' ? 1 : 0) + (org ? 1 : 0) ? 'is-on' : ''}`}>
              <Filter className="w-3.5 h-3.5" />Filters{(status !== 'all' ? 1 : 0) + (read !== 'all' ? 1 : 0) + (org ? 1 : 0) > 0 && <b>{(status !== 'all' ? 1 : 0) + (read !== 'all' ? 1 : 0) + (org ? 1 : 0)}</b>}
            </button>
            <button type="button" onClick={refresh} disabled={refreshing} className="zx-pill" title="Load the latest tenders saved by the downloader">
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />Refresh
            </button>
            <button type="button" onClick={() => setShowHelp(v => !v)} aria-expanded={showHelp} className={`zx-pill ${showHelp ? 'is-on' : ''}`} title="What the columns mean">
              <Info className="w-3.5 h-3.5" />Guide
            </button>
          </div>
        </div>
        <div className="tt-status-line">
          <span>{updatedAt ? `Updated ${updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })} · refreshes every minute` : 'Loading…'}</span>
          {arrived > 0 && <span className="tt-arrived">{arrived} new tender{arrived === 1 ? '' : 's'} arrived since you opened this page</span>}
          {filtered && <button type="button" className="tt-clear" onClick={() => { setSearch(''); setParams({}, { replace: true }); }}><X className="w-3 h-3" />Clear filters</button>}
        </div>

        {showFilters && (
          <div className="tt-filters">
            <div className="tt-filter-group">
              <span className="tt-filter-label">Status</span>
              <div className="flex items-center gap-1.5 flex-wrap" role="group" aria-label="Filter by status">
                {[
                  { id: 'all', label: 'All tenders', n: summary?.total },
                  { id: 'open', label: 'Open', n: summary?.open },
                  { id: 'soon', label: 'Closing in 7 days', n: summary?.closing_soon },
                  { id: 'closed', label: 'Closed', n: summary ? summary.total - summary.open : undefined },
                ].map(f => (
                  <button key={f.id} type="button" onClick={() => update({ status: f.id === 'all' ? null : f.id })}
                    className={`zx-pill ${status === f.id ? 'is-on' : ''}`} aria-pressed={status === f.id}>
                    {f.label}{f.n !== undefined && <b>{f.n}</b>}
                  </button>
                ))}
              </div>
            </div>
            <div className="tt-filter-group">
              <span className="tt-filter-label">Your reading</span>
              <div className="flex items-center gap-1.5 flex-wrap" role="group" aria-label="Filter by read state">
                {[
                  { id: 'all', label: 'Any' },
                  { id: 'new', label: 'New', n: summary?.new },
                  { id: 'unread', label: 'Unread', n: summary && summary.read !== undefined ? summary.total - summary.read : undefined },
                  { id: 'read', label: 'Read', n: summary?.read },
                ].map(f => (
                  <button key={f.id} type="button" onClick={() => update({ read: f.id === 'all' ? null : f.id })}
                    className={`zx-pill ${read === f.id ? 'is-on' : ''}`} aria-pressed={read === f.id}>
                    {f.id === 'new' && <i className="zx-new-dot" aria-hidden="true" />}{f.label}{f.n !== undefined && <b>{f.n}</b>}
                  </button>
                ))}
              </div>
            </div>
            <div className="tt-filter-group grow">
              <span className="tt-filter-label">Organisation</span>
              <select value={org} onChange={(e) => update({ org: e.target.value || null })} aria-label="Organization" className="zx-select w-full">
                <option value="">All organisations</option>
                {orgs.map(o => <option key={o.name} value={o.name}>{o.name} ({o.count})</option>)}
              </select>
            </div>
            <div className="tt-filter-group">
              <span className="tt-filter-label">Export</span>
              <button type="button" onClick={exportCsv} disabled={exporting || !data?.total}
                className="btn-ghost-pill cursor-pointer whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed" title="Download the tenders shown by these filters as a CSV file">
                {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4 text-indigo-500" />}<span>Export CSV</span>
              </button>
            </div>
          </div>
        )}

        {showHelp && (
          <div className="tt-help">
            <p><b>What this list is.</b> Every tender the Tender Tiger downloader (n8n) has collected, with its documents saved on the server. New tenders appear after each download run (9 am, 1 pm, 6 pm and 9 pm).</p>
            <ul>
              <li><b>New / Viewed / Read</b>: your own progress. New = you have not opened it; Viewed = you opened it; Read = you marked it with ✓.</li>
              <li><b>⬇ time</b>: when the downloader saved the tender.</li>
              <li><b>Value</b>: the estimated contract value from the notice. <b>EMD</b>: the bid security (earnest money) you must deposit. “Ref Doc” means the figure is only in the tender documents.</li>
              <li><b>Due date</b>: the last date to submit; the chip shows days left (red = 3 days or less, amber = 10 or less).</li>
              <li><b>Eligibility</b>: the result of the last eligibility check run on one of its files, and how many requirements were met.</li>
              <li><b>Files</b>: documents downloaded for the tender. Click a row to open them; use <b>›</b> for a quick summary without leaving the list.</li>
            </ul>
          </div>
        )}
      </div>

      {error && <p className="text-sm font-mono font-semibold text-rose-600" role="alert">{error}</p>}

      {loading && !data ? (
        <div className="glass-panel p-3 rounded-3xl space-y-2" role="status" aria-label="Loading tenders">
          {[0, 1, 2, 3].map(i => (
            <div key={i} className="flex items-center gap-4 p-4">
              <div className="skeleton w-14 h-14 rounded-2xl" />
              <div className="flex-1 space-y-2">
                <div className="skeleton h-4 w-1/3 rounded-md" />
                <div className="skeleton h-3 w-1/5 rounded-md" />
              </div>
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="glass-panel p-20 rounded-3xl text-center space-y-5">
          <Inbox className="w-16 h-16 text-muted mx-auto" />
          <h3 className="text-xl font-semibold text-primary">No tenders found</h3>
          <p className="text-base text-secondary max-w-md mx-auto">Try a different search or filter.</p>
          {filtered && <button type="button" onClick={() => { setSearch(''); setParams({}, { replace: true }); }} className="btn-primary mx-auto text-base py-3 px-7 cursor-pointer">Clear filters</button>}
        </div>
      ) : (
        <div className="space-y-6">
          <div className={`glass-panel rounded-3xl overflow-hidden border border-mid shadow-sm ${loading ? 'opacity-60' : ''}`}>
            <div className="overflow-x-auto">
              <table className="data-table w-full border-collapse table-fixed min-w-[1250px]">
                <colgroup>
                  <col style={{ width: '34%' }} />
                  <col style={{ width: '14%' }} />
                  <col style={{ width: '11%' }} />
                  <col style={{ width: '12%' }} />
                  <col style={{ width: '13%' }} />
                  <col style={{ width: '6%' }} />
                  <col style={{ width: '10%' }} />
                </colgroup>
                <thead>
                  <tr className="bg-raised border-b border-mid">
                    <SortTh label="Tender" field="title" first="asc" sort={sort} onSort={v => update({ sort: v })} hint="Title" />
                    <th className="px-4 py-2 text-left hero-subtitle-custom text-xs font-semibold text-muted">Location</th>
                    <SortTh label="Value / EMD" field="value" sort={sort} onSort={v => update({ sort: v })} hint="Estimated value" />
                    <SortTh label="Due date" field="due" first="asc" align="center" sort={sort} onSort={v => update({ sort: v })} hint="Last date to submit" />
                    <th className="px-4 py-4 text-center hero-subtitle-custom text-xs font-semibold text-muted">Eligibility</th>
                    <th className="px-4 py-4 text-center hero-subtitle-custom text-xs font-semibold text-muted">Files</th>
                    <th className="px-4 py-4" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-mid">
                  {items.map((t, idx) => (
                    <React.Fragment key={t.tid}>
                    <tr
                      onClick={() => navigate(`/tender/tiger/${encodeURIComponent(t.tid)}`)}
                      className={`cursor-pointer transition-colors hover:bg-indigo-500/10 group tt-row is-${t.seen ?? 'new'}`}
                      style={{ animationDelay: `${idx * 30}ms` }}
                    >
                      <td className="px-4 py-2">
                        <div className="flex items-start gap-4">
                          <div className="w-8 h-8 min-w-[32px] mt-0.5 rounded-xl flex items-center justify-center flex-shrink-0 shadow-md border border-indigo-500/20 bg-indigo-500/10 group-hover:scale-105 transition-transform">
                            <Radar className="w-4 h-4 text-indigo-500" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="tt-title-line">
                              {t.seen === 'new' && <span className="zx-new-tag">New</span>}
                              {t.seen === 'viewed' && <span className="zx-seen-tag" title="You opened this tender"><Eye className="w-3 h-3" />Viewed</span>}
                              {t.seen === 'read' && <span className="zx-read-tag" title="You marked this tender read"><CheckCheck className="w-3 h-3" />Read</span>}
                              {t.tender_type && <span className="tt-type">{t.tender_type}</span>}
                            </div>
                            <div className="tt-title" title={t.tender_title || ''}>{t.tender_title || 'Untitled tender'}</div>
                            <div className="tt-org">
                              <Building2 className="w-3.5 h-3.5 flex-shrink-0" />
                              <span><b>{t.organization || 'Organisation not listed'}</b>{t.department && t.department !== t.organization ? <> · {t.department}</> : null}</span>
                            </div>
                            <div className="tt-facts">
                              <span title="Tender Tiger ID">ID {t.tid}</span>
                              {t.published_date && <span title="Date the notice was published">Published {formatDate(t.published_date)}</span>}
                              {t.opening_date && <span title="Date the bids are opened">Opens {formatDate(t.opening_date)}</span>}
                              {(t.doc_fee_amount || (t.doc_fees && t.doc_fees !== 'Ref Doc')) && <span title="Fee to buy the tender documents">Doc fee {money(t.doc_fee_amount, t.doc_fees).short}</span>}
                              {t.downloaded_at && <span className={`tt-dl ${Date.now() - new Date(t.downloaded_at).getTime() < 864e5 ? 'is-fresh' : ''}`}
                                title={`Downloaded ${new Date(t.downloaded_at).toLocaleString()}${t.updated_at && t.updated_at !== t.downloaded_at ? ` · updated ${new Date(t.updated_at).toLocaleString()}` : ''}`}>
                                <Download className="w-3 h-3" />Downloaded {downloadedText(t.downloaded_at)}</span>}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-start gap-2">
                          <MapPin className="w-4 h-4 text-indigo-500 flex-shrink-0" />
                          <span className="tt-loc" title={t.key_location || ''}>{t.key_location || 'Not stated'}</span>
                        </div>
                      </td>
                      <td className="px-4 py-2">
                        <div className="tt-money-label">Value</div>
                        <div className="text-sm text-primary font-semibold" title={`Estimated value: ${money(t.worth_amount, t.worth).full}`}>{t.worth_amount ? money(t.worth_amount, t.worth).short : 'In documents'}</div>
                        <div className="tt-money-label mt-1.5">EMD</div>
                        <div className="text-xs text-secondary font-semibold" title={`EMD (bid security): ${money(t.emd_amount, t.emd).full}`}>{t.emd_amount ? money(t.emd_amount, t.emd).short : 'In documents'}</div>
                      </td>
                      <td className="px-4 py-2 text-center">
                        <div className="flex flex-col items-center gap-1">
                          <span className="flex items-center gap-1.5 text-sm text-secondary font-semibold">
                            <Clock className="w-4 h-4 text-indigo-500" />{formatDate(t.due_date)}
                          </span>
                          <DueBadge iso={t.due_date} />
                        </div>
                      </td>
                      <td className="px-4 py-2 text-center">
                        <RunBadge run={t.last_run} onOpen={() => t.last_run && navigate(
                          t.last_run.state === 'RUNNING' ? `/tender/processing/${t.last_run.run_id}` : `/tender/report/${t.last_run!.run_id}`)} />
                      </td>
                      <td className="px-4 py-2 text-center">
                        <span className="inline-flex items-center justify-center gap-1.5 px-3 h-9 bg-raised border border-mid rounded-xl text-sm font-semibold text-primary">
                          <FileText className="w-4 h-4 text-muted" />{t.file_count ?? 0}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-center">
                        <div className="flex items-center justify-center gap-2">
                          <button type="button" onClick={(e) => { e.stopPropagation(); setSeen(t.tid, t.seen !== 'read'); }}
                            className={`tt-read-btn ${t.seen === 'read' ? 'is-read' : ''}`}
                            title={t.seen === 'read' ? 'Marked read. Click to mark unread' : 'Mark as read'}
                            aria-label={t.seen === 'read' ? `Mark ${t.tender_title || t.tid} as unread` : `Mark ${t.tender_title || t.tid} as read`}>
                            {t.seen === 'read' ? <CheckCheck className="w-4 h-4" /> : <Check className="w-4 h-4" />}
                          </button>
                          {t.tender_link && (
                            <a href={t.tender_link} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                              className="p-2 rounded-xl border border-mid hover:border-indigo-500/40 text-muted hover:text-indigo-600 transition-colors" title="Open the original listing">
                              <ExternalLink className="w-4 h-4" />
                            </a>
                          )}
                          <button type="button" onClick={(e) => { e.stopPropagation(); setExpanded(x => x === t.tid ? null : t.tid); }}
                            className={`tt-expand ${expanded === t.tid ? 'is-open' : ''}`} aria-expanded={expanded === t.tid}
                            title={expanded === t.tid ? 'Hide the summary' : 'Show a summary of this tender'}>
                            <ChevronRight className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expanded === t.tid && (
                      <tr className="tt-detail-row"><td colSpan={7}>
                        <div className="tt-detail">
                          {[
                            ['Organisation', t.organization], ['Department', t.department], ['Location', t.key_location],
                            ['Tender type', t.tender_type], ['Published', formatDate(t.published_date)], ['Bid opening', formatDate(t.opening_date)],
                            ['Last date to submit', `${formatDate(t.due_date)}${daysLeft(t.due_date) !== null ? ` (${(daysLeft(t.due_date) as number) < 0 ? 'closed' : `${daysLeft(t.due_date)} days left`})` : ''}`],
                            ['Estimated value', money(t.worth_amount, t.worth).full], ['EMD (bid security)', money(t.emd_amount, t.emd).full],
                            ['Document fee', money(t.doc_fee_amount, t.doc_fees).full], ['Documents downloaded', `${t.file_count ?? 0} file${t.file_count === 1 ? '' : 's'}`],
                            ['Downloaded on', t.downloaded_at ? new Date(t.downloaded_at).toLocaleString() : '—'], ['Tender Tiger ID', t.tid],
                          ].map(([k, v]) => (
                            <div key={k as string} className="tt-detail-item"><span>{k}</span><b>{v || '—'}</b></div>
                          ))}
                        </div>
                        <div className="tt-detail-actions">
                          <button type="button" className="btn-primary text-xs py-2 px-4" onClick={() => navigate(`/tender/tiger/${encodeURIComponent(t.tid)}`)}>Open documents <ArrowRight className="w-4 h-4" /></button>
                          {t.tender_link && <a className="btn-ghost-pill" href={t.tender_link} target="_blank" rel="noreferrer"><ExternalLink className="w-4 h-4" /> Original listing</a>}
                        </div>
                      </td></tr>
                    )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-3 px-3">
              <div className="text-sm text-secondary font-semibold hero-subtitle-custom">
                Page <span className="font-semibold text-primary">{page}</span> of{' '}
                <span className="font-semibold text-primary">{totalPages}</span>
                {' '}· {data?.total} tenders
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => update({ page: String(Math.max(1, page - 1)) }, true)}
                  disabled={page === 1}
                  className="px-4 py-2 rounded-xl border border-mid bg-surface hover:bg-raised text-primary text-sm font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 cursor-pointer shadow-sm"
                >
                  <ChevronLeft className="w-4.5 h-4.5" />
                  Previous
                </button>
                <button
                  onClick={() => update({ page: String(Math.min(totalPages, page + 1)) }, true)}
                  disabled={page === totalPages}
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

export default TenderTigerPage;
