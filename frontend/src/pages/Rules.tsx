import { useMemo, useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { RuleCatalogTemplate } from '@/types';
import { useTranslation } from 'react-i18next';
import { BookOpen, TrafficCone } from 'lucide-react';
import { loadRuleGuides } from '@/i18n/loadRuleGuides';
import PageShell from '@/components/ui/PageShell';
import RuleCatalogPanel from '@/components/rules/RuleCatalogPanel';
import RuleStudioDialog from '@/components/rules/RuleStudioDialog';
import RedLightAssistant from '@/components/rules/RedLightAssistant';
import ActiveRulesPanel from '@/components/rules/ActiveRulesPanel';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import { RulesSkeleton } from '@/components/ui/Skeleton';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import { orgApi, rulesApi, zonesApi } from '@/api/client';
import { useRules, useRuleCatalog } from '@/hooks/api/queries';
import { useAuthStore } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';
import { useUndoToast } from '@/hooks/useUndoToast';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import SegmentedTabs from '@/components/ui/SegmentedTabs';
import GuideIllustration from '@/components/ui/GuideIllustration';
import type { Rule } from '@/types';

export default function Rules() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { playClick } = useSound();
  const { showUndo, ToastContainer } = useUndoToast();
  const orgId = useAuthStore((s) => s.orgId);
  const { data: rules = [], isLoading, isError, refetch } = useRules();
  const catalog = useRuleCatalog();
  const startRulesTour = useAutoPageTour('rules');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editRule, setEditRule] = useState<Rule | null>(null);
  const [editInitialStep, setEditInitialStep] = useState<1 | 2 | 3 | 4>(1);
  const [configuringTemplate, setConfiguringTemplate] = useState<RuleCatalogTemplate | null>(null);
  const [pickTemplate, setPickTemplate] = useState(false);
  const [confirm, setConfirm] = useState<{ type: 'delete' | 'disable' | 'reset-all'; rule?: Rule } | null>(null);
  const [resetting, setResetting] = useState(false);
  const [deploymentScope, setDeploymentScope] = useState<'all' | 'national' | 'enterprise' | 'domestic'>('all');
  const [orgDeployLoaded, setOrgDeployLoaded] = useState(false);
  const [highlightedRuleId, setHighlightedRuleId] = useState<string | null>(null);
  const [redLightOpen, setRedLightOpen] = useState(false);
  const [assistantZones, setAssistantZones] = useState<Array<{ name: string; behavior?: string }>>([]);

  const flashRuleHighlight = (ruleId: string) => {
    setHighlightedRuleId(ruleId);
    window.setTimeout(() => {
      setHighlightedRuleId((cur) => (cur === ruleId ? null : cur));
    }, 2000);
  };

  const ruleOrigin = (rule: Rule) => String((rule.definition?.bindings as Record<string, unknown>)?.origin ?? '');

  const userRules = useMemo(() => rules.filter((r) => ruleOrigin(r) === 'user'), [rules]);

  const occupiedTemplateIds = useMemo(
    () =>
      userRules
        .map((r) => String((r.definition?.bindings as Record<string, unknown>)?.template_id ?? ''))
        .filter(Boolean),
    [userRules],
  );

  const location = useLocation();
  const navState = location.state as {
    editRuleId?: string;
    editStep?: 1 | 2 | 3 | 4;
    configureTemplateId?: string;
  } | null;

  useEffect(() => {
    if (!navState?.editRuleId || rules.length === 0) return;
    const rule = rules.find((r) => r.id === navState.editRuleId);
    if (rule) {
      setEditInitialStep(navState.editStep ?? 3);
      setEditRule(rule);
      window.history.replaceState({}, document.title);
    }
  }, [navState?.editRuleId, navState?.editStep, rules]);

  useEffect(() => {
    if (!navState?.configureTemplateId || !catalog.data?.length) return;
    const tpl = catalog.data.find((t) => t.id === navState.configureTemplateId);
    if (tpl) {
      if (tpl.id === 'tpl-red-light') {
        setRedLightOpen(true);
      } else {
        setConfiguringTemplate(tpl);
      }
      window.history.replaceState({}, document.title);
    }
  }, [navState?.configureTemplateId, catalog.data]);

  const handleConfigureTemplate = (tpl: RuleCatalogTemplate) => {
    if (tpl.id === 'tpl-red-light') {
      setRedLightOpen(true);
      return;
    }
    setConfiguringTemplate(tpl);
  };

  useEffect(() => {
    if (!orgId) return;
    if (orgDeployLoaded) return;
    void orgApi
      .get(orgId)
      .then((r) => {
        const profile = (r.data.notification_prefs as Record<string, unknown> | undefined)?.deployment_profile;
        if (profile === 'national' || profile === 'enterprise' || profile === 'domestic') {
          setDeploymentScope(profile);
        } else {
          setDeploymentScope('enterprise');
        }
      })
      .catch(() => undefined)
      .finally(() => setOrgDeployLoaded(true));
  }, [orgId, orgDeployLoaded]);

  useEffect(() => {
    void loadRuleGuides();
  }, []);

  useEffect(() => {
    if (!redLightOpen || !orgId) return;
    void zonesApi.list(orgId).then((res) => {
      const rows = res.data ?? [];
      setAssistantZones(
        rows.map((z) => {
          const bc = z.behavior_config as { behavior?: string } | undefined;
          return { name: z.name, behavior: bc?.behavior };
        }),
      );
    }).catch(() => setAssistantZones([]));
  }, [redLightOpen, orgId]);

  const activeTemplateIds = useMemo(
    () =>
      userRules
        .filter((r) => r.enabled)
        .map((r) => String((r.definition?.bindings as Record<string, unknown>)?.template_id ?? ''))
        .filter(Boolean),
    [userRules],
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

  const [inlineError, setInlineError] = useState('');

  const runResetAll = async () => {
    if (!orgId) return;
    setResetting(true);
    setInlineError('');
    try {
      for (const rule of userRules) {
        await rulesApi.delete(orgId, rule.id);
      }
      void refetch();
    } catch {
      setInlineError(t('rules.resetError', { defaultValue: 'Erreur lors de la réinitialisation. Veuillez réessayer.' }));
    } finally {
      setResetting(false);
      setConfirm(null);
    }
  };

  const runDisable = async (rule: Rule) => {
    if (!orgId) return;
    playClick();
    setBusyId(rule.id);
    setInlineError('');
    try {
      await rulesApi.disable(orgId, rule.id);
      void refetch();
    } catch {
      setInlineError(t('rules.disableError'));
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
    setInlineError('');
    try {
      const res = await rulesApi.create(orgId, {
        name: `${rule.name} (${t('rules.copySuffix')})`,
        definition: rule.definition ?? {},
        description: rule.description,
      });
      await rulesApi.disable(orgId, res.data.id);
      await refetch();
      setEditInitialStep(1);
      setEditRule({ ...res.data, enabled: false });
      flashRuleHighlight(res.data.id);
    } catch {
      setInlineError(t('rules.duplicateError', { defaultValue: 'Impossible de dupliquer cette règle.' }));
    }
  };


  if (isLoading || catalog.isLoading) {
    return (
      <PageShell title={t('rules.title')} onHelpTour={startRulesTour} tourTriggerAttr="rules-help">
        <RulesSkeleton />
      </PageShell>
    );
  }

  if (isError || catalog.isError) {
    return (
      <PageShell title={t('rules.title')} onHelpTour={startRulesTour} tourTriggerAttr="rules-help">
        <ErrorState onRetry={() => { void refetch(); void catalog.refetch(); }} />
      </PageShell>
    );
  }

  return (
    <PageShell
      title={t('rules.title')}
      subtitle={t('rules.catalogSubtitle')}
      onHelpTour={startRulesTour}
      tourTriggerAttr="rules-help"
    >
      <ToastContainer />

      {inlineError && (
        <div className="mb-4 flex items-start gap-2 text-sm bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-4 py-3">
          <span className="flex-1">{inlineError}</span>
          <button type="button" className="cv-btn-ghost p-0.5" onClick={() => setInlineError('')} aria-label={t('common.cancel')}>×</button>
        </div>
      )}

      <GuideIllustration
        variant="rules"
        imageRole="catalog"
        title={t('rules.guide.bannerTitle')}
        caption={
          deploymentScope === 'national'
            ? t('rules.guide.national')
            : deploymentScope === 'domestic'
              ? t('rules.guide.domestic')
              : deploymentScope === 'enterprise'
                ? t('rules.guide.enterprise')
                : t('rules.guide.all')
        }
      />

      <section id="rules-catalog" className="cv-card p-5">
        <header className="flex items-center gap-3 mb-4 flex-wrap">
          <BookOpen className="w-5 h-5 text-cv-accent shrink-0" />
          <h2 className="cv-section-title flex-1">{t('rules.catalog')}</h2>
          <button
            type="button"
            className="cv-btn-secondary text-xs inline-flex items-center gap-1.5"
            onClick={() => setRedLightOpen(true)}
          >
            <TrafficCone className="w-3.5 h-3.5" />
            {t('rules.redLightAssistant.launch', { defaultValue: 'Assistant feu rouge' })}
          </button>
        </header>

        <div className="space-y-4">
          <SegmentedTabs
            tabs={[
              { id: 'national', label: t('rules.scope.national') },
              { id: 'enterprise', label: t('rules.scope.enterprise') },
              { id: 'domestic', label: t('rules.scope.domestic') },
              { id: 'all', label: t('rules.scope.all') },
            ]}
            value={deploymentScope}
            onChange={(id) => setDeploymentScope(id as 'all' | 'national' | 'enterprise' | 'domestic')}
            className="w-full sm:w-auto"
          />

          <RuleCatalogPanel
          templates={catalog.data ?? []}
          occupiedTemplateIds={occupiedTemplateIds}
          activeTemplateIds={activeTemplateIds}
          onConfigure={handleConfigureTemplate}
          onActivated={() => void refetch()}
          catalogOnly
          deploymentScope={deploymentScope}
        />
        </div>
      </section>

      {userRules.length === 0 ? (
        <EmptyState
          title={t('rules.empty')}
          hint={t('rules.emptyHint')}
          guideVariant="rules"
          action={
            <button className="cv-btn-primary inline-flex items-center gap-2" onClick={() => setPickTemplate(true)}>
              <BookOpen className="w-4 h-4" />
              Parcourir le catalogue de règles
            </button>
          }
        />
      ) : (
        <ActiveRulesPanel
          rules={userRules}
          busyId={busyId}
          highlightedRuleId={highlightedRuleId}
          onHighlight={flashRuleHighlight}
          onEdit={(r) => { setEditInitialStep(1); setEditRule(r); }}
          onEditEvidence={(r) => { setEditInitialStep(3); setEditRule(r); }}
          onDelete={(r) => setConfirm({ type: 'delete', rule: r })}
          onDisable={(r) => setConfirm({ type: 'disable', rule: r })}
          onEnable={runEnable}
          onDuplicate={(r) => void runDuplicate(r)}
          onNewRule={() => setPickTemplate(true)}
          onResetAll={() => setConfirm({ type: 'reset-all' })}
          resetting={resetting}
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
          initialStep={editInitialStep}
          onClose={() => setEditRule(null)}
          onActivated={() => void refetch()}
        />
      )}

      {pickTemplate && (
        <div className="fixed inset-0 z-40 flex items-center justify-center p-4 bg-black/50">
          <div className="cv-card max-w-lg w-full p-5 max-h-[80vh] overflow-y-auto cv-stack-md">
            <h3 className="font-display font-semibold text-lg leading-tight">{t('rules.pickTemplate')}</h3>
            <RuleCatalogPanel
              templates={(catalog.data ?? []).filter((tpl) => tpl.supported !== false)}
              occupiedTemplateIds={[]}
              activeTemplateIds={[]}
              onConfigure={(tpl) => {
                setPickTemplate(false);
                handleConfigureTemplate(tpl);
              }}
              onActivated={() => {
                setPickTemplate(false);
                void refetch();
              }}
              compact
              catalogOnly
              deploymentScope="all"
            />
            <button type="button" className="cv-btn-secondary w-full" onClick={() => setPickTemplate(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirm?.type === 'delete'}
        title={t('rules.confirmDeleteTitle')}
        message={t('rules.confirmDeleteMessage', { name: confirm?.rule?.name ?? '' })}
        confirmLabel={t('common.delete')}
        danger
        onConfirm={() => confirm?.rule && void runDelete(confirm.rule)}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm?.type === 'disable'}
        title={t('rules.confirmDisableTitle')}
        message={t('rules.confirmDisableMessage', { name: confirm?.rule?.name ?? '' })}
        confirmLabel={t('rules.disable')}
        onConfirm={() => confirm?.rule && void runDisable(confirm.rule)}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm?.type === 'reset-all'}
        title={t('rules.confirmResetAllTitle', { defaultValue: 'Réinitialiser toutes les règles ?' })}
        message={t('rules.confirmResetAllMessage', { count: userRules.length, defaultValue: `Cette action supprimera définitivement {{count}} règles configurées. Vous repartirez d'une page vierge.` })}
        confirmLabel={t('rules.resetAll', { defaultValue: 'Réinitialiser toutes les règles' })}
        danger
        onConfirm={() => void runResetAll()}
        onCancel={() => setConfirm(null)}
      />

      <RedLightAssistant
        open={redLightOpen}
        onClose={() => setRedLightOpen(false)}
        zones={assistantZones}
        onOpenZoneEditor={() => navigate('/zones')}
        onOpenRule={() => {
          const tpl = (catalog.data ?? []).find((t) => t.id === 'tpl-red-light');
          if (tpl) setConfiguringTemplate(tpl);
        }}
      />
    </PageShell>
  );
}
