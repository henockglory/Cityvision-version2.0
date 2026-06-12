import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  trend?: string;
  accent?: boolean;
}

export default function StatCard({ label, value, icon: Icon, trend, accent }: StatCardProps) {
  return (
    <div className="cv-card-hover p-5 animate-fade-in">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-cv-muted mb-1">{label}</p>
          <p className={`cv-stat-value ${accent ? '' : 'text-[var(--cv-text)]'}`}>{value}</p>
          {trend && <p className="text-xs text-cv-muted mt-1">{trend}</p>}
        </div>
        <div className="p-2.5 rounded-lg bg-cv-accent/10 border border-cv-accent/20">
          <Icon className="w-5 h-5 text-cv-accent" />
        </div>
      </div>
    </div>
  );
}
