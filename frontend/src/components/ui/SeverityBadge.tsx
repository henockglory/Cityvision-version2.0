import type { Alert } from '@/types';

const styles: Record<Alert['severity'], string> = {
  low: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
  medium: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  high: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  critical: 'bg-red-500/15 text-red-400 border-red-500/30',
};

export default function SeverityBadge({ severity }: { severity: Alert['severity'] }) {
  return (
    <span className={`cv-badge border uppercase tracking-wider ${styles[severity]}`}>
      {severity}
    </span>
  );
}
