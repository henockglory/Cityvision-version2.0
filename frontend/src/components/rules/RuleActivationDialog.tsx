import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Clock, Loader2, Settings2, X, MapPin, GitBranch, Zap, Check, AlertTriangle, Info } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  identityApi,
  rulesApi,
  zonesApi,
  type BackendZone,
  type SurveillanceList,
} from '@/api/client';
import {
  activationConfigFromValues,
  buildConfiguredDefinition,
  ensureSpatialConditions,
} from '@/lib/ruleDefinitionBuilder';
import ExplanatorySelect from '@/components/ui/ExplanatorySelect';
import {
  buildCameraOptions,
  buildLineOptions,
  buildSchemaEnumOptions,
  buildSeverityOptions,
  buildSurveillanceListOptions,
  buildZoneOptions,
} from '@/lib/conditionValueOptions';
import ClassFilterPicker from '@/components/rules/ClassFilterPicker';
import { classLabel } from '@/lib/detectionClasses';
import { resolveConfigSchema, getSchemaDefaults } from '@/lib/ruleConfigSchema';
import {
  ACTION_FAMILIES,
  actionKey,
  buildActionsPayload,
  defaultActionsSelection,
  executedActionsOnly,
  actionsFromRule,
} from '@/lib/ruleActionsRegistry';
import ConditionTreeVisualEditor from '@/components/rules/ConditionTreeVisualEditor';
import ConditionTreeTechnicalMirror from '@/components/rules/ConditionTreeTechnicalMirror';
import ConditionLogicSimulator from '@/components/rules/ConditionLogicSimulator';
import RuleStudioGuideRail from '@/components/rules/RuleStudioGuideRail';
import RuleFlowBuilder from '@/components/rules/RuleFlowBuilder';
import EvidencePolicyPanel from '@/components/rules/EvidencePolicyPanel';
import OutputChannelsPanel from '@/components/rules/OutputChannelsPanel';
import { DEFAULT_EVIDENCE_POLICY, SPATIAL_TEMPLATES_REQUIRING_CLASS, normalizeEvidencePolicy, type EvidencePolicy } from '@/lib/evidencePolicy';
import { orgApi } from '@/api/client';
import {
  cloneCondition,
  createGroup,
  createLeaf,
  type ConditionNode,
  validateConditionTree,
} from '@/lib/conditionTree';
import { narrateConditionSummary } from '@/lib/conditionNarrative';
import { templatePrimaryEventType } from '@/lib/conditionValueOptions';
import { loadRuleGuides } from '@/i18n/loadRuleGuides';
import InfoTip from '@/components/ui/InfoTip';
import Modal from '@/components/ui/Modal';
import WizardSteps from '@/components/ui/WizardSteps';
import SegmentedTabs from '@/components/ui/SegmentedTabs';
import GuideIllustration from '@/components/ui/GuideIllustration';
import { useAuthStore } from '@/stores/authStore';
import { useCameras } from '@/hooks/api/queries';
import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';
import RuleActivationFeedback from '@/components/rules/RuleActivationFeedback';
import { go2rtcStreamSrc } from '@/config/streams';
import type { ConfigSchemaField, Rule, RuleCatalogTemplate } from '@/types';

interface BackendLine {
  id: string;
  name: string;
}

interface RuleActivationDialogProps {
  template: RuleCatalogTemplate | null;
  existingRule?: Rule | null;
  initialStep?: 1 | 2 | 3 | 4;
  demoMode?: boolean;
  demoCameraIds?: string[];
  onClose: () => void;
  onActivated: () => void;
}

const STEP_LABELS_KEYS = ['config', 'conditions', 'actionsEvidence', 'preview'] as const;

