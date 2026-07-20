import type { Alert } from '@/types';

const severityStyles: Record<Alert['severity'], string> = {
  low: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
  medium: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  high: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  critical: 'bg-red-500/15 text-red-400 border-red-500/30',
};

interface SeverityBadgeProps {
  severity: Alert['severity'];
}

export default function SeverityBadge({ severity }: SeverityBadgeProps) {
  return (
    <span className={`cv-badge border capitalize shrink-0 ${severityStyles[severity]}`}>
      {severity}
    </span>
  );
}
