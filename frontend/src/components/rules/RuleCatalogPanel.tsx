import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Check, CheckCircle2, Layers, Loader2, PowerOff, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { mapRuleCatalogItem } from '@/api/mappers';
import { resolveConfigSchema } from '@/lib/ruleConfigSchema';
import { iconForTemplate } from '@/lib/iconMap';
import { buildCatalogTree, catalogSearchHaystack, defaultOpenGroups } from '@/lib/catalogNavigation';
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

const MEGA_ICON_CATEGORY: Record<string, string> = {
  places: 'spatial',
  people: 'crowd',
  road: 'road-enforcement',
  identity: 'identity',
  objects: 'incident',
  camera: 'quality',
};

const TILE_BASE =
  'relative flex w-full items-start gap-3 rounded-xl border p-3.5 text-left transition-all duration-200 hover:border-cv-accent/35 hover:bg-cv-surface/40';
const TILE_IDLE = `${TILE_BASE} border-cv-border/55 bg-cv-surface/25`;
const TILE_ACTIVE =
  `${TILE_BASE} border-cv-accent/50 bg-gradient-to-br from-cv-accent/12 via-cv-surface/35 to-cv-deep/20 ring-1 ring-cv-accent/25 shadow-lg shadow-cv-accent/10`;

function pillClass(active: boolean): string {
  return [
    'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors whitespace-nowrap',
    active
      ? 'border-cv-accent/45 bg-cv-accent/15 text-cv-text shadow-sm'
      : 'border-cv-border/55 bg-cv-surface/30 text-cv-muted hover:border-cv-accent/30 hover:text-cv-text',
  ].join(' ');
}

function hasConfigSchema(tpl: RuleCatalogTemplate): boolean {
  return (resolveConfigSchema(tpl).fields?.length ?? 0) > 0;
}

