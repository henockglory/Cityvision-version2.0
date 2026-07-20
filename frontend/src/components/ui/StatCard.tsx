import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  accent?: boolean;
  trend?: string;
}

export default function StatCard({ label, value, icon: Icon, accent, trend }: StatCardProps) {
  return (
    <div className={`cv-card-hover p-5 ${accent ? 'border-cv-electric/30' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-cv-muted uppercase tracking-wide text-xs">{label}</span>
        <div className={`p-2 rounded-lg ${accent ? 'bg-cv-electric/15 border border-cv-cyan-glow/30 shadow-glow' : 'bg-cv-black/50 border border-cv-border'}`}>
          <Icon className={`w-4 h-4 ${accent ? 'text-cv-cyan-glow' : 'text-cv-muted'}`} />
        </div>
      </div>
      <p className="cv-stat-value">{value}</p>
      {trend && <p className="text-xs text-cv-muted mt-1">{trend}</p>}
    </div>
  );
}