function WizardStepContext({ step, template, t }: {
  step: number;
  template: { name: string; partial_status?: string; partial_reason_fr?: string; category?: string };
  t: (k: string, opts?: Record<string, unknown>) => string;
}) {
  const ctxMap: Record<number, { why: string; what: string }> = {
    1: {
      why: t('rules.studio.step1Why', { defaultValue: 'Choisissez la caméra à surveiller et les paramètres spécifiques à cette règle (zone, durée, classe d\'objet…)' }),
      what: t('rules.studio.step1What', { defaultValue: 'Ces réglages définissent précisément quand et où la règle sera active.' }),
    },
    2: {
      why: t('rules.studio.step2Why', { defaultValue: 'Vérifiez la logique de déclenchement : c\'est la condition exacte que le système évaluera sur chaque événement.' }),
      what: t('rules.studio.step2What', { defaultValue: 'Vous pouvez affiner avec des opérateurs ET / OU / SAUF pour des scénarios complexes.' }),
    },
    3: {
      why: t('rules.studio.step3Why', { defaultValue: 'Définissez ce qui se passe quand la règle se déclenche : alerte, enregistrement, notification.' }),
      what: t('rules.studio.step3What', { defaultValue: 'Vous pouvez combiner plusieurs actions et choisir le niveau de sévérité de l\'alerte.' }),
    },
    4: {
      why: t('rules.studio.step4Why', { defaultValue: 'Vérifiez le résumé de votre règle avant de l\'activer.' }),
      what: t('rules.studio.step4What', { defaultValue: 'Après activation, la règle surveillera le flux en temps réel. La première alerte devrait arriver dans ~30 secondes si un événement est détecté.' }),
    },
  };
  const ctx = ctxMap[step];
  if (!ctx) return null;
  const hasPartial = template.partial_status && template.partial_status !== 'full';
  return (
    <div className="cv-stack-sm mb-5">
      {hasPartial && (
        <div className="cv-callout text-amber-300 bg-amber-400/5 border border-amber-400/20">
          <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
          <span>{template.partial_reason_fr ?? t('rules.studio.partialWarning', { defaultValue: 'Cette règle nécessite une configuration ou un module supplémentaire pour être pleinement opérationnelle.' })}</span>
        </div>
      )}
      <div className="cv-callout text-cv-muted bg-cv-accent/5 border border-cv-accent/15">
        <Info className="w-4 h-4 shrink-0 text-cv-accent" />
        <div className="space-y-1 min-w-0">
          <p className="text-cv-text/90 leading-relaxed">{ctx.why}</p>
          <p className="text-cv-muted/80 leading-relaxed">{ctx.what}</p>
        </div>
      </div>
    </div>
  );
}