function isFullyOperational(_tpl: RuleCatalogTemplate): boolean {
  // Product: all catalog rules are presented as complete (no partial/DoD UI).
  return true;
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
  tone: 'accent' | 'rules';
  icon: ReactNode;
  label: string;
  count: number;
  onClick: () => void;
}) {
  const chipTone = active
    ? tone === 'rules'
      ? 'cv-filter-chip-active-rules'
      : 'cv-filter-chip-active-accent'
    : 'hover:border-cv-accent/25 hover:text-cv-text';

  const countTone = active
    ? tone === 'rules'
      ? 'cv-filter-count-rules'
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

function StatusChip({ tpl, subtle = false }: { tpl: RuleCatalogTemplate; subtle?: boolean }) {
  const { t } = useTranslation();
  if (tpl.activation_blocked) {
    return (
      <span
        title={tpl.activation_block_reason ?? undefined}
        className="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-md border border-rose-400/40 text-rose-400 bg-rose-400/10"
      >
        {t('rules.status.activationBlocked', { defaultValue: 'Activation bloquée — modèle manquant' })}
      </span>
    );
  }
  if (subtle) return null;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-md border border-metric-rules/40 text-metric-rules bg-metric-rules/10">
      <CheckCircle2 className="w-3 h-3 shrink-0" />
      {t('rules.status.operational')}
    </span>
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
  const operable = isConfigurable(tpl);
  const activationBlocked = Boolean(tpl.activation_blocked);
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

  const compactCatalog = catalogOnly && nested;
  const blurb = summary || tpl.human_description || '';

  return (
    <article
      className={`rounded-lg border transition-colors ${
        nested
          ? `cv-catalog-variant ${
              isActive ? 'cv-catalog-variant-active' :
              isOccupied ? 'cv-catalog-variant-occupied' : ''
            }`
          : isActive ? 'border-metric-rules/40 bg-metric-rules/5' :
            isOccupied ? 'border-metric-alerts/30 bg-metric-alerts/5' :
            'border-cv-border/70 bg-cv-deep/30 hover:border-cv-accent/20'
      }`}
    >
      <div className={`flex items-start gap-3 ${compactCatalog ? 'p-3' : 'p-4 gap-4'}`}>
        <IconBadge src={iconForTemplate(tpl.id, tpl.category)} alt="" size={compactCatalog ? 'sm' : 'md'} category={tpl.category} className="shrink-0" />
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="cv-meta-row">
            <p className={`font-medium leading-snug ${compactCatalog ? 'text-sm' : 'text-sm'}`}>{tpl.name}</p>
            {isActive && <span className="cv-badge-online text-xs">{t('rules.enabled')}</span>}
            {isOccupied && !isActive && <span className="text-xs text-metric-alerts font-semibold">{t('rules.disabled')}</span>}
            {!compactCatalog && <StatusChip tpl={tpl} subtle={nested} />}
          </div>

          {blurb && (
            <p className="text-xs text-cv-muted leading-relaxed line-clamp-2">{blurb}</p>
          )}

          {!compactCatalog && summary && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="text-xs text-cv-accent hover:underline"
            >
              {expanded ? t('rules.catalogCard.hideGuide') : t('rules.catalogCard.showGuide')}
            </button>
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
              disabled={!operable || isOccupied || activationBlocked}
              onClick={() => onConfigure(tpl)}
              title={activationBlocked ? (tpl.activation_block_reason ?? undefined) : undefined}
              className="cv-btn-primary text-xs whitespace-nowrap disabled:opacity-40"
            >
              {activationBlocked
                ? t('rules.catalogCard.blocked', { defaultValue: 'Modèle manquant' })
                : t('rules.catalogCard.configure')}
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
              activationBlocked
                ? (tpl.activation_block_reason ?? t('rules.catalogCard.activationBlockedHint', { defaultValue: 'Modèle requis non chargé — ouvrez pour voir le détail ; activation refusée.' }))
                : !operable
                ? (tpl.partial_reason_fr ?? t('rules.catalogCard.notConfigurableHint', { defaultValue: 'Ce template nécessite des modules ou une configuration supplémentaire' }))
                : t('rules.catalogCard.configureHint', { defaultValue: 'Cliquez pour configurer et activer cette règle sur une caméra' })
            }
            helpKey={activationBlocked ? 'catalogActivationBlocked' : !operable ? 'catalogNotConfigurable' : 'catalogConfigure'}
            >
              <button
                type="button"
                disabled={!operable && !activationBlocked}
                onClick={() => onConfigure(tpl)}
                className="cv-btn-primary text-xs whitespace-nowrap disabled:opacity-40"
              >
                {activationBlocked
                  ? t('rules.catalogCard.viewBlocked', { defaultValue: 'Voir (bloqué)' })
                  : operable
                    ? t('rules.catalogCard.configure')
                    : t('rules.catalogCard.needsSetup', { defaultValue: 'Config. requise' })}
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
  const tr = (key: string, frDefault: string) => {
    const value = t(key);
    return value === key ? frDefault : value;
  };
  const [message, setMessage] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'operational'>('all');
  const [activeMegaId, setActiveMegaId] = useState<string | null>(null);
  const [activeSubId, setActiveSubId] = useState<string | null>(null);

  const labelForMega = (id: string) => t(`rules.catalogMega.${id}`);
  const labelForSub = (id: string) => t(`rules.catalogSub.${id}`);
  const hintForMega = (id: string) => t(`rules.catalogMega.${id}Hint`);
  const hintForSub = (id: string) => t(`rules.catalogSub.${id}Hint`);
  const countLabel = (n: number) => t('rules.catalogGroup.rulesCount', { count: n });

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

  const filtered = useMemo(() => {
    let base = sorted;
    if (filter === 'operational') base = base.filter(isFullyOperational);
    const q = query.trim().toLowerCase();
    if (!q) return base;
    return base.filter((tpl) => catalogSearchHaystack(tpl, labelForMega, labelForSub).includes(q));
  }, [sorted, filter, query, t]);

  const scopeTree = useMemo(
    () => buildCatalogTree(sorted, deploymentScope),
    [sorted, deploymentScope],
  );

  const catalogTree = useMemo(
    () => buildCatalogTree(filtered, deploymentScope),
    [filtered, deploymentScope],
  );

  useEffect(() => {
    const def = defaultOpenGroups(scopeTree, isFullyOperational);
    if (def) {
      setActiveMegaId(def.megaId);
      setActiveSubId(def.subId);
    } else if (scopeTree[0]) {
      setActiveMegaId(scopeTree[0].id);
      setActiveSubId(scopeTree[0].subGroups[0]?.id ?? null);
    } else {
      setActiveMegaId(null);
      setActiveSubId(null);
    }
  }, [deploymentScope, scopeTree]);

  const activeMega = catalogTree.find((m) => m.id === activeMegaId) ?? null;
  const activeSub = activeMega?.subGroups.find((s) => s.id === activeSubId) ?? activeMega?.subGroups[0] ?? null;

  useEffect(() => {
    if (!activeMega) return;
    if (!activeMega.subGroups.some((s) => s.id === activeSubId)) {
      setActiveSubId(activeMega.subGroups[0]?.id ?? null);
    }
  }, [activeMega, activeSubId]);

  const primaryTree = useMemo(() => catalogTree.filter((m) => !m.muted), [catalogTree]);
  const maintenanceTree = useMemo(() => catalogTree.filter((m) => m.muted), [catalogTree]);
  const isSearching = query.trim().length > 0;

  const selectMega = (megaId: string) => {
    setActiveMegaId(megaId);
    const mega = catalogTree.find((m) => m.id === megaId);
    const def = mega ? defaultOpenGroups([mega], isFullyOperational) : null;
    setActiveSubId(def?.subId ?? mega?.subGroups[0]?.id ?? null);
  };

  return (
    <div className={compact ? 'cv-stack-sm' : 'space-y-5'}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <FilterChip
            active={filter === 'all'}
            tone="accent"
            icon={<Layers className="w-3.5 h-3.5" />}
            label={tr('rules.catalogFilter.all', 'Toutes')}
            count={allCount}
            onClick={() => setFilter('all')}
          />
          <FilterChip
            active={filter === 'operational'}
            tone="rules"
            icon={<CheckCircle2 className="w-3.5 h-3.5" />}
            label={tr('rules.catalogFilter.operational', 'Prêtes à activer')}
            count={operationalCount}
            onClick={() => setFilter('operational')}
          />
        </div>

        <div className="relative w-full lg:w-80 lg:shrink-0">
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


      {message && <p className="text-xs text-cv-accent font-medium px-1">{message}</p>}

      {filtered.length === 0 ? (
        <p className="text-sm text-cv-muted py-10 text-center">{t('rules.catalogTab.emptyFilter')}</p>
      ) : isSearching ? (
        <div className="cv-catalog-search-results cv-stack-sm">
          {catalogTree.map((mega) =>
            mega.subGroups.map((sub) => (
              <section key={`${mega.id}:${sub.id}`} className="cv-stack-sm">
                <header className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 px-1">
                  <p className="text-sm font-semibold text-cv-text">{labelForSub(sub.id)}</p>
                  <span className="text-xs text-cv-muted">{labelForMega(mega.id)} · {countLabel(sub.templates.length)}</span>
                </header>
                <div className="cv-stack-sm">
                  {sub.templates.map((tpl) => (
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
              </section>
            )),
          )}
        </div>
      ) : (
        <>
          <div className="space-y-3">
            <p className="text-sm font-semibold text-cv-text tracking-tight">
              {tr('rules.catalogNav.lead', 'Que souhaitez-vous surveiller ?')}
            </p>
            <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
              {primaryTree.map((mega) => (
                <button
                  key={mega.id}
                  type="button"
                  className={activeMegaId === mega.id ? TILE_ACTIVE : TILE_IDLE}
                  aria-pressed={activeMegaId === mega.id}
                  onClick={() => selectMega(mega.id)}
                >
                  <IconBadge
                    src={iconForTemplate(undefined, MEGA_ICON_CATEGORY[mega.id])}
                    alt=""
                    size="md"
                    category={MEGA_ICON_CATEGORY[mega.id]}
                    className="shrink-0"
                  />
                  <div className="min-w-0 flex-1 text-left">
                    <p className="text-sm font-semibold leading-snug text-cv-text">{labelForMega(mega.id)}</p>
                    <p className="text-xs text-cv-muted leading-relaxed mt-1 line-clamp-2">{hintForMega(mega.id)}</p>
                  </div>
                  <span className="shrink-0 min-w-[1.75rem] h-7 px-2 inline-flex items-center justify-center rounded-full text-xs font-semibold tabular-nums bg-cv-deep/50 text-cv-muted border border-cv-border/50">
                    {mega.templateCount}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {activeMega && activeSub && !activeMega.muted && (
            <div className="rounded-xl border border-cv-border/50 bg-cv-deep/25 p-4 space-y-3">
              <div className="flex flex-wrap gap-2" role="tablist" aria-label={labelForMega(activeMega.id)}>
                {activeMega.subGroups.map((sub) => (
                  <button
                    key={sub.id}
                    type="button"
                    role="tab"
                    aria-selected={activeSub.id === sub.id}
                    className={pillClass(activeSub.id === sub.id)}
                    onClick={() => setActiveSubId(sub.id)}
                  >
                    <span>{labelForSub(sub.id)}</span>
                    <span className="inline-flex min-w-[1.25rem] h-5 px-1.5 items-center justify-center rounded-full bg-cv-deep/60 text-[10px] font-semibold tabular-nums">
                      {sub.templates.length}
                    </span>
                  </button>
                ))}
              </div>
              <p className="text-xs text-cv-muted leading-relaxed">{hintForSub(activeSub.id)}</p>
              <div className="cv-stack-sm pt-1">
                {activeSub.templates.map((tpl) => (
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
            </div>
          )}

          {maintenanceTree.length > 0 && (
            <div className="pt-3 border-t border-cv-border/35 space-y-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-cv-muted/80">
                {tr('rules.catalogNav.maintenance', 'Entretien caméra')}
              </p>
              <div className="grid gap-2.5 sm:grid-cols-1 xl:grid-cols-2">
                {maintenanceTree.map((mega) => (
                  <button
                    key={mega.id}
                    type="button"
                    className={`${activeMegaId === mega.id ? TILE_ACTIVE : TILE_IDLE} opacity-95`}
                    aria-pressed={activeMegaId === mega.id}
                    onClick={() => selectMega(mega.id)}
                  >
                    <IconBadge
                      src={iconForTemplate(undefined, MEGA_ICON_CATEGORY[mega.id])}
                      alt=""
                      size="sm"
                      category={MEGA_ICON_CATEGORY[mega.id]}
                      className="shrink-0"
                    />
                    <div className="min-w-0 flex-1 text-left">
                      <p className="text-sm font-semibold leading-snug text-cv-text">{labelForMega(mega.id)}</p>
                      <p className="text-xs text-cv-muted leading-relaxed mt-1 line-clamp-2">{hintForMega(mega.id)}</p>
                    </div>
                    <span className="shrink-0 min-w-[1.75rem] h-7 px-2 inline-flex items-center justify-center rounded-full text-xs font-semibold tabular-nums bg-cv-deep/50 text-cv-muted border border-cv-border/50">
                      {mega.templateCount}
                    </span>
                  </button>
                ))}
              </div>
              {activeMega?.muted && activeSub && (
                <div className="rounded-xl border border-cv-border/40 bg-cv-deep/15 p-4 space-y-3">
                  <div className="flex flex-wrap gap-2" role="tablist">
                    {activeMega.subGroups.map((sub) => (
                      <button
                        key={sub.id}
                        type="button"
                        role="tab"
                        aria-selected={activeSub.id === sub.id}
                        className={pillClass(activeSub.id === sub.id)}
                        onClick={() => setActiveSubId(sub.id)}
                      >
                        <span>{labelForSub(sub.id)}</span>
                        <span className="inline-flex min-w-[1.25rem] h-5 px-1.5 items-center justify-center rounded-full bg-cv-deep/60 text-[10px] font-semibold tabular-nums">
                          {sub.templates.length}
                        </span>
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-cv-muted leading-relaxed">{hintForSub(activeSub.id)}</p>
                  <div className="cv-stack-sm pt-1">
                    {activeSub.templates.map((tpl) => (
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
                </div>
              )}
            </div>
          )}
        </>
      )}

      {!compact && filter === 'all' && !isSearching && (
        <p className="text-xs text-cv-muted/70 text-center pt-1 leading-relaxed">
          {t('rules.catalogFooter', {
            total: allCount,
            operational: operationalCount,
            defaultValue: `${allCount} règles · ${operationalCount} prêtes`,
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
