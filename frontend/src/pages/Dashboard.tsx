import { useTranslation } from 'react-i18next';
import { Camera, Bell, Clock, Workflow, ArrowRight, Activity } from 'lucide-react';
import { Link } from 'react-router-dom';
import PageHeader from '@/components/ui/PageHeader';
import StatCard from '@/components/ui/StatCard';
import SeverityBadge from '@/components/ui/SeverityBadge';
import LoadingState from '@/components/ui/LoadingState';
import ErrorState from '@/components/ErrorState';
import { useAlerts, useDashboardSummary, useHealth } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';

export default function Dashboard() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const summary = useDashboardSummary();
  const alerts = useAlerts();
  const health = useHealth();

  if (summary.isLoading) return <LoadingState />;

  if (summary.isError) {
    return (
      <div>
        <PageHeader title={t('dashboard.title')} />
        <ErrorState onRetry={() => void summary.refetch()} />
      </div>
    );
  }

  const data = summary.data;
  const camerasOnline = data?.cameras_active ?? 0;
  const camerasTotal = data?.cameras_total ?? 0;
  const activeAlerts = data?.open_alerts ?? 0;
  const eventsToday = data?.events_last_24h ?? 0;
  const rulesActive = data?.rules_enabled ?? 0;
  const recentAlerts = alerts.data ?? [];

  return (
    <div>
      <PageHeader title={t('dashboard.title')} />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          label={t('dashboard.camerasOnline')}
          value={`${camerasOnline}/${camerasTotal}`}
          icon={Camera}
          accent
        />
        <StatCard label={t('dashboard.activeAlerts')} value={activeAlerts} icon={Bell} />
        <StatCard label={t('dashboard.eventsToday')} value={eventsToday} icon={Clock} />
        <StatCard label={t('dashboard.rulesActive')} value={rulesActive} icon={Workflow} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 cv-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg font-semibold">{t('dashboard.recentAlerts')}</h2>
            <Link
              to="/alerts"
              onClick={() => playClick()}
              className="text-cv-accent text-sm flex items-center gap-1 hover:underline"
            >
              {t('dashboard.viewAll')} <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
          {alerts.isError ? (
            <ErrorState onRetry={() => void alerts.refetch()} />
          ) : recentAlerts.length === 0 ? (
            <p className="text-sm text-cv-muted text-center py-8">{t('dashboard.noAlerts')}</p>
          ) : (
            <div className="space-y-3">
              {recentAlerts.slice(0, 4).map((alert) => (
                <div
                  key={alert.id}
                  className="flex items-center gap-4 p-3 rounded-lg bg-cv-deep/50 border border-cv-border hover:border-cv-accent/20 transition-colors"
                >
                  <SeverityBadge severity={alert.severity} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{alert.message}</p>
                    <p className="text-xs text-cv-muted">{alert.cameraName}</p>
                  </div>
                  <span className="text-xs text-cv-muted whitespace-nowrap">
                    {new Date(alert.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="cv-card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-5 h-5 text-cv-accent" />
            <h2 className="font-display text-lg font-semibold">{t('dashboard.systemStatus')}</h2>
          </div>
          {health.isError ? (
            <ErrorState onRetry={() => void health.refetch()} />
          ) : (health.data ?? []).length === 0 ? (
            <p className="text-sm text-cv-muted text-center py-4">{t('systemHealth.empty')}</p>
          ) : (
            <div className="space-y-3">
              {(health.data ?? []).slice(0, 5).map((metric) => (
                <div key={metric.name} className="flex items-center justify-between">
                  <span className="text-sm text-cv-muted">{metric.name}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{metric.value}</span>
                    <span className={`w-2 h-2 rounded-full ${
                      metric.status === 'healthy' ? 'bg-emerald-400' :
                      metric.status === 'warning' ? 'bg-amber-400' : 'bg-red-400'
                    }`} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="mt-6 cv-card p-5">
        <h2 className="font-display text-lg font-semibold mb-4">{t('dashboard.quickActions')}</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { to: '/live', label: t('nav.liveView') },
            { to: '/video-wall', label: t('nav.videoWall') },
            { to: '/cameras', label: t('nav.cameras') },
            { to: '/alerts', label: t('nav.alerts') },
          ].map((action) => (
            <Link
              key={action.to}
              to={action.to}
              onClick={() => playClick()}
              className="cv-btn-secondary py-3 text-center"
            >
              {action.label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
