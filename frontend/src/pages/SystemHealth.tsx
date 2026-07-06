import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { Activity, Cpu, MemoryStick, HardDrive, Wifi, Server, Eye, ScanLine, CheckCircle2, XCircle, AlertTriangle, Upload } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import LoadingState from '@/components/ui/LoadingState';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import ModelImportWizard from '@/components/aimodels/ModelImportWizard';
import { useHealth, useAiHealth, useModelPack } from '@/hooks/api/queries';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import { useAuthStore } from '@/stores/authStore';
import type { SystemHealthMetric } from '@/types';

const metricIcons: Record<string, typeof Cpu> = {
  CPU: Cpu,
  Mémoire: MemoryStick,
  Memory: MemoryStick,
  Disque: HardDrive,
  Disk: HardDrive,
  Réseau: Wifi,
  Network: Wifi,
  postgres: Server,
  database: Server,
  redis: Server,
  mqtt: Wifi,
};

const METRIC_LABELS_FR: Record<string, string> = {
  CPU: 'Processeur (CPU)',
  Memory: 'Mémoire vive (RAM)',
  Disk: 'Disque',
  Network: 'Réseau',
  postgres: 'Base de données',
  database: 'Base de données',
  redis: 'Cache Redis',
  mqtt: 'Messagerie MQTT',
  storage: 'Stockage',
};

