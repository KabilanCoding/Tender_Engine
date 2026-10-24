import React, { useState } from 'react';
import { CriterionResult } from '../api';
import { StatusBadge } from './StatusBadge';
import { ChevronDown, ChevronUp, BookOpen, FileText, Search, X, ShieldCheck, Tag } from 'lucide-react';

interface CriteriaTableProps {
  results?: CriterionResult[];
}

const STATUS_FILTERS = ['ALL', 'FAIL', 'MISSING', 'NEEDS_REVIEW', 'PASS', 'INFORMATIONAL'];
const FILTER_NAMES: Record<string, string> = {
  ALL: 'All', FAIL: 'Not met', MISSING: 'No company data', NEEDS_REVIEW: 'Check by hand', PASS: 'Met', INFORMATIONAL: 'For information',
};

function renderSafeValue(value: any): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'object') {
    try {
      if (Array.isArray(value)) {
        return value.map(v => (typeof v === 'object' ? JSON.stringify(v) : String(v))).join(', ');
      }
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function getFormattedFieldLabel(r: CriterionResult): string {
  if (r.title) return r.title;
  const f = (r.field || '').toLowerCase().trim();
  const src = (r.source_text || '').toLowerCase();
  const val = renderSafeValue(r.tender_requirement || r.tender_value).toLowerCase();
  const combined = `${src} ${val}`;

  if (f === 'annual_turnover') return 'Annual Turnover';
  if (f === 'experience_years' || f === 'years_in_business') return 'Years of Experience';
  if (f === 'iso_9001') return 'ISO 9001 Quality Cert';
  if (f === 'iso_27001') return 'ISO 27001 Security Cert';
  if (f === 'cmmi' || f === 'cmmi_level') return 'CMMI Quality Standard';
  if (f === 'blacklisted') return 'Non-Blacklisting Status';
  if (f === 'gst_registration') return 'GST Registration';
  if (f === 'pan_card') return 'PAN Card Document';
  if (f === 'emd_amount') return 'EMD Amount';
  if (f === 'tender_fee') return 'Tender Fee';
  if (f === 'bid_validity_days') return 'Bid Validity Period';
  if (f === 'technology_stack_certificate' || f === 'tech_stack') return 'Technical Stack & Frameworks';
  if (f === 'security_controls') return 'Security & OWASP Compliance';
  if (f === 'api_protocols' || f === 'api_architecture') return 'API Architecture & Protocols';

  // Keyword heuristics for unmapped / 'other' fields
  if (combined.includes('owasp') || combined.includes('security')) return 'Security & OWASP Compliance';
  if (combined.includes('api') || combined.includes('mqtt') || combined.includes('grpc') || combined.includes('graphql')) return 'API Architecture & Protocols';
  if (combined.includes('java') || combined.includes('golang') || combined.includes('node') || combined.includes('python') || combined.includes('.net') || combined.includes('framework')) return 'Backend Frameworks & Languages';
  if (combined.includes('gps') || combined.includes('iot') || combined.includes('telematics')) return 'IoT & Telematics Capability';
  if (combined.includes('turnover') || combined.includes('inr') || combined.includes('crore') || combined.includes('lakh')) return 'Financial Capacity';
  if (combined.includes('experience') || combined.includes('project')) return 'Past Project Experience';

  if (!f || f === 'other' || f === 'procedural') return 'Technical Specification';

  return f.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function getExactRequirementText(r: CriterionResult): string {
  if (r.requirement) return r.requirement;
  const reqVal = renderSafeValue(r.tender_requirement || r.tender_value);
  const srcText = r.source_text ? renderSafeValue(r.source_text).trim() : '';

  if (!srcText) return reqVal;

  if (srcText.length > reqVal.length + 15) {
    return srcText;
  }

  if (reqVal !== '-' && !srcText.toLowerCase().includes(reqVal.toLowerCase())) {
    return `${reqVal} — ${srcText}`;
  }

  return srcText || reqVal;
}

export const CriteriaTable: React.FC<CriteriaTableProps> = ({ results = [] }) => {
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  const safeResults = Array.isArray(results) ? results : [];

  // Filter by status and search query
  const filtered = safeResults.filter(r => {
    if (!r) return false;
    const matchesStatus = filterStatus === 'ALL' || r.status === filterStatus;
    if (!matchesStatus) return false;

    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    const idStr = String(r.criterion_id || '').toLowerCase();
    const fieldStr = getFormattedFieldLabel(r).toLowerCase();
    const reqStr = getExactRequirementText(r).toLowerCase();
    const companyStr = renderSafeValue(r.company_value).toLowerCase();
    const reasonStr = String(r.reason || (r as any).ai_reasoning || '').toLowerCase();

    return idStr.includes(q) || fieldStr.includes(q) || reqStr.includes(q) || companyStr.includes(q) || reasonStr.includes(q);
  });

  const mandatory = filtered.filter(r => r && r.mandatory !== false);
  const optional = filtered.filter(r => r && r.mandatory === false);

  const renderSection = (title: string, filtered_rows: CriterionResult[], accent: string) => {
    if (filtered_rows.length === 0) return null;

    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2.5 px-1">
          <span className="text-sm font-semibold text-primary">
            {title} ({filtered_rows.length})
          </span>
        </div>

        <div className="rounded-2xl overflow-hidden border border-mid shadow-sm bg-surface">
          <table className="data-table">
            <thead>
              <tr>
                <th className="w-20">ID</th>
                <th className="w-48">Requirement</th>
                <th>What the tender asks</th>
                <th>What the company has</th>
                <th className="w-36 text-center">Result</th>
                <th className="w-20 text-center">Page</th>
                <th className="w-12 text-center" />
              </tr>
            </thead>
            <tbody>
              {filtered_rows.map((r) => {
                const key = r.criterion_id || `${r.field}-${r.page_no}`;
                const isExpanded = expandedRow === key;
                const fieldLabel = getFormattedFieldLabel(r);
                const exactReqText = getExactRequirementText(r);
                const reasoningText = r.reason || (r as any).ai_reasoning;

                return (
                  <React.Fragment key={key}>
                    <tr
                      className={`cursor-pointer transition-colors ${
                        isExpanded ? 'bg-indigo-500/10 dark:bg-indigo-500/20' : 'hover:bg-indigo-500/5'
                      }`}
                      onClick={() => setExpandedRow(isExpanded ? null : key)}
                    >
                      <td>
                        <span className="font-mono text-xs font-semibold criterion-id-text text-indigo-600 dark:text-indigo-400">
                          {r.criterion_id || '-'}
                        </span>
                      </td>
                      <td>
                        <span className="font-mono text-xs criterion-field-text font-semibold text-primary">
                          {fieldLabel}
                        </span>
                      </td>
                      <td>
                        <span className="text-secondary text-xs leading-relaxed line-clamp-3 font-mono font-medium">
                          {exactReqText}
                        </span>
                      </td>
                      <td>
                        <span className="text-primary text-xs leading-relaxed line-clamp-3 font-medium">
                          {renderSafeValue(r.company_value ?? r.evidence)}
                        </span>
                      </td>
                      <td className="text-center">
                        <div className="flex justify-center">
                          <StatusBadge status={r.status || 'UNKNOWN'} />
                        </div>
                      </td>
                      <td className="text-center">
                        <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded-md bg-raised border border-mid text-secondary">
                          {r.page_no ? `p.${r.page_no}` : '-'}
                        </span>
                      </td>
                      <td className="text-center">
                        <button className="text-muted hover:text-primary transition-colors p-1 rounded-md">
                          {isExpanded
                            ? <ChevronUp className="w-4 h-4 text-indigo-500" />
                            : <ChevronDown className="w-4 h-4" />}
                        </button>
                      </td>
                    </tr>

                    {/* Expanded Grounding & Rationale Drawer */}
                    {isExpanded && (
                      <tr>
                        <td colSpan={7} className="p-0 border-b border-mid bg-raised/50">
                          <div className="p-5 space-y-4 animate-fade-in">
                            {r.source_text && (
                              <div className="space-y-1.5">
                                <div className="flex items-center gap-2 text-xs font-mono font-semibold text-indigo-600 dark:text-indigo-400">
                                  <BookOpen className="w-4 h-4" />
                                  <span>Where this is in the tender</span>
                                </div>
                                <div className="bg-surface border border-mid rounded-xl p-4 text-xs leading-relaxed font-mono text-primary shadow-inner">
                                  "{renderSafeValue(r.source_text)}"
                                </div>
                              </div>
                            )}

                            {r.evidence && (
                              <div className="space-y-1.5">
                                <div className="flex items-center gap-2 text-xs font-mono font-semibold text-secondary">
                                  <ShieldCheck className="w-4 h-4 text-emerald-500" />
                                  <span>What the company records show</span>
                                </div>
                                <div className="text-xs text-secondary leading-relaxed font-mono bg-surface/80 border border-mid rounded-xl p-3.5">
                                  {renderSafeValue(r.evidence)}
                                </div>
                              </div>
                            )}

                            {r.grounded === false && (
                              <div className="text-xs font-mono font-semibold text-rose-600 bg-rose-500/10 border border-rose-500/30 rounded-xl p-3">
                                We could not find these exact words in the tender. Please check this requirement in the tender document before relying on it.
                              </div>
                            )}

                            {reasoningText && (
                              <div className="space-y-1.5">
                                <div className="flex items-center gap-2 text-xs font-mono font-semibold text-secondary">
                                  <FileText className="w-4 h-4 text-purple-500" />
                                  <span>Explanation</span>
                                </div>
                                <div className="text-xs text-secondary leading-relaxed font-mono bg-surface/80 border border-mid rounded-xl p-3.5">
                                  {renderSafeValue(reasoningText)}
                                </div>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Search and Filter Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        {/* Search input */}
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search requirements..."
            className="w-full pl-10 pr-9 py-2.5 rounded-xl border border-mid bg-surface text-primary text-xs font-mono placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-primary p-0.5 rounded-full"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Status filter pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {STATUS_FILTERS.map(s => {
            const isActive = filterStatus === s;
            const count = s === 'ALL'
              ? safeResults.length
              : safeResults.filter(r => r && r.status === s).length;

            return (
              <button
                key={s}
                onClick={() => setFilterStatus(s)}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-mono font-semibold border transition-all cursor-pointer flex items-center gap-1.5 ${
                  isActive
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-md shadow-indigo-500/20'
                    : 'bg-surface text-secondary border-mid hover:border-indigo-500/40 hover:text-primary'
                }`}
              >
                <span>{FILTER_NAMES[s] ?? s}</span>
                <span className={`px-1.5 py-0.2 rounded-md text-[10px] font-mono ${
                  isActive ? 'bg-white/20 text-white' : 'bg-raised text-muted'
                }`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {mandatoriesCount(mandatory, optional, renderSection)}
    </div>
  );
};

function mandatoriesCount(mandatory: CriterionResult[], optional: CriterionResult[], renderSection: any) {
  return (
    <div className="space-y-8">
      {renderSection('Must-have requirements', mandatory, '#014BAA')}
      {renderSection('Nice-to-have and information only', optional, '#06b6d4')}
    </div>
  );
}
