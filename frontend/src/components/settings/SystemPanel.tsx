import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Server, CheckCircle2, XCircle, AlertTriangle, Loader2, Settings2,
} from 'lucide-react';
import { systemApi, type SystemStatus } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import UninstallDialog from './UninstallDialog';

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
        ok ? 'bg-emerald-500/15 text-emerald-400' : 'bg-cv-muted/15 text-cv-muted'
      }`}
    >
      {ok ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
      {label}
    </span>
  );
}

export default function SystemPanel() {
  const { t } = useTranslation();
  const isAdmin = useAuthStore((s) => s.hasRole('admin'));
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [uninstallOpen, setUninstallOpen] = useState(false);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await systemApi.status();
      setStatus(data);
    } catch {
      setError(t('system.uninstall.statusError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (isAdmin) void loadStatus();
  }, [isAdmin, loadStatus]);

  if (!isAdmin) {
    return (
      <p className="text-sm text-cv-muted">{t('system.uninstall.adminOnly')}</p>
    );
  }

  const platformLabel =
    status?.platform === 'windows'
      ? t('system.platformWindows')
      : status?.platform === 'linux'
        ? t('system.platformLinux')
        : status?.platform ?? '—';

  const modeLabel =
    status?.start_mode === 'manual'
      ? t('system.startModeManual')
      : t('system.startModeAuto');

  return (
    <div className="space-y-6">
      {/* Status card */}
      <div className="cv-card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Server className="w-5 h-5 text-cv-accent" />
          <h3 className="font-display text-base font-semibold">{t('system.serviceStatus')}</h3>
        </div>
        {loading && (
          <div className="flex items-center gap-2 text-sm text-cv-muted">
            <Loader2 className="w-4 h-4 animate-spin" />
            {t('common.loading')}
          </div>
        )}
        {error && (
          <div className="flex items-center gap-2 text-sm text-red-400">
            <AlertTriangle className="w-4 h-4" />
            {error}
            <button type="button" className="cv-btn-secondary text-xs ml-2" onClick={() => void loadStatus()}>
              {t('common.retry')}
            </button>
          </div>
        )}
        {!loading && !error && status && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-cv-border/50">
              <span className="text-sm text-cv-muted">{t('system.platform')}</span>
              <span className="text-sm font-medium">{platformLabel}</span>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-cv-border/50">
              <span className="text-sm text-cv-muted">{t('system.serviceName')}</span>
              <span className="text-sm font-medium font-mono">{status.service_name}</span>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-cv-border/50">
              <span className="text-sm text-cv-muted">{t('system.startMode')}</span>
              <span className="text-sm font-medium">{modeLabel}</span>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-cv-border/50">
              <span className="text-sm text-cv-muted">{t('system.registered')}</span>
              <StatusBadge
                ok={status.service_registered}
                label={status.service_registered ? t('system.yes') : t('system.no')}
              />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="text-sm text-cv-muted">{t('system.running')}</span>
              <StatusBadge
                ok={status.service_running}
                label={status.service_running ? t('system.active') : t('system.stopped')}
              />
            </div>
          </div>
        )}
      </div>

      {/* Gestion de l'installation */}
      <div className="cv-card p-5">
        <div className="flex items-center gap-2 mb-3">
          <Settings2 className="w-5 h-5 text-cv-accent" />
          <h3 className="font-display text-base font-semibold">
            {t('system.uninstall.title')}
          </h3>
        </div>
        <p className="text-sm text-cv-muted mb-4">
          {t('system.uninstall.description')}
        </p>
        <button
          type="button"
          className="cv-btn-secondary flex items-center gap-2"
          onClick={() => setUninstallOpen(true)}
        >
          <Settings2 className="w-4 h-4" />
          {t('system.uninstall.button')}
        </button>
      </div>

      <UninstallDialog open={uninstallOpen} onClose={() => setUninstallOpen(false)} />
    </div>
  );
}
