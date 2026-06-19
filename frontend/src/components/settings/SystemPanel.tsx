import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Server, HardDrive, CheckCircle2, XCircle, AlertTriangle, Loader2, Trash2,
} from 'lucide-react';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import Modal from '@/components/ui/Modal';
import { systemApi, type SystemStatus, type SystemStreamEvent } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';

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
  const [keepData, setKeepData] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmTextOpen, setConfirmTextOpen] = useState(false);
  const [confirmInput, setConfirmInput] = useState('');
  const [progressOpen, setProgressOpen] = useState(false);
  const [logs, setLogs] = useState<SystemStreamEvent[]>([]);
  const [uninstallDone, setUninstallDone] = useState(false);
  const [uninstallOk, setUninstallOk] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

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

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  const startUninstall = async () => {
    setConfirmTextOpen(false);
    setConfirmInput('');
    setProgressOpen(true);
    setLogs([]);
    setUninstallDone(false);
    setUninstallOk(false);
    abortRef.current = new AbortController();
    try {
      for await (const evt of systemApi.streamUninstall(keepData, abortRef.current.signal)) {
        setLogs((prev) => [...prev, evt]);
        if (evt.event === 'done') {
          setUninstallDone(true);
          setUninstallOk(true);
          break;
        }
        if (evt.event === 'error' && evt.ok === false) {
          setUninstallDone(true);
          setUninstallOk(false);
          break;
        }
      }
    } catch (err) {
      setLogs((prev) => [
        ...prev,
        { event: 'error', message: err instanceof Error ? err.message : String(err) },
      ]);
      setUninstallDone(true);
      setUninstallOk(false);
    }
  };

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

      {/* Danger zone */}
      <div className="cv-card p-5 border border-red-500/30 bg-red-500/5">
        <div className="flex items-center gap-2 mb-3">
          <Trash2 className="w-5 h-5 text-red-400" />
          <h3 className="font-display text-base font-semibold text-red-400">
            {t('system.uninstall.title')}
          </h3>
        </div>
        <p className="text-sm text-cv-muted mb-4">{t('system.uninstall.description')}</p>
        <label className="flex items-start gap-3 mb-4 cursor-pointer group">
          <input
            type="checkbox"
            checked={keepData}
            onChange={(e) => setKeepData(e.target.checked)}
            className="mt-1 rounded border-cv-border"
          />
          <span className="text-sm">
            <span className="font-medium text-cv-text">{t('system.uninstall.keepData')}</span>
            <span className="block text-cv-muted text-xs mt-0.5">
              {t('system.uninstall.keepDataHint')}
            </span>
          </span>
        </label>
        {!keepData && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-500/10 text-amber-400 text-xs mb-4">
            <HardDrive className="w-4 h-4 shrink-0 mt-0.5" />
            {t('system.uninstall.wipeWarning')}
          </div>
        )}
        <button
          type="button"
          className="cv-btn-danger"
          onClick={() => setConfirmOpen(true)}
        >
          {t('system.uninstall.button')}
        </button>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title={t('system.uninstall.confirmTitle')}
        message={keepData ? t('system.uninstall.confirmKeepData') : t('system.uninstall.confirmWipe')}
        confirmLabel={t('system.uninstall.continue')}
        danger
        onConfirm={() => {
          setConfirmOpen(false);
          setConfirmTextOpen(true);
        }}
        onCancel={() => setConfirmOpen(false)}
      />

      <Modal
        open={confirmTextOpen}
        onClose={() => setConfirmTextOpen(false)}
        title={t('system.uninstall.typeConfirmTitle')}
        maxWidth="md"
        footer={
          <>
            <button type="button" className="cv-btn-secondary" onClick={() => setConfirmTextOpen(false)}>
              {t('common.cancel')}
            </button>
            <button
              type="button"
              className="cv-btn-danger"
              disabled={confirmInput !== 'DESINSTALLER'}
              onClick={() => void startUninstall()}
            >
              {t('system.uninstall.finalConfirm')}
            </button>
          </>
        }
      >
        <p className="text-sm text-cv-muted mb-3">{t('system.uninstall.typeConfirmHint')}</p>
        <input
          type="text"
          value={confirmInput}
          onChange={(e) => setConfirmInput(e.target.value)}
          placeholder="DESINSTALLER"
          className="cv-input w-full font-mono"
          autoComplete="off"
        />
      </Modal>

      <Modal
        open={progressOpen}
        onClose={() => uninstallDone && setProgressOpen(false)}
        title={t('system.uninstall.progressTitle')}
        maxWidth="2xl"
        footer={
          uninstallDone ? (
            <button type="button" className="cv-btn-primary" onClick={() => setProgressOpen(false)}>
              {t('common.close')}
            </button>
          ) : undefined
        }
      >
        {!uninstallDone && (
          <div className="flex items-center gap-2 text-sm text-cv-muted mb-3">
            <Loader2 className="w-4 h-4 animate-spin text-cv-accent" />
            {t('system.uninstall.inProgress')}
          </div>
        )}
        {uninstallDone && (
          <div
            className={`flex items-center gap-2 text-sm mb-3 p-3 rounded-lg ${
              uninstallOk ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
            }`}
          >
            {uninstallOk ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
            {uninstallOk ? t('system.uninstall.done') : t('system.uninstall.failed')}
          </div>
        )}
        {uninstallDone && uninstallOk && (
          <p className="text-sm text-cv-muted mb-3">{t('system.uninstall.reinstallHint')}</p>
        )}
        <div
          ref={logRef}
          className="h-48 overflow-y-auto rounded-lg bg-cv-deep/80 p-3 font-mono text-xs space-y-1 border border-cv-border/50"
        >
          {logs.length === 0 && !uninstallDone && (
            <span className="text-cv-muted">{t('system.uninstall.waitingLog')}</span>
          )}
          {logs.map((line, i) => (
            <div
              key={i}
              className={
                line.event === 'error'
                  ? 'text-red-400'
                  : line.event === 'warn'
                    ? 'text-amber-400'
                    : line.event === 'ok'
                      ? 'text-emerald-400'
                      : line.event === 'step'
                        ? 'text-cv-accent'
                        : 'text-cv-muted'
              }
            >
              {line.message}
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
}
