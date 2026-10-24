import React from 'react';
import { CheckCircle2, XCircle, AlertTriangle, Minus } from 'lucide-react';

interface VerdictBannerProps {
  verdict: string;
}

interface VerdictConfig {
  label: string;
  sublabel: string;
  icon: React.ElementType;
  containerClass: string;
  iconColor: string;
  labelColor: string;
}

const VERDICT_CONFIG: Record<string, VerdictConfig> = {
  PASS: {
    label: 'Eligible',
    sublabel: 'The company meets every must-have requirement',
    icon: CheckCircle2,
    containerClass: 'verdict-pass',
    iconColor: 'var(--ok)',
    labelColor: 'var(--ok)',
  },
  FAIL: {
    label: 'Not eligible',
    sublabel: 'The company does not meet at least one must-have requirement',
    icon: XCircle,
    containerClass: 'verdict-fail',
    iconColor: 'var(--bad)',
    labelColor: 'var(--bad)',
  },
  PARTIAL: {
    label: 'Cannot confirm yet',
    sublabel: 'Some must-have points need company data or a person to check',
    icon: AlertTriangle,
    containerClass: 'verdict-partial',
    iconColor: 'var(--warn)',
    labelColor: 'var(--warn)',
  },
  PARTIAL_PROVISIONAL: {
    label: 'Cannot confirm yet',
    sublabel: 'Some must-have points need company data or a person to check',
    icon: AlertTriangle,
    containerClass: 'verdict-partial',
    iconColor: 'var(--warn)',
    labelColor: 'var(--warn)',
  },
};

export const VerdictBanner: React.FC<VerdictBannerProps> = ({ verdict }) => {
  const normalised = verdict?.toUpperCase().replace(/-/g, '_') || '';
  const config = VERDICT_CONFIG[normalised] || {
    label: verdict || 'UNKNOWN',
    sublabel: 'Evaluation status undetermined',
    icon: Minus,
    containerClass: '',
    iconColor: '#64748b',
    labelColor: '#94a3b8',
  };

  const Icon = config.icon;

  return (
    <div
      className={`verdict-hero rounded-2xl px-5 py-4 flex items-center gap-4 ${config.containerClass} animate-fade-slide-in`}
      role="status"
      aria-label={`Verdict: ${config.label}`}
    >
      <span className="verdict-icon" style={{ color: config.iconColor }}>
        <Icon className="w-6 h-6" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <div className="verdict-eyebrow">Verdict</div>
        <div className="verdict-title text-xl font-bold tracking-tight" style={{ color: config.labelColor }}>
          {config.label}
        </div>
        <div className="verdict-sublabel text-sm mt-0.5" style={{ color: config.labelColor }}>
          {config.sublabel}
        </div>
      </div>
    </div>
  );
};
