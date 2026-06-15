import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Pencil, Plus, Power, PowerOff, Trash2 } from 'lucide-react';
import IconBadge from '@/components/ui/IconBadge';
import SeverityBadge from '@/components/ui/SeverityBadge';
import { explainRule } from '@/lib/ruleExplainability';
import { iconForTemplate } from '@/lib/iconMap';
import type { Rule } from '@/types';

type Filter = 'all' | 'enabled' | 'disabled';

interface ActiveRulesPanelProps {
  rules: Rule[];
  busyId: string | null;
  onEdit: (rule: Rule) => void;
  onDelete: (rule: Rule) => void;
  onDisable: (rule: Rule) => void;
  onEnable: (ruleId: string) => void;
  onDuplicate: (rule: Rule) => void;
  onNewRule: () => void;
}

export default function ActiveRulesPanel({
  rules,
  busyId,
  onEdit,
  onDelete,
  onDisable,
  onEnable,
  onDuplicate,
  onNewRule,
}: ActiveRulesPanelProps) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<Filter>('all');

  const filtered = useMemo(() => {
    if (filter === 'enabled') return rules.filter((r) => r.enabled);
    if (filter === 'disabled') return rules.filter((r) => !r.enabled);
    return rules;
  }, [rules, filter]);

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
          {filtered.map((rule) => {
            const templateId = String((rule.definition?.bindings as Record<string, unknown>)?.template_id ?? '');
            return (
              <div
                key={rule.id}
                className="flex items-center gap-3 p-3 rounded-lg border border-cv-border/70 bg-cv-deep/30 hover:border-cv-accent/25 transition-all group"
              >
                <IconBadge
                  src={iconForTemplate(templateId, rule.category)}
                  alt=""
                  size="md"
                  className="cv-icon-spin-slow group-hover:shadow-glow"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-medium text-sm truncate">{rule.name}</p>
                    <SeverityBadge severity={(rule.severity ?? 'medium') as 'low' | 'medium' | 'high' | 'critical'} />
                    <span className={`text-[10px] uppercase font-semibold ${rule.enabled ? 'text-metric-rules' : 'text-cv-muted'}`}>
                      {rule.enabled ? t('rules.enabled') : t('rules.disabled')}
                    </span>
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
                      onClick={() => onDisable(rule)}
                      className="cv-btn-secondary text-xs py-1.5 px-2"
                    >
                      <PowerOff className="w-3.5 h-3.5" />
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={busyId === rule.id}
                      onClick={() => onEnable(rule.id)}
                      className="cv-btn-secondary text-xs py-1.5 px-2"
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
