import { useTranslation } from 'react-i18next';
import { ArrowDownLeft, ArrowUpRight, Gauge, RotateCcw } from 'lucide-react';
import { observationApi, type ObservationCounter } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useCameras } from '@/hooks/api/queries';
import { useObservationCounters } from '@/hooks/api/queries';

interface CameraObservationPanelProps {
  cameraId?: string;
  /** When set and differs from cameraId, polling pauses (demo multi-video). */
  activeCameraId?: string;
  className?: string;
}

const KIND_ORDER = ['line', 'line_class', 'rule', 'rule_set_or', 'rule_set_n', 'event'];

function kindGroupLabel(kind: string, lang: 'fr' | 'en'): string {
  const fr: Record<string, string> = {
    line: 'Lignes',
    line_class: 'Lignes (par classe)',
    rule: 'Règles d\'observation',
    rule_set_or: 'Ensembles (OU)',
    rule_set_n: 'Ensembles (N-sur-M)',
    event: 'Événements',
  };
  const en: Record<string, string> = {
    line: 'Lines',
    line_class: 'Lines (by class)',
    rule: 'Observation rules',
    rule_set_or: 'Sets (OR)',
    rule_set_n: 'Sets (N-of-M)',
    event: 'Events',
  };
  return (lang === 'fr' ? fr : en)[kind] ?? kind;
}

export default function CameraObservationPanel({
  cameraId,
  activeCameraId,
  className = '',
}: CameraObservationPanelProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith('en') ? 'en' : 'fr';
  const orgId = useAuthStore((s) => s.orgId);
  const { data: cameras = [] } = useCameras();

  const counterCamera = cameras.find((c) => c.id === cameraId);
  const paused = Boolean(cameraId && activeCameraId && cameraId !== activeCameraId);

  const { data: counters = [], refetch } = useObservationCounters(cameraId, !paused);

  const handleReset = async () => {
    if (!orgId) return;
    if (!window.confirm(t('observation.resetConfirm', { defaultValue: 'Remettre à zéro les compteurs de cette caméra ?' }))) return;
    await observationApi.resetCounters(orgId, { cameraId });
    void refetch();
  };

  const grouped = counters.reduce<Record<string, ObservationCounter[]>>((acc, c) => {
    const k = c.kind || 'rule';
    if (!acc[k]) acc[k] = [];
    acc[k].push(c);
    return acc;
  }, {});

  const sortedKinds = Object.keys(grouped).sort(
    (a, b) => (KIND_ORDER.indexOf(a) === -1 ? 99 : KIND_ORDER.indexOf(a)) - (KIND_ORDER.indexOf(b) === -1 ? 99 : KIND_ORDER.indexOf(b)),
  );

  return (
    <div className={`cv-card overflow-hidden ${className}`}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-cv-border gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Gauge className="w-4 h-4 text-cv-accent shrink-0" />
            {t('observation.panelTitle', { defaultValue: 'Compteurs d\'observation' })}
            <span className="text-cv-muted font-normal">({counters.length})</span>
          </div>
          <p className="text-[11px] text-cv-muted mt-0.5 leading-relaxed">
            {counterCamera
              ? t('observation.panelSubtitleNamed', {
                  defaultValue: 'Caméra « {{camera}} » — comptages actifs (lignes, règles observation, ensembles).',
                  camera: counterCamera.name,
                })
              : t('observation.panelSubtitle', {
                  defaultValue: 'Comptages configurés et activés sur cette caméra.',
                })}
          </p>
        </div>
        {counters.length > 0 && !paused && (
          <button
            type="button"
            onClick={() => void handleReset()}
            className="text-xs text-cv-muted hover:text-cv-accent flex items-center gap-1 shrink-0"
          >
            <RotateCcw className="w-3 h-3" />
            {t('observation.reset', { defaultValue: 'Réinitialiser' })}
          </button>
        )}
      </div>

      {paused ? (
        <p className="text-xs text-cv-muted p-4 text-center">
          {t('observation.paused', { defaultValue: 'Compteurs en pause — sélectionnez la caméra de comptage.' })}
        </p>
      ) : counters.length === 0 ? (
        <p className="text-xs text-cv-muted p-4 text-center">
          {t('observation.empty', {
            defaultValue: 'Aucun compteur actif. Activez une règle en mode observation ou tracez une ligne de comptage.',
          })}
        </p>
      ) : (
        <div className="p-4 space-y-4">
          {sortedKinds.map((kind) => (
            <div key={kind}>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-cv-muted mb-2">
                {kindGroupLabel(kind, lang)}
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {grouped[kind].map((c) => (
                  <ObservationCard key={c.id} counter={c} lang={lang} t={t} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ObservationCard({
  counter: c,
  lang,
  t,
}: {
  counter: ObservationCounter;
  lang: 'fr' | 'en';
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const label = lang === 'en' ? (c.label_en || c.label_fr) : (c.label_fr || c.label_en);
  const legend = lang === 'en' ? (c.legend_en || c.legend_fr) : (c.legend_fr || c.legend_en);
  const isLine = c.kind === 'line' || c.kind === 'line_class';

  return (
    <div className="rounded-lg border border-cv-border bg-cv-surface/60 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <span className="text-sm font-medium truncate block" title={label}>
            {label}
          </span>
          <span className="text-[10px] text-cv-muted line-clamp-2" title={legend}>
            {legend}
          </span>
        </div>
        <span className="text-2xl font-bold tabular-nums text-cv-accent shrink-0">{c.count}</span>
      </div>
      {isLine && (c.count_in != null || c.count_out != null) && (
        <div className="mt-2 flex items-center gap-4 text-xs text-cv-muted">
          <span className="flex items-center gap-1">
            <ArrowDownLeft className="w-3.5 h-3.5 text-emerald-400" />
            {t('demoCenter.counterIn', { defaultValue: 'Entrées' })}:{' '}
            <span className="tabular-nums text-cv-text">{c.count_in ?? 0}</span>
          </span>
          <span className="flex items-center gap-1">
            <ArrowUpRight className="w-3.5 h-3.5 text-amber-400" />
            {t('demoCenter.counterOut', { defaultValue: 'Sorties' })}:{' '}
            <span className="tabular-nums text-cv-text">{c.count_out ?? 0}</span>
          </span>
        </div>
      )}
      {c.last_class && (
        <p className="mt-1.5 text-[10px] text-cv-muted">
          {t('demoCenter.counterLastClass', { defaultValue: 'Dernier objet' })}: {c.last_class}
        </p>
      )}
    </div>
  );
}
