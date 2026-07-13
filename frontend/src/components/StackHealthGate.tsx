import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';

type PlatformHealth = {
  status?: string;
  components?: Record<string, { status?: string; detail?: Record<string, unknown> }>;
};

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

export default function StackHealthGate({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const [platform, setPlatform] = useState<PlatformHealth | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    const poll = () => {
      void fetch('/health/platform')
        .then((r) => (r.ok ? r.json() : null))
        .then((j) => {
          if (cancelled) return;
          setPlatform(j);
          if (modelsOk(j)) setLoading(false);
        })
        .catch(() => {
          if (!cancelled) setPlatform(null);
        });
    };

    poll();
    timer = setInterval(poll, 5000);
    const stop = setTimeout(() => { if (!cancelled) setLoading(false); }, 45_000);

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      clearTimeout(stop);
    };
  }, []);

  if (loading) return <>{children}</>;

  const incomplete = !modelsOk(platform) || platform?.status === 'down';

  if (!incomplete) return <>{children}</>;

  const ai = platform?.components?.ai_engine?.detail ?? {};

  return (
    <div className="min-h-[60vh] flex items-center justify-center p-6">
      <div className="max-w-lg w-full rounded-xl border border-amber-500/40 bg-amber-500/10 p-6 space-y-4">
        <p className="font-display font-semibold text-lg flex items-center gap-2 text-cv-text">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
          {t('stackHealth.blockTitle', { defaultValue: 'Stack plateforme incomplète' })}
        </p>
        <p className="text-sm text-cv-muted">
          {t('stackHealth.blockBody', {
            defaultValue:
              'La santé unifiée signale un composant dégradé. Rechargement automatique toutes les 5 s.',
          })}
        </p>
        <ul className="text-xs text-cv-muted space-y-1 font-mono">
          <li>platform: {String(platform?.status ?? 'unknown')}</li>
          <li>models_all_ok: {String(ai.models_all_ok ?? false)}</li>
          <li>rules_engine: {String(platform?.components?.rules_engine?.status ?? '?')}</li>
          <li>frigate: {String(platform?.components?.frigate?.status ?? '?')}</li>
        </ul>
        <div className="flex flex-wrap gap-2 pt-2">
          <Link to="/system-health" className="cv-btn-primary text-sm">
            {t('stackHealth.openHealth', { defaultValue: 'Santé système' })}
          </Link>
        </div>
      </div>
    </div>
  );
}
