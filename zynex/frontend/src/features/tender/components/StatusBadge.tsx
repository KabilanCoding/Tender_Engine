import React from 'react';
import { CheckCircle2, XCircle, HelpCircle, AlertTriangle, Info, Clock } from 'lucide-react';

interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
  /** 'verdict' = a whole-tender result (Eligible / Not eligible / Cannot confirm), not one requirement */
  kind?: 'requirement' | 'verdict';
}

const VERDICT_LABEL: Record<string, string> = { PASS: 'Eligible', FAIL: 'Not eligible', PARTIAL: 'Cannot confirm' };

const STATUS_CONFIG: Record<string, {
  icon: React.ElementType;
  label: string;
  className: string;
}> = {
  PASS: {
    icon: CheckCircle2,
    label: 'Met',
    className: 'status-badge-PASS',
  },
  FAIL: {
    icon: XCircle,
    label: 'Not met',
    className: 'status-badge-FAIL',
  },
  MISSING: {
    icon: HelpCircle,
    label: 'No company data',
    className: 'status-badge-MISSING',
  },
  NEEDS_REVIEW: {
    icon: AlertTriangle,
    label: 'Check by hand',
    className: 'status-badge-NEEDS_REVIEW',
  },
  INFORMATIONAL: {
    icon: Info,
    label: 'For information',
    className: 'status-badge-INFORMATIONAL',
  },
  PARTIAL: {
    icon: HelpCircle,
    label: 'Partial',
    className: 'status-badge-MISSING',
  },
  PROVISIONAL: {
    icon: Clock,
    label: 'Not final',
    className: 'status-badge-PROVISIONAL',
  },
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'md', kind = 'requirement' }) => {
  const config = STATUS_CONFIG[status] || {
    icon: HelpCircle,
    label: status || 'UNKNOWN',
    className: 'status-badge-MISSING',
  };

  const Icon = config.icon;
  const iconSize = size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5';

  return (
    <span className={config.className}>
      <Icon className={iconSize} />
      {(kind === 'verdict' && VERDICT_LABEL[status]) || config.label}
    </span>
  );
};
