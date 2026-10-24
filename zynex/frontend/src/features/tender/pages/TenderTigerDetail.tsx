import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { tigerApi, TigerFile, TigerTenderDetail, TigerZipEntry, daysLeft, formatDate, formatMoney, formatSize } from '../tigerApi';
import { TigerViewer, ViewerSource } from '../components/TigerViewer';
import { RunBadge } from './TenderTiger';
import { CheckCheck, ArrowLeft, Building2, Calendar, Check, ChevronDown, ChevronUp, Copy, Download, Eye, ExternalLink, FileText, MapPin, Package, Play, Archive, Loader2 } from 'lucide-react';

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-semibold text-muted">{label}</div>
      <div className="text-sm font-semibold text-primary break-words">{value || '—'}</div>
    </div>
  );
}

export const TenderTigerDetailPage: React.FC = () => {
  const { tid = '' } = useParams();
  const navigate = useNavigate();
  const [tender, setTender] = useState<TigerTenderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [viewing, setViewing] = useState<{ title: string; subtitle?: string; load: () => Promise<ViewerSource>;
    download?: () => void; file?: TigerFile } | null>(null);
  const [openZip, setOpenZip] = useState<string | null>(null);
  const [zipEntries, setZipEntries] = useState<Record<string, TigerZipEntry[] | 'loading' | string>>({});
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setLoading(true);
    tigerApi.detail(tid)
      .then(setTender)
      .catch(e => setError(e?.response?.status === 404 ? 'This tender was not found.' : e?.message || 'Could not load the tender'))
      .finally(() => setLoading(false));
  }, [tid]);

  const analyse = async (file: TigerFile) => {
    setError(null);
    setBusy(file.id);
    try {
      const run = await tigerApi.analyse(file.id);
      navigate(`/tender/processing/${run.run_id}`);
    } catch (e: any) {
      setError(e.message || 'Could not start the analysis');
      setBusy(null);
    }
  };

  const view = (file: TigerFile) => setViewing({
    title: file.file_name,
    subtitle: `${file.kind === 'zip' ? 'Zip file' : 'Tender document'} · ${formatSize(file.size)}`,
    file,
    download: () => download(file),
    load: async () => {
      if (file.file_name.toLowerCase().endsWith('.pdf')) return { kind: 'pdf', url: await tigerApi.pdfUrl(file.id) };
      const t = await tigerApi.text(file.id);
      return { kind: 'text', text: t.text, note: t.truncated ? `Showing the first ${t.text.length.toLocaleString()} of ${t.characters.toLocaleString()} characters. Download the file to read all of it.` : undefined };
    },
  });

  const toggleZip = async (file: TigerFile) => {
    if (openZip === file.id) { setOpenZip(null); return; }
    setOpenZip(file.id);
    if (zipEntries[file.id] && zipEntries[file.id] !== 'loading') return;
    setZipEntries(z => ({ ...z, [file.id]: 'loading' }));
    try {
      setZipEntries(z => ({ ...z, [file.id]: [] }));
      const entries = await tigerApi.zipContents(file.id);
      setZipEntries(z => ({ ...z, [file.id]: entries }));
    } catch (e: any) {
      setZipEntries(z => ({ ...z, [file.id]: e?.response?.data?.detail || e?.message || 'Could not open this zip' }));
    }
  };

  const entryName = (e: TigerZipEntry) => e.name.split('/').pop() || e.name;

  const viewEntry = (file: TigerFile, e: TigerZipEntry) => setViewing({
    title: entryName(e),
    subtitle: `Inside ${file.file_name} · ${formatSize(e.size)}`,
    download: async () => tigerApi.saveBlob(await tigerApi.zipEntryBlob(file.id, e.index), entryName(e)),
    load: async () => {
      const blob = await tigerApi.zipEntryBlob(file.id, e.index);
      if (e.name.toLowerCase().endsWith('.pdf')) return { kind: 'pdf', url: URL.createObjectURL(new Blob([blob], { type: 'application/pdf' })) };
      return { kind: 'text', text: await blob.text() };
    },
  });

  const copyId = async () => {
    try { await navigator.clipboard.writeText(tid); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  };

  const download = async (file: TigerFile) => {
    try { await tigerApi.downloadFile(file); } catch (e: any) { setError(e?.message || 'Download failed'); }
  };

  const back = (
    <button onClick={() => navigate('/tender/tiger')} className="btn-ghost-pill cursor-pointer w-fit">
      <ArrowLeft className="w-4 h-4 text-indigo-500" /><span>Back to Tender Tiger</span>
    </button>
  );

  if (loading) {
    return (
      <div className="w-full max-w-[1700px] mx-auto py-2 px-4 sm:px-8 space-y-3" role="status" aria-label="Loading tender">
        {back}
        <div className="glass-panel p-6 rounded-3xl space-y-3">
          <div className="skeleton h-6 w-1/2 rounded-md" /><div className="skeleton h-4 w-1/4 rounded-md" /><div className="skeleton h-24 w-full rounded-md" />
        </div>
      </div>
    );
  }

  if (!tender) {
    return (
      <div className="w-full max-w-[1700px] mx-auto py-2 px-4 sm:px-8 space-y-3">
        {back}
        <div className="zx-empty" role="alert">
          <div className="zx-empty-icon"><Package size={28} strokeWidth={1.5} /></div>
          <h2>{error === 'This tender was not found.' ? 'Tender not found' : 'Could not open this tender'}</h2>
          <p>{error === 'This tender was not found.' ? `No tender with ID ${tid} is stored. It may have been removed, or the link is wrong.` : (error || 'Tender not found')}</p>
          <div className="zx-actions">
            <button type="button" onClick={() => navigate('/tender/tiger')} className="zx-action primary"><ArrowLeft size={14} /> All tenders</button>
          </div>
        </div>
      </div>
    );
  }

  const days = daysLeft(tender.due_date);
  const dueText = days === null ? '' : days < 0 ? 'Closed' : days === 0 ? 'Due today' : `${days} day${days === 1 ? '' : 's'} left`;
  const link = tender.tender_link || tender.dept_tender_link || tender.dept_portal_url;
  const about = tender.tender_description || tender.product_description;

  return (
    <div className="w-full max-w-[1700px] mx-auto py-2 px-4 sm:px-8 space-y-3 animate-fade-in hero-subtitle-custom">
      {back}

      <div className="glass-panel rounded-3xl border border-mid shadow-sm p-5 sm:p-6 space-y-5">
        <div className="space-y-1.5 pb-4 border-b border-mid">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <h2 className="text-xl font-semibold tracking-tight text-primary min-w-0">{tender.tender_title || 'Untitled tender'}</h2>
            <button type="button" className={`tt-read-wide ${tender.seen === 'read' ? 'is-read' : ''}`}
              onClick={async () => { const r = await tigerApi.markRead(tender.tid, tender.seen !== 'read'); setTender(t => t && { ...t, seen: r.seen as 'viewed' | 'read' }); }}>
              {tender.seen === 'read' ? <><CheckCheck className="w-4 h-4" /> Read · mark unread</> : <><Check className="w-4 h-4" /> Mark as read</>}
            </button>
          </div>
          <div className="flex items-center gap-4 flex-wrap text-sm text-secondary font-semibold">
            <span className="flex items-center gap-1.5"><Building2 className="w-4 h-4 text-indigo-500" />{tender.organization || 'Organization not listed'}</span>
            <span className="flex items-center gap-1.5"><MapPin className="w-4 h-4 text-indigo-500" />{tender.key_location || '—'}</span>
            <span className="flex items-center gap-1.5"><Calendar className="w-4 h-4 text-indigo-500" />Due {formatDate(tender.due_date)}{dueText && ` · ${dueText}`}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-5">
          <Field label="Downloaded" value={tender.downloaded_at ? new Date(tender.downloaded_at).toLocaleString() : null} />
          <Field label="Tender ID" value={
            <span className="inline-flex items-center gap-2">{tender.tid}
              <button type="button" onClick={copyId} className="p-1 rounded-lg text-muted hover:text-indigo-600 cursor-pointer" title="Copy the tender ID" aria-label="Copy the tender ID">
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
              </button></span>} />
          <Field label="Department tender number" value={tender.dept_tender_number} />
          <Field label="Department" value={tender.department} />
          <Field label="Tender type" value={tender.tender_type} />
          <Field label="Estimated value" value={formatMoney(tender.worth_amount, tender.worth)} />
          <Field label="EMD (bid security)" value={formatMoney(tender.emd_amount, tender.emd)} />
          <Field label="Document fee" value={formatMoney(tender.doc_fee_amount, tender.doc_fees)} />
          <Field label="Quantity" value={tender.quantity} />
          <Field label="Published" value={formatDate(tender.published_date)} />
          <Field label="Due date" value={formatDate(tender.due_date)} />
          <Field label="Opening date" value={formatDate(tender.opening_date)} />
          <Field label="Startup relaxation" value={tender.startup_relaxation} />
        </div>

        {about && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-muted">About this tender</div>
            <p className="text-sm text-secondary leading-relaxed whitespace-pre-line">{about}</p>
          </div>
        )}

        {link && (
          <a href={link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-sm font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
            <ExternalLink className="w-4 h-4" />Open the original listing
          </a>
        )}
      </div>

      <div className="glass-panel rounded-3xl border border-mid shadow-sm overflow-hidden">
        <div className="px-5 py-3 bg-raised border-b border-mid flex items-center justify-between">
          <h3 className="text-sm font-semibold text-primary flex items-center gap-2"><Package className="w-4 h-4 text-indigo-500" />Files ({tender.files.length})</h3>
          <span className="text-xs text-muted font-semibold">Read a file here, or run the eligibility check on a PDF or DOCX</span>
        </div>
        {error && <p className="px-5 pt-3 text-sm font-mono font-semibold text-rose-600" role="alert">{error}</p>}
        {tender.files.length === 0 ? (
          <p className="p-8 text-center text-sm text-secondary">No files were saved for this tender.</p>
        ) : (
          <ul className="divide-y divide-mid">
            {tender.files.map(f => {
              const isZip = f.kind === 'zip';
              const entries = zipEntries[f.id];
              return (
                <li key={f.id}>
                  <div className="px-5 py-3 flex items-center gap-4 flex-wrap sm:flex-nowrap">
                    <div className="w-8 h-8 min-w-[32px] rounded-xl flex items-center justify-center border border-indigo-500/20 bg-indigo-500/10">
                      {isZip ? <Archive className="w-4 h-4 text-indigo-500" /> : <FileText className="w-4 h-4 text-indigo-500" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-primary truncate" title={f.file_name}>{f.file_name}</div>
                      <div className="text-xs text-muted">{isZip ? 'All documents in one zip' : 'Tender document'} · {f.on_disk === false
                        ? <span style={{ color: 'var(--bad)' }}>not in the tender folder on this server</span> : formatSize(f.size)}</div>
                    </div>
                    {!isZip && <RunBadge run={f.last_run} onOpen={() => f.last_run && navigate(
                      f.last_run.state === 'RUNNING' ? `/tender/processing/${f.last_run.run_id}` : `/tender/report/${f.last_run.run_id}`)} />}
                    {isZip ? (
                      <button type="button" onClick={() => toggleZip(f)} className="btn-ghost-pill cursor-pointer" aria-expanded={openZip === f.id}>
                        {openZip === f.id ? <ChevronUp className="w-4 h-4 text-indigo-500" /> : <ChevronDown className="w-4 h-4 text-indigo-500" />}
                        <span>{openZip === f.id ? 'Hide contents' : 'See contents'}</span>
                      </button>
                    ) : (
                      <button type="button" onClick={() => view(f)} className="btn-ghost-pill cursor-pointer" title="Read this file here">
                        <Eye className="w-4 h-4 text-indigo-500" /><span>View</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => download(f)}
                      className="p-2 rounded-xl border border-mid hover:border-indigo-500/40 text-muted hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors min-w-[38px] min-h-[38px] flex items-center justify-center cursor-pointer"
                      title="Download this file"
                      aria-label={`Download ${f.file_name}`}
                    >
                      <Download className="w-4.5 h-4.5" />
                    </button>
                    {f.analysable ? (
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => analyse(f)}
                        className="btn-primary cursor-pointer text-sm py-2.5 px-5 shadow-lg shadow-indigo-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {busy === f.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                        {f.last_run ? 'Check again' : 'Check eligibility'}
                      </button>
                    ) : (
                      <span className="text-xs text-muted font-semibold w-[150px] text-right">{isZip ? 'Open a file from inside' : ''}</span>
                    )}
                  </div>
                  {isZip && openZip === f.id && (
                    <div className="bg-raised border-t border-mid px-5 py-3 space-y-1.5">
                      {entries === 'loading' || entries === undefined ? (
                        <div className="flex items-center gap-2 text-sm text-secondary"><Loader2 className="w-4 h-4 animate-spin text-indigo-500" />Reading the zip…</div>
                      ) : typeof entries === 'string' ? (
                        <p className="text-sm font-mono font-semibold text-rose-600" role="alert">{entries}</p>
                      ) : entries.length === 0 ? (
                        <p className="text-sm text-secondary">This zip is empty.</p>
                      ) : entries.map(e => (
                        <div key={e.index} className="flex items-center gap-3 py-1">
                          <FileText className="w-4 h-4 text-muted flex-shrink-0" />
                          <span className="text-sm font-semibold text-primary truncate flex-1" title={e.name}>{e.name}</span>
                          <span className="text-xs text-muted w-16 text-right">{formatSize(e.size)}</span>
                          {/\.(pdf|txt)$/i.test(e.name) ? (
                            <button type="button" onClick={() => viewEntry(f, e)} className="btn-ghost-pill cursor-pointer"><Eye className="w-4 h-4 text-indigo-500" /><span>View</span></button>
                          ) : <span className="w-[84px]" />}
                          <button type="button" onClick={async () => tigerApi.saveBlob(await tigerApi.zipEntryBlob(f.id, e.index), entryName(e))}
                            className="p-2 rounded-xl border border-mid hover:border-indigo-500/40 text-muted hover:text-indigo-600 transition-colors cursor-pointer" title="Download" aria-label={`Download ${entryName(e)}`}>
                            <Download className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {viewing && (
        <TigerViewer
          title={viewing.title}
          subtitle={viewing.subtitle}
          load={viewing.load}
          onClose={() => setViewing(null)}
          onDownload={viewing.download}
          onAnalyse={viewing.file?.analysable ? () => analyse(viewing.file!) : undefined}
          analysing={busy !== null}
        />
      )}
    </div>
  );
};

export default TenderTigerDetailPage;
