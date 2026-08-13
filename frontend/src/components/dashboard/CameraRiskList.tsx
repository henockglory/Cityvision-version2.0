import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Camera } from 'lucide-react';
import { Link } from 'react-router-dom';
import DenseEmpty from '@/components/ui/DenseEmpty';
import ErrorState from '@/components/ErrorState';
import type { Alert } from '@/types';
import { useSound } from '@/hooks/useSound';

interface CameraRiskListProps {
  alerts: Alert[];
  isError?: boolean;
  onRetry?: () => void;
}

export default function CameraRiskList({ alerts, isError, onRetry }: CameraRiskListProps) {
  const { t } = useTranslation();
  const { playClick } = useSound();

  const rows = useMemo(() => {
    const map = new Map<string, { name: string; count: number; critical: number }>();
    for (const a of alerts) {
      const key = a.cameraId || a.cameraName || 'unknown';
      const cur = map.get(key) ?? { name: a.cameraName || key, count: 0, critical: 0 };
      cur.count += 1;
      if (a.severity === 'critical' || a.severity === 'high') cur.critical += 1;
      map.set(key, cur);
    }
    return Array.from(map.values())
      .sort((a, b) => b.count - a.count || b.critical - a.critical)
      .slice(0, 6);
  }, [alerts]);

  const max = Math.max(...rows.map((r) => r.count), 1);

  return (
    <div id="dashboard-alerts" className="cv-card p-4 min-h-[260px] flex flex-col border border-metric-alerts/20">
      <div className="flex items-center justify-between mb-3 gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1.5 rounded-lg bg-metric-alerts/10 text-metric-alerts border border-metric-alerts/25">
            <Camera className="w-3.5 h-3.5" />
          </div>
          <h2 className="font-display text-sm font-semibold truncate">{t('dashboard.camerasAtRisk')}</h2>
        </div>
        <Link
          to="/alerts"
          onClick={() => playClick()}
          className="text-cv-accent text-xs flex items-center gap-1 hover:underline shrink-0"
        >
          {t('dashboard.viewAll')} <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      {isError ? (
        <ErrorState onRetry={onRetry} />
      ) : rows.length === 0 ? (
        <DenseEmpty title={t('dashboard.noAlerts')} hint={t('dashboard.noAlertsHint')} />
      ) : (
        <div className="space-y-2.5 flex-1">
          {rows.map((row) => (
            <div key={row.name} className="space-y-1">
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate font-medium">{row.name}</span>
                <span className="text-xs text-cv-muted tabular-nums shrink-0">
                  {t('dashboard.alertCount', { count: row.count })}
                  {row.critical > 0 && (
                    <span className="text-metric-alerts ml-1">· {row.critical}</span>
                  )}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-cv-deep/60 border border-cv-border/40 overflow-hidden">
                <div
                  className="h-full rounded-full bg-metric-alerts/80 transition-all duration-500"
                  style={{ width: `${Math.max(8, (row.count / max) * 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="text-[11px] text-cv-muted mt-3 pt-3 border-t border-cv-border/40 flex items-start gap-1.5 leading-relaxed">
        <span className="inline-flex w-4 h-4 rounded-full border border-cv-border items-center justify-center shrink-0 text-[9px] mt-0.5">i</span>
        {t('dashboard.camerasAtRiskHint')}
      </p>
    </div>
  );
}
