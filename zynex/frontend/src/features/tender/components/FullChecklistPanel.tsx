import React, { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ClipboardCopy, Download, ListChecks, Search } from 'lucide-react';
import type { ChecklistItem, FullChecklist } from '../api';

const ORDER = ['eligibility', 'scope', 'deliverables', 'timeline', 'commercial', 'submission', 'evaluation', 'obligations'];
const HINT: Record<string, string> = {
  eligibility: 'What the bidder must be or have',
  scope: 'What the selected company must build, supply or run',
  deliverables: 'What must be handed over',
  timeline: 'Dates and periods',
  commercial: 'EMD, fees, payment, guarantees and penalties',
  submission: 'Forms, documents and how to submit',
  evaluation: 'How bids are scored and ranked',
  obligations: 'Service levels, warranty, security and other duties',
};

function csvCell(v: string) { return `"${v.replace(/"/g, '""')}"`; }

export const FullChecklistPanel: React.FC<{ data: FullChecklist | null; filename: string }> = ({ data, filename }) => {
  const [cat, setCat] = useState<string>('all');
  const [q, setQ] = useState('');
  const [copied, setCopied] = useState(false);
  const items = data?.items ?? [];
  const labels = data?.labels ?? {};

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const i of items) c[i.category] = (c[i.category] ?? 0) + 1;
    return c;
  }, [items]);

  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    return items.filter(i => (cat === 'all' || i.category === cat) && (!t || i.text.toLowerCase().includes(t)));
  }, [items, cat, q]);

  if (!data) {
    return (
      <div className="glass-panel p-6 rounded-2xl text-center text-sm text-secondary">
        <ListChecks className="w-6 h-6 mx-auto mb-2 text-muted" />
        The full checklist was not produced for this run. Turn on “Full tender checklist” in Settings, then upload the tender again.
      </div>
    );
  }

  const lines = (list: ChecklistItem[]) => ORDER.filter(c => list.some(i => i.category === c)).flatMap(c => [
    `${labels[c] ?? c}`,
    ...list.filter(i => i.category === c).map(i => `  - ${i.text} (page ${i.page})`),
    '',
  ]).join('\n');

  async function copy() {
    try { await navigator.clipboard.writeText(`Checklist for ${filename}\n\n${lines(shown)}`); setCopied(true); setTimeout(() => setCopied(false), 2500); }
    catch { /* clipboard blocked: the CSV download still works */ }
  }

  function download() {
    const rows = [['ID', 'Group', 'Requirement (word for word from the tender)', 'Page', 'Compared with company records'],
      ...shown.map(i => [i.id, labels[i.category] ?? i.category, i.text, String(i.page), i.category === 'eligibility' ? (i.compared ? 'Yes' : 'No: check by hand') : ''])];
    const blob = new Blob(['﻿' + rows.map(r => r.map(csvCell).join(',')).join('\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${filename.replace(/\.[^.]+$/, '')}-checklist.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="space-y-3">
      <div className="glass-panel p-4 rounded-2xl flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-primary flex items-center gap-2"><ListChecks className="w-4 h-4" /> Full tender checklist ({items.length} items)</h3>
          <p className="text-xs text-secondary mt-0.5 max-w-3xl">
            Everything the tender asks for, read from the whole document and copied word for word with its page, so you can compare it with your company records yourself.
            Eligibility items marked “compared” were also checked against the knowledge base in the Requirements tab.
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={copy} className="btn-ghost-pill cursor-pointer"><ClipboardCopy className="w-3.5 h-3.5" /> {copied ? 'Copied' : 'Copy'}</button>
          <button type="button" onClick={download} className="btn-ghost-pill cursor-pointer"><Download className="w-3.5 h-3.5" /> Download CSV</button>
        </div>
      </div>

      {data.incomplete && (
        <p className="text-xs flex items-start gap-2 px-1" style={{ color: 'var(--warn)' }} role="status">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {data.metrics?.failed_windows} part(s) of the tender could not be read by the AI model, so this list may be missing items from those pages.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2" />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search the checklist…" aria-label="Search the checklist"
            className="w-full pl-9 pr-3 py-2 bg-surface text-primary border border-mid rounded-xl text-sm focus:outline-none" />
        </div>
        {[['all', 'All', items.length], ...ORDER.filter(c => counts[c]).map(c => [c, labels[c] ?? c, counts[c]] as [string, string, number])].map(([id, label, n]) => (
          <button key={id as string} type="button" onClick={() => setCat(id as string)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold border cursor-pointer ${cat === id ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-surface text-secondary border-mid hover:border-indigo-500'}`}>
            {label} <span className="opacity-70 tabular-nums">{n}</span>
          </button>
        ))}
      </div>

      <div className="tender-scroll space-y-3" style={{ maxHeight: 'calc(100vh - 430px)', minHeight: '16rem' }}>
        {ORDER.filter(c => shown.some(i => i.category === c)).map(c => (
          <section key={c} className="glass-panel rounded-2xl overflow-hidden">
            <header className="px-4 py-2.5 border-b border-subtle flex items-baseline justify-between gap-3">
              <h4 className="text-sm font-semibold text-primary">{labels[c] ?? c} <span className="text-muted font-normal tabular-nums">({shown.filter(i => i.category === c).length})</span></h4>
              <span className="text-xs text-muted hidden sm:inline">{HINT[c]}</span>
            </header>
            <ul>
              {shown.filter(i => i.category === c).map(i => (
                <li key={i.id} className="flex items-start gap-3 px-4 py-2.5 border-t border-subtle first:border-t-0">
                  <span className="text-[11px] tabular-nums text-muted w-10 shrink-0 pt-0.5">{i.id}</span>
                  <p className="text-sm text-primary flex-1 min-w-0" style={{ whiteSpace: 'pre-wrap' }}>{i.text}</p>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className="text-[11px] px-2 py-0.5 rounded-md bg-raised border border-subtle text-secondary tabular-nums">p.{i.page}</span>
                    {i.found_by === 'pattern' && <span className="text-[10px] text-muted" title="Added by a rule that reads numbered clauses, not by the AI model.">found by rule</span>}
                    {i.closest_wording && <span className="text-[10px] text-muted" title="The AI reworded this line; the tender's own closest sentence is shown. Check it on the page.">closest wording</span>}
                    {c === 'eligibility' && (
                      i.compared
                        ? <span className="zx-chip is-ok"><CheckCircle2 className="w-3 h-3" /> Compared</span>
                        : <span className="zx-chip is-review">Check by hand</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
        {shown.length === 0 && <div className="glass-panel p-6 rounded-2xl text-center text-sm text-secondary">No item matches.</div>}
      </div>
    </div>
  );
};