function HealthBar({ metric }: { metric: SystemHealthMetric }) {
  const numValue = parseFloat(metric.value);
  const isPercent = metric.unit === '%';
  const percent = isPercent ? numValue : metric.status === 'healthy' ? 100 : metric.status === 'warning' ? 70 : 30;
  const barColor =
    metric.status === 'healthy' ? 'bg-emerald-400' :
    metric.status === 'warning' ? 'bg-amber-400' : 'bg-red-400';

  return (
    <div className="cv-card-hover p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {(() => {
            const Icon = metricIcons[metric.name] ?? Server;
            return <Icon className="w-5 h-5 text-cv-accent" />;
          })()}
          <span className="font-medium capitalize">{METRIC_LABELS_FR[metric.name] ?? metric.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-display text-lg font-bold">
            {metric.value}{metric.unit ? ` ${metric.unit}` : ''}
          </span>
          <span className={`w-2.5 h-2.5 rounded-full ${barColor}`} />
        </div>
      </div>
      {isPercent && (
        <div className="h-2 rounded-full bg-cv-deep overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${barColor}`}
            style={{ width: `${Math.min(percent, 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}

interface ModelRowProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  loaded: boolean;
  hint?: string;
}

function ModelRow({ icon: Icon, label, loaded, hint }: ModelRowProps) {
  const { t } = useTranslation();
  return (
    <div className="cv-card-hover p-4 flex items-start gap-3">
      <Icon className={`w-5 h-5 mt-0.5 flex-shrink-0 ${loaded ? 'text-emerald-400' : 'text-red-400'}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm">{label}</span>
          {loaded ? (
            <span className="flex items-center gap-1 text-xs text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              {t('systemHealth.modelLoaded')}
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs text-red-400">
              <XCircle className="w-3.5 h-3.5" />
              {t('systemHealth.modelMissing')}
            </span>
          )}
        </div>
        {!loaded && hint && (
          <p className="text-xs text-cv-muted mt-1 flex items-start gap-1">
            <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5 text-amber-400" />
            {hint}
          </p>
        )}
      </div>
    </div>
  );
}

export default function SystemHealth() {
  const { t, i18n } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const orgId = useAuthStore((s) => s.orgId);
  const startTour = useAutoPageTour('health');
  const { data: health = [], isLoading, isError, refetch } = useHealth();
  const { data: aiHealth, refetch: refetchAi } = useAiHealth();
  const { data: modelPack, refetch: refetchPack } = useModelPack();
  const lang = i18n.language.startsWith('en') ? 'en' : 'fr';
  const wizardOpen = searchParams.get('wizard') === 'import-model';

  const closeWizard = () => {
    searchParams.delete('wizard');
    setSearchParams(searchParams, { replace: true });
  };

  const openWizard = () => {
    searchParams.set('wizard', 'import-model');
    setSearchParams(searchParams, { replace: true });
  };

  if (isLoading) return <LoadingState />;

  if (isError) {
    return (
      <div>
        <PageHeader title={t('systemHealth.title')} onHelpTour={startTour} />
        <ErrorState onRetry={() => void refetch()} />
      </div>
    );
  }

  if (health.length === 0) {
    return (
      <div>
        <PageHeader title={t('systemHealth.title')} onHelpTour={startTour} />
        <EmptyState
          title={t('systemHealth.empty')}
          hint={t('systemHealth.emptyHint')}
          icon={Activity}
          action={
            <button className="cv-btn-secondary inline-flex items-center gap-2" onClick={() => { void refetch(); void refetchAi(); void refetchPack(); }}>
              Relancer la vérification
            </button>
          }
        />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title={t('systemHealth.title')} onHelpTour={startTour} />
      <h2 className="font-display text-sm font-semibold text-cv-muted uppercase tracking-wider mb-3">
        {t('systemHealth.services')}
      </h2>
      <div id="health-services" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {health.map((metric) => (
          <HealthBar key={metric.name} metric={metric} />
        ))}
      </div>

      <h2 className="font-display text-sm font-semibold text-cv-muted uppercase tracking-wider mt-8 mb-3 flex items-center justify-between gap-3 flex-wrap">
        <span>{t('systemHealth.aiModels')}</span>
        {orgId && (
          <button type="button" data-tour="import-model" className="cv-btn-primary text-xs inline-flex items-center gap-1.5" onClick={openWizard}>
            <Upload className="w-3.5 h-3.5" />
            {t('modelImport.openWizard', 'Importer un modèle ONNX')}
          </button>
        )}
      </h2>
      {modelPack?.gpu_health_key && (
        <div className={`mb-3 text-xs rounded-lg px-3 py-2 border ${
          modelPack.gpu_loaded
            ? 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30'
            : 'text-amber-300 bg-amber-500/10 border-amber-500/30'
        }`}>
          {modelPack.gpu_loaded
            ? t('systemHealth.gpuOk', { defaultValue: "GPU CUDA actif pour l'inférence YOLO." })
            : t('systemHealth.gpuMissing', { defaultValue: 'GPU CUDA indisponible — inférence CPU (repli).' })}
        </div>
      )}
      {aiHealth && !aiHealth.reachable ? (
        <div className="flex items-center gap-2 text-sm text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-3">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>{t('systemHealth.aiUnreachable', 'Moteur IA non joignable — les modèles ne peuvent pas être vérifiés.')}</span>
        </div>
      ) : modelPack?.models?.length ? (
        <div id="health-ai-models" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {modelPack.models.map((m) => (
            <ModelRow
              key={m.id}
              icon={m.kind === 'secondary' ? ScanLine : m.id === 'insightface' ? Eye : Cpu}
              label={lang === 'en' ? (m.label_en || m.id) : (m.label_fr || m.id)}
              loaded={m.loaded}
              hint={!m.loaded ? (m.notes || t('systemHealth.modelMissingHint')) : undefined}
            />
          ))}
        </div>
      ) : (
        <div id="health-ai-models" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <ModelRow icon={Cpu} label="YOLO (détection)" loaded={aiHealth?.yolo ?? false} hint={t('systemHealth.modelMissingHint')} />
          <ModelRow icon={Eye} label={t('systemHealth.faceModel', 'Reconnaissance faciale')} loaded={aiHealth?.face ?? false} hint={t('systemHealth.modelMissingHint')} />
          <ModelRow icon={ScanLine} label={t('systemHealth.plateModel', 'Lecture de plaques (OCR)')} loaded={aiHealth?.plate ?? false} hint={t('systemHealth.modelMissingHint')} />
        </div>
      )}
      {modelPack?.install_command && (
        <p className="text-[10px] text-cv-muted mt-3 font-mono">
          {t('systemHealth.modelPackInstall', { defaultValue: 'Installation / vérif' })}: {modelPack.install_command}
          {modelPack.verify_command ? ` · ${modelPack.verify_command}` : ''}
        </p>
      )}
      {orgId && (
        <ModelImportWizard
          orgId={orgId}
          open={wizardOpen}
          onClose={closeWizard}
          onSuccess={() => {
            void refetchAi();
            void refetchPack();
          }}
        />
      )}
    </div>
  );
}
