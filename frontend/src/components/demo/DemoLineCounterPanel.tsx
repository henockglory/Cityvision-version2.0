import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { ArrowDownLeft, ArrowUpRight, Gauge, RotateCcw } from 'lucide-react';
import { zonesApi, type LineCounter } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';

interface DemoLineCounterPanelProps {
  cameraId?: string;
}

/**
 * Live, persistent line-crossing counters. Polls the backend every 3s so the
 * tally is visible during a demo without a manual refresh.
 */
export default function DemoLineCounterPanel({ cameraId }: DemoLineCounterPanelProps) {
  const { t } = useTranslation();
  const orgId = useAuthStore((s) => s.orgId);

  const { data: counters = [], refetch } = useQuery({
    queryKey: ['line-counters', orgId, cameraId ?? 'all'],
    queryFn: () => zonesApi.lineCounters(orgId!, cameraId).then((r) => r.data),
    enabled: Boolean(orgId),
    refetchInterval: 3000,
  });

  const handleReset = async () => {
    if (!orgId) return;
    if (!window.confirm(t('demoCenter.counterResetConfirm'))) return;
    await zonesApi.resetLineCounters(orgId, cameraId);
    void refetch();
  };

  return (
    <div className="cv-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-cv-border">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Gauge className="w-4 h-4 text-cv-accent" />
          {t('demoCenter.lineCountersTitle')}
          <span className="text-cv-muted font-normal">({counters.length})</span>
          {!cameraId && counters.length > 0 && (
            <span className="text-[10px] text-cv-muted font-normal">{t('demoCenter.lineCountersAllOrg')}</span>
          )}
        </div>
        {counters.length > 0 && (
          <button
            type="button"
            onClick={() => void handleReset()}
            className="text-xs text-cv-muted hover:text-cv-accent flex items-center gap-1"
          >
            <RotateCcw className="w-3 h-3" />
            {t('demoCenter.counterReset')}
          </button>
        )}
      </div>

      {counters.length === 0 ? (
        <p className="text-xs text-cv-muted p-4 text-center">{t('demoCenter.lineCountersEmpty')}</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-4">
          {counters.map((c: LineCounter) => (
            <div key={c.line_id} className="rounded-lg border border-cv-border bg-cv-surface/60 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium truncate" title={c.line_id}>
                  {c.line_id.includes('-') && c.line_id.length > 20 ? c.line_id.slice(0, 8) : c.line_id}
                </span>
                <span className="text-2xl font-bold tabular-nums text-cv-accent">{c.count_total}</span>
              </div>
              <div className="mt-2 flex items-center gap-4 text-xs text-cv-muted">
                <span className="flex items-center gap-1" title={t('demoCenter.counterIn')}>
                  <ArrowDownLeft className="w-3.5 h-3.5 text-emerald-400" />
                  {t('demoCenter.counterIn')}: <span className="tabular-nums text-cv-text">{c.count_in}</span>
                </span>
                <span className="flex items-center gap-1" title={t('demoCenter.counterOut')}>
                  <ArrowUpRight className="w-3.5 h-3.5 text-amber-400" />
                  {t('demoCenter.counterOut')}: <span className="tabular-nums text-cv-text">{c.count_out}</span>
                </span>
              </div>
              {c.last_class && (
                <p className="mt-1.5 text-[10px] text-cv-muted">
                  {t('demoCenter.counterLastClass')}: {c.last_class}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
