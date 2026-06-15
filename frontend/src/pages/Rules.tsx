import { useMemo, useState } from 'react';
import type { RuleCatalogTemplate } from '@/types';
import { useTranslation } from 'react-i18next';
import { BookOpen } from 'lucide-react';
import PageShell from '@/components/ui/PageShell';
import RuleCatalogPanel from '@/components/rules/RuleCatalogPanel';
import RuleStudioDialog from '@/components/rules/RuleStudioDialog';
import ActiveRulesPanel from '@/components/rules/ActiveRulesPanel';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import { RulesSkeleton } from '@/components/ui/Skeleton';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import { rulesApi } from '@/api/client';
import { useRules, useRuleCatalog } from '@/hooks/api/queries';
import { useAuthStore } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';
import { useUndoToast } from '@/hooks/useUndoToast';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import type { Rule } from '@/types';

export default function Rules() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const { showUndo, ToastContainer } = useUndoToast();
  const orgId = useAuthStore((s) => s.orgId);
  const { data: rules = [], isLoading, isError, refetch } = useRules();
  const catalog = useRuleCatalog();
  const startRulesTour = useAutoPageTour('rules');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editRule, setEditRule] = useState<Rule | null>(null);
  const [configuringTemplate, setConfiguringTemplate] = useState<RuleCatalogTemplate | null>(null);
  const [pickTemplate, setPickTemplate] = useState(false);
  const [confirm, setConfirm] = useState<{ type: 'delete' | 'disable'; rule: Rule } | null>(null);

  const occupiedTemplateIds = useMemo(
    () =>
      rules
        .map((r) => String((r.definition?.bindings as Record<string, unknown>)?.template_id ?? ''))
        .filter(Boolean),
    [rules],
  );

  const activeTemplateIds = useMemo(
    () =>
      rules
        .filter((r) => r.enabled)
        .map((r) => String((r.definition?.bindings as Record<string, unknown>)?.template_id ?? ''))
        .filter(Boolean),
    [rules],
  );

  const runDelete = async (rule: Rule) => {
    if (!orgId) return;
    playClick();
    setBusyId(rule.id);
    try {
      await rulesApi.delete(orgId, rule.id);
      showUndo(t('rules.deletedToast', { name: rule.name }), async () => {
        await rulesApi.create(orgId, {
          name: rule.name,
          definition: rule.definition ?? {},
          description: rule.description,
        });
        void refetch();
      });
      void refetch();
    } finally {
      setBusyId(null);
      setConfirm(null);
    }
  };

  const runDisable = async (rule: Rule) => {
    if (!orgId) return;
    playClick();
    setBusyId(rule.id);
    try {
      await rulesApi.disable(orgId, rule.id);
      void refetch();
    } catch {
      window.alert(t('rules.disableError'));
    } finally {
      setBusyId(null);
      setConfirm(null);
    }
  };

  const runEnable = async (ruleId: string) => {
    if (!orgId) return;
    playClick();
    setBusyId(ruleId);
    try {
      await rulesApi.enable(orgId, ruleId);
      void refetch();
    } finally {
      setBusyId(null);
    }
  };

  const runDuplicate = async (rule: Rule) => {
    if (!orgId) return;
    playClick();
    await rulesApi.create(orgId, {
      name: `${rule.name} (${t('rules.copySuffix')})`,
      definition: rule.definition ?? {},
      description: rule.description,
    });
    void refetch();
  };

  if (isLoading || catalog.isLoading) {
    return (
      <PageShell title={t('rules.title')} onHelpTour={startRulesTour}>
        <RulesSkeleton />
      </PageShell>
    );
  }

  if (isError || catalog.isError) {
    return (
      <PageShell title={t('rules.title')} onHelpTour={startRulesTour}>
        <ErrorState onRetry={() => { void refetch(); void catalog.refetch(); }} />
      </PageShell>
    );
  }

  return (
    <PageShell
      title={t('rules.title')}
      subtitle={t('rules.catalogSubtitle')}
      onHelpTour={startRulesTour}
    >
      <ToastContainer />

      <section id="rules-catalog" className="cv-card p-5">
        <div className="flex items-center gap-2 mb-4">
          <BookOpen className="w-5 h-5 text-cv-accent" />
          <h2 className="font-display text-lg font-semibold">{t('rules.catalog')}</h2>
        </div>
        <RuleCatalogPanel
          templates={catalog.data ?? []}
          occupiedTemplateIds={occupiedTemplateIds}
          activeTemplateIds={activeTemplateIds}
          onConfigure={setConfiguringTemplate}
          onActivated={() => void refetch()}
          catalogOnly
        />
      </section>

      {rules.length === 0 ? (
        <EmptyState title={t('rules.empty')} hint={t('rules.emptyHint')} />
      ) : (
        <ActiveRulesPanel
          rules={rules}
          busyId={busyId}
          onEdit={setEditRule}
          onDelete={(r) => setConfirm({ type: 'delete', rule: r })}
          onDisable={(r) => setConfirm({ type: 'disable', rule: r })}
          onEnable={runEnable}
          onDuplicate={(r) => void runDuplicate(r)}
          onNewRule={() => setPickTemplate(true)}
        />
      )}

      {configuringTemplate && (
        <RuleStudioDialog
          template={configuringTemplate}
          onClose={() => setConfiguringTemplate(null)}
          onActivated={() => {
            setConfiguringTemplate(null);
            void refetch();
          }}
        />
      )}

      {editRule && (
        <RuleStudioDialog
          template={null}
          existingRule={editRule}
          onClose={() => setEditRule(null)}
          onActivated={() => void refetch()}
        />
      )}

      {pickTemplate && (
        <div className="fixed inset-0 z-40 flex items-center justify-center p-4 bg-black/50">
          <div className="cv-card max-w-lg w-full p-5 max-h-[80vh] overflow-y-auto">
            <h3 className="font-display font-semibold mb-3">{t('rules.pickTemplate')}</h3>
            <RuleCatalogPanel
              templates={(catalog.data ?? []).filter((tpl) => tpl.supported !== false)}
              occupiedTemplateIds={[]}
              activeTemplateIds={[]}
              onConfigure={(tpl) => {
                setPickTemplate(false);
                setConfiguringTemplate(tpl);
              }}
              onActivated={() => {
                setPickTemplate(false);
                void refetch();
              }}
              compact
              catalogOnly
            />
            <button type="button" className="cv-btn-secondary w-full mt-4" onClick={() => setPickTemplate(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirm?.type === 'delete'}
        title={t('rules.confirmDeleteTitle')}
        message={t('rules.confirmDeleteMessage', { name: confirm?.rule.name ?? '' })}
        confirmLabel={t('common.delete')}
        danger
        onConfirm={() => confirm && void runDelete(confirm.rule)}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm?.type === 'disable'}
        title={t('rules.confirmDisableTitle')}
        message={t('rules.confirmDisableMessage', { name: confirm?.rule.name ?? '' })}
        confirmLabel={t('rules.disable')}
        onConfirm={() => confirm && void runDisable(confirm.rule)}
        onCancel={() => setConfirm(null)}
      />
    </PageShell>
  );
}
