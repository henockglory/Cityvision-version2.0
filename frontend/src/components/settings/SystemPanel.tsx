import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Server, CheckCircle2, XCircle, AlertTriangle, Loader2, Settings2, Zap, Hand, Play, Square,
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

type StartMode = 'auto' | 'manual';

export default function SystemPanel() {
  const { t } = useTranslation();
  const isAdmin = useAuthStore((s) => s.hasRole('admin'));
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [uninstallOpen, setUninstallOpen] = useState(false);
  const [modeSaving, setModeSaving] = useState(false);
  const [modeError, setModeError] = useState('');
  const [modeSuccess, setModeSuccess] = useState('');
  const [actionSaving, setActionSaving] = useState<'start' | 'stop' | null>(null);
  const [actionError, setActionError] = useState('');
  const [actionSuccess, setActionSuccess] = useState('');

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

  async function handleStartModeChange(mode: StartMode) {
    if (!status || mode === status.start_mode || modeSaving) return;
    const confirmMsg =
      mode === 'auto'
        ? t('system.startModeConfirmAuto')
        : t('system.startModeConfirmManual');
    if (!window.confirm(confirmMsg)) return;

    setModeSaving(true);
    setModeError('');
    setModeSuccess('');
    try {
      const { data } = await systemApi.setStartMode(mode);
      if (!data.ok) {
        setModeError(data.message || t('system.startModeError'));
        return;
      }
      setModeSuccess(data.message || t('system.startModeSaved'));
      await loadStatus();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setModeError(`${t('system.startModeError')}: ${msg}`);
    } finally {
      setModeSaving(false);
    }
  }

  async function handleServiceAction(action: 'start' | 'stop') {
    if (!status || actionSaving) return;
    const confirmMsg =
      action === 'start'
        ? t('system.actionConfirmStart')
        : t('system.actionConfirmStop');
    if (!window.confirm(confirmMsg)) return;

    setActionSaving(action);
    setActionError('');
    setActionSuccess('');
    try {
      const { data } = await systemApi.serviceAction(action);
      if (!data.ok) {
        setActionError(data.message || t('system.actionError'));
        return;
      }
      setActionSuccess(data.message || t('system.actionSaved'));
      await loadStatus();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { message?: string } } };
      const msg = ax.response?.data?.message
        ?? (err instanceof Error ? err.message : String(err));
      setActionError(`${t('system.actionError')}: ${msg}`);
    } finally {
      setActionSaving(null);
    }
  }

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

  const effectiveMode = status?.start_mode_effective || status?.start_mode;
  const modeMismatch =
    status &&
    status.start_mode_effective &&
    status.start_mode_effective !== status.start_mode;

  const appActive = Boolean(status?.app_running);
  const canStart =
    Boolean(status?.service_registered) &&
    !status?.service_needs_repair &&
    !appActive;
  const canStop = appActive || Boolean(status?.service_running);

  return (
    <div className="space-y-6">
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

            {status.service_registered && (
              <div className="py-3 border-b border-cv-border/50 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm text-cv-muted">{t('system.startMode')}</span>
                  {modeSaving && (
                    <span className="text-xs text-cv-muted flex items-center gap-1">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      {t('system.startModeApplying')}
                    </span>
                  )}
                </div>
                <div className="inline-flex rounded-lg border border-cv-border bg-cv-surface/50 p-1 gap-1">
                  {(['auto', 'manual'] as const).map((mode) => {
                    const selected = status.start_mode === mode;
                    const Icon = mode === 'auto' ? Zap : Hand;
                    return (
                      <button
                        key={mode}
                        type="button"
                        disabled={modeSaving}
                        onClick={() => void handleStartModeChange(mode)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
                          selected
                            ? 'bg-cv-accent text-cv-deep shadow-sm'
                            : 'text-cv-muted hover:text-cv-text hover:bg-cv-surface'
                        }`}
                      >
                        <Icon className="w-4 h-4" />
                        {mode === 'auto' ? t('system.startModeAuto') : t('system.startModeManual')}
                      </button>
                    );
                  })}
                </div>
                <p className="text-xs text-cv-muted">{t('system.startModeHint')}</p>
                {modeMismatch && (
                  <p className="text-xs text-amber-400">
                    {t('system.startModeMismatch', {
                      configured: status.start_mode,
                      effective: effectiveMode,
                    })}
                  </p>
                )}
                {modeError && <p className="text-xs text-red-400">{modeError}</p>}
                {modeSuccess && <p className="text-xs text-emerald-400">{modeSuccess}</p>}
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-cv-border/50">
              <span className="text-sm text-cv-muted">{t('system.registered')}</span>
              <StatusBadge
                ok={status.service_registered}
                label={status.service_registered ? t('system.yes') : t('system.no')}
              />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-cv-border/50">
              <span className="text-sm text-cv-muted">{t('system.appRunning')}</span>
              <StatusBadge
                ok={appActive}
                label={appActive ? t('system.active') : t('system.stopped')}
              />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="text-sm text-cv-muted">{t('system.running')}</span>
              <StatusBadge
                ok={status.service_running}
                label={status.service_running ? t('system.active') : t('system.stopped')}
              />
            </div>

            {status.service_needs_repair && (
              <div className="mt-2 rounded-lg border border-red-500/30 bg-red-500/5 p-4 space-y-1.5">
                <div className="flex items-center gap-2 text-sm font-medium text-red-300">
                  <AlertTriangle className="w-4 h-4" />
                  {t('system.serviceNeedsRepairTitle')}
                </div>
                <p className="text-xs text-cv-muted">{t('system.serviceNeedsRepairCta')}</p>
              </div>
            )}

            {!status.service_registered && (
              <div className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 space-y-1.5">
                <div className="flex items-center gap-2 text-sm font-medium text-amber-300">
                  <AlertTriangle className="w-4 h-4" />
                  {t('system.serviceNotRegisteredTitle')}
                </div>
                <p className="text-xs text-cv-muted">{t('system.serviceNotRegisteredCta')}</p>
              </div>
            )}

            {(status.service_registered || appActive) && (
              <div className="pt-2 space-y-2">
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={actionSaving !== null || !canStart}
                    onClick={() => void handleServiceAction('start')}
                    className="cv-btn-secondary flex items-center gap-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {actionSaving === 'start' ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Play className="w-4 h-4" />
                    )}
                    {t('system.actionStart')}
                  </button>
                  <button
                    type="button"
                    disabled={actionSaving !== null || !canStop}
                    onClick={() => void handleServiceAction('stop')}
                    className="cv-btn-secondary flex items-center gap-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {actionSaving === 'stop' ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Square className="w-4 h-4" />
                    )}
                    {t('system.actionStop')}
                  </button>
                </div>
                {actionError && <p className="text-xs text-red-400">{actionError}</p>}
                {actionSuccess && <p className="text-xs text-emerald-400">{actionSuccess}</p>}
              </div>
            )}
          </div>
        )}
      </div>

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
