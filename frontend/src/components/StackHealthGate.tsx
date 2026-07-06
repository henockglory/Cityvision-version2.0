import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import { AI_ENGINE_HEALTH } from '@/config/streams';

type HealthPayload = Record<string, unknown>;

function isLoadedFlag(v: unknown): boolean {
  return v === true || v === 'true';
}

function stackIncomplete(h: HealthPayload | null): boolean {
  if (!h) return true;
  const yolo = isLoadedFlag(h.yolo_loaded);
  const plate = isLoadedFlag(h.plate_loaded);
  const phone = isLoadedFlag(h.driver_phone_model_loaded);
  const belt = isLoadedFlag(h.seatbelt_model_loaded);
  return !(yolo && plate && phone && belt);
}

export default function StackHealthGate({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void fetch(AI_ENGINE_HEALTH)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (!cancelled) setHealth(j); })
      .catch(() => { if (!cancelled) setHealth(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) return <>{children}</>;

  const incomplete = stackIncomplete(health);

  if (!incomplete) return <>{children}</>;

  return (
    <div className="min-h-[60vh] flex items-center justify-center p-6">
      <div className="max-w-lg w-full rounded-xl border border-amber-500/40 bg-amber-500/10 p-6 space-y-4">
        <p className="font-display font-semibold text-lg flex items-center gap-2 text-cv-text">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
          {t('stackHealth.blockTitle', { defaultValue: 'Stack IA incomplète' })}
        </p>
        <p className="text-sm text-cv-muted">
          {t('stackHealth.blockBody', {
            defaultValue:
              'Des modèles critiques ne sont pas chargés. L\'application reste bloquée jusqu\'à correction de la stack IA (CUDA + modèles requis).',
          })}
        </p>
        <ul className="text-xs text-cv-muted space-y-1 font-mono">
          <li>yolo_loaded: {String(health?.yolo_loaded ?? false)}</li>
          <li>plate_loaded: {String(health?.plate_loaded ?? false)}</li>
          <li>driver_phone: {String(health?.driver_phone_model_loaded ?? false)}</li>
          <li>seatbelt: {String(health?.seatbelt_model_loaded ?? false)}</li>
        </ul>
        <div className="flex flex-wrap gap-2 pt-2">
          <Link to="/health" className="cv-btn-primary text-sm">
            {t('stackHealth.openHealth', { defaultValue: 'Corriger la stack' })}
          </Link>
        </div>
      </div>
    </div>
  );
}
