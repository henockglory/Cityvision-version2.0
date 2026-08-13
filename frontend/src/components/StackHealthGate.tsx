import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';

type PlatformHealth = {
  status?: string;
  components?: Record<string, { status?: string; detail?: Record<string, unknown> }>;
};

type GateKind = 'ok' | 'unreachable' | 'models';

function modelsOk(platform: PlatformHealth | null): boolean {
  const ai = platform?.components?.ai_engine?.detail;
  if (!ai) return false;
  const allOk = ai.models_all_ok;
  if (allOk === true || allOk === 'true') return true;
  const yolo = ai.yolo_loaded === true || ai.yolo_loaded === 'true';
  const phone = ai.driver_phone_model_loaded === true || ai.driver_phone_model_loaded === 'true';
  const belt = ai.seatbelt_model_loaded === true || ai.seatbelt_model_loaded === 'true';
  const plate = ai.plate_loaded === true || ai.plate_loaded === 'true';
  return yolo && phone && belt && plate;
}

function classify(platform: PlatformHealth | null, fetchFailed: boolean): GateKind {
  // No successful /health/platform → connectivity/proxy issue, NOT "models missing".
  if (fetchFailed || !platform) return 'unreachable';
  if (!modelsOk(platform)) return 'models';
  return 'ok';
}

/**
 * Honesty rules:
 * - Hard-block only when platform health was fetched and models are confirmed down.
 * - Unreachable API/proxy: keep the app usable + sticky banner (was falsely saying YOLO missing).
 */
export default function StackHealthGate({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const [platform, setPlatform] = useState<PlatformHealth | null>(null);
  const [fetchFailed, setFetchFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [bypassModels, setBypassModels] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    const poll = () => {
      void fetch('/health/platform')
        .then(async (r) => {
          if (!r.ok) throw new Error(`http ${r.status}`);
          return r.json() as Promise<PlatformHealth>;
        })
        .then((j) => {
          if (cancelled) return;
          setPlatform(j);
          setFetchFailed(false);
          if (modelsOk(j)) {
            setLoading(false);
            setBypassModels(false);
          }
        })
        .catch(() => {
          if (cancelled) return;
          setFetchFailed(true);
          setPlatform(null);
        });
    };

    poll();
    timer = setInterval(poll, 5000);
    const stop = setTimeout(() => {
      if (!cancelled) setLoading(false);
    }, 20_000);

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      clearTimeout(stop);
    };
  }, []);

  if (loading) return <>{children}</>;

  const kind = classify(platform, fetchFailed);
  const ai = platform?.components?.ai_engine?.detail ?? {};

  if (kind === 'ok') return <>{children}</>;

  // Transient proxy/WSL/localhost flap — do not claim models are missing, do not lock the UI.
  if (kind === 'unreachable') {
    return (
      <>
        <div className="sticky top-0 z-50 border-b border-amber-500/40 bg-amber-500/15 px-4 py-2">
          <div className="max-w-5xl mx-auto flex flex-wrap items-center gap-3 text-sm">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <p className="text-cv-text flex-1 min-w-[12rem]">
              {t('stackHealth.unreachableTitle')}
              <span className="text-cv-muted"> — {t('stackHealth.unreachableBody')}</span>
            </p>
            <Link to="/system-health" className="cv-btn-secondary text-xs shrink-0">
              {t('stackHealth.openHealth')}
            </Link>
          </div>
        </div>
        {children}
      </>
    );
  }

  // Confirmed models incomplete after a real health payload.
  if (bypassModels) {
    return (
      <>
        <div className="sticky top-0 z-50 border-b border-amber-500/40 bg-amber-500/15 px-4 py-2">
          <div className="max-w-5xl mx-auto flex flex-wrap items-center gap-3 text-sm">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <p className="text-cv-text flex-1">{t('stackHealth.degradedBody')}</p>
            <Link to="/system-health" className="cv-btn-secondary text-xs shrink-0">
              {t('stackHealth.openHealth')}
            </Link>
          </div>
        </div>
        {children}
      </>
    );
  }

  return (
    <div className="min-h-[60vh] flex items-center justify-center p-6">
      <div className="max-w-lg w-full rounded-xl border border-amber-500/40 bg-amber-500/10 p-6 space-y-4">
        <p className="font-display font-semibold text-lg flex items-center gap-2 text-cv-text">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
          {t('stackHealth.blockTitle')}
        </p>
        <p className="text-sm text-cv-muted">{t('stackHealth.blockBody')}</p>
        <ul className="text-xs text-cv-muted space-y-1 font-mono">
          <li>platform: {String(platform?.status ?? 'unknown')}</li>
          <li>models_all_ok: {String(ai.models_all_ok ?? false)}</li>
          <li>rules_engine: {String(platform?.components?.rules_engine?.status ?? '?')}</li>
          <li>frigate: {String(platform?.components?.frigate?.status ?? '?')}</li>
        </ul>
        <div className="flex flex-wrap gap-2 pt-2">
          <button type="button" className="cv-btn-secondary text-sm" onClick={() => setBypassModels(true)}>
            {t('stackHealth.degradedContinue')}
          </button>
          <Link to="/system-health" className="cv-btn-primary text-sm">
            {t('stackHealth.openHealth')}
          </Link>
        </div>
      </div>
    </div>
  );
}
