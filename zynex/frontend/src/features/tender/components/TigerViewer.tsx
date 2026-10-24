import React, { useEffect, useState } from 'react';
import { Download, Loader2, Play, X, FileText } from 'lucide-react';

export type ViewerSource =
  | { kind: 'pdf'; url: string }
  | { kind: 'text'; text: string; note?: string };

interface Props {
  title: string;
  subtitle?: string;
  /** Loads what to show; called once when the viewer opens. */
  load: () => Promise<ViewerSource>;
  onClose: () => void;
  onDownload?: () => void;
  onAnalyse?: () => void;
  analysing?: boolean;
}

/** Full-screen reader for a tender file: PDFs in the browser's own viewer, DOCX/TXT as plain text. */
export const TigerViewer: React.FC<Props> = ({ title, subtitle, load, onClose, onDownload, onAnalyse, analysing }) => {
  const [source, setSource] = useState<ViewerSource | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    let url: string | null = null;
    load()
      .then(src => { if (!live) { if (src.kind === 'pdf') URL.revokeObjectURL(src.url); return; } if (src.kind === 'pdf') url = src.url; setSource(src); })
      .catch(e => { if (live) setError(e?.response?.data?.detail || e?.message || 'Could not open this file'); });
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = prev; };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={title} onClick={onClose}>
      <div className="bg-surface border border-mid rounded-3xl shadow-2xl w-full max-w-[1700px] h-full max-h-[94vh] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-3 px-5 py-3 bg-raised border-b border-mid">
          <div className="w-8 h-8 min-w-[32px] rounded-xl flex items-center justify-center border border-indigo-500/20 bg-indigo-500/10">
            <FileText className="w-4 h-4 text-indigo-500" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-primary truncate" title={title}>{title}</div>
            {subtitle && <div className="text-xs text-muted truncate">{subtitle}</div>}
          </div>
          {onDownload && (
            <button type="button" onClick={onDownload} className="btn-ghost-pill cursor-pointer" title="Download this file">
              <Download className="w-4 h-4 text-indigo-500" /><span>Download</span>
            </button>
          )}
          {onAnalyse && (
            <button type="button" onClick={onAnalyse} disabled={analysing}
              className="btn-primary cursor-pointer text-sm py-2.5 px-5 disabled:opacity-50 disabled:cursor-not-allowed">
              {analysing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Check eligibility
            </button>
          )}
          <button type="button" onClick={onClose} className="p-2 rounded-xl border border-mid hover:border-rose-500/50 text-muted hover:text-rose-600 transition-colors cursor-pointer" title="Close (Esc)" aria-label="Close viewer">
            <X className="w-4.5 h-4.5" />
          </button>
        </div>

        <div className="flex-1 min-h-0 bg-raised">
          {error ? (
            <p className="p-8 text-sm font-mono font-semibold text-rose-600" role="alert">{error}</p>
          ) : !source ? (
            <div className="h-full flex flex-col items-center justify-center gap-3 text-secondary" role="status">
              <Loader2 className="w-7 h-7 animate-spin text-indigo-500" />
              <span className="text-sm font-semibold">Opening the file…</span>
            </div>
          ) : source.kind === 'pdf' ? (
            <iframe title={title} src={source.url} className="w-full h-full border-0 bg-white" />
          ) : (
            <div className="h-full overflow-auto p-5 sm:p-8">
              {source.note && <p className="mb-4 text-xs font-semibold text-amber-600">{source.note}</p>}
              <pre className="text-sm text-primary leading-relaxed whitespace-pre-wrap break-words font-sans max-w-[900px] mx-auto">{source.text || 'No readable text was found in this file.'}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TigerViewer;
