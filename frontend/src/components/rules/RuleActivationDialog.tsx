import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Settings2, X } from 'lucide-react';
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
import ConditionTreeEditor from '@/components/rules/ConditionTreeEditor';
import RuleFlowBuilder from '@/components/rules/RuleFlowBuilder';
import {
  cloneCondition,
  createGroup,
  createLeaf,
  type ConditionNode,
  validateConditionTree,
} from '@/lib/conditionTree';
import InfoTip from '@/components/ui/InfoTip';
import ModalPortal from '@/components/ui/ModalPortal';
import { useAuthStore } from '@/stores/authStore';
import { useCameras } from '@/hooks/api/queries';
import type { ConfigSchemaField, Rule, RuleCatalogTemplate } from '@/types';

interface BackendLine {
  id: string;
  name: string;
}

interface RuleActivationDialogProps {
  template: RuleCatalogTemplate | null;
  existingRule?: Rule | null;
  onClose: () => void;
  onActivated: () => void;
}

export default function RuleStudioDialog({
  template,
  existingRule,
  onClose,
  onActivated,
}: RuleActivationDialogProps) {
  const { t } = useTranslation();
  const orgId = useAuthStore((s) => s.orgId);
  const siteId = useAuthStore((s) => s.siteId);
  const { data: cameras = [] } = useCameras();
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
  const [error, setError] = useState('');
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [ruleName, setRuleName] = useState('');
  const [conditionTree, setConditionTree] = useState<ConditionNode>(createGroup('AND', [createLeaf()]));
  const [selectedActions, setSelectedActions] = useState<string[]>(defaultActionsSelection());
  const [actionSeverity, setActionSeverity] = useState('medium');
  const [notifyEmail, setNotifyEmail] = useState('');

  const cameraId = String(values.camera_id ?? '');

  useEffect(() => {
    if (!activeTemplate) return;
    const defaults = getSchemaDefaults(schema);
    const bindings = (existingRule?.definition?.bindings ?? {}) as Record<string, unknown>;
    const virtual =
      cameras.find((c) => c.name.toLowerCase().includes('virtual') || c.name.toLowerCase().includes('benedicte')) ??
      cameras[0];
    setValues({
      ...defaults,
      camera_id: bindings.camera_id ?? virtual?.id ?? '',
      zone_name: bindings.zone_name ?? '',
      line_name: bindings.line_name ?? '',
      duration_seconds: bindings.duration_seconds ?? defaults.duration_seconds ?? 120,
      speed_kmh: bindings.speed_kmh ?? defaults.speed_kmh ?? 50,
      watchlist_id: bindings.watchlist_id ?? '',
      plate_list_id: bindings.plate_list_id ?? '',
      class_filter: bindings.class_filter ?? defaults.class_filter ?? 'person',
      direction: bindings.direction ?? defaults.direction ?? 'both',
    });
    setRuleName(existingRule?.name ?? activeTemplate.name);
    const cond = (existingRule?.definition?.condition ?? activeTemplate.definition?.condition) as ConditionNode | undefined;
    setConditionTree(cloneCondition(cond) ?? createGroup('AND', [createLeaf()]));
    setStep(1);
    const defActions = (existingRule?.definition?.actions ?? activeTemplate.definition?.actions) as Array<{ type: string; config?: Record<string, unknown> }> | undefined;
    setSelectedActions(actionsFromRule(defActions));
    const sev = defActions?.find((a) => a.type === 'alert')?.config?.severity;
    setActionSeverity(String(sev ?? activeTemplate.severity ?? 'medium'));
    setError('');
  }, [activeTemplate, schema, cameras, existingRule]);

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
    const cfg = {
      ...activationCfg,
      actions: buildActionsPayload(selectedActions, actionSeverity, notifyEmail || undefined),
    };
    const def = buildConfiguredDefinition(activeTemplate, cfg, conditionTree);
    return {
      id: existingRule?.id ?? 'preview',
      name: ruleName || activeTemplate.name,
      enabled: true,
      category: activeTemplate.category,
      severity: activeTemplate.severity,
      definition: def,
      actions: def.actions as Rule['actions'],
    } as Rule;
  }, [activeTemplate, activationCfg, conditionTree, selectedActions, actionSeverity, notifyEmail, ruleName, existingRule]);

  if (!activeTemplate) return null;

  const setField = (key: string, val: unknown) => setValues((v) => ({ ...v, [key]: val }));

  const validate = (): string | null => {
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
      const cfg = {
        ...activationCfg,
        actions: buildActionsPayload(selectedActions, actionSeverity, notifyEmail || undefined),
      };
      const syncedCond = ensureSpatialConditions(conditionTree, cfg);
      const definition = buildConfiguredDefinition(activeTemplate, cfg, syncedCond);
      const name = ruleName.trim() || activeTemplate.name;
      if (isEdit && existingRule) {
        await rulesApi.update(orgId, existingRule.id, { definition, name });
      } else {
        await rulesApi.create(orgId, {
          name,
          definition,
          priority: 10,
          description: `Activée: cam=${cfg.cameraId}${cfg.zoneName ? ` zone=${cfg.zoneName}` : ''}${cfg.lineName ? ` ligne=${cfg.lineName}` : ''}`,
          ...(siteId ? { site_id: siteId } : {}),
        });
      }
      onActivated();
      onClose();
    } catch {
      setError(t('rules.studio.saveError'));
    } finally {
      setSubmitting(false);
    }
  };

  const actionsStepContent = (
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
          <label className="cv-label">{t('rules.studio.alertSeverity')}</label>
          <select className="cv-input w-full" value={actionSeverity} onChange={(e) => setActionSeverity(e.target.value)}>
            <option value="low">{t('rules.severity.low')}</option>
            <option value="medium">{t('rules.severity.medium')}</option>
            <option value="high">{t('rules.severity.high')}</option>
            <option value="critical">{t('rules.severity.critical')}</option>
          </select>
        </div>
      )}
      {selectedActions.some((k) => k.startsWith('notify:')) && (
        <div>
          <label className="cv-label">{t('rules.studio.notifyEmail')}</label>
          <input
            type="email"
            className="cv-input w-full"
            placeholder="alertes@exemple.cd"
            value={notifyEmail}
            onChange={(e) => setNotifyEmail(e.target.value)}
          />
        </div>
      )}
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

  return (
    <ModalPortal>
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="cv-card w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6" role="dialog">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-cv-accent font-semibold mb-1">
              {isEdit ? t('rules.studio.editTitle') : t('rules.studio.createTitle')}
            </p>
            <h2 className="text-lg font-display font-semibold">{activeTemplate.name}</h2>
            <p className="text-xs text-cv-muted mt-1">
              {t('rules.studio.step', { step, total: 4 })} · {activeTemplate.category} · {activeTemplate.severity}
            </p>
          </div>
          <button type="button" onClick={onClose} className="cv-btn-ghost p-2 rounded-lg" aria-label={t('common.cancel')}>
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex gap-1 mb-4">
          {[1, 2, 3, 4].map((s) => (
            <div
              key={s}
              className={`h-1 flex-1 rounded-full transition-colors ${step >= s ? 'bg-cv-accent' : 'bg-cv-border'}`}
            />
          ))}
        </div>

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
            <ConditionTreeEditor value={conditionTree} onChange={setConditionTree} />
          )}
          {step === 3 && actionsStepContent}
          {step === 4 && previewRule && (
            <div className="space-y-3">
              <p className="text-sm font-medium">{t('rules.studio.previewTitle')}</p>
              {previewSummary && (
                <p className="text-sm text-cv-muted bg-cv-border/20 rounded-lg p-3 border border-cv-border">
                  {t('rules.studio.previewSummary', { details: previewSummary })}
                </p>
              )}
              <RuleFlowBuilder rule={previewRule} />
            </div>
          )}
        </div>

        {error && (
          <p className="mt-4 text-sm text-red-500 bg-red-500/10 border border-red-500/30 rounded-lg p-3">{error}</p>
        )}

        <div className="flex gap-3 mt-6">
          {step > 1 && (
            <button type="button" onClick={() => setStep((s) => (s - 1) as 1 | 2 | 3 | 4)} className="cv-btn-secondary">
              {t('onboarding.prev')}
            </button>
          )}
          <button type="button" onClick={onClose} className="cv-btn-secondary flex-1">
            {t('common.cancel')}
          </button>
          {step < 4 ? (
            <button type="button" onClick={goNext} className="cv-btn-primary flex-1">
              {t('onboarding.next')}
            </button>
          ) : (
            <button type="button" disabled={submitting} onClick={() => void submit()} className="cv-btn-primary flex-1">
              {submitting ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : t('common.save')}
            </button>
          )}
        </div>
      </div>
    </div>
    </ModalPortal>
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
  const label = field.label ?? field.key;

  return (
    <div>
      <label className="cv-label flex items-center gap-1.5">
        {label}
        {field.required && <span className="text-red-500">*</span>}
        {field.hint && <InfoTip content={field.hint} />}
      </label>

      {field.type === 'camera' && (
        <select className="cv-input w-full" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}>
          <option value="">— Choisir —</option>
          {cameras.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      )}

      {field.type === 'zone' && (
        loadingSpatial ? (
          <p className="text-xs text-cv-muted">Chargement…</p>
        ) : zones.length === 0 ? (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            Aucune zone. <Link to="/zones" className="underline text-cv-accent">Éditeur de zones</Link>
          </p>
        ) : (
          <select className="cv-input w-full" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}>
            <option value="">— Choisir —</option>
            {zones.map((z) => (
              <option key={z.id} value={z.name}>{z.name}</option>
            ))}
          </select>
        )
      )}

      {field.type === 'line' && (
        loadingSpatial ? (
          <p className="text-xs text-cv-muted">Chargement…</p>
        ) : lines.length === 0 ? (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            Aucune ligne. <Link to="/zones" className="underline text-cv-accent">Éditeur de zones</Link>
          </p>
        ) : (
          <select className="cv-input w-full" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}>
            <option value="">— Choisir —</option>
            {lines.map((l) => (
              <option key={l.id} value={l.name}>{l.name}</option>
            ))}
          </select>
        )
      )}

      {(field.type === 'number' || field.type === 'threshold') && (
        <input
          type="number"
          min={field.min}
          max={field.max}
          className="cv-input w-full"
          value={value != null ? Number(value) : ''}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      )}

      {field.type === 'watchlist' && (
        watchlists.length === 0 ? (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            <Settings2 className="w-3.5 h-3.5 inline mr-1" />
            <Link to="/settings" className="underline text-cv-accent">Paramètres → Identité</Link>
          </p>
        ) : (
          <select className="cv-input w-full" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}>
            <option value="">— Choisir —</option>
            {watchlists.map((w) => (
              <option key={w.id} value={w.id}>{w.name}</option>
            ))}
          </select>
        )
      )}

      {field.type === 'plate_list' && (
        plateLists.length === 0 ? (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            <Link to="/settings" className="underline text-cv-accent">Créer une liste de plaques</Link>
          </p>
        ) : (
          <select className="cv-input w-full" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}>
            <option value="">— Choisir —</option>
            {plateLists.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
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
        <select className="cv-input w-full" value={String(value ?? field.default ?? '')} onChange={(e) => onChange(e.target.value)}>
          <option value="">— Choisir —</option>
          {(field.options ?? []).map((opt) => {
            const val = typeof opt === 'string' ? opt : opt.value;
            const lab = typeof opt === 'string' ? opt : opt.label;
            return (
              <option key={val} value={val}>{lab}</option>
            );
          })}
        </select>
      )}

      {field.type === 'schedule' && (
        <p className="text-xs text-cv-muted">Plage horaire héritée du modèle (6h–22h par défaut).</p>
      )}
    </div>
  );
}
