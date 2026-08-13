import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarClock, CheckCircle2, Crosshair, Sparkles } from 'lucide-react';
import type { Alert, SystemHealthMetric } from '@/types';

interface OpsInsightStripProps {
  camerasOnline: number;
  camerasTotal: number;
  openAlerts: number;
  eventsToday: number;
  rulesActive: number;
  alerts: Alert[];
  health: SystemHealthMetric[];
}

export default function OpsInsightStrip({
  camerasOnline,
  camerasTotal,
  openAlerts,
  eventsToday,
  rulesActive,
  alerts,
  health,
}: OpsInsightStripProps) {
  const { t } = useTranslation();

  const insights = useMemo(() => {
    const offline = Math.max(0, camerasTotal - camerasOnline);
    const critical = alerts.filter((a) => a.severity === 'critical').length;
    const high = alerts.filter((a) => a.severity === 'high').length;
    const healthBad = health.filter((h) => h.status === 'critical' || h.status === 'warning');
    const coverage = camerasTotal > 0 ? Math.round((camerasOnline / camerasTotal) * 100) : 0;

    let priority: string;
    if (critical > 0) {
      priority = t('dashboard.insights.priorityCritical', { count: critical });
    } else if (high > 0) {
      priority = t('dashboard.insights.priorityHigh', { count: high });
    } else if (offline > 0) {
      priority = t('dashboard.insights.priorityOffline', { count: offline });
    } else if (openAlerts > 0) {
      priority = t('dashboard.insights.priorityOpen', { count: openAlerts });
    } else {
      priority = t('dashboard.insights.priorityClear');
    }

    let watch: string;
    if (healthBad.length > 0) {
      watch = t('dashboard.insights.watchHealth', {
        name: healthBad[0].name,
        status: healthBad[0].status,
      });
    } else if (rulesActive === 0) {
      watch = t('dashboard.insights.watchNoRules');
    } else if (offline > 0) {
      watch = t('dashboard.insights.watchOffline', { count: offline });
    } else {
      watch = t('dashboard.insights.watchStable');
    }

    let performance: string;
    if (coverage >= 90 && rulesActive > 0 && critical === 0) {
      performance = t('dashboard.insights.perfStrong', { coverage, events: eventsToday });
    } else if (coverage < 70) {
      performance = t('dashboard.insights.perfCoverage', { coverage });
    } else {
      performance = t('dashboard.insights.perfMixed', {
        coverage,
        rules: rulesActive,
        events: eventsToday,
      });
    }

    return { priority, watch, performance };
  }, [
    camerasOnline,
    camerasTotal,
    openAlerts,
    eventsToday,
    rulesActive,
    alerts,
    health,
    t,
  ]);

  const cols = [
    {
      key: 'priority',
      title: t('dashboard.insights.priorityTitle'),
      text: insights.priority,
      Icon: Crosshair,
      tone: 'text-metric-alerts bg-metric-alerts/10 border-metric-alerts/25',
    },
    {
      key: 'watch',
      title: t('dashboard.insights.watchTitle'),
      text: insights.watch,
      Icon: CalendarClock,
      tone: 'text-metric-events bg-metric-events/10 border-metric-events/25',
    },
    {
      key: 'perf',
      title: t('dashboard.insights.perfTitle'),
      text: insights.performance,
      Icon: CheckCircle2,
      tone: 'text-metric-rules bg-metric-rules/10 border-metric-rules/25',
    },
  ] as const;

  return (
    <div className="cv-card p-5 md:p-6 border border-cv-accent/20">
      <div className="flex items-center gap-2 mb-5">
        <div className="p-1.5 rounded-lg bg-cv-accent/10 text-cv-accent border border-cv-accent/25">
          <Sparkles className="w-3.5 h-3.5" />
        </div>
        <h2 className="font-display text-sm font-semibold">{t('dashboard.insights.title')}</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 md:gap-6">
        {cols.map(({ key, title, text, Icon, tone }) => (
          <div key={key} className="flex gap-3 min-w-0">
            <div className={`shrink-0 w-10 h-10 rounded-xl border flex items-center justify-center ${tone}`}>
              <Icon className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-wide text-cv-muted font-medium mb-1">{title}</p>
              <p className="text-sm text-cv-text leading-relaxed">{text}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
