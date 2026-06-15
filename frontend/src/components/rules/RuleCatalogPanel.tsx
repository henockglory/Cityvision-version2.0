import { useMemo, useState } from 'react';
import { Check, ChevronDown, Clock, PowerOff, Search } from 'lucide-react';
import { mapRuleCatalogItem } from '@/api/mappers';
import { resolveConfigSchema } from '@/lib/ruleConfigSchema';
import { iconForTemplate } from '@/lib/iconMap';
import IconBadge from '@/components/ui/IconBadge';
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
}

type CatalogTab = 'supported' | 'extended';

const CATEGORY_LABELS: Record<string, string> = {
  security: 'Sécurité & intrusion',
  spatial: 'Spatial & zones',
  traffic: 'Trafic & vitesse',
  identity: 'Identité & plaques',
  behavior: 'Comportements',
  composite: 'Composites',
  crowd: 'Foule & densité',
  time: 'Temps & horaires',
};

function hasConfigSchema(tpl: RuleCatalogTemplate): boolean {
  return (resolveConfigSchema(tpl).fields?.length ?? 0) > 0;
}

function capabilityHint(tpl: RuleCatalogTemplate): string {
  if (tpl.unsupported_message_fr) return tpl.unsupported_message_fr;
  if (tpl.prerequisites?.length) return `Requiert : ${tpl.prerequisites.join(' · ')}`;
  if (tpl.human_description) return tpl.human_description;
  if (tpl.capability_id) return `Événement « ${tpl.capability_id} » non émis par l'IA locale`;
  return 'Configuration non disponible avec l\'IA locale actuelle';
}

