import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Pencil, Plus, Power, PowerOff, Trash2 } from 'lucide-react';
import IconBadge from '@/components/ui/IconBadge';
import SeverityBadge from '@/components/ui/SeverityBadge';
import { explainRule } from '@/lib/ruleExplainability';
import { evidencePolicyChip, type EvidencePolicy } from '@/lib/evidencePolicy';
import { iconForTemplate } from '@/lib/iconMap';
import type { Rule } from '@/types';

type Filter = 'all' | 'enabled' | 'disabled';

interface ActiveRulesPanelProps {
  rules: Rule[];
  busyId: string | null;
  highlightedRuleId?: string | null;
  onEdit: (rule: Rule) => void;
  onEditEvidence?: (rule: Rule) => void;
  onDelete: (rule: Rule) => void;
  onDisable: (rule: Rule) => void;
  onEnable: (ruleId: string) => void;
  onDuplicate: (rule: Rule) => void;
  onNewRule: () => void;
  onHighlight?: (ruleId: string) => void;
}

export default function ActiveRulesPanel({
  rules,
  busyId,
  highlightedRuleId = null,
  onEdit,
  onEditEvidence,
  onDelete,
  onDisable,
  onEnable,
  onDuplicate,
  onNewRule,
  onHighlight,
}: ActiveRulesPanelProps) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<Filter>('all');
  const [announce, setAnnounce] = useState('');

  const filtered = useMemo(() => {
    if (filter === 'enabled') return rules.filter((r) => r.enabled);
    if (filter === 'disabled') return rules.filter((r) => !r.enabled);
    return rules;
  }, [rules, filter]);

  const flash = (ruleId: string, ruleName: string, enabled: boolean) => {
    onHighlight?.(ruleId);
    setAnnounce(enabled ? `Règle « ${ruleName} » activée.` : `Règle « ${ruleName} » désactivée.`);
  };

  return (
    <section id="rules-active-panel" className="cv-card p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold">{t('rules.activeTitle')}</h2>
          <p className="text-xs text-cv-muted mt-0.5">{t('rules.activeSubtitle')}</p>
        </div>
        <button type="button" onClick={onNewRule} className="cv-btn-primary text-sm">
          <Plus className="w-4 h-4" />
          {t('rules.newRule')}
        </button>
      </div>

      <div className="flex gap-2 flex-wrap">
        {(['all', 'enabled', 'disabled'] as Filter[]).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
              filter === f
                ? 'border-cv-accent/40 bg-cv-accent/10 text-cv-accent'
                : 'border-cv-border text-cv-muted hover:text-cv-text'
            }`}
          >
            {t(`rules.filter.${f}`)}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-cv-muted py-6 text-center">{t('rules.activeEmpty')}</p>
      ) : (
        <div className="space-y-2">
          <div aria-live="polite" className="sr-only">
            {announce}
          </div>
          {filtered.map((rule) => {
            const templateId = String((rule.definition?.bindings as Record<string, unknown>)?.template_id ?? '');
            const evPolicy = (rule.definition?.evidence ?? {}) as Partial<EvidencePolicy>;
            return (
              <div
                key={rule.id}
                data-testid={`rule-row-${rule.id}`}
                data-highlighted={highlightedRuleId === rule.id ? 'true' : 'false'}
                className={`flex items-center gap-3 p-3 rounded-lg border border-cv-border/70 bg-cv-deep/30 hover:border-cv-accent/25 transition-all group ${
                  highlightedRuleId === rule.id ? 'border-cv-accent/70 bg-cv-accent/10 shadow-glow' : ''
                }`}
              >
                <IconBadge
                  src={iconForTemplate(templateId, rule.category)}
                  alt=""
                  size="md"
                  className="group-hover:shadow-glow"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-medium text-sm truncate">{rule.name}</p>
                    <SeverityBadge severity={(rule.severity ?? 'medium') as 'low' | 'medium' | 'high' | 'critical'} />
                    <span className={`text-[10px] uppercase font-semibold ${rule.enabled ? 'text-metric-rules' : 'text-cv-muted'}`}>
                      {rule.enabled ? t('rules.enabled') : t('rules.disabled')}
                    </span>
                    <button
                      type="button"
                      className="text-[10px] px-2 py-0.5 rounded-full bg-cv-accent/10 text-cv-accent hover:bg-cv-accent/20"
                      title="Configurer les preuves"
                      onClick={(e) => { e.stopPropagation(); (onEditEvidence ?? onEdit)(rule); }}
                    >
                      {evidencePolicyChip(evPolicy)}
                    </button>
                  </div>
                  <p className="text-xs text-cv-muted mt-0.5 line-clamp-2">{explainRule(rule)}</p>
                </div>
                <div className="flex gap-1 shrink-0">
                  <button type="button" onClick={() => onEdit(rule)} className="cv-btn-ghost p-2" title={t('common.edit')}>
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button type="button" onClick={() => onDuplicate(rule)} className="cv-btn-ghost p-2" title={t('rules.duplicate')}>
                    <Copy className="w-4 h-4" />
                  </button>
                  <button type="button" onClick={() => onDelete(rule)} className="cv-btn-ghost p-2 text-red-500" title={t('common.delete')}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                  {rule.enabled ? (
                    <button
                      type="button"
                      disabled={busyId === rule.id}
                      onClick={() => {
                        flash(rule.id, rule.name, false);
                        onDisable(rule);
                      }}
                      data-testid={`rule-toggle-${rule.id}`}
                      className="cv-btn-secondary text-xs py-1.5 px-2 min-h-10 min-w-10 flex items-center justify-center"
                      aria-label={t('rules.disable')}
                    >
                      <PowerOff className="w-3.5 h-3.5" />
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={busyId === rule.id}
                      onClick={() => {
                        flash(rule.id, rule.name, true);
                        onEnable(rule.id);
                      }}
                      data-testid={`rule-toggle-${rule.id}`}
                      className="cv-btn-secondary text-xs py-1.5 px-2 min-h-10 min-w-10 flex items-center justify-center"
                      aria-label={t('rules.enable')}
                    >
                      <Power className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
