import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Grid3x3 } from 'lucide-react';
import DenseEmpty from '@/components/ui/DenseEmpty';
import ErrorState from '@/components/ErrorState';
import type { Alert } from '@/types';

const SEVERITIES = ['critical', 'high', 'medium', 'low'] as const;

function dayKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function last7Days(): Date[] {
  const days: Date[] = [];
  const now = new Date();
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now);
    d.setHours(12, 0, 0, 0);
    d.setDate(d.getDate() - i);
    days.push(d);
  }
  return days;
}

function cellTone(count: number): string {
  if (count <= 0) return 'bg-cv-deep/40 text-cv-muted/50 border-cv-border/40';
  if (count === 1) return 'bg-metric-events/20 text-metric-events border-metric-events/30';
  if (count <= 3) return 'bg-metric-alerts/25 text-metric-alerts border-metric-alerts/35';
  return 'bg-severity-critical/30 text-severity-critical border-severity-critical/40';
}

interface AlertHeatmapProps {
  alerts: Alert[];
  isError?: boolean;
  onRetry?: () => void;
}

export default function AlertHeatmap({ alerts, isError, onRetry }: AlertHeatmapProps) {
  const { t, i18n } = useTranslation();
  const days = useMemo(() => last7Days(), []);

  const grid = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of alerts) {
      const ts = new Date(a.timestamp);
      if (Number.isNaN(ts.getTime())) continue;
      const sev = SEVERITIES.includes(a.severity as (typeof SEVERITIES)[number])
        ? a.severity
        : 'medium';
      const key = `${dayKey(ts)}|${sev}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return counts;
  }, [alerts]);

  const hasAny = alerts.length > 0;
  const locale = i18n.language?.startsWith('fr') ? 'fr-FR' : 'en-US';

  return (
    <div className="cv-card p-4 min-h-[260px] flex flex-col border border-metric-events/20">
      <div className="flex items-center gap-2 mb-3">
        <div className="p-1.5 rounded-lg bg-metric-events/10 text-metric-events border border-metric-events/25">
          <Grid3x3 className="w-3.5 h-3.5" />
        </div>
        <h2 className="font-display text-sm font-semibold">{t('dashboard.alertHeatmap')}</h2>
      </div>

      {isError ? (
        <ErrorState onRetry={onRetry} />
      ) : !hasAny ? (
        <DenseEmpty title={t('dashboard.noAlerts')} hint={t('dashboard.alertHeatmapHint')} />
      ) : (
        <div className="overflow-x-auto flex-1">
          <table className="w-full text-xs border-separate border-spacing-y-1.5 border-spacing-x-1 min-w-[320px]">
            <thead>
              <tr>
                <th className="text-left text-cv-muted font-medium pb-1 pr-2 w-20">{t('dashboard.severity')}</th>
                {days.map((d) => (
                  <th key={dayKey(d)} className="text-center text-cv-muted font-medium pb-1 px-0.5">
                    {d.toLocaleDateString(locale, { weekday: 'short' }).replace(/\.$/, '')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SEVERITIES.map((sev) => (
                <tr key={sev}>
                  <td className="text-cv-muted pr-2 py-0.5">{t(`rules.severity.${sev}`, sev)}</td>
                  {days.map((d) => {
                    const count = grid.get(`${dayKey(d)}|${sev}`) ?? 0;
                    return (
                      <td key={`${sev}-${dayKey(d)}`} className="text-center py-0.5">
                        <span
                          className={`inline-flex min-w-[1.75rem] justify-center px-1.5 py-1 rounded-md border tabular-nums ${cellTone(count)}`}
                        >
                          {count || '·'}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[11px] text-cv-muted mt-3 pt-3 border-t border-cv-border/40 flex items-start gap-1.5 leading-relaxed">
        <span className="inline-flex w-4 h-4 rounded-full border border-cv-border items-center justify-center shrink-0 text-[9px] mt-0.5">i</span>
        {t('dashboard.alertHeatmapHint')}
      </p>
    </div>
  );
}

/** Daily alert totals for sparklines (oldest → newest, length 7). */
export function alertDailySeries(alerts: Alert[]): number[] {
  const days = last7Days();
  return days.map((d) => {
    const key = dayKey(d);
    return alerts.filter((a) => {
      const ts = new Date(a.timestamp);
      return !Number.isNaN(ts.getTime()) && dayKey(ts) === key;
    }).length;
  });
}
