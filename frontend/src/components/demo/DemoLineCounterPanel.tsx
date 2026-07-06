import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { ArrowDownLeft, ArrowUpRight, Gauge, RotateCcw } from 'lucide-react';
import { zonesApi, type LineCounter } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useCameras } from '@/hooks/api/queries';

interface DemoLineCounterPanelProps {
  cameraId?: string;
  /** Active demo video camera — counters hidden when it differs (other cameras paused). */
  activeCameraId?: string;
}

/**
 * Live, persistent line-crossing counters. Polls the backend every 3s so the
 * tally is visible during a demo without a manual refresh.
 */
export default function DemoLineCounterPanel({ cameraId, activeCameraId }: DemoLineCounterPanelProps) {
  const { t } = useTranslation();
  const orgId = useAuthStore((s) => s.orgId);
  const { data: cameras = [] } = useCameras();

  const counterCamera = cameras.find((c) => c.id === cameraId);

  const { data: lines = [] } = useQuery({
    queryKey: ['lines', orgId, cameraId ?? 'none'],
    queryFn: () => zonesApi.listLines(orgId!, cameraId).then((r) => r.data as { id: string; name: string }[]),
    enabled: Boolean(orgId && cameraId),
  });

  const paused = Boolean(cameraId && activeCameraId && cameraId !== activeCameraId);

  const { data: counters = [], refetch } = useQuery({
    queryKey: ['line-counters', orgId, cameraId ?? 'all'],
    queryFn: () => zonesApi.lineCounters(orgId!, cameraId).then((r) => r.data),
    enabled: Boolean(orgId && cameraId && !paused),
    refetchInterval: paused ? false : 3000,
  });

  const lineLabel = (lineId: string) => {
    const line = lines.find((l) => l.id === lineId);
    if (line?.name) return line.name;
    if (lineId.includes('-') && lineId.length > 20) return `${lineId.slice(0, 8)}…`;
    return lineId;
  };

  const handleReset = async () => {
    if (!orgId) return;
    if (!window.confirm(t('demoCenter.counterResetConfirm'))) return;
    await zonesApi.resetLineCounters(orgId, cameraId);
    void refetch();
  };

  return (
    <div className="cv-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-cv-border gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Gauge className="w-4 h-4 text-cv-accent shrink-0" />
            {t('demoCenter.lineCountersTitle')}
            <span className="text-cv-muted font-normal">({counters.length})</span>
          </div>
          <p className="text-[11px] text-cv-muted mt-0.5 leading-relaxed">
            {counterCamera
              ? t('demoCenter.lineCountersSubtitleNamed', { camera: counterCamera.name })
              : t('demoCenter.lineCountersSubtitle')}
          </p>
        </div>
        {counters.length > 0 && (
          <button
            type="button"
            onClick={() => void handleReset()}
            className="text-xs text-cv-muted hover:text-cv-accent flex items-center gap-1 shrink-0"
          >
            <RotateCcw className="w-3 h-3" />
            {t('demoCenter.counterReset')}
          </button>
        )}
      </div>

      {paused ? (
        <p className="text-xs text-cv-muted p-4 text-center">{t('demoCenter.lineCountersPaused')}</p>
      ) : counters.length === 0 ? (
        <p className="text-xs text-cv-muted p-4 text-center">{t('demoCenter.lineCountersEmpty')}</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-4">
          {counters.map((c: LineCounter) => (
            <div key={c.line_id} className="rounded-lg border border-cv-border bg-cv-surface/60 p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <span className="text-sm font-medium truncate block" title={lineLabel(c.line_id)}>
                    {lineLabel(c.line_id)}
                  </span>
                  <span className="text-[10px] text-cv-muted">{t('demoCenter.counterTotalLabel')}</span>
                </div>
                <span className="text-2xl font-bold tabular-nums text-cv-accent">{c.count_total}</span>
              </div>
              <div className="mt-2 flex items-center gap-4 text-xs text-cv-muted">
                <span className="flex items-center gap-1" title={t('demoCenter.counterInHint')}>
                  <ArrowDownLeft className="w-3.5 h-3.5 text-emerald-400" />
                  {t('demoCenter.counterIn')}: <span className="tabular-nums text-cv-text">{c.count_in}</span>
                </span>
                <span className="flex items-center gap-1" title={t('demoCenter.counterOutHint')}>
                  <ArrowUpRight className="w-3.5 h-3.5 text-amber-400" />
                  {t('demoCenter.counterOut')}: <span className="tabular-nums text-cv-text">{c.count_out}</span>
                </span>
              </div>
              {c.count_in === 0 && c.count_out === 0 && c.count_total > 0 && (
                <p className="mt-1.5 text-[10px] text-amber-400/90">{t('demoCenter.counterDirectionHint')}</p>
              )}
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