export default function RuleStudioDialog({
  template,
  existingRule,
  initialStep = 1,
  demoMode = false,
  demoCameraIds,
  onClose,
  onActivated,
}: RuleActivationDialogProps) {
  const { t, i18n } = useTranslation();
  const orgId = useAuthStore((s) => s.orgId);
  const siteId = useAuthStore((s) => s.siteId);
  const { data: allCameras = [] } = useCameras();
  const cameras = useMemo(() => {
    if (!demoMode) return allCameras;
    if (demoCameraIds?.length) {
      return allCameras.filter((c) => demoCameraIds.includes(c.id));
    }
    return allCameras.filter((c) => {
      const meta = c.metadata as Record<string, unknown> | undefined;
      const isVirtual = meta?.virtual === true;
      const isDemo = meta?.demo === true;
      if (isDemo) return true;
      if (!isVirtual) return true;
      return false;
    });
  }, [allCameras, demoMode, demoCameraIds]);
  const isEdit = Boolean(existingRule);

  const activeTemplate = useMemo(() => {
    if (template) return template;
    if (!existingRule) return null;
    return {
      id: String((existingRule.definition?.bindings as Record<string, unknown>)?.template_id ?? 'custom'),
      name: existingRule.name,
      category: existingRule.category ?? 'custom',
      severity: existingRule.severity ?? 'medium',
      definition: existingRule.definition ?? {},
    } as RuleCatalogTemplate;
  }, [template, existingRule]);

  const schema = useMemo(
    () => (activeTemplate ? resolveConfigSchema(activeTemplate) : { fields: [] }),
    [activeTemplate],
  );

  const [values, setValues] = useState<Record<string, unknown>>({});
  const [zones, setZones] = useState<BackendZone[]>([]);
  const [lines, setLines] = useState<BackendLine[]>([]);
  const [watchlists, setWatchlists] = useState<SurveillanceList[]>([]);
  const [plateLists, setPlateLists] = useState<SurveillanceList[]>([]);
  const [loadingSpatial, setLoadingSpatial] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedbackCamera, setFeedbackCamera] = useState<{id:string;name:string}|null>(null);
  const [error, setError] = useState('');
  const [step, setStep] = useState<1 | 2 | 3 | 4>(initialStep);
  const [step3Tab, setStep3Tab] = useState<'actions' | 'evidence' | 'notifications'>('actions');
  const [ruleName, setRuleName] = useState('');
  const [conditionTree, setConditionTree] = useState<ConditionNode>(createGroup('AND', [createLeaf()]));
  const [selectedActions, setSelectedActions] = useState<string[]>(defaultActionsSelection());
  const [actionSeverity, setActionSeverity] = useState('medium');
  const [notifyEmail, setNotifyEmail] = useState('');
  const [evidencePolicy, setEvidencePolicy] = useState<EvidencePolicy>(DEFAULT_EVIDENCE_POLICY);
  const [enableWebhook, setEnableWebhook] = useState(false);
  const [webhookPreset, setWebhookPreset] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [guideRailCollapsed, setGuideRailCollapsed] = useState(false);

  const cameraId = String(values.camera_id ?? '');

  useEffect(() => {
    if (activeTemplate) void loadRuleGuides();
  }, [activeTemplate?.id]);

  const templateEventHint = useMemo(
    () => templatePrimaryEventType(activeTemplate?.definition),
    [activeTemplate],
  );

  const spatialContext = useMemo(
    () => ({ zones, lines, loadingSpatial }),
    [zones, lines, loadingSpatial],
  );

  useEffect(() => {
    if (!activeTemplate) return;
    const defaults = getSchemaDefaults(schema);
    const bindings = (existingRule?.definition?.bindings ?? {}) as Record<string, unknown>;
    const demoCam =
      cameras.find((c) => {
        const meta = c.metadata as Record<string, unknown> | undefined;
        return meta?.demo === true || meta?.demo === 'true';
      }) ?? cameras[0];
    setValues({
      ...defaults,
      camera_id: bindings.camera_id ?? demoCam?.id ?? '',
      zone_name: bindings.zone_name ?? '',
      zone_name_2: bindings.zone_name_2 ?? '',
      line_name: bindings.line_name ?? '',
      duration_seconds: bindings.duration_seconds ?? defaults.duration_seconds ?? 120,
      speed_kmh: bindings.speed_kmh ?? defaults.speed_kmh ?? 50,
      watchlist_id: bindings.watchlist_id ?? '',
      plate_list_id: bindings.plate_list_id ?? '',
      class_filter: bindings.class_filter ?? defaults.class_filter ?? 'person',
      direction: bindings.direction ?? defaults.direction ?? 'both',
      schedule: bindings.schedule ?? defaults.schedule,
    });
    setRuleName(existingRule?.name ?? activeTemplate.name);
    const cond = (existingRule?.definition?.condition ?? activeTemplate.definition?.condition) as ConditionNode | undefined;
    setConditionTree(cloneCondition(cond) ?? createGroup('AND', [createLeaf()]));
    setStep(initialStep);
    setStep3Tab(initialStep === 3 ? 'evidence' : 'actions');
    const defActions = (existingRule?.definition?.actions ?? activeTemplate.definition?.actions) as Array<{ type: string; config?: Record<string, unknown> }> | undefined;
    setSelectedActions(actionsFromRule(defActions));
    const sev = defActions?.find((a) => a.type === 'alert')?.config?.severity;
    setActionSeverity(String(sev ?? activeTemplate.severity ?? 'medium'));
    const ev = (existingRule?.definition?.evidence ?? {}) as Partial<EvidencePolicy>;
    setEvidencePolicy({ ...DEFAULT_EVIDENCE_POLICY, ...ev, images: ev.images ?? DEFAULT_EVIDENCE_POLICY.images });
    const wh = defActions?.find((a) => a.type === 'webhook');
    setEnableWebhook(Boolean(wh));
    setWebhookUrl(String(wh?.config?.url ?? ''));
    setWebhookPreset(String(wh?.config?.preset ?? ''));
    setNotifyEmail(String(defActions?.find((a) => a.type === 'notify')?.config?.to ?? ''));
    setError('');
  }, [activeTemplate, schema, cameras, existingRule, initialStep]);

  useEffect(() => {
    if (!orgId || isEdit) return;
    void orgApi.get(orgId).then((r) => {
      const raw = (r.data.notification_prefs as Record<string, unknown> | undefined)?.evidence_defaults as Partial<EvidencePolicy> | undefined;
      if (raw) setEvidencePolicy(normalizeEvidencePolicy(raw));
    }).catch(() => undefined);
  }, [orgId, isEdit]);

  useEffect(() => {
    if (!orgId || !cameraId) return;
    setLoadingSpatial(true);
    Promise.all([
      zonesApi.list(orgId, cameraId),
      zonesApi.listLines(orgId, cameraId),
      identityApi.list(orgId, 'face_watchlist'),
      identityApi.list(orgId, 'plate_block'),
    ])
      .then(([zRes, lRes, wRes, pRes]) => {
        setZones((Array.isArray(zRes.data) ? zRes.data : []) as BackendZone[]);
        setLines((Array.isArray(lRes.data) ? lRes.data : []) as BackendLine[]);
        setWatchlists(Array.isArray(wRes.data) ? wRes.data : []);
        setPlateLists(Array.isArray(pRes.data) ? pRes.data : []);
      })
      .catch(() => {
        setZones([]);
        setLines([]);
        setWatchlists([]);
        setPlateLists([]);
      })
      .finally(() => setLoadingSpatial(false));
  }, [orgId, cameraId]);

  const sortedFields = useMemo(() => {
    const order = ['camera_id', 'class_filter', 'zone_name', 'line_name', 'duration_seconds'];
    return [...schema.fields].sort((a, b) => {
      const ai = order.indexOf(a.key);
      const bi = order.indexOf(b.key);
      const ao = ai === -1 ? 99 : ai;
      const bo = bi === -1 ? 99 : bi;
      return ao - bo;
    });
  }, [schema.fields]);

  const activationCfg = useMemo(() => activationConfigFromValues(values), [values]);

  const narrativeContext = useMemo(
    () => ({
      zoneName: activationCfg.zoneName,
      lineName: activationCfg.lineName,
      classFilter: activationCfg.classFilter,
      cameraName: cameras.find((c) => c.id === cameraId)?.name,
    }),
    [activationCfg, cameras, cameraId],
  );

  const resolveActionKeys = () => {
    let keys = [...selectedActions];
    if (enableWebhook && !keys.some((k) => k.startsWith('webhook:'))) {
      keys.push('webhook:Webhook / n8n / Make');
    }
    if (notifyEmail && !keys.some((k) => k.startsWith('notify:'))) {
      keys.push('notify:E-mail');
    }
    return keys;
  };

  const buildDefinition = (cond: ConditionNode) => {
    if (!activeTemplate) return {};
    const cfg = {
      ...activationCfg,
      actions: buildActionsPayload(
        resolveActionKeys(),
        actionSeverity,
        notifyEmail || undefined,
        enableWebhook ? { url: webhookUrl || undefined, preset: webhookPreset || undefined } : undefined,
      ),
    };
    const definition = buildConfiguredDefinition(activeTemplate, cfg, cond, { demo: demoMode });
    definition.evidence = evidencePolicy;
    return definition;
  };

  const previewSummary = useMemo(() => {
    const parts: string[] = [];
    const cls = values.class_filter ? String(values.class_filter) : '';
    const zone = values.zone_name ? String(values.zone_name) : '';
    const dur = values.duration_seconds != null ? Number(values.duration_seconds) : null;
    if (cls) parts.push(t('rules.studio.previewClass', { cls: classLabel(cls) }));
    if (zone) parts.push(t('rules.studio.previewZone', { zone }));
    if (dur != null && !Number.isNaN(dur)) parts.push(t('rules.studio.previewDuration', { seconds: dur }));
    return parts.join(' · ');
  }, [values, t]);

  const previewRule: Rule | null = useMemo(() => {
    if (!activeTemplate) return null;
    const def = buildDefinition(conditionTree);
    return {
      id: existingRule?.id ?? 'preview',
      name: ruleName || activeTemplate.name,
      enabled: true,
      category: activeTemplate.category,
      severity: activeTemplate.severity,
      definition: def,
      actions: def.actions as Rule['actions'],
    } as Rule;
  }, [activeTemplate, activationCfg, conditionTree, selectedActions, actionSeverity, notifyEmail, evidencePolicy, enableWebhook, webhookUrl, webhookPreset, ruleName, existingRule]);

  if (!activeTemplate) return null;

  const setField = (key: string, val: unknown) => setValues((v) => ({ ...v, [key]: val }));

  const validate = (): string | null => {
    const tplId = activeTemplate?.id ?? '';
    if (SPATIAL_TEMPLATES_REQUIRING_CLASS.has(tplId) && !values.class_filter) {
      return t('rules.studio.classRequired');
    }
    for (const f of schema.fields) {
      if (!f.required) continue;
      const v = values[f.key];
      if (v === undefined || v === null || v === '') {
        return `Le champ « ${f.label ?? f.key} » est requis.`;
      }
    }
    return null;
  };

  const submit = async () => {
    if (!orgId) return;
    const err = validate();
    if (err) {
      setError(err);
      return;
    }
    const condErr = validateConditionTree(conditionTree);
    if (condErr) {
      setError(condErr);
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const syncedCond = ensureSpatialConditions(conditionTree, activationCfg);
      const definition = buildDefinition(syncedCond);
      const name = ruleName.trim() || activeTemplate.name;
      if (isEdit && existingRule) {
        await rulesApi.update(orgId, existingRule.id, { definition, name });
      } else {
        await rulesApi.create(orgId, {
          name,
          definition,
          priority: 10,
          description: `Activée: cam=${activationCfg.cameraId}${activationCfg.zoneName ? ` zone=${activationCfg.zoneName}` : ''}${activationCfg.lineName ? ` ligne=${activationCfg.lineName}` : ''}`,
          ...(siteId ? { site_id: siteId } : {}),
        });
      }
      onActivated();
      // Show post-activation feedback instead of closing immediately
      const cam = cameras.find((c) => c.id === cameraId);
      setFeedbackCamera(cam ? { id: cam.id, name: cam.name } : { id: cameraId, name: cameraId });
      setShowFeedback(true);
    } catch {
      setError(t('rules.studio.saveError'));
    } finally {
      setSubmitting(false);
    }
  };

  const actionsOnlyContent = (
    <div className="space-y-4">
      <p className="text-sm font-medium">{t('rules.studio.actionsTitle')}</p>
      {Object.entries(ACTION_FAMILIES).map(([familyId, familyLabel]) => {
        const acts = executedActionsOnly().filter((a) => a.family === familyId);
        if (acts.length === 0) return null;
        return (
          <div key={familyId}>
            <p className="text-xs font-semibold text-cv-muted uppercase tracking-wide mb-2">{familyLabel}</p>
            <div className="space-y-2">
              {acts.map((act) => {
                const key = actionKey(act);
                return (
                  <label key={key} className="flex items-start gap-3 p-3 rounded-lg border border-cv-border cursor-pointer hover:border-cv-accent/30 transition-colors">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={selectedActions.includes(key)}
                      onChange={(e) => {
                        setSelectedActions((prev) =>
                          e.target.checked ? [...prev, key] : prev.filter((item) => item !== key),
                        );
                      }}
                    />
                    <div>
                      <p className="text-sm font-medium">{act.label}</p>
                      <p className="text-xs text-cv-muted">{act.description}</p>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        );
      })}
      {selectedActions.some((k) => k.startsWith('alert:')) && (
        <div>
          <label className="cv-label flex items-center gap-1.5">
            {t('rules.studio.alertSeverity')}
            <InfoTip content="Faible : notification discrète. Moyenne : badge visible + son. Élevée : bandeau rouge. Critique : alerte sonore continue + notification push — à réserver aux situations urgentes." />
          </label>
          <ExplanatorySelect
            className="w-full"
            value={actionSeverity}
            onChange={setActionSeverity}
            options={buildSeverityOptions(i18n.language.startsWith('en') ? 'en' : 'fr', {
              low: t('rules.severity.low'),
              medium: t('rules.severity.medium'),
              high: t('rules.severity.high'),
              critical: t('rules.severity.critical'),
            })}
            searchable={false}
          />
        </div>
      )}
    </div>
  );

  const actionsStepContent = (
    <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
      <div className="shrink-0 pb-3 border-b border-cv-border/40 bg-cv-surface/95 backdrop-blur-md -mx-1 px-1">
        <SegmentedTabs
          tabs={[
            { id: 'actions', label: 'Actions' },
            { id: 'evidence', label: 'Preuves' },
            { id: 'notifications', label: 'Notifications' },
          ]}
          value={step3Tab}
          onChange={(id) => setStep3Tab(id as 'actions' | 'evidence' | 'notifications')}
        />
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto pt-4 space-y-4 pr-1">
        {step3Tab === 'actions' && actionsOnlyContent}
        {step3Tab === 'evidence' && (
          <div id="evidence-policy-panel">
            <p className="text-xs text-cv-muted mb-2">Clip de preuve automatique (H.264, {evidencePolicy.clip_seconds} s par défaut) — distinct de l&apos;enregistrement long ffmpeg.</p>
            <EvidencePolicyPanel policy={evidencePolicy} onChange={setEvidencePolicy} />
          </div>
        )}
        {step3Tab === 'notifications' && (
          <OutputChannelsPanel
            notifyEmail={notifyEmail}
            onNotifyEmail={setNotifyEmail}
            webhookPreset={webhookPreset}
            onWebhookPreset={setWebhookPreset}
            webhookUrl={webhookUrl}
            onWebhookUrl={setWebhookUrl}
            enableWebhook={enableWebhook}
            onEnableWebhook={setEnableWebhook}
          />
        )}
      </div>
    </div>
  );

  const goNext = () => {
    if (step === 1) {
      const err = validate();
      if (err) { setError(err); return; }
      setError('');
      setConditionTree(ensureSpatialConditions(conditionTree, activationCfg));
      setStep(2);
    } else if (step === 2) {
      const condErr = validateConditionTree(conditionTree);
      if (condErr) { setError(condErr); return; }
      setError('');
      setStep(3);
    } else if (step === 3) {
      setError('');
      setStep(4);
    }
  };

  const stepLabels = STEP_LABELS_KEYS.map((k) => t(`rules.studio.steps.${k}`, k));
  const wizardSteps = [
    { n: 1, label: stepLabels[0], icon: MapPin },
    { n: 2, label: stepLabels[1], icon: GitBranch },
    { n: 3, label: stepLabels[2], icon: Zap },
    { n: 4, label: stepLabels[3], icon: Check },
  ];

  if (showFeedback && activeTemplate) {
    return (
      <Modal
        open
        onClose={() => { setShowFeedback(false); onClose(); }}
        title={activeTemplate.name}
        maxWidth="sm"
      >
        <RuleActivationFeedback
          ruleName={ruleName || activeTemplate.name}
          cameraId={feedbackCamera?.id ?? cameraId}
          cameraName={feedbackCamera?.name}
          zoneName={activationCfg.zoneName}
          lineName={activationCfg.lineName}
          onClose={() => { setShowFeedback(false); onClose(); }}
        />
      </Modal>
    );
  }

  return (
    <Modal
      open
      onClose={onClose}
      maxWidth="studio"
      className="max-h-[92vh] overflow-hidden flex flex-col"
      footer={
        <>
          {step > 1 && (
            <button type="button" className="cv-btn-secondary" onClick={() => setStep((step - 1) as 1 | 2 | 3 | 4)}>
              {t('common.back')}
            </button>
          )}
          {step < 4 ? (
            <button type="button" className="cv-btn-primary" onClick={goNext}>
              {t('common.next')}
            </button>
          ) : (
            <button type="button" className="cv-btn-primary" disabled={submitting} onClick={() => void submit()}>
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              {isEdit ? t('common.save') : t('rules.studio.activate')}
            </button>
          )}
        </>
      }
    >
      <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
      <div className="flex items-start justify-between gap-3 mb-4 shrink-0">
        <div>
          <p className="text-xs uppercase tracking-wide text-cv-accent font-semibold mb-1">
            {isEdit ? t('rules.studio.editTitle') : t('rules.studio.createTitle')}
          </p>
          <h2 className="text-lg font-display font-semibold">{activeTemplate.name}</h2>
          <p className="text-xs text-cv-muted mt-1">
            {stepLabels[step - 1]} · {t(`rules.catalogCategory.${activeTemplate.category}`, activeTemplate.category)}
          </p>
        </div>
        <button type="button" onClick={onClose} className="cv-btn-ghost p-2 rounded-lg" aria-label={t('common.cancel')}>
          <X className="w-4 h-4" />
        </button>
      </div>

      <WizardSteps steps={wizardSteps} current={step} className="mb-4 shrink-0" />
      <WizardStepContext step={step} template={activeTemplate as { name: string; partial_status?: string; partial_reason_fr?: string; category?: string }} t={t} />

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(240px,280px)_1fr] gap-5 flex-1 min-h-0 overflow-hidden">
        <RuleStudioGuideRail
          templateId={activeTemplate.id}
          category={activeTemplate.category}
          step={step}
          collapsed={guideRailCollapsed}
          onToggleCollapse={() => setGuideRailCollapsed((v) => !v)}
        />
        <div
          className={
            step === 3
              ? 'flex flex-col flex-1 min-h-0 overflow-hidden pr-1'
              : 'flex flex-col flex-1 min-h-0 overflow-y-auto overscroll-contain pr-1 space-y-4 pb-4'
          }
        >
      {step === 3 ? (
        actionsStepContent
      ) : (
        <>
      {activeTemplate.tutorial && step === 1 && typeof activeTemplate.tutorial === 'string' && (
        <GuideIllustration
          variant="rules"
          imageRole="howItWorks"
          title={t('rules.guide.wizardTitle')}
          caption={activeTemplate.tutorial}
          className="mb-4"
        />
      )}

      {step === 1 && !!activeTemplate.definition?.pipeline && (
        <div className="mb-4 rounded-xl border border-cv-accent/30 bg-cv-accent/5 p-4 space-y-2">
          <p className="text-sm font-semibold text-cv-accent">
            {t('rules.pipeline.title', { defaultValue: 'Pipeline multi-étapes' })}
          </p>
          <p className="text-xs text-cv-muted">
            {t('rules.pipeline.legend', {
              defaultValue: 'Déclencheur → enrichissements (OCR, vitesse) → condition → preuves',
            })}
          </p>
          <ol className="text-xs text-cv-muted list-decimal list-inside space-y-1">
            {(Array.isArray((activeTemplate.tutorial as unknown as { steps?: string[] })?.steps)
              ? (activeTemplate.tutorial as unknown as { steps: string[] }).steps
              : [
                  t('rules.pipeline.stepZone', { defaultValue: 'Dessinez la zone sur la voie' }),
                  t('rules.pipeline.stepClass', { defaultValue: 'Filtrez la classe véhicule' }),
                  t('rules.pipeline.stepEnrich', { defaultValue: 'OCR plaque + vitesse dans la zone' }),
                  t('rules.pipeline.stepCondition', { defaultValue: 'Définissez la condition (ex. vitesse)' }),
                  t('rules.pipeline.stepProofs', { defaultValue: 'Configurez preuves et notifications' }),
                ]
            ).map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </div>
      )}

      <div className="space-y-4">
          {step === 1 && (
            <>
              <div>
                <label className="cv-label">{t('rules.studio.ruleName')}</label>
                <input
                  className="cv-input w-full"
                  value={ruleName}
                  onChange={(e) => setRuleName(e.target.value)}
                />
              </div>
              {sortedFields.map((field) => (
                <SchemaField
                  key={field.key}
                  field={field}
                  value={values[field.key]}
                  onChange={(v) => setField(field.key, v)}
                  cameras={cameras}
                  zones={zones}
                  lines={lines}
                  watchlists={watchlists}
                  plateLists={plateLists}
                  loadingSpatial={loadingSpatial}
                />
              ))}
            </>
          )}
          {step === 2 && (
            <div className="space-y-4">
              <ConditionTreeVisualEditor
                value={conditionTree}
                onChange={setConditionTree}
                narrativeContext={narrativeContext}
                spatialContext={spatialContext}
                templateEventHint={templateEventHint}
              />
              <ConditionLogicSimulator tree={conditionTree} />
              <ConditionTreeTechnicalMirror value={conditionTree} />
            </div>
          )}
          {step === 4 && previewRule && (
            <div className="space-y-3">
              <p className="text-sm font-medium">{t('rules.studio.previewTitle')}</p>
              {previewSummary && (
                <p className="text-sm text-cv-muted bg-cv-border/20 rounded-lg p-3 border border-cv-border">
                  {narrateConditionSummary(conditionTree, t, narrativeContext)}
                </p>
              )}
              {(() => {
                const previewCam = cameras.find((c) => c.id === cameraId);
                const streamSrc = previewCam ? go2rtcStreamSrc(previewCam) : undefined;
                return streamSrc ? (
                  <div className="rounded-xl overflow-hidden border border-cv-accent/20 bg-black/40 aspect-video w-full max-h-40 relative">
                    <Go2RtcPlayer src={streamSrc} bare className="w-full h-full object-contain" />
                    <span className="absolute top-2 left-2 text-[10px] bg-cv-deep/70 text-cv-accent px-2 py-0.5 rounded font-mono">
                      {previewCam?.name}
                    </span>
                  </div>
                ) : previewCam ? (
                  <div className="rounded-xl border border-cv-border/40 bg-cv-deep/20 p-3 text-xs text-cv-muted flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-cv-muted/40 shrink-0" />
                    {previewCam.name} — aperçu vidéo non disponible (go2rtc non actif)
                  </div>
                ) : null;
              })()}
              <div className="p-3 rounded-lg border border-cv-border/60 bg-cv-deep/20 text-xs">
                <p className="font-medium text-sm mb-1">Preuves configurées</p>
                <p className="text-cv-muted">
                  Clip {evidencePolicy.clip_seconds}s · {evidencePolicy.images.length} image(s)
                  {evidencePolicy.draw_bbox ? ' · cadre bbox' : ''}
                  {!evidencePolicy.enabled ? ' · désactivées' : ''}
                </p>
              </div>
              <RuleFlowBuilder rule={previewRule} />
            </div>
          )}
        </div>

        </>
      )}

        {error && (
          <p className="mt-4 text-sm text-red-500 bg-red-500/10 border border-red-500/30 rounded-lg p-3 shrink-0">{error}</p>
        )}
        </div>
      </div>
      </div>
    </Modal>
  );
}

function SchemaField({
  field,
  value,
  onChange,
  cameras,
  zones,
  lines,
  watchlists,
  plateLists,
  loadingSpatial,
}: {
  field: ConfigSchemaField;
  value: unknown;
  onChange: (v: unknown) => void;
  cameras: Array<{ id: string; name: string }>;
  zones: BackendZone[];
  lines: BackendLine[];
  watchlists: SurveillanceList[];
  plateLists: SurveillanceList[];
  loadingSpatial: boolean;
}) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith('en') ? 'en' : 'fr';
  const label = field.label ?? field.key;
  const choose = t('common.choose', { defaultValue: '— Choisir —' });

  return (
    <div>
      <label className="cv-label flex items-center gap-1.5">
        {label}
        {field.required && <span className="text-red-500">*</span>}
        {field.hint && <InfoTip content={field.hint} />}
      </label>

      {field.type === 'camera' && (
        <ExplanatorySelect
          className="w-full"
          value={String(value ?? '')}
          onChange={(v) => onChange(v)}
          options={buildCameraOptions(cameras, lang)}
          placeholder={choose}
          searchable={cameras.length > 8}
        />
      )}

      {field.type === 'zone' && (
        loadingSpatial ? (
          <p className="text-xs text-cv-muted">{t('common.loading')}</p>
        ) : zones.length === 0 ? (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            Aucune zone. <Link to="/zones" className="underline text-cv-accent">Éditeur de zones</Link>
          </p>
        ) : (
          <ExplanatorySelect
            className="w-full"
            value={String(value ?? '')}
            onChange={(v) => onChange(v)}
            options={buildZoneOptions(zones, lang)}
            placeholder={choose}
            searchable={zones.length > 8}
          />
        )
      )}

      {field.type === 'line' && (
        loadingSpatial ? (
          <p className="text-xs text-cv-muted">{t('common.loading')}</p>
        ) : lines.length === 0 ? (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            Aucune ligne. <Link to="/zones" className="underline text-cv-accent">Éditeur de zones</Link>
          </p>
        ) : (
          <ExplanatorySelect
            className="w-full"
            value={String(value ?? '')}
            onChange={(v) => onChange(v)}
            options={buildLineOptions(lines, lang)}
            placeholder={choose}
            searchable={lines.length > 8}
          />
        )
      )}

      {field.type === 'number' || field.type === 'threshold' ? (
        <input
          type="number"
          min={field.min}
          max={field.max}
          className="cv-input w-full"
          value={value != null ? Number(value) : ''}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      ) : null}

      {field.type === 'watchlist' && (
        watchlists.length === 0 ? (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            <Settings2 className="w-3.5 h-3.5 inline mr-1" />
            <Link to="/settings" className="underline text-cv-accent">Paramètres → Identité</Link>
          </p>
        ) : (
          <ExplanatorySelect
            className="w-full"
            value={String(value ?? '')}
            onChange={(v) => onChange(v)}
            options={buildSurveillanceListOptions(watchlists, lang, 'watchlist')}
            placeholder={choose}
            searchable={watchlists.length > 8}
          />
        )
      )}

      {field.type === 'plate_list' && (
        plateLists.length === 0 ? (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            <Link to="/settings" className="underline text-cv-accent">Créer une liste de plaques</Link>
          </p>
        ) : (
          <ExplanatorySelect
            className="w-full"
            value={String(value ?? '')}
            onChange={(v) => onChange(v)}
            options={buildSurveillanceListOptions(plateLists, lang, 'plate_list')}
            placeholder={choose}
            searchable={plateLists.length > 8}
          />
        )
      )}

      {field.type === 'class_filter' && (
        <ClassFilterPicker
          value={String(value ?? field.default ?? '')}
          onChange={onChange}
          required={field.required}
        />
      )}

      {field.type === 'enum' && (
        <ExplanatorySelect
          className="w-full"
          value={String(value ?? field.default ?? '')}
          onChange={(v) => onChange(v)}
          options={buildSchemaEnumOptions(field.options ?? [], lang, field.key)}
          placeholder={choose}
          searchable={(field.options ?? []).length > 8}
        />
      )}

      {field.type === 'schedule' && (
        <ScheduleField value={value as ScheduleValue | undefined} onChange={onChange} />
      )}
    </div>
  );
}

interface ScheduleValue {
  from: string;
  to: string;
  allDay?: boolean;
}

function ScheduleField({
  value,
  onChange,
}: {
  value: ScheduleValue | undefined;
  onChange: (v: unknown) => void;
}) {
  const { t } = useTranslation();
  const current = value ?? { from: '06:00', to: '22:00', allDay: false };

  const update = (patch: Partial<ScheduleValue>) => {
    onChange({ ...current, ...patch });
  };

  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          className="rounded"
          checked={Boolean(current.allDay)}
          onChange={(e) => update({ allDay: e.target.checked })}
        />
        <span className="text-sm">{t('rules.studio.scheduleAllDay')}</span>
      </label>
      {!current.allDay && (
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-cv-muted" />
            <span className="text-xs text-cv-muted">{t('rules.studio.scheduleFrom')}</span>
            <input
              type="time"
              className="cv-input py-1 w-28 text-sm"
              value={current.from}
              onChange={(e) => update({ from: e.target.value })}
            />
          </div>
          <span className="text-cv-muted text-xs">–</span>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-cv-muted">{t('rules.studio.scheduleTo')}</span>
            <input
              type="time"
              className="cv-input py-1 w-28 text-sm"
              value={current.to}
              onChange={(e) => update({ to: e.target.value })}
            />
          </div>
        </div>
      )}
      <p className="text-xs text-cv-muted">{t('rules.studio.scheduleHint')}</p>
    </div>
  );
}
