import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import {
  Box,
  CheckCircle2,
  FileUp,
  ScanLine,
  Sparkles,
  Upload,
  X,
} from 'lucide-react';
import WizardSteps, { type WizardStep } from '@/components/ui/WizardSteps';
import ExplanatorySelect from '@/components/ui/ExplanatorySelect';
import DialogTourHelpButton from '@/components/ui/DialogTourHelpButton';
import { useDialogTour } from '@/hooks/useDialogTour';
import {
  buildModelImportStructureOptions,
  resolveModelImportStructure,
  slugifyEventType,
  slugifyModelId,
} from '@/lib/modelImportTemplates';
import { orgModelsApi, type OrgModelRow, type UploadOrgModelResponse } from '@/api/client';
import { ModalLayerProvider } from '@/components/ui/ModalLayerContext';
import { LAYER } from '@/lib/layerZIndex';

export interface ModelImportWizardProps {
  orgId: string;
  open: boolean;
  onClose: () => void;
  onSuccess?: (result: UploadOrgModelResponse) => void;
}

type SourceMode = 'file' | 'url';

function parseList(raw: string): string[] {
  return raw
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function ModelImportWizard({ orgId, open, onClose, onSuccess }: ModelImportWizardProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith('en') ? 'en' : 'fr';

  const [step, setStep] = useState(1);
  const [structureId, setStructureId] = useState<string>('custom');
  const [orgModels, setOrgModels] = useState<OrgModelRow[]>([]);
  const [sourceMode, setSourceMode] = useState<SourceMode>('file');
  const [file, setFile] = useState<File | null>(null);
  const [downloadUrl, setDownloadUrl] = useState('');
  const [modelId, setModelId] = useState('');
  const [labelFr, setLabelFr] = useState('');
  const [labelEn, setLabelEn] = useState('');
  const [eventType, setEventType] = useState('');
  const [descFr, setDescFr] = useState('');
  const [task, setTask] = useState<'classification' | 'detection'>('classification');
  const [appliesTo, setAppliesTo] = useState<'zone' | 'line' | 'both'>('zone');
  const [inputSource, setInputSource] = useState<'crop_vehicle' | 'crop_zone' | 'full_frame'>('crop_vehicle');
  const [inputSize, setInputSize] = useState(224);
  const [classesRaw, setClassesRaw] = useState('negative, positive');
  const [positiveRaw, setPositiveRaw] = useState('positive');
  const [observationCapable, setObservationCapable] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadOrgModelResponse | null>(null);

  const structure = useMemo(
    () => resolveModelImportStructure(structureId, orgModels),
    [structureId, orgModels],
  );

  useEffect(() => {
    if (!open || !orgId) return;
    void orgModelsApi.list(orgId)
      .then((r) => setOrgModels(r.data.models ?? []))
      .catch(() => setOrgModels([]));
  }, [open, orgId]);

  const wizardSteps: WizardStep[] = [
    { n: 1, label: t('modelImport.stepStructure', 'Structure'), icon: Sparkles },
    { n: 2, label: t('modelImport.stepSource', 'Fichier'), icon: FileUp },
    { n: 3, label: t('modelImport.stepIdentity', 'Identité'), icon: ScanLine },
    { n: 4, label: t('modelImport.stepClasses', 'Classes'), icon: Box },
    { n: 5, label: t('modelImport.stepConfirm', 'Validation'), icon: CheckCircle2 },
  ];

  const applyStructure = useCallback(
    (id: string) => {
      const tpl = resolveModelImportStructure(id, orgModels);
      if (!tpl) return;
      setStructureId(id);
      setTask(tpl.task);
      setAppliesTo(tpl.applies_to);
      setInputSource(tpl.input_source);
      setInputSize(tpl.input_size);
      setClassesRaw(tpl.classes.join(', '));
      setPositiveRaw(tpl.positive_classes.join(', '));
      if (tpl.fromOrgModel) {
        const m = tpl.fromOrgModel;
        setModelId(`${m.id}_v2`);
        setLabelFr(m.label_fr);
        setLabelEn(m.label_en ?? m.label_fr);
        setEventType(m.event_type);
        setDescFr(m.human_description_fr ?? m.label_fr);
      } else if (id === 'custom') {
        /* keep user-entered identity */
      } else {
        setModelId('');
        setLabelFr('');
        setLabelEn('');
        setEventType('');
        setDescFr('');
      }
    },
    [orgModels],
  );

  const structureOptions = useMemo(
    () => buildModelImportStructureOptions(lang, orgModels),
    [lang, orgModels],
  );

  const step2Valid =
    sourceMode === 'file'
      ? Boolean(file && file.name.toLowerCase().endsWith('.onnx'))
      : Boolean(downloadUrl.trim().startsWith('http'));
  const step3Valid =
    slugifyModelId(modelId).length >= 2
    && labelFr.trim().length >= 2
    && slugifyEventType(eventType).length >= 2
    && descFr.trim().length >= 8;
  const classes = parseList(classesRaw);
  const positive = parseList(positiveRaw);
  const step4Valid =
    classes.length >= 2
    && positive.length >= 1
    && positive.every((p) => classes.includes(p))
    && inputSize >= 64
    && inputSize <= 2048;

  const prepareTourStep = useCallback((selector: string) => {
    const map: Record<string, number> = {
      '#model-import-step1': 1,
      '#model-import-step2': 2,
      '#model-import-step3': 3,
      '#model-import-step4': 4,
      '#model-import-step5': 5,
    };
    const n = map[selector];
    if (n) setStep(n);
  }, []);

  const startTour = useDialogTour('modelImport', open, { prepareStep: prepareTourStep });

  const canNext =
    step === 1
    || (step === 2 && step2Valid)
    || (step === 3 && step3Valid)
    || (step === 4 && step4Valid)
    || step === 5;

  const reset = () => {
    setStep(1);
    setError(null);
    setResult(null);
    setSubmitting(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const id = slugifyModelId(modelId);
      const ev = slugifyEventType(eventType);
      const behavior = structure?.behavior || `custom:${id}`;
      const res = await orgModelsApi.upload(orgId, {
        id,
        task,
        event_type: ev,
        label_fr: labelFr.trim(),
        label_en: (labelEn || labelFr).trim(),
        human_description_fr: descFr.trim(),
        applies_to: appliesTo,
        input_source: inputSource,
        input_size: inputSize,
        capability: structure?.capability ?? 'beta',
        behavior,
        classes,
        positive_classes: positive,
        file: sourceMode === 'file' ? file ?? undefined : undefined,
        download_url: sourceMode === 'url' ? downloadUrl.trim() : undefined,
      });
      setResult(res.data);
      onSuccess?.(res.data);
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? (e as Error)?.message
        ?? t('modelImport.errorGeneric', 'Import impossible');
      setError(String(msg));
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      style={{ zIndex: LAYER.modalOverlay }}
    >
      <ModalLayerProvider>
      <div id="model-import-wizard" className="cv-card w-full max-w-3xl max-h-[92vh] flex flex-col shadow-2xl border border-cv-border/80" role="dialog" aria-modal="true">
        <div className="flex items-start justify-between gap-4 p-5 border-b border-cv-border/60 shrink-0">
          <div>
            <h2 className="text-lg font-display font-semibold flex items-center gap-2">
              <Upload className="w-5 h-5 text-cv-accent" />
              {t('modelImport.title', 'Importer un modèle ONNX')}
            </h2>
            <p className="text-xs text-cv-muted mt-1 max-w-xl leading-relaxed">
              {t('modelImport.subtitle', 'Comportement zone/ligne ajouté seulement si fichier valide, métadonnées complètes et IA confirme le chargement.')}
            </p>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <DialogTourHelpButton onClick={() => startTour()} />
            <button type="button" className="cv-btn-ghost p-2 rounded-lg" onClick={handleClose}>
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="px-5 pt-4 shrink-0"><WizardSteps steps={wizardSteps} current={step} /></div>
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {step === 1 && (
            <div id="model-import-step1">
            <ExplanatorySelect
              value={structureId}
              onChange={(v) => applyStructure(v)}
              options={structureOptions}
              searchable={structureOptions.length > 6}
            />
            </div>
          )}
          {step === 2 && (
            <div id="model-import-step2">
              <div className="flex gap-2">
                <button type="button" className={`cv-btn-secondary text-xs flex-1 ${sourceMode === 'file' ? 'border-cv-accent' : ''}`} onClick={() => setSourceMode('file')}>{t('modelImport.sourceFile', 'Fichier .onnx')}</button>
                <button type="button" className={`cv-btn-secondary text-xs flex-1 ${sourceMode === 'url' ? 'border-cv-accent' : ''}`} onClick={() => setSourceMode('url')}>{t('modelImport.sourceUrl', 'Lien HTTPS')}</button>
              </div>
              {sourceMode === 'file' ? (
                <input type="file" accept=".onnx" className="cv-input w-full text-sm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              ) : (
                <input className="cv-input w-full text-sm font-mono" placeholder="https://…/modele.onnx" value={downloadUrl} onChange={(e) => setDownloadUrl(e.target.value)} />
              )}
            </div>
          )}
          {step === 3 && (
            <div id="model-import-step3" className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <input className="cv-input text-sm font-mono" placeholder="id modèle" value={modelId} onChange={(e) => setModelId(e.target.value)} />
              <input className="cv-input text-sm font-mono" placeholder="event_type" value={eventType} onChange={(e) => setEventType(e.target.value)} />
              <input className="cv-input text-sm" placeholder="Libellé FR" value={labelFr} onChange={(e) => setLabelFr(e.target.value)} />
              <input className="cv-input text-sm" placeholder="Libellé EN" value={labelEn} onChange={(e) => setLabelEn(e.target.value)} />
              <textarea className="cv-input text-sm sm:col-span-2 min-h-[72px]" placeholder="Description" value={descFr} onChange={(e) => setDescFr(e.target.value)} />
              <label className="flex items-start gap-2 sm:col-span-2 p-3 rounded-lg border border-cv-border/60 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={observationCapable}
                  onChange={(e) => setObservationCapable(e.target.checked)}
                />
                <span className="text-xs text-cv-muted leading-relaxed">
                  {t('modelImport.observationCapable', {
                    defaultValue: 'Disponible en mode observation (comptage sans alerte ni preuve par défaut)',
                  })}
                </span>
              </label>
              <select className="cv-input text-sm" value={appliesTo} onChange={(e) => setAppliesTo(e.target.value as typeof appliesTo)}>
                <option value="zone">Zone</option><option value="line">Ligne</option><option value="both">Les deux</option>
              </select>
              <select className="cv-input text-sm" value={inputSource} onChange={(e) => setInputSource(e.target.value as typeof inputSource)}>
                <option value="crop_vehicle">Crop véhicule</option><option value="crop_zone">Crop zone</option><option value="full_frame">Image complète</option>
              </select>
            </div>
          )}
          {step === 4 && (
            <div id="model-import-step4">
              <select className="cv-input text-sm" value={task} onChange={(e) => setTask(e.target.value as typeof task)}>
                <option value="classification">Classification</option><option value="detection">Détection</option>
              </select>
              <input type="number" className="cv-input text-sm" value={inputSize} onChange={(e) => setInputSize(Number(e.target.value))} />
              <textarea className="cv-input text-sm font-mono" value={classesRaw} onChange={(e) => setClassesRaw(e.target.value)} />
              <textarea className="cv-input text-sm font-mono" value={positiveRaw} onChange={(e) => setPositiveRaw(e.target.value)} />
            </div>
          )}
          {step === 5 && !result && (
            <div id="model-import-step5">
            <p className="text-sm text-cv-muted font-mono">ID: {slugifyModelId(modelId)} · {slugifyEventType(eventType)} · {appliesTo}</p>
            <p className="text-xs text-cv-muted mt-2">
              {observationCapable
                ? t('modelImport.observationCapableOn', { defaultValue: 'Mode observation : activé pour ce modèle' })
                : t('modelImport.observationCapableOff', { defaultValue: 'Mode observation : désactivé (alertes uniquement)' })}
            </p>
            </div>
          )}
          {result && <p className="text-sm text-emerald-400">OK — {result.behavior} · reload IA: {String(result.ai_reload_ok)}</p>}
          {error && <p className="text-sm text-red-400">{error}</p>}
        </div>
        <div className="flex justify-between p-5 border-t border-cv-border/60">
          <button type="button" className="cv-btn-ghost text-sm" onClick={result ? handleClose : step <= 1 ? handleClose : () => setStep((s) => s - 1)}>{result ? t('common.close', 'Fermer') : t('common.cancel')}</button>
          {!result && (
            <button type="button" className="cv-btn-primary text-sm" disabled={!canNext || submitting} onClick={() => { if (step < 5) setStep((s) => s + 1); else void handleSubmit(); }}>
              {step < 5 ? t('common.next', 'Suivant') : t('modelImport.submit', 'Importer')}
            </button>
          )}
        </div>
      </div>
      </ModalLayerProvider>
    </div>,
    document.body,
  );
}
