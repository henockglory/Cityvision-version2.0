import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Filter } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import SeverityBadge from '@/components/ui/SeverityBadge';
import LoadingState from '@/components/ui/LoadingState';
import { useAlerts, useAcknowledgeAlert } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';

export default function Alerts() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const { data: alerts = [], isLoading } = useAlerts();
  const acknowledgeMutation = useAcknowledgeAlert();
  const [filter, setFilter] = useState<'all' | 'active'>('all');

  const filtered = filter === 'active' ? alerts.filter((a) => !a.acknowledged) : alerts;

  const acknowledge = (id: string) => {
    playClick();
    acknowledgeMutation.mutate(id);
  };

  if (isLoading) return <LoadingState />;

  return (
    <div>
      <PageHeader
        title={t('alerts.title')}
        actions={
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => { playClick(); setFilter('all'); }}
              className={`cv-btn-secondary text-xs ${filter === 'all' ? 'border-cv-accent/40' : ''}`}
            >
              {t('alerts.all')}
            </button>
            <button
              type="button"
              onClick={() => { playClick(); setFilter('active'); }}
              className={`cv-btn-secondary text-xs ${filter === 'active' ? 'border-cv-accent/40' : ''}`}
            >
              <Filter className="w-3 h-3" />
              {t('alerts.active')}
            </button>
          </div>
        }
      />

      <div className="space-y-3">
        {filtered.map((alert) => (
          <div
            key={alert.id}
            className={`cv-card p-4 flex items-center gap-4 transition-all ${
              !alert.acknowledged ? 'border-l-2 border-l-cv-accent shadow-glow' : 'opacity-70'
            }`}
          >
            <SeverityBadge severity={alert.severity} />
            <div className="flex-1 min-w-0">
              <p className="font-medium">{alert.message}</p>
              <div className="flex items-center gap-3 mt-1 text-xs text-cv-muted">
                <span>{alert.cameraName}</span>
                <span>{new Date(alert.timestamp).toLocaleString()}</span>
                <span className="capitalize">{alert.type.replace('_', ' ')}</span>
              </div>
            </div>
            {!alert.acknowledged && (
              <button
                type="button"
                onClick={() => acknowledge(alert.id)}
                className="cv-btn-secondary text-xs shrink-0"
              >
                <Check className="w-3 h-3" />
                {t('alerts.acknowledge')}
              </button>
            )}
            {alert.acknowledged && (
              <span className="text-xs text-emerald-400 flex items-center gap-1 shrink-0">
                <Check className="w-3 h-3" /> {t('alerts.acknowledged')}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
