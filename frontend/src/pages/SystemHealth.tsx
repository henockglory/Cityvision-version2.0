import { useTranslation } from 'react-i18next';
import { Activity, Cpu, MemoryStick, HardDrive, Wifi, Server } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import LoadingState from '@/components/ui/LoadingState';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import { useHealth } from '@/hooks/api/queries';
import type { SystemHealthMetric } from '@/types';

const metricIcons: Record<string, typeof Cpu> = {
  CPU: Cpu,
  Mémoire: MemoryStick,
  Memory: MemoryStick,
  Disque: HardDrive,
  Disk: HardDrive,
  Réseau: Wifi,
  Network: Wifi,
  postgres: Server,
  database: Server,
};

function HealthBar({ metric }: { metric: SystemHealthMetric }) {
  const numValue = parseFloat(metric.value);
  const isPercent = metric.unit === '%';
  const percent = isPercent ? numValue : metric.status === 'healthy' ? 100 : metric.status === 'warning' ? 70 : 30;
  const barColor =
    metric.status === 'healthy' ? 'bg-emerald-400' :
    metric.status === 'warning' ? 'bg-amber-400' : 'bg-red-400';

  return (
    <div className="cv-card-hover p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {(() => {
            const Icon = metricIcons[metric.name] ?? Server;
            return <Icon className="w-5 h-5 text-cv-accent" />;
          })()}
          <span className="font-medium capitalize">{metric.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-display text-lg font-bold">
            {metric.value}{metric.unit ? ` ${metric.unit}` : ''}
          </span>
          <span className={`w-2.5 h-2.5 rounded-full ${barColor}`} />
        </div>
      </div>
      {isPercent && (
        <div className="h-2 rounded-full bg-cv-deep overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${barColor}`}
            style={{ width: `${Math.min(percent, 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}

export default function SystemHealth() {
  const { t } = useTranslation();
  const { data: health = [], isLoading, isError, refetch } = useHealth();

  if (isLoading) return <LoadingState />;

  if (isError) {
    return (
      <div>
        <PageHeader title={t('systemHealth.title')} />
        <ErrorState onRetry={() => void refetch()} />
      </div>
    );
  }

  if (health.length === 0) {
    return (
      <div>
        <PageHeader title={t('systemHealth.title')} />
        <EmptyState title={t('systemHealth.empty')} hint={t('systemHealth.emptyHint')} icon={Activity} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title={t('systemHealth.title')} />
      <h2 className="font-display text-sm font-semibold text-cv-muted uppercase tracking-wider mb-3">
        {t('systemHealth.services')}
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {health.map((metric) => (
          <HealthBar key={metric.name} metric={metric} />
        ))}
      </div>
    </div>
  );
}
