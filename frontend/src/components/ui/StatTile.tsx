import type { LucideIcon } from 'lucide-react';
import AnimatedHint from '@/components/ui/AnimatedHint';

export type MetricTone = 'cameras' | 'alerts' | 'events' | 'rules' | 'default';

const TONE_STYLES: Record<MetricTone, { ring: string; icon: string; glow: string }> = {
  cameras: {
    ring: 'border-metric-cameras/40',
    icon: 'text-metric-cameras bg-metric-cameras/10',
    glow: 'shadow-metric-cameras/20',
  },
  alerts: {
    ring: 'border-metric-alerts/40',
    icon: 'text-metric-alerts bg-metric-alerts/10',
    glow: 'shadow-metric-alerts/20',
  },
  events: {
    ring: 'border-metric-events/40',
    icon: 'text-metric-events bg-metric-events/10',
    glow: 'shadow-metric-events/20',
  },
  rules: {
    ring: 'border-metric-rules/40',
    icon: 'text-metric-rules bg-metric-rules/10',
    glow: 'shadow-metric-rules/20',
  },
  default: {
    ring: 'border-cv-border',
    icon: 'text-cv-muted bg-cv-black/50',
    glow: '',
  },
};

interface StatTileProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  tone?: MetricTone;
  hint?: string;
  animateIcon?: boolean;
}

export default function StatTile({
  label,
  value,
  icon: Icon,
  tone = 'default',
  hint,
  animateIcon = true,
}: StatTileProps) {
  const s = TONE_STYLES[tone];
  const inner = (
    <div className={`cv-card-hover p-4 border ${s.ring} ${s.glow} shadow-soft h-full`}>
      <div className="flex items-center justify-between gap-3 mb-2">
        {hint ? (
          <AnimatedHint hint={hint}>
            <span className="text-xs text-cv-muted uppercase tracking-wide font-medium">{label}</span>
          </AnimatedHint>
        ) : (
          <span className="text-xs text-cv-muted uppercase tracking-wide font-medium">{label}</span>
        )}
        <div className={`p-2 rounded-lg border border-cv-border/50 ${s.icon}`}>
          <Icon className={`w-4 h-4 ${animateIcon ? 'cv-icon-spin-slow' : ''}`} />
        </div>
      </div>
      <p className="cv-stat-value text-2xl md:text-3xl">{value}</p>
    </div>
  );

  return inner;
}
