import type { LucideIcon } from 'lucide-react';
import AnimatedHint from '@/components/ui/AnimatedHint';

export type MetricTone = 'cameras' | 'alerts' | 'events' | 'rules';

const TONE: Record<MetricTone, { ring: string; icon: string; spark: string; glow: string }> = {
  cameras: {
    ring: 'border-metric-cameras/35',
    icon: 'text-metric-cameras bg-metric-cameras/15',
    spark: 'stroke-metric-cameras',
    glow: 'shadow-metric-cameras/15',
  },
  alerts: {
    ring: 'border-metric-alerts/35',
    icon: 'text-metric-alerts bg-metric-alerts/15',
    spark: 'stroke-metric-alerts',
    glow: 'shadow-metric-alerts/15',
  },
  events: {
    ring: 'border-metric-events/35',
    icon: 'text-metric-events bg-metric-events/15',
    spark: 'stroke-metric-events',
    glow: 'shadow-metric-events/15',
  },
  rules: {
    ring: 'border-metric-rules/35',
    icon: 'text-metric-rules bg-metric-rules/15',
    spark: 'stroke-metric-rules',
    glow: 'shadow-metric-rules/15',
  },
};

function Sparkline({ points, className }: { points: number[]; className: string }) {
  if (points.length < 2) return null;
  const w = 88;
  const h = 32;
  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const span = Math.max(max - min, 1);
  const coords = points.map((v, i) => {
    const x = (i / (points.length - 1)) * w;
    const y = h - ((v - min) / span) * (h - 4) - 2;
    return `${x},${y}`;
  });
  const path = `M ${coords.join(' L ')}`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="shrink-0 opacity-90" aria-hidden>
      <path d={path} fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} />
    </svg>
  );
}

interface DashboardMetricCardProps {
  label: string;
  value: string | number;
  secondary?: string;
  icon: LucideIcon;
  tone: MetricTone;
  hint?: string;
  sparkline?: number[];
}

export default function DashboardMetricCard({
  label,
  value,
  secondary,
  icon: Icon,
  tone,
  hint,
  sparkline,
}: DashboardMetricCardProps) {
  const s = TONE[tone];
  const labelEl = (
    <span className="text-[11px] text-cv-muted uppercase tracking-wide font-medium">{label}</span>
  );

  return (
    <div className={`cv-card-hover p-5 border ${s.ring} ${s.glow} shadow-soft h-full flex flex-col gap-4`}>
      <div className="flex items-start justify-between gap-3">
        <div className={`p-2.5 rounded-full border border-cv-border/40 ${s.icon}`}>
          <Icon className="w-4 h-4" />
        </div>
        {hint ? <AnimatedHint hint={hint}>{labelEl}</AnimatedHint> : labelEl}
      </div>
      <div className="flex items-end justify-between gap-3 mt-auto">
        <div className="min-w-0">
          <p className="cv-stat-value text-2xl md:text-3xl leading-none">{value}</p>
          {secondary && <p className="text-xs text-cv-muted mt-1.5 leading-snug">{secondary}</p>}
        </div>
        {sparkline && sparkline.length >= 2 && <Sparkline points={sparkline} className={s.spark} />}
      </div>
    </div>
  );
}
