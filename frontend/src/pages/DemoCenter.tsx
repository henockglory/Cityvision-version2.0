import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
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

const STEPS = [
  { n: 1, title: 'Regardez la vidéo', body: 'Flux benedicte.mp4 en boucle. Badge LIVE = OK.', href: null },
  { n: 2, title: 'Dessinez une zone', body: '3 clics → Fermer polygone → Enregistrer.', href: '/zones', cta: 'Éditeur de zones' },
  { n: 3, title: 'Activez une règle', body: 'Catalogue ci-dessous → Activer.', href: '/rules?catalog=1', cta: 'Toutes les règles' },
  { n: 4, title: 'Alertes & détections', body: 'Résultats en direct (30–60 s après activation).', href: '/alerts', cta: 'Centre d\'alertes' },
] as const;

export default function DemoCenter() {
  const orgId = useAuthStore((s) => s.orgId);
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
            Ministère · Urbanisme & Transport · Kinshasa
          </p>
          <h1 className="text-2xl md:text-3xl font-display font-semibold tracking-tight">
            Démonstration CitéVision
          </h1>
          <p className="text-sm text-cv-muted mt-1 max-w-xl">
            Vidéo, zonage, règles et alertes — prêt pour présentation client.
          </p>
        </div>
        <button type="button" onClick={() => void refresh()} className="cv-btn-secondary text-sm">
          <RefreshCw className="w-4 h-4" />
          Actualiser
        </button>
      </header>

      <div className="flex flex-wrap gap-2 text-xs">
        <StatusChip label="Serveur" ok={services.backend} />
        <StatusChip label="Vidéo" ok={services.go2rtc} />
        <StatusChip label="Analyse IA" ok={services.ai} />
        <StatusChip label="GPU CUDA" ok={services.cuda} />
        <StatusChip label="Détections" ok={recentEvents.length > 0} />
        <StatusChip label="Alertes" ok={recentAlerts.length > 0} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 space-y-4">
          <div className="cv-card overflow-hidden p-0">
            <Go2RtcPlayer className="aspect-video w-full min-h-[280px]" src={DEFAULT_STREAM} />
          </div>
        </div>

        <div className="space-y-3">
          <h2 className="text-sm font-semibold">Parcours (4 étapes)</h2>
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
          Étape 3 — Catalogue de règles
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
          title="Détections live"
          icon={Activity}
          empty="En attente… laissez la vidéo tourner 30–60 s."
          link="/events"
          items={recentEvents.map((e) => ({
            id: e.id,
            primary: e.typeLabel ?? e.type,
            secondary: e.cameraName,
            time: new Date(e.timestamp).toLocaleTimeString(),
          }))}
        />
        <FeedPanel
          title="Alertes live"
          icon={Bell}
          empty="Activez une règle du catalogue."
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
        <QuickLink to="/zones" icon={PenTool} label="Éditeur de zones" />
        <QuickLink to="/rules?catalog=1" icon={Workflow} label="Règles & catalogue" />
        <QuickLink to="/events" icon={Activity} label="Événements" />
        <QuickLink to="/alerts" icon={Bell} label="Alertes" />
      </div>
    </div>
  );
}

function StatusChip({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className={`px-3 py-1 rounded-full border text-xs ${
      ok ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400' : 'border-cv-border bg-cv-surface text-cv-muted'
    }`}>
      {label}{ok ? ' ✓' : ' …'}
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
  return (
    <div className="cv-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-cv-border">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Icon className="w-4 h-4 text-cv-accent" />
          {title}
          <span className="text-cv-muted font-normal">({items.length})</span>
        </div>
        <Link to={link} className="text-xs text-cv-accent hover:underline">Tout voir</Link>
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
                    <Check className="w-3 h-3" /> Acquitter
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
