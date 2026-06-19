import { useMemo, useState, type ReactNode } from 'react';
import { AlertTriangle, Check, CheckCircle2, ChevronDown, FlaskConical, Layers, Loader2, PowerOff, Search, Wrench, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { mapRuleCatalogItem } from '@/api/mappers';
import { resolveConfigSchema } from '@/lib/ruleConfigSchema';
import { iconForTemplate } from '@/lib/iconMap';
import IconBadge from '@/components/ui/IconBadge';
import GuideIllustration from '@/components/ui/GuideIllustration';
import InfoTip from '@/components/ui/InfoTip';
import type { Rule, RuleCatalogTemplate } from '@/types';

interface RuleCatalogPanelProps {
  templates: RuleCatalogTemplate[];
  occupiedTemplateIds: string[];
  activeTemplateIds: string[];
  rulesByTemplate?: Map<string, Rule>;
  onConfigure: (template: RuleCatalogTemplate) => void;
  onDisable?: (templateId: string) => void;
  onEnable?: (templateId: string) => void;
  onActivated?: () => void;
  compact?: boolean;
  catalogOnly?: boolean;
  deploymentScope?: 'all' | 'national' | 'enterprise' | 'domestic';
}

function hasConfigSchema(tpl: RuleCatalogTemplate): boolean {
  return (resolveConfigSchema(tpl).fields?.length ?? 0) > 0;
}

function isFullyOperational(tpl: RuleCatalogTemplate): boolean {
  const ps = tpl.partial_status;
  return !ps || ps === 'full';
}

function isConfigurable(tpl: RuleCatalogTemplate): boolean {
  return tpl.supported !== false && hasConfigSchema(tpl);
}

function FilterChip({
  active,
  tone,
  icon,
  label,
  count,
  onClick,
}: {
  active: boolean;
  tone: 'accent' | 'rules' | 'amber';
  icon: ReactNode;
  label: string;
  count: number;
  onClick: () => void;
}) {
  const chipTone = active
    ? tone === 'rules'
      ? 'cv-filter-chip-active-rules'
      : tone === 'amber'
        ? 'cv-filter-chip-active-amber'
        : 'cv-filter-chip-active-accent'
    : 'hover:border-cv-accent/25 hover:text-cv-text';

  const countTone = active
    ? tone === 'rules'
      ? 'cv-filter-count-rules'
      : tone === 'amber'
        ? 'cv-filter-count-amber'
        : 'cv-filter-count-accent'
    : '';

  return (
    <button type="button" onClick={onClick} className={`cv-filter-chip ${chipTone}`}>
      <span className="inline-flex items-center justify-center w-3.5 h-3.5 shrink-0">{icon}</span>
      <span className="whitespace-nowrap">{label}</span>
      <span className={`cv-filter-count ${countTone}`}>{count}</span>
    </button>
  );
}

function StatusChip({ tpl }: { tpl: RuleCatalogTemplate }) {
  const { t } = useTranslation();
  const ps = tpl.partial_status;

  if (!ps || ps === 'full') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-md border border-metric-rules/40 text-metric-rules bg-metric-rules/10">
        <CheckCircle2 className="w-3 h-3 shrink-0" />
        {t('rules.status.operational', { defaultValue: 'Opérationnel' })}
      </span>
    );
  }

  const cfg = {
    requires_calibration: {
      icon: <Wrench className="w-3 h-3 shrink-0" />,
      label: t('rules.partial.requires_calibration'),
      cls: 'text-amber-400 bg-amber-400/8 border-amber-400/30',
    },
    requires_ocr: {
      icon: <FlaskConical className="w-3 h-3 shrink-0" />,
      label: t('rules.partial.requires_ocr'),
      cls: 'text-violet-400 bg-violet-400/8 border-violet-400/30',
    },
    requires_face_ai: {
      icon: <FlaskConical className="w-3 h-3 shrink-0" />,
      label: t('rules.partial.requires_face_ai'),
      cls: 'text-violet-400 bg-violet-400/8 border-violet-400/30',
    },
    partial_aggregate: {
      icon: <AlertTriangle className="w-3 h-3 shrink-0" />,
      label: t('rules.partial.partial_aggregate'),
      cls: 'text-yellow-400 bg-yellow-400/8 border-yellow-400/30',
    },
  } as const;

  const item = cfg[ps as keyof typeof cfg];
  if (!item) return null;

  return (
    <span
      title={tpl.partial_reason_fr ?? item.label}
      className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-md border ${item.cls}`}
    >
      {item.icon}
      {item.label}
    </span>
  );
}

function PrerequisitesPanel({ tpl }: { tpl: RuleCatalogTemplate }) {
  const { t } = useTranslation();
  const ps = tpl.partial_status;

  const prereqs: Array<{ ok: boolean; label: string; action?: string }> = [
    { ok: true, label: t('rules.prereq.yolo', { defaultValue: 'Moteur IA YOLO (inclus par défaut)' }) },
  ];

  if (ps === 'requires_calibration') {
    prereqs.push({
      ok: false,
      label: t('rules.prereq.calibration', { defaultValue: 'Calibration caméra (homographie vitesse)' }),
      action: t('rules.prereq.calibrationHint', { defaultValue: '→ Contactez votre intégrateur pour configurer la grille métrique de la caméra' }),
    });
  }
  if (ps === 'requires_ocr') {
    prereqs.push({
      ok: false,
      label: t('rules.prereq.ocr', { defaultValue: 'Module PaddleOCR (lecture de plaques)' }),
      action: t('rules.prereq.ocrHint', { defaultValue: "→ pip install paddleocr dans l'environnement AI engine" }),
    });
  }
  if (ps === 'requires_face_ai') {
    prereqs.push({
      ok: false,
      label: t('rules.prereq.faceAi', { defaultValue: 'Module InsightFace (reconnaissance faciale)' }),
      action: t('rules.prereq.faceAiHint', { defaultValue: '→ pip install insightface + configuration base de données visages' }),
    });
  }
  if (ps === 'partial_aggregate') {
    prereqs.push({
      ok: false,
      label: t('rules.prereq.aggregate', { defaultValue: 'Flux vidéo avec activité suffisante' }),
      action: tpl.partial_reason_fr ?? t('rules.prereq.aggregateHint', { defaultValue: "→ Vérifiez que la caméra couvre bien la zone d'intérêt" }),
    });
  }

  return (
    <div className="cv-panel cv-stack-sm">
      <p className="text-xs font-semibold text-cv-muted uppercase tracking-wider">
        {t('rules.prereq.title', { defaultValue: "Ce qu'il faut pour que ça fonctionne" })}
      </p>
      <div className="cv-stack-sm">
        {prereqs.map((p, i) => (
          <div key={i} className="space-y-1">
            <div className="flex items-start gap-2">
              {p.ok
                ? <Check className="w-3.5 h-3.5 text-metric-rules shrink-0 mt-0.5" />
                : <XCircle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />}
              <span className={`text-xs leading-relaxed ${p.ok ? 'text-cv-muted' : 'text-amber-300'}`}>{p.label}</span>
            </div>
            {p.action && (
              <p className="text-xs text-cv-muted/80 leading-relaxed pl-5">{p.action}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function RuleCard({
  tpl,
  isActive,
  isOccupied,
  onConfigure,
  onDisable,
  onEnable,
  setMessage,
  catalogOnly,
  nested = false,
  t,
}: {
  tpl: RuleCatalogTemplate;
  isActive: boolean;
  isOccupied: boolean;
  onConfigure: (t: RuleCatalogTemplate) => void;
  onDisable: (id: string) => void;
  onEnable?: (id: string) => void;
  setMessage: (m: string) => void;
  catalogOnly?: boolean;
  nested?: boolean;
  t: (k: string, opts?: Record<string, unknown>) => string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showPrereqs, setShowPrereqs] = useState(false);
  const operable = isConfigurable(tpl);
  const operational = isFullyOperational(tpl);
  const summary = tpl.role_summary_fr ?? tpl.human_description ?? '';

  const CATEGORY_GUIDE: Record<string, string> = {
    spatial: '/guides/spatial.svg',
    security: '/guides/spatial.svg',
    'road-enforcement': '/guides/road-enforcement.svg',
    traffic: '/guides/road-enforcement.svg',
    speed: '/guides/road-enforcement.svg',
    crowd: '/guides/crowd.svg',
    identity: '/guides/identity.svg',
    composite: '/guides/composite.svg',
    incident: '/guides/composite.svg',
    alerts: '/guides/alerts.svg',
    live: '/guides/live.svg',
  };
  const illustration = tpl.illustration ?? CATEGORY_GUIDE[tpl.category ?? ''] ?? '/guides/rules-banner.svg';

  return (
    <article
      className={`rounded-lg border transition-colors ${
        nested
          ? `cv-catalog-variant ${
              isActive ? 'cv-catalog-variant-active' :
              isOccupied ? 'cv-catalog-variant-occupied' :
              !operational ? 'cv-catalog-variant-partial' : ''
            }`
          : isActive ? 'border-metric-rules/40 bg-metric-rules/5' :
            isOccupied ? 'border-metric-alerts/30 bg-metric-alerts/5' :
            !operational ? 'border-amber-400/20 bg-amber-400/3' :
            'border-cv-border/70 bg-cv-deep/30 hover:border-cv-accent/20'
      }`}
    >
      <div className="flex items-start gap-4 p-4">
        <IconBadge src={iconForTemplate(tpl.id, tpl.category)} alt="" size="md" category={tpl.category} className="shrink-0" />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="cv-meta-row">
            <p className="font-medium text-sm leading-snug">{tpl.name}</p>
            {isActive && <span className="cv-badge-online text-xs">{t('rules.enabled')}</span>}
            {isOccupied && !isActive && <span className="text-xs text-metric-alerts font-semibold">{t('rules.disabled')}</span>}
            <StatusChip tpl={tpl} />
          </div>

          {tpl.human_description && (
            <p className="text-xs text-cv-muted leading-relaxed line-clamp-2">{tpl.human_description}</p>
          )}

          {!operational && tpl.partial_reason_fr && (
            <p className="cv-callout text-amber-300/90 bg-amber-400/5 border border-amber-400/20 !p-2.5">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-amber-400" />
              <span>{tpl.partial_reason_fr}</span>
            </p>
          )}

          {(summary || !operational) && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-0.5">
              {summary && (
                <button
                  type="button"
                  onClick={() => setExpanded((v) => !v)}
                  className="text-xs text-cv-accent hover:underline"
                >
                  {expanded ? t('rules.catalogCard.hideGuide') : t('rules.catalogCard.showGuide')}
                </button>
              )}
              {!operational && (
                <button
                  type="button"
                  onClick={() => setShowPrereqs((v) => !v)}
                  className="text-xs text-amber-400/90 hover:underline"
                >
                  {showPrereqs
                    ? t('rules.catalogCard.hidePrereqs', { defaultValue: 'Masquer les prérequis' })
                    : t('rules.catalogCard.showPrereqs', { defaultValue: 'Voir ce qu\'il faut' })}
                </button>
              )}
            </div>
          )}
        </div>

        <div className="shrink-0 flex flex-col items-end gap-2 pt-0.5">
          {catalogOnly && isOccupied && (
            <span className="text-xs text-metric-rules flex items-center gap-1.5">
              <Check className="w-3.5 h-3.5" />
              {isActive ? t('rules.enabled') : t('rules.catalogCard.configured')}
            </span>
          )}
          {catalogOnly ? (
            <button
              type="button"
              disabled={!operable || isOccupied}
              onClick={() => onConfigure(tpl)}
              className="cv-btn-primary text-xs whitespace-nowrap disabled:opacity-40"
            >
              {t('rules.catalogCard.configure')}
            </button>
          ) : isActive ? (
            <button
              type="button"
              onClick={() => { onDisable?.(tpl.id); setMessage(t('rules.catalogCard.disabling', { name: tpl.name })); }}
              className="cv-btn-secondary text-xs whitespace-nowrap"
            >
              <PowerOff className="w-3.5 h-3.5" />
              {t('rules.disable')}
            </button>
          ) : isOccupied ? (
            <button type="button" disabled={!onEnable} onClick={() => onEnable?.(tpl.id)} className="cv-btn-secondary text-xs whitespace-nowrap">
              {t('rules.catalogCard.reactivate')}
            </button>
          ) : (
            <InfoTip content={
              !operable
                ? (tpl.partial_reason_fr ?? t('rules.catalogCard.notConfigurableHint', { defaultValue: 'Ce template nécessite des modules ou une configuration supplémentaire' }))
                : t('rules.catalogCard.configureHint', { defaultValue: 'Cliquez pour configurer et activer cette règle sur une caméra' })
            }>
              <button
                type="button"
                disabled={!operable}
                onClick={() => onConfigure(tpl)}
                className="cv-btn-primary text-xs whitespace-nowrap disabled:opacity-40"
              >
                {operable ? t('rules.catalogCard.configure') : t('rules.catalogCard.needsSetup', { defaultValue: 'Config. requise' })}
              </button>
            </InfoTip>
          )}
        </div>
      </div>

      {expanded && summary && (
        <div className="cv-card-divider !pt-3">
          <GuideIllustration
            variant={(tpl.category as 'rules' | 'spatial' | 'alerts' | 'live' | 'road-enforcement' | 'crowd' | 'identity' | 'composite' | 'default') ?? 'rules'}
            src={illustration}
            title={tpl.name}
            caption={summary}
            compact
          />
        </div>
      )}

      {showPrereqs && !operational && (
        <div className="cv-card-divider !pt-3">
          <PrerequisitesPanel tpl={tpl} />
        </div>
      )}
    </article>
  );
}

export default function RuleCatalogPanel({
  templates,
  occupiedTemplateIds,
  activeTemplateIds,
  onConfigure,
  onDisable,
  onEnable,
  compact = false,
  catalogOnly = false,
  deploymentScope = 'all',
}: RuleCatalogPanelProps) {
  const { t } = useTranslation();
  const [message, setMessage] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'operational' | 'partial'>('all');
  const [openCats, setOpenCats] = useState<Set<string>>(() => new Set());

  const scopedTemplates = useMemo(() => {
    if (!deploymentScope || deploymentScope === 'all') return templates;
    return templates.filter((tpl) => (tpl.deployment_scopes ?? []).includes(deploymentScope));
  }, [templates, deploymentScope]);

  const sorted = useMemo(
    () => [...scopedTemplates].map(mapRuleCatalogItem).sort((a, b) => a.name.localeCompare(b.name)),
    [scopedTemplates],
  );

  const allCount = sorted.length;
  const operationalCount = sorted.filter(isFullyOperational).length;
  const partialCount = sorted.filter((tpl) => !isFullyOperational(tpl)).length;

  const filtered = useMemo(() => {
    let base = sorted;
    if (filter === 'operational') base = base.filter(isFullyOperational);
    if (filter === 'partial') base = base.filter((tpl) => !isFullyOperational(tpl));
    const q = query.trim().toLowerCase();
    if (!q) return base;
    return base.filter(
      (tpl) =>
        tpl.name.toLowerCase().includes(q) ||
        (tpl.category ?? '').toLowerCase().includes(q) ||
        (tpl.capability_id ?? '').toLowerCase().includes(q) ||
        (tpl.human_description ?? '').toLowerCase().includes(q),
    );
  }, [sorted, filter, query]);

  const byCategory = useMemo(() => {
    const m = new Map<string, RuleCatalogTemplate[]>();
    for (const tpl of filtered) {
      const cat = tpl.category ?? 'other';
      if (!m.has(cat)) m.set(cat, []);
      m.get(cat)!.push(tpl);
    }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtered]);

  const toggleCat = (cat: string) => {
    setOpenCats((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  return (
    <div className={compact ? 'cv-stack-sm' : 'space-y-4'}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <FilterChip
            active={filter === 'all'}
            tone="accent"
            icon={<Layers className="w-3.5 h-3.5" />}
            label={t('rules.catalogFilter.all', { defaultValue: 'Tout' })}
            count={allCount}
            onClick={() => setFilter('all')}
          />
          <FilterChip
            active={filter === 'operational'}
            tone="rules"
            icon={<CheckCircle2 className="w-3.5 h-3.5" />}
            label={t('rules.catalogFilter.operational', { defaultValue: 'Opérationnels' })}
            count={operationalCount}
            onClick={() => setFilter('operational')}
          />
          <FilterChip
            active={filter === 'partial'}
            tone="amber"
            icon={<Wrench className="w-3.5 h-3.5" />}
            label={t('rules.catalogFilter.partial', { defaultValue: 'Module requis' })}
            count={partialCount}
            onClick={() => setFilter('partial')}
          />
        </div>

        <div className="relative w-full lg:w-72 lg:shrink-0">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-cv-muted pointer-events-none" />
          <input
            type="search"
            className="cv-input text-sm !pl-10"
            placeholder={t('rules.catalogTab.search')}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      {filter === 'partial' && (
        <div className="cv-callout text-amber-300/90 bg-amber-400/5 border border-amber-400/20">
          <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
          <span>
            {t('rules.catalogFilter.partialExplain', {
              defaultValue: "Ces règles nécessitent un module ou une configuration supplémentaire. Cliquez sur « Voir ce qu'il faut » pour comprendre les étapes à suivre.",
            })}
          </span>
        </div>
      )}

      {message && <p className="text-xs text-cv-accent font-medium px-1">{message}</p>}

      {filtered.length === 0 ? (
        <p className="text-sm text-cv-muted py-8 text-center">{t('rules.catalogTab.emptyFilter')}</p>
      ) : (
        <div className="cv-stack-sm">
          {byCategory.map(([cat, items]) => {
            const catPartial = items.filter((tpl) => !isFullyOperational(tpl)).length;
            const isOpen = openCats.has(cat);
            return (
              <div key={cat} className="cv-catalog-group" data-open={isOpen ? 'true' : 'false'}>
                <button
                  type="button"
                  onClick={() => toggleCat(cat)}
                  className="cv-catalog-group-trigger"
                  aria-expanded={isOpen}
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <IconBadge src={iconForTemplate(undefined, cat)} alt="" size="lg" category={cat} className="shrink-0" />
                    <div className="min-w-0 text-left">
                      <span className="text-sm font-medium leading-snug block truncate">
                        {t(`rules.catalogCategory.${cat}`, { defaultValue: cat })}
                      </span>
                      <span className="text-xs text-cv-muted leading-relaxed block mt-0.5">
                        {items.length} {items.length > 1 ? 'règles' : 'règle'}
                        {catPartial > 0 && (
                          <span className="text-amber-400/80"> · {catPartial} module{catPartial > 1 ? 's' : ''} requis</span>
                        )}
                      </span>
                    </div>
                  </div>
                  <ChevronDown className={`w-4 h-4 text-cv-muted shrink-0 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                </button>
                {isOpen && (
                  <div className="cv-catalog-group-body">
                    <p className="cv-catalog-group-body-label">
                      {t('rules.catalogGroup.variantsLabel', { defaultValue: 'Règles de ce groupe' })}
                    </p>
                    {items.map((tpl) => (
                      <RuleCard
                        key={tpl.id}
                        tpl={tpl}
                        nested
                        isActive={activeTemplateIds.includes(tpl.id)}
                        isOccupied={occupiedTemplateIds.includes(tpl.id)}
                        onConfigure={onConfigure}
                        onDisable={onDisable ?? (() => undefined)}
                        onEnable={onEnable}
                        setMessage={setMessage}
                        catalogOnly={catalogOnly}
                        t={t}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {!compact && filter === 'all' && (
        <p className="text-xs text-cv-muted/70 text-center pt-2 leading-relaxed">
          {t('rules.catalogFooter', {
            total: allCount,
            operational: operationalCount,
            partial: partialCount,
            defaultValue: `${allCount} règles · ${operationalCount} opérationnelles immédiatement · ${partialCount} nécessitent un module ou réglage`,
          })}
        </p>
      )}
    </div>
  );
}

export function RuleCatalogSkeleton() {
  return (
    <div className="cv-stack-sm">
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-20 rounded-lg bg-cv-surface/40 animate-pulse" />
      ))}
      <Loader2 className="w-4 h-4 animate-spin mx-auto text-cv-muted/40" />
    </div>
  );
}
