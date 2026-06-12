import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Workflow, ToggleLeft, ToggleRight, Zap, Bell, Video } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import RuleFlowBuilder from '@/components/rules/RuleFlowBuilder';
import LoadingState from '@/components/ui/LoadingState';
import { useRules } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';

const conditionIcons: Record<string, typeof Zap> = {
  motion: Zap,
  zone: Workflow,
  line: Workflow,
  schedule: Workflow,
  object: Zap,
};

const actionIcons: Record<string, typeof Bell> = {
  alert: Bell,
  record: Video,
  notify: Bell,
  relay: Zap,
};

export default function Rules() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const { data: fetchedRules = [], isLoading } = useRules();
  const [enabledOverrides, setEnabledOverrides] = useState<Record<string, boolean>>({});

  const rules = useMemo(
    () => fetchedRules.map((r) => ({ ...r, enabled: enabledOverrides[r.id] ?? r.enabled })),
    [fetchedRules, enabledOverrides]
  );

  if (isLoading) return <LoadingState />;

  const toggleRule = (id: string) => {
    playClick();
    const rule = fetchedRules.find((r) => r.id === id);
    if (!rule) return;
    const current = enabledOverrides[id] ?? rule.enabled;
    setEnabledOverrides((prev) => ({ ...prev, [id]: !current }));
  };

  return (
    <div>
      <PageHeader
        title={t('rules.title')}
        actions={
          <button type="button" onClick={() => playClick()} className="cv-btn-primary">
            <Plus className="w-4 h-4" />
            {t('rules.add')}
          </button>
        }
      />

      <div className="space-y-4">
        {rules.map((rule) => (
          <div key={rule.id} className="cv-card-hover p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-cv-accent/10 border border-cv-accent/20">
                  <Workflow className="w-5 h-5 text-cv-accent" />
                </div>
                <div>
                  <h3 className="font-display text-lg font-semibold">{rule.name}</h3>
                  <p className="text-xs text-cv-muted">{rule.cameraIds.length} caméra(s)</p>
                </div>
              </div>
              <button type="button" onClick={() => toggleRule(rule.id)} className="text-cv-accent">
                {rule.enabled ? <ToggleRight className="w-8 h-8" /> : <ToggleLeft className="w-8 h-8 text-cv-muted" />}
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-lg bg-cv-deep/50 border border-cv-border">
                <p className="text-xs text-cv-muted uppercase tracking-wider mb-3">{t('rules.conditions')}</p>
                <div className="flex flex-wrap gap-2">
                  {rule.conditions.map((cond) => {
                    const Icon = conditionIcons[cond.type] ?? Zap;
                    return (
                      <div key={cond.id} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cv-surface border border-cv-border text-sm">
                        <Icon className="w-3.5 h-3.5 text-cv-accent" />
                        <span className="capitalize">{cond.type}</span>
                      </div>
                    );
                  })}
                  <button type="button" onClick={() => playClick()} className="px-3 py-1.5 rounded-lg border border-dashed border-cv-border text-cv-muted text-sm hover:border-cv-accent/40">
                    +
                  </button>
                </div>
              </div>

              <div className="p-4 rounded-lg bg-cv-deep/50 border border-cv-border">
                <p className="text-xs text-cv-muted uppercase tracking-wider mb-3">{t('rules.actions')}</p>
                <div className="flex flex-wrap gap-2">
                  {rule.actions.map((action) => {
                    const Icon = actionIcons[action.type] ?? Bell;
                    return (
                      <div key={action.id} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cv-accent/10 border border-cv-accent/20 text-sm text-cv-accent">
                        <Icon className="w-3.5 h-3.5" />
                        <span className="capitalize">{action.type}</span>
                      </div>
                    );
                  })}
                  <button type="button" onClick={() => playClick()} className="px-3 py-1.5 rounded-lg border border-dashed border-cv-border text-cv-muted text-sm hover:border-cv-accent/40">
                    +
                  </button>
                </div>
              </div>
            </div>

            <RuleFlowBuilder rule={rule} />

            <div className="mt-3 flex items-center gap-2">
              <span className={`cv-badge ${rule.enabled ? 'cv-badge-online' : 'cv-badge-offline'}`}>
                {rule.enabled ? t('rules.enabled') : t('rules.disabled')}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
