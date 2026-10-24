import React from 'react';
import { CheckCircle2, Loader2, ShieldCheck, FileText, Database, Scale, Workflow, FileUp, FileCheck2, ListChecks } from 'lucide-react';
import { ListMagnifyingGlass } from '@phosphor-icons/react'

interface ProgressStepperProps {
  currentStep?: string;
  isDone?: boolean;
  metrics?: Record<string, any>;
}

const STAGES = [
  { id: 'S1',  label: 'S1 Check the file',           icon: ShieldCheck, desc: 'Verifying file format, size & that it is a tender' },
  { id: 'S2A', label: 'S2a Read the text',  icon: FileUp,      desc: 'Reading text content and page layouts' },
  { id: 'S2B', label: 'S2b Read scanned pages',       icon: FileText,    desc: 'OCR for scanned pages (skipped when not needed)' },
  { id: 'S3',  label: 'S3 Find chapters and sections',        icon: Workflow,    desc: 'Organizing chapters, sections & clauses' },
  { id: 'S4',  label: 'S4 Split into clauses',       icon: Database,    desc: 'Grouping related terms & conditions' },
  { id: 'S5',  label: 'S5 Find the eligibility pages',       icon: Workflow,    desc: 'Finding the pages that state who may bid' },
  { id: 'S6',  label: 'S6 AI lists the requirements',         icon: ListMagnifyingGlass, desc: 'AI extracts the eligibility requirements' },
  { id: 'S7',  label: 'S7 Check quotes against the tender', icon: ShieldCheck, desc: 'Verifying each quote exists in the tender' },
  { id: 'S8',  label: 'S8 Match with company records',    icon: Database,    desc: 'Mapping each requirement to the company records that answer it' },
  { id: 'S9',  label: 'S9 Compare and mark each one',      icon: Scale,       desc: 'Checking each requirement against the company records' },
  { id: 'S10', label: 'S10 Final result and explanations',   icon: FileCheck2,  desc: 'Working out the final result and writing simple explanations' },
  { id: 'S11', label: 'S11 Full tender checklist',   icon: ListChecks,  desc: 'Reading the whole tender: scope of work, dates, money terms, submission and evaluation rules' },
];

const STAGE_ORDER: Record<string, number> = {
  S1: 1, S1_FILE_VALIDATION: 1, S1_FILE_VALIDATOR: 1,
  S2: 2, S2A: 2, S2_PDF_EXTRACTION: 2, S2A_PDF_EXTRACTOR: 2,
  S2B: 3, S2B_OCR_FALLBACK: 3, S2B_OCR_SERVICE: 3,
  S3: 4, S3_STRUCTURE_ANALYSIS: 4, S3_STRUCTURE_ANALYZER: 4,
  S4: 5, S4_CHUNKING: 5, S4_CHUNKER: 5,
  S5: 6, S5_CHUNK_STORE: 6, S5_POSTGRES_STORE: 6,
  S6: 7, S6_LLM_EXTRACTION: 7, S6_LLM_EXTRACTOR: 7,
  S7: 8, S7_POST_VALIDATION: 8, S7_POST_VALIDATOR: 8, S7_GROUNDING_VALIDATOR: 8,
  S8: 9, S8_NORMALISATION: 9, S8_NORMALISER: 9, S8_VALUE_NORMALISER: 9, S8_NORMALIZER: 9,
  S9: 10, S9_RULE_ENGINE: 10,
  S10: 11, S10_VERDICT_AGGREGATION: 11, S10_VERDICT_AGGREGATOR: 11,
  S11: 12, S11_REPORT_BUILDER: 12
};

function getStageStatus(stageId: string, currentStep?: string, isDone?: boolean) {
  if (isDone) return 'done';
  if (!currentStep) return 'pending';

  const cleanStep = currentStep.trim().toUpperCase();
  const currentNum = STAGE_ORDER[cleanStep] || STAGE_ORDER[cleanStep.split('_')[0]] || 0;
  const stageNum   = STAGE_ORDER[stageId] || 0;

  if (currentNum === 0) {
    const currentPrefix = cleanStep.split('_')[0];
    const stagePrefix = stageId.split('_')[0];
    if (stagePrefix === currentPrefix) return 'active';
    return 'pending';
  }

  if (stageNum < currentNum) return 'done';
  if (stageNum === currentNum) return 'active';
  return 'pending';
}

export const ProgressStepper: React.FC<ProgressStepperProps> = ({
  currentStep,
  isDone = false,
  metrics = {}
}) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
      {STAGES.map((stage) => {
        const status = getStageStatus(stage.id, currentStep, isDone);
        const Icon = stage.icon;

        let borderClass = 'stage-item-pending border-mid';
        let textClass   = 'text-muted';
        let iconBg      = 'bg-surface text-muted border border-mid';
        let badgeText   = 'Pending';
        let badgeClass  = 'bg-raised text-muted border-mid';

        if (status === 'done') {
          borderClass = 'stage-item-done border-emerald-500/40 shadow-sm';
          textClass   = 'text-primary font-semibold';
          iconBg      = 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/40 shadow-sm';
          badgeText   = 'Completed';
          badgeClass  = 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/40';
        } else if (status === 'active') {
          borderClass = 'stage-item-active border-indigo-500/60 shadow-lg shadow-indigo-500/15 scale-[1.01]';
          textClass   = 'text-primary font-semibold';
          iconBg      = 'bg-indigo-600 text-white shadow-md shadow-indigo-500/30';
          badgeText   = 'Processing';
          badgeClass  = 'bg-indigo-600 text-white animate-pulse shadow-sm';
        }

        return (
          <div
            key={stage.id}
            title={stage.desc}
            className={`stage-item px-3 py-2 rounded-xl border transition-all duration-200 flex items-center justify-between gap-3 ${borderClass}`}
          >
            <div className="flex items-center gap-4 min-w-0 flex-1">
              <div className={`w-8 h-8 min-w-[32px] min-h-[32px] max-w-[32px] max-h-[32px] rounded-lg flex items-center justify-center flex-shrink-0 font-semibold ${iconBg}`}>
                {status === 'active' ? (
                  <Loader2 className="w-4 h-4 animate-spin text-white" />
                ) : status === 'done' ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                ) : (
                  <Icon className="w-4 h-4" />
                )}
              </div>

              <div className="min-w-0 flex-1">
                <div className={`text-xs font-semibold leading-tight ${textClass} hero-subtitle-custom`}>
                  {stage.label}
                </div>
                <div className="hidden text-xs text-secondary truncate hero-subtitle-custom font-medium">
                  {stage.desc}
                </div>
              </div>
            </div>

            <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-md border flex-shrink-0 hero-subtitle-custom ${badgeClass}`}>
              {badgeText}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export default ProgressStepper;
