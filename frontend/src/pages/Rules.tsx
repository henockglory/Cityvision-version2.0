import { useTranslation } from 'react-i18next';
import { Plus, Workflow } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import RuleFlowBuilder from '@/components/rules/RuleFlowBuilder';
import LoadingState from '@/components/ui/LoadingState';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import { useRules } from '@/hooks/api/queries';
import { useSound } from '@/hooks/useSound';

export default function Rules() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const { data: rules = [], isLoading, isError, refetch } = useRules();

  if (isLoading) return <LoadingState />;

  if (isError) {
    return (
      <div>
        <PageHeader title={t('rules.title')} />
        <ErrorState onRetry={() => void refetch()} />
      </div>
    );
  }

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

      {rules.length === 0 ? (
        <EmptyState title={t('rules.empty')} hint={t('rules.emptyHint')} icon={Workflow} />
      ) : (
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
                    <p className="text-xs text-cv-muted">
                      {rule.cameraIds.length} caméra(s) · {rule.enabled ? t('rules.enabled') : t('rules.disabled')}
                    </p>
                  </div>
                </div>
              </div>
              {(rule.conditions.length > 0 || rule.actions.length > 0) && (
                <RuleFlowBuilder rule={rule} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
