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
    <div className="cv-card-hover p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-cv-muted">{label}</span>
        <div className={`p-2 rounded-lg ${accent ? 'bg-cv-accent/15 border border-cv-accent/25' : 'bg-cv-deep/50 border border-cv-border'}`}>
          <Icon className={`w-4 h-4 ${accent ? 'text-cv-accent' : 'text-cv-muted'}`} />
        </div>
      </div>
      <p className="cv-stat-value">{value}</p>
      {trend && <p className="text-xs text-cv-muted mt-1">{trend}</p>}
    </div>
  );
}
