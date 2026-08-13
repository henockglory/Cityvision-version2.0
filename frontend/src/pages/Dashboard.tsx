import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Camera, Bell, Clock, Workflow, RefreshCw, Activity } from 'lucide-react';
import { Link } from 'react-router-dom';
import PageShell from '@/components/ui/PageShell';
import DenseEmpty from '@/components/ui/DenseEmpty';
import { DashboardSkeleton } from '@/components/ui/Skeleton';
import ErrorState from '@/components/ErrorState';
import LiveEventStream from '@/components/dashboard/LiveEventStream';
import DashboardMetricCard from '@/components/dashboard/DashboardMetricCard';
import CameraRiskList from '@/components/dashboard/CameraRiskList';
import AlertHeatmap, { alertDailySeries } from '@/components/dashboard/AlertHeatmap';
import OpsInsightStrip from '@/components/dashboard/OpsInsightStrip';
import FirstRuleWizard from '@/components/rules/FirstRuleWizard';
import AnimatedTutorial from '@/components/onboarding/AnimatedTutorial';
import { useAlerts, useDashboardSummary, useHealth } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';

function sevenDaysAgoIso(): string {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString();
}

export default function Dashboard() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const startTour = useAutoPageTour('dashboard');
  const summary = useDashboardSummary();
  const openAlerts = useAlerts({ status: 'open', limit: 40 });
  const weekAlerts = useAlerts({ from: sevenDaysAgoIso(), limit: 80 });
  const health = useHealth();

  const refreshing =
    summary.isFetching || openAlerts.isFetching || weekAlerts.isFetching || health.isFetching;

  const handleRefresh = () => {
    playClick();
    void summary.refetch();
    void openAlerts.refetch();
    void weekAlerts.refetch();
    void health.refetch();
  };

  const sparkAlerts = useMemo(
    () => alertDailySeries(weekAlerts.data ?? []),
    [weekAlerts.data],
  );

  if (summary.isLoading) {
    return (
      <PageShell title={t('dashboard.title')} subtitle={t('dashboard.subtitle')}>
        <DashboardSkeleton />
      </PageShell>
    );
  }

  if (summary.isError) {
    return (
      <PageShell title={t('dashboard.title')} subtitle={t('dashboard.subtitle')}>
        <ErrorState onRetry={() => void summary.refetch()} />
      </PageShell>
    );
  }

  const data = summary.data;
  const camerasOnline = data?.cameras_active ?? 0;
  const camerasTotal = data?.cameras_total ?? 0;
  const activeAlerts = data?.open_alerts ?? 0;
  const eventsToday = data?.events_last_24h ?? 0;
  const rulesActive = data?.rules_enabled ?? 0;
  const offline = Math.max(0, camerasTotal - camerasOnline);
  const coverage = camerasTotal > 0 ? Math.round((camerasOnline / camerasTotal) * 100) : 0;
  const openList = openAlerts.data ?? [];
  const weekList = weekAlerts.data ?? [];
  const healthMetrics = health.data ?? [];
  const criticalOpen = openList.filter((a) => a.severity === 'critical').length;

  // Sparklines only from real weekly alert series (or flat current coverage / rules level).
  const sparkCameras = Array.from({ length: 7 }, () => camerasOnline);
  const sparkEvents = sparkAlerts.some((n) => n > 0)
    ? sparkAlerts
    : Array.from({ length: 7 }, (_, i) => (i === 6 ? Math.max(0, eventsToday) : 0));
  const sparkRules = Array.from({ length: 7 }, () => rulesActive);

  return (
    <PageShell
      title={t('dashboard.title')}
      subtitle={t('dashboard.subtitle')}
      onHelpTour={startTour}
      actions={
        <div className="flex items-center gap-2">
          <span className="cv-btn-secondary text-xs py-2 px-3 pointer-events-none">
            {t('dashboard.period24h')}
          </span>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
            className="cv-btn-secondary text-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            {t('dashboard.refresh')}
          </button>
        </div>
      }
    >
      <AnimatedTutorial />
      <FirstRuleWizard />

      <div id="dashboard-stats" className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <DashboardMetricCard
          label={t('dashboard.camerasOnline')}
          value={`${camerasOnline}/${camerasTotal}`}
          secondary={t('dashboard.kpiCamerasSecondary', { coverage, offline })}
          icon={Camera}
          tone="cameras"
          hint={t('dashboard.hintCameras')}
          sparkline={sparkCameras}
        />
        <DashboardMetricCard
          label={t('dashboard.activeAlerts')}
          value={activeAlerts}
          secondary={
            criticalOpen > 0
              ? t('dashboard.kpiAlertsCritical', { count: criticalOpen })
              : t('dashboard.kpiAlertsSecondary')
          }
          icon={Bell}
          tone="alerts"
          hint={t('dashboard.hintAlerts')}
          sparkline={sparkAlerts}
        />
        <DashboardMetricCard
          label={t('dashboard.eventsToday')}
          value={eventsToday}
          secondary={t('dashboard.kpiEventsSecondary')}
          icon={Clock}
          tone="events"
          hint={t('dashboard.hintEvents')}
          sparkline={sparkEvents}
        />
        <DashboardMetricCard
          label={t('dashboard.rulesActive')}
          value={rulesActive}
          secondary={t('dashboard.kpiRulesSecondary')}
          icon={Workflow}
          tone="rules"
          hint={t('dashboard.hintRules')}
          sparkline={sparkRules}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CameraRiskList
          alerts={openList}
          isError={openAlerts.isError}
          onRetry={() => void openAlerts.refetch()}
        />
        <AlertHeatmap
          alerts={weekList}
          isError={weekAlerts.isError}
          onRetry={() => void weekAlerts.refetch()}
        />
      </div>

      <OpsInsightStrip
        camerasOnline={camerasOnline}
        camerasTotal={camerasTotal}
        openAlerts={activeAlerts}
        eventsToday={eventsToday}
        rulesActive={rulesActive}
        alerts={openList}
        health={healthMetrics}
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-8">
          <LiveEventStream />
        </div>

        <div className="lg:col-span-4 space-y-4">
          <div className="cv-card p-4">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-4 h-4 text-metric-rules" />
              <h2 className="font-display text-sm font-semibold">{t('dashboard.systemStatus')}</h2>
            </div>
            {health.isError ? (
              <ErrorState onRetry={() => void health.refetch()} />
            ) : healthMetrics.length === 0 ? (
              <DenseEmpty title={t('systemHealth.empty')} />
            ) : (
              <div className="space-y-2">
                {healthMetrics.slice(0, 5).map((metric) => (
                  <div
                    key={metric.name}
                    className="flex items-center justify-between text-sm py-1 border-b border-cv-border/40 last:border-0"
                  >
                    <span className="text-cv-muted truncate">{metric.name}</span>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="font-medium tabular-nums text-xs">{metric.value}</span>
                      <span
                        className={`w-2 h-2 rounded-full ${
                          metric.status === 'healthy'
                            ? 'bg-metric-rules'
                            : metric.status === 'warning'
                              ? 'bg-metric-alerts'
                              : 'bg-severity-critical'
                        }`}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="cv-card p-4">
            <h2 className="font-display text-sm font-semibold mb-3">{t('dashboard.quickActions')}</h2>
            <div className="grid grid-cols-2 gap-2">
              {[
                { to: '/map', label: t('dashboard.mapSig') },
                { to: '/live', label: t('nav.liveView') },
                { to: '/rules', label: t('nav.rules') },
                { to: '/alerts', label: t('nav.alerts') },
              ].map((action) => (
                <Link
                  key={action.to}
                  to={action.to}
                  onClick={() => playClick()}
                  className="cv-btn-secondary py-2.5 text-xs text-center"
                >
                  {action.label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
}
