import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  PenTool, Workflow, Bell, Activity, ChevronRight, RefreshCw, Check,
} from 'lucide-react';
import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';
import RuleCatalogPanel from '@/components/rules/RuleCatalogPanel';
import RuleActivationDialog from '@/components/rules/RuleActivationDialog';
import { rulesApi } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import type { RuleCatalogTemplate } from '@/types';
import {
  useAlerts, useEvents, useRules, useRuleCatalog, useAcknowledgeAlert,
} from '@/hooks/api/queries';
import { AI_ENGINE_HEALTH, DEFAULT_STREAM, GO2RTC_STREAMS_API } from '@/config/streams';

type StepDef = { n: number; title: string; body: string; href: string | null; cta?: string };

function go2rtcStreamHealthy(stream: unknown): boolean {
  if (!stream || typeof stream !== 'object') return false;
  const s = stream as {
    producers?: { url?: string; medias?: string[] }[];
    consumers?: unknown[];
  };
  const producers = s.producers ?? [];
  if (producers.length === 0) return false;
  return producers.some(
    (p) => Boolean(p.url) || (p.medias?.length ?? 0) > 0,
  );
}

export default function DemoCenter() {
  const { t } = useTranslation();
  const orgId = useAuthStore((s) => s.orgId);

  const STEPS: StepDef[] = [
    { n: 1, title: t('demoCenter.step1Title'), body: t('demoCenter.step1Body'), href: null },
    { n: 2, title: t('demoCenter.step2Title'), body: t('demoCenter.step2Body'), href: '/zones', cta: t('demoCenter.step2Cta') },
    { n: 3, title: t('demoCenter.step3Title'), body: t('demoCenter.step3Body'), href: '/rules?catalog=1', cta: t('demoCenter.step3Cta') },
    { n: 4, title: t('demoCenter.step4Title'), body: t('demoCenter.step4Body'), href: '/alerts', cta: t('demoCenter.step4Cta') },
  ];
  const events = useEvents();
  const alerts = useAlerts();
  const rules = useRules();
  const catalog = useRuleCatalog();
  const ack = useAcknowledgeAlert();
  const [services, setServices] = useState({ go2rtc: false, ai: false, backend: true, cuda: false });
  const [configuringTemplate, setConfiguringTemplate] = useState<RuleCatalogTemplate | null>(null);

  const refresh = useCallback(async () => {
    const [g, a] = await Promise.all([
      fetch(GO2RTC_STREAMS_API).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(AI_ENGINE_HEALTH).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]);
    setServices({
      go2rtc: go2rtcStreamHealthy(g?.[DEFAULT_STREAM]),
      ai: a?.yolo_loaded === 'true',
      cuda: a?.yolo_cuda === 'true',
      backend: true,
    });
    void events.refetch();
    void alerts.refetch();
    void rules.refetch();
    void catalog.refetch();
  }, [events, alerts, rules, catalog]);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const recentEvents = (events.data ?? []).slice(0, 8);
  const recentAlerts = (alerts.data ?? []).slice(0, 5);
  const rulesList = rules.data ?? [];
  const rulesByTemplate = useMemo(() => {
    const m = new Map<string, (typeof rulesList)[0]>();
    for (const r of rulesList) {
      if (!r.enabled) continue;
      const tid = String((r.definition?.bindings as Record<string, unknown>)?.template_id ?? '');
      if (tid) m.set(tid, r);
    }
    return m;
  }, [rulesList]);
  const occupiedTemplateIds = rulesList
    .map((r) => String((r.definition?.bindings as Record<string, unknown>)?.template_id ?? ''))
    .filter(Boolean);
  const activeTemplateIds = [...rulesByTemplate.keys()];

  return (
    <div className="max-w-7xl mx-auto space-y-6 pb-12">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-cv-accent mb-1">
            {t('demoCenter.context')}
          </p>
          <h1 className="text-2xl md:text-3xl font-display font-semibold tracking-tight">
            {t('demoCenter.title')}
          </h1>
          <p className="text-sm text-cv-muted mt-1 max-w-xl">
            {t('demoCenter.subtitle')}
          </p>
        </div>
        <button type="button" onClick={() => void refresh()} className="cv-btn-secondary text-sm">
          <RefreshCw className="w-4 h-4" />
          {t('demoCenter.refresh')}
        </button>
      </header>

      <div id="demo-status" className="flex flex-wrap gap-2 text-xs">
        <StatusChip label={t('demoCenter.serveur')} ok={services.backend} />
        <StatusChip label={t('demoCenter.video')} ok={services.go2rtc} />
        <StatusChip label={t('demoCenter.analyseIA')} ok={services.ai} />
        <StatusChip label={t('demoCenter.gpuCuda')} ok={services.cuda} />
        <StatusChip label={t('demoCenter.detections')} ok={recentEvents.length > 0} />
        <StatusChip label={t('demoCenter.alertes')} ok={recentAlerts.length > 0} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 space-y-4">
          <div className="cv-card overflow-hidden p-0">
            <Go2RtcPlayer className="aspect-video w-full min-h-[280px]" src={DEFAULT_STREAM} />
          </div>
        </div>

        <div className="space-y-3">
          <h2 className="text-sm font-semibold">{t('demoCenter.stepsTitle')}</h2>
          {STEPS.map((step) => (
            <div key={step.n} className="cv-card p-4">
              <div className="flex gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-cv-accent/20 text-cv-accent text-sm font-bold">
                  {step.n}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-sm">{step.title}</p>
                  <p className="text-xs text-cv-muted mt-1">{step.body}</p>
                  {step.href && step.cta && (
                    <Link to={step.href} className="inline-flex items-center gap-1 mt-2 text-xs font-medium text-cv-accent hover:underline">
                      {step.cta}
                      <ChevronRight className="w-3 h-3" />
                    </Link>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="cv-card p-5">
        <h2 className="font-display text-lg font-semibold mb-3 flex items-center gap-2">
          <Workflow className="w-5 h-5 text-cv-accent" />
          {t('demoCenter.step3Title')} — {t('rules.catalog')}
        </h2>
        <RuleCatalogPanel
          templates={catalog.data ?? []}
          occupiedTemplateIds={occupiedTemplateIds}
          activeTemplateIds={activeTemplateIds}
          rulesByTemplate={rulesByTemplate}
          onConfigure={setConfiguringTemplate}
          onDisable={(templateId) => {
            const rule =
              rulesByTemplate.get(templateId) ??
              rulesList.find(
                (r) =>
                  String((r.definition?.bindings as Record<string, unknown>)?.template_id ?? '') === templateId,
              );
            if (rule && orgId) void rulesApi.disable(orgId, rule.id).then(() => rules.refetch());
          }}
          onActivated={() => void rules.refetch()}
          compact
        />
      </div>

      {configuringTemplate && (
        <RuleActivationDialog
          template={configuringTemplate}
          onClose={() => setConfiguringTemplate(null)}
          onActivated={() => {
            setConfiguringTemplate(null);
            void rules.refetch();
          }}
        />
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FeedPanel
          title={t('demoCenter.detectionsLive')}
          icon={Activity}
          empty={t('demoCenter.emptyDetections')}
          link="/events"
          items={recentEvents.map((e) => ({
            id: e.id,
            primary: e.typeLabel ?? e.type,
            secondary: e.cameraName,
            time: new Date(e.timestamp).toLocaleTimeString(),
          }))}
        />
        <FeedPanel
          title={t('demoCenter.alertesLive')}
          icon={Bell}
          empty={t('demoCenter.emptyAlertes')}
          link="/alerts"
          items={recentAlerts.map((a) => ({
            id: a.id,
            primary: a.message,
            secondary: a.cameraName,
            time: new Date(a.timestamp).toLocaleTimeString(),
            acknowledged: a.acknowledged,
            onAck: () => void ack.mutate({ alertId: a.id }),
          }))}
        />
      </div>

      <div className="flex flex-wrap gap-3">
        <QuickLink to="/zones" icon={PenTool} label={t('nav.zoneEditor')} />
        <QuickLink to="/rules?catalog=1" icon={Workflow} label={t('nav.rules')} />
        <QuickLink to="/events" icon={Activity} label={t('nav.events')} />
        <QuickLink to="/alerts" icon={Bell} label={t('nav.alerts')} />
      </div>
    </div>
  );
}

function StatusChip({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className={`px-3 py-1 rounded-full border text-xs ${
      ok ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400' : 'border-cv-border bg-cv-surface text-cv-muted'
    }`} title={ok ? 'Opérationnel' : 'Hors ligne ou en attente'}>
      {label}{ok ? ' ✓' : ' ✗'}
    </span>
  );
}

function FeedPanel({
  title, icon: Icon, empty, link, items,
}: {
  title: string;
  icon: typeof Activity;
  empty: string;
  link: string;
  items: {
    id: string; primary: string; secondary: string; time: string;
    acknowledged?: boolean; onAck?: () => void;
  }[];
}) {
  const { t } = useTranslation();
  return (
    <div className="cv-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-cv-border">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Icon className="w-4 h-4 text-cv-accent" />
          {title}
          <span className="text-cv-muted font-normal">({items.length})</span>
        </div>
        <Link to={link} className="text-xs text-cv-accent hover:underline">{t('demoCenter.voirTout')}</Link>
      </div>
      <div className="max-h-52 overflow-y-auto divide-y divide-cv-border">
        {items.length === 0 ? (
          <p className="text-xs text-cv-muted p-4 text-center">{empty}</p>
        ) : (
          items.map((item) => (
            <div key={item.id} className="px-4 py-2.5 flex justify-between gap-2 text-sm">
              <div className="min-w-0 flex-1">
                <p className="truncate">{item.primary}</p>
                <p className="text-xs text-cv-muted truncate">{item.secondary}</p>
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <span className="text-xs text-cv-muted font-mono">{item.time}</span>
                {item.onAck && !item.acknowledged && (
                  <button type="button" onClick={item.onAck} className="text-[10px] text-cv-accent flex items-center gap-0.5 hover:underline">
                    <Check className="w-3 h-3" /> {t('demoCenter.acquitter')}
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function QuickLink({ to, icon: Icon, label }: { to: string; icon: typeof PenTool; label: string }) {
  return (
    <Link to={to} className="cv-btn-secondary text-sm">
      <Icon className="w-4 h-4 text-cv-accent" />
      {label}
    </Link>
  );
}
