import { useTranslation } from 'react-i18next';
import { Camera, Bell, Clock, Workflow, ArrowRight, Activity, Film } from 'lucide-react';
import { evidenceCompleteness, parseEvidenceSnapshot } from '@/lib/evidence';
import { Link } from 'react-router-dom';
import PageShell from '@/components/ui/PageShell';
import StatTile from '@/components/ui/StatTile';
import SeverityBadge from '@/components/ui/SeverityBadge';
import DenseEmpty from '@/components/ui/DenseEmpty';
import { DashboardSkeleton } from '@/components/ui/Skeleton';
import ErrorState from '@/components/ErrorState';
import LiveEventStream from '@/components/dashboard/LiveEventStream';
import FirstRuleWizard from '@/components/rules/FirstRuleWizard';
import { useAlerts, useDashboardSummary, useHealth } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';

export default function Dashboard() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const startTour = useAutoPageTour('dashboard');
  const summary = useDashboardSummary();
  const alerts = useAlerts({ status: 'open', limit: 6 });
  const health = useHealth();

  if (summary.isLoading) {
    return (
      <PageShell title={t('dashboard.title')}>
        <DashboardSkeleton />
      </PageShell>
    );
  }

  if (summary.isError) {
    return (
      <PageShell title={t('dashboard.title')}>
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
  const recentAlerts = alerts.data ?? [];
  const healthMetrics = health.data ?? [];

  return (
    <PageShell title={t('dashboard.title')} onHelpTour={startTour}>
      <FirstRuleWizard />

      <div id="dashboard-stats" className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <StatTile
          label={t('dashboard.camerasOnline')}
          value={`${camerasOnline}/${camerasTotal}`}
          icon={Camera}
          tone="cameras"
          hint="Nombre de caméras actives et diffusant sur le site."
        />
        <StatTile
          label={t('dashboard.activeAlerts')}
          value={activeAlerts}
          icon={Bell}
          tone="alerts"
          hint="Alertes ouvertes nécessitant une action opérateur."
        />
        <StatTile
          label={t('dashboard.eventsToday')}
          value={eventsToday}
          icon={Clock}
          tone="events"
          hint="Événements IA enregistrés sur les dernières 24 h."
        />
        <StatTile
          label={t('dashboard.rulesActive')}
          value={rulesActive}
          icon={Workflow}
          tone="rules"
          hint="Règles d'analyse actuellement activées."
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div id="dashboard-alerts" className="lg:col-span-7 cv-card p-4 min-h-[220px] flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display text-sm font-semibold">{t('dashboard.recentAlerts')}</h2>
            <Link
              to="/alerts"
              onClick={() => playClick()}
              className="text-cv-accent text-xs flex items-center gap-1 hover:underline shrink-0"
            >
              {t('dashboard.viewAll')} <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
          {alerts.isError ? (
            <ErrorState onRetry={() => void alerts.refetch()} />
          ) : recentAlerts.length === 0 ? (
            <DenseEmpty title={t('dashboard.noAlerts')} hint={t('dashboard.noAlertsHint')} />
          ) : (
            <div className="space-y-2 flex-1">
              {recentAlerts.slice(0, 5).map((alert) => {
                const evComplete = evidenceCompleteness(parseEvidenceSnapshot(alert.evidenceSnapshot));
                return (
                  <Link
                    key={alert.id}
                    to="/alerts"
                    onClick={() => playClick()}
                    className="flex items-center gap-3 p-2.5 rounded-lg bg-cv-deep/40 border border-cv-border/60 hover:border-metric-alerts/30 transition-colors"
                  >
                    <SeverityBadge severity={alert.severity} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{alert.message}</p>
                      <p className="text-xs text-cv-muted">{alert.cameraName}</p>
                    </div>
                    {evComplete.have > 0 && (
                      <span
                        className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0 ${
                          evComplete.complete ? 'bg-metric-rules/15 text-metric-rules' : 'bg-cv-surface text-cv-muted'
                        }`}
                        title={evComplete.complete ? t('evidence.complete') : t('evidence.partial', { have: evComplete.have, total: evComplete.total })}
                      >
                        <Film className="w-3 h-3" />
                        {evComplete.have}/{evComplete.total}
                      </span>
                    )}
                    <span className="text-xs text-cv-muted tabular-nums shrink-0">
                      {new Date(alert.timestamp).toLocaleTimeString()}
                    </span>
                  </Link>
                );
              })}
            </div>
          )}
        </div>

        <div className="lg:col-span-5 cv-card p-4 min-h-[220px]">
          <div className="flex items-center gap-2 mb-3">
            <Activity className="w-4 h-4 text-metric-rules cv-icon-spin-slow" />
            <h2 className="font-display text-sm font-semibold">{t('dashboard.systemStatus')}</h2>
          </div>
          {health.isError ? (
            <ErrorState onRetry={() => void health.refetch()} />
          ) : healthMetrics.length === 0 ? (
            <DenseEmpty title={t('systemHealth.empty')} />
          ) : (
            <div className="space-y-2">
              {healthMetrics.slice(0, 6).map((metric) => (
                <div key={metric.name} className="flex items-center justify-between text-sm py-1 border-b border-cv-border/40 last:border-0">
                  <span className="text-cv-muted truncate">{metric.name}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="font-medium tabular-nums">{metric.value}</span>
                    <span className={`w-2 h-2 rounded-full ${
                      metric.status === 'healthy' ? 'bg-metric-rules' :
                      metric.status === 'warning' ? 'bg-metric-alerts' : 'bg-severity-critical'
                    }`} />
                  </div>
                </div>
              ))}
              <p className="text-xs text-cv-muted pt-2 border-t border-cv-border/40 mt-2">
                Événements 24h : <span className="text-metric-events font-semibold">{eventsToday.toLocaleString()}</span>
              </p>
            </div>
          )}
        </div>

        <div id="dashboard-live" className="lg:col-span-8">
          <LiveEventStream />
        </div>

        <div className="lg:col-span-4 cv-card p-4">
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
    </PageShell>
  );
}