function RuleCard({
  tpl,
  isActive,
  isOccupied,
  isSupported,
  onConfigure,
  onDisable,
  onEnable,
  setMessage,
  catalogOnly,
}: {
  tpl: RuleCatalogTemplate;
  isActive: boolean;
  isOccupied: boolean;
  isSupported: boolean;
  onConfigure: (t: RuleCatalogTemplate) => void;
  onDisable: (id: string) => void;
  onEnable?: (id: string) => void;
  setMessage: (m: string) => void;
  catalogOnly?: boolean;
}) {
  return (
    <div
      className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${
        isActive ? 'border-metric-rules/40 bg-metric-rules/5' :
        isOccupied ? 'border-metric-alerts/30 bg-metric-alerts/5' :
        'border-cv-border/70 bg-cv-deep/30 hover:border-cv-accent/20'
      }`}
    >
      <IconBadge src={iconForTemplate(tpl.id, tpl.category)} alt="" size="md" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="font-medium text-sm">{tpl.name}</p>
          {isActive && <span className="cv-badge-online text-[10px]">Active</span>}
          {isOccupied && !isActive && <span className="text-[10px] text-metric-alerts font-semibold">Désactivée</span>}
          {!isSupported && <span className="text-[10px] text-cv-muted bg-cv-surface px-1.5 py-0.5 rounded">Bientôt</span>}
        </div>
        <p className="text-xs text-cv-muted mt-0.5">{tpl.severity}</p>
        {tpl.human_description && (
          <p className="text-xs text-cv-muted/90 mt-1 line-clamp-2">{tpl.human_description}</p>
        )}
        {!isSupported && (
          <p className="text-[10px] text-metric-alerts mt-1 flex items-start gap-1">
            <Clock className="w-3 h-3 shrink-0 mt-0.5" />
            {capabilityHint(tpl)}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-1.5 shrink-0">
        {catalogOnly ? (
          <>
            {isOccupied && (
              <span className="text-[10px] text-metric-rules flex items-center gap-1 justify-end">
                <Check className="w-3 h-3" /> {isActive ? 'Active' : 'Configurée'}
              </span>
            )}
            <button
              type="button"
              disabled={!isSupported || isOccupied}
              onClick={() => onConfigure(tpl)}
              className="cv-btn-primary text-xs py-1.5 px-2 disabled:opacity-40"
            >
              Configurer
            </button>
          </>
        ) : isActive ? (
          <button
            type="button"
            onClick={() => { onDisable?.(tpl.id); setMessage(`Désactivation de « ${tpl.name} »…`); }}
            className="cv-btn-secondary text-xs py-1.5 px-2"
          >
            <PowerOff className="w-3 h-3" />
            Désactiver
          </button>
        ) : isOccupied ? (
          <button type="button" disabled={!onEnable} onClick={() => onEnable?.(tpl.id)} className="cv-btn-secondary text-xs py-1.5 px-2">
            Réactiver
          </button>
        ) : (
          <button
            type="button"
            disabled={!isSupported}
            onClick={() => onConfigure(tpl)}
            className="cv-btn-primary text-xs py-1.5 px-2 disabled:opacity-40"
          >
            Configurer
          </button>
        )}
      </div>
    </div>
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
}: RuleCatalogPanelProps) {
  const [message, setMessage] = useState('');
  const [tab, setTab] = useState<CatalogTab>('supported');
  const [query, setQuery] = useState('');
  const [openCats, setOpenCats] = useState<Set<string>>(new Set(['security', 'spatial']));

  const sorted = useMemo(
    () => [...templates].map(mapRuleCatalogItem).sort((a, b) => a.name.localeCompare(b.name)),
    [templates],
  );

  const supported = sorted.filter((t) => t.supported !== false && hasConfigSchema(t));
  const extended = sorted.filter((t) => t.supported === false || !hasConfigSchema(t));
  const visible = tab === 'supported' ? supported : extended;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return visible;
    return visible.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        (t.category ?? '').toLowerCase().includes(q) ||
        (t.capability_id ?? '').toLowerCase().includes(q),
    );
  }, [visible, query]);

  const byCategory = useMemo(() => {
    const m = new Map<string, RuleCatalogTemplate[]>();
    for (const t of filtered) {
      const cat = t.category ?? 'other';
      if (!m.has(cat)) m.set(cat, []);
      m.get(cat)!.push(t);
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
    <div className={compact ? 'space-y-2' : 'space-y-3'}>
      <div className="flex flex-col sm:flex-row gap-2 sm:items-center sm:justify-between">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setTab('supported')}
            className={`text-xs font-medium px-3 py-1.5 rounded-lg ${tab === 'supported' ? 'bg-cv-accent/15 text-cv-accent' : 'text-cv-muted'}`}
          >
            Disponibles ({supported.length})
          </button>
          <button
            type="button"
            onClick={() => setTab('extended')}
            className={`text-xs font-medium px-3 py-1.5 rounded-lg ${tab === 'extended' ? 'bg-cv-accent/15 text-cv-accent' : 'text-cv-muted'}`}
          >
            Bientôt ({extended.length})
          </button>
        </div>
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-cv-muted" />
          <input
            type="search"
            className="cv-input text-xs pl-9 py-2"
            placeholder="Rechercher une règle…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      {message && <p className="text-xs text-cv-accent font-medium">{message}</p>}

      {filtered.length === 0 ? (
        <p className="text-sm text-cv-muted py-4 text-center">Aucune règle ne correspond.</p>
      ) : (
        <div className="space-y-2">
          {byCategory.map(([cat, items]) => (
            <div key={cat} className="border border-cv-border/60 rounded-xl overflow-hidden">
              <button
                type="button"
                onClick={() => toggleCat(cat)}
                className="w-full flex items-center justify-between gap-2 px-3 py-2.5 bg-cv-deep/40 hover:bg-cv-deep/60 text-left"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <img src={iconForTemplate(undefined, cat)} alt="" className="w-6 h-6" />
                  <span className="text-sm font-medium truncate">{CATEGORY_LABELS[cat] ?? cat}</span>
                  <span className="text-xs text-cv-muted">({items.length})</span>
                </div>
                <ChevronDown className={`w-4 h-4 text-cv-muted transition-transform ${openCats.has(cat) ? 'rotate-180' : ''}`} />
              </button>
              {openCats.has(cat) && (
                <div className="p-2 space-y-2 bg-cv-surface/30">
                  {items.map((tpl) => (
                    <RuleCard
                      key={tpl.id}
                      tpl={tpl}
                      isActive={activeTemplateIds.includes(tpl.id)}
                      isOccupied={occupiedTemplateIds.includes(tpl.id)}
                      isSupported={tpl.supported !== false && hasConfigSchema(tpl)}
                      onConfigure={onConfigure}
                      onDisable={onDisable ?? (() => undefined)}
                      onEnable={onEnable}
                      setMessage={setMessage}
                      catalogOnly={catalogOnly}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
