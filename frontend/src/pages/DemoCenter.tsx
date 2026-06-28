import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  PenTool, Workflow, Bell, Activity, ChevronRight, RotateCcw,
} from 'lucide-react';
import DemoEditableHeader from '@/components/demo/DemoEditableHeader';
import DemoVideoPanel from '@/components/demo/DemoVideoPanel';
import DemoFeedPanel from '@/components/demo/DemoFeedPanel';
import DemoZoneInlinePanel from '@/components/demo/DemoZoneInlinePanel';
import RuleCatalogPanel from '@/components/rules/RuleCatalogPanel';
import RuleActivationDialog from '@/components/rules/RuleActivationDialog';
import { demoApi, rulesApi } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useQueryClient } from '@tanstack/react-query';
import type { RuleCatalogTemplate } from '@/types';
import {
  useAlerts, useEvents, useRules, useRuleCatalog, useAcknowledgeAlert, useDemoSettings, useCameras,
  queryKeys,
} from '@/hooks/api/queries';
import { AI_ENGINE_HEALTH, GO2RTC_STREAMS_API } from '@/config/streams';

const MAX_DEMO_EVENTS = 20;

type StepDef = { n: number; title: string; body: string; href?: string; cta?: string; onCtaClick?: () => void };

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

function isDemoPayload(raw: unknown): boolean {
  if (!raw || typeof raw !== 'object') return false;
  const p = raw as Record<string, unknown>;
  if (p.demo === true || p.demo === 'true') return true;
  const meta = p.metadata as Record<string, unknown> | undefined;
  return meta?.demo === true || meta?.demo === 'true';
}

function isDemoCameraMeta(meta: unknown): boolean {
  if (!meta || typeof meta !== 'object') return false;
  const m = meta as Record<string, unknown>;
  return m.demo === true || m.demo === 'true';
}

export default function DemoCenter() {
  const { t } = useTranslation();
  const orgId = useAuthStore((s) => s.orgId);
  const qc = useQueryClient();
  const demoSettings = useDemoSettings();
  const { data: cameras = [] } = useCameras();
  const [configuringTemplate, setConfiguringTemplate] = useState<RuleCatalogTemplate | null>(null);
  const [resetting, setResetting] = useState(false);
  const [explicitSourceKey, setExplicitSourceKey] = useState<string | null>(null);
  const [sourceKeySeeded, setSourceKeySeeded] = useState(false);
  const [services, setServices] = useState({ go2rtc: false, ai: false, backend: true, cuda: false });
  const zonePanelRef = useRef<HTMLDivElement>(null);
  const rulesCatalogRef = useRef<HTMLDivElement>(null);

  const activeStream = demoSettings.data?.active_go2rtc_src ?? '';

  const STEPS: StepDef[] = [
    { n: 1, title: t('demoCenter.step1Title'), body: t('demoCenter.step1Body') },
    { n: 2, title: t('demoCenter.step2Title'), body: t('demoCenter.step2Body') },
    {
      n: 3,
      title: t('demoCenter.step3Title'),
      body: t('demoCenter.step3Body'),
      cta: t('demoCenter.step3Cta', 'Voir le catalogue'),
      onCtaClick: () => rulesCatalogRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
    },
    { n: 4, title: t('demoCenter.step4Title'), body: t('demoCenter.step4Body'), href: '/alerts', cta: t('demoCenter.step4Cta') },
  ];

  const events = useEvents({ showAll: true });
  const alerts = useAlerts();
  const rules = useRules();
  const catalog = useRuleCatalog();
  const ack = useAcknowledgeAlert();

  // Use refs so the polling effect never needs to list query results as deps.
  // TanStack Query's .refetch and the data objects change identity every render,
  // so putting them in a useCallback/useEffect dep array causes an infinite loop.
  const eventsRef = useRef(events);
  const alertsRef = useRef(alerts);
  const rulesRef = useRef(rules);
  const catalogRef = useRef(catalog);
  const demoSettingsRef = useRef(demoSettings);
  const activeStreamRef = useRef(activeStream);
  eventsRef.current = events;
  alertsRef.current = alerts;
  rulesRef.current = rules;
  catalogRef.current = catalog;
  demoSettingsRef.current = demoSettings;
  activeStreamRef.current = activeStream;

  const doRefresh = useCallback(async () => {
    const stream = activeStreamRef.current;
    const checks: Promise<void>[] = [
      fetch(AI_ENGINE_HEALTH).then((r) => (r.ok ? r.json() : null)).then((a) => {
        setServices((s) => ({
          ...s,
          ai: a?.yolo_loaded === 'true',
          cuda: a?.yolo_cuda === 'true',
        }));
      }).catch(() => {}),
    ];
    if (stream) {
      checks.push(
        fetch(GO2RTC_STREAMS_API).then((r) => (r.ok ? r.json() : null)).then((g) => {
          setServices((s) => ({ ...s, go2rtc: go2rtcStreamHealthy(g?.[stream]) }));
        }).catch(() => {}),
      );
    } else {
      setServices((s) => ({ ...s, go2rtc: false }));
    }
    await Promise.all(checks);
    void eventsRef.current.refetch();
    void alertsRef.current.refetch();
    void rulesRef.current.refetch();
    void catalogRef.current.refetch();
    void demoSettingsRef.current.refetch();
  // Only depends on stable refs + setServices (which is stable from useState)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = doRefresh; // alias used by reset handler and header

  useEffect(() => {
    void doRefresh();
    const id = setInterval(doRefresh, 5000);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentionally empty: refs always hold the latest values

  const demoEvents = useMemo(() => {
    const all = events.data ?? [];
    return all.filter((e) => isDemoPayload(e.payload)).slice(0, MAX_DEMO_EVENTS);
  }, [events.data]);

  const demoAlerts = useMemo(() => {
    const all = alerts.data ?? [];
    return all.filter((a) => isDemoPayload(a.metadata)).slice(0, 5);
  }, [alerts.data]);

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

  const activeSourceKey = useMemo(() => {
    if (demoSettings.data?.source_mode === 'camera' && demoSettings.data.active_camera_id) {
      return `camera:${demoSettings.data.active_camera_id}`;
    }
    if (demoSettings.data?.source_mode !== 'camera' && demoSettings.data?.active_video_id) {
      return `video:${demoSettings.data.active_video_id}`;
    }
    return null;
  }, [demoSettings.data?.source_mode, demoSettings.data?.active_camera_id, demoSettings.data?.active_video_id]);

  const zoneCameraId = useMemo(() => {
    if (demoSettings.data?.source_mode === 'camera' && demoSettings.data.active_camera_id) {
      return demoSettings.data.active_camera_id;
    }
    if (demoSettings.data?.source_mode !== 'camera' && demoSettings.data?.active_video_id) {
      const activeVideoID = demoSettings.data.active_video_id;
      const demoCam = cameras.find((c) => {
        const meta = c.metadata as Record<string, unknown> | undefined;
        return isDemoCameraMeta(meta) && String(meta?.demo_video_id ?? '') === activeVideoID;
      });
      return demoCam?.id;
    }
    return undefined;
  }, [cameras, demoSettings.data?.source_mode, demoSettings.data?.active_camera_id, demoSettings.data?.active_video_id]);

  const zoneStreamSrc = useMemo(() => {
    if (!activeStream) return undefined;
    const videos = demoSettings.data?.videos ?? [];
    if (demoSettings.data?.source_mode !== 'camera') {
      const active = videos.find((v) => v.id === demoSettings.data?.active_video_id);
      if (!active || active.status !== 'ready') return undefined;
      return activeStream;
    }
    return activeStream;
  }, [activeStream, demoSettings.data?.source_mode, demoSettings.data?.active_video_id, demoSettings.data?.videos]);

  const canEditZones = Boolean(
    zoneCameraId
    && zoneStreamSrc
    && activeSourceKey
    && explicitSourceKey === activeSourceKey,
  );

  const demoCameraIds = useMemo(() => {
    if (zoneCameraId) return [zoneCameraId];
    return cameras
      .filter((c) => isDemoCameraMeta(c.metadata))
      .map((c) => c.id);
  }, [cameras, zoneCameraId]);

  // Seed explicitSourceKey from DB state on first load (restores session after page refresh).
  useEffect(() => {
    if (!sourceKeySeeded && activeSourceKey && demoSettings.data) {
      setExplicitSourceKey(activeSourceKey);
      setSourceKeySeeded(true);
    }
  }, [activeSourceKey, demoSettings.data, sourceKeySeeded]);

  // Invalidate cameras when a video transitions to ready (virtual camera was just created).
  const prevVideoStatuses = useRef<Record<string, string>>({});
  useEffect(() => {
    const videos = demoSettings.data?.videos ?? [];
    for (const v of videos) {
      const prev = prevVideoStatuses.current[v.id];
      if (prev && prev !== 'ready' && v.status === 'ready') {
        void qc.invalidateQueries({ queryKey: queryKeys.cameras });
      }
    }
    prevVideoStatuses.current = Object.fromEntries(videos.map((v) => [v.id, v.status]));
  }, [demoSettings.data?.videos, qc]);

  const handleEditZones = useCallback(async (videoId: string) => {
    if (!orgId) return;
    // Activate the video if it's not already the active source.
    if (demoSettings.data?.active_video_id !== videoId) {
      try {
        await demoApi.patchSettings(orgId, { active_video_id: videoId, active_camera_id: null, source_mode: 'video' });
        void demoSettings.refetch();
        void qc.invalidateQueries({ queryKey: queryKeys.cameras });
      } catch { /* best-effort */ }
    }
    setExplicitSourceKey(`video:${videoId}`);
    // Scroll to zone panel after a short delay to allow React to re-render.
    setTimeout(() => {
      zonePanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 350);
  }, [orgId, demoSettings, qc]);

  const handleReset = async () => {
    if (!orgId || !window.confirm(t('demoCenter.resetConfirm'))) return;
    setResetting(true);
    try {
      await demoApi.reset(orgId);
      setExplicitSourceKey(null);
      setSourceKeySeeded(false);
      void refresh();
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 pb-12 cv-demo-center">
      <DemoEditableHeader settings={demoSettings.data} onRefresh={() => void refresh()} />

      <div id="demo-status" className="flex flex-wrap items-center gap-2 text-xs">
        <StatusChip label={t('demoCenter.serveur')} ok={services.backend} />
        <StatusChip label={t('demoCenter.video')} ok={services.go2rtc} />
        <StatusChip label={t('demoCenter.analyseIA')} ok={services.ai} />
        <StatusChip label={t('demoCenter.gpuCuda')} ok={services.cuda} />
        <StatusChip label={t('demoCenter.detections')} ok={demoEvents.length > 0} />
        <StatusChip label={t('demoCenter.alertes')} ok={demoAlerts.length > 0} />
        <button
          type="button"
          onClick={() => void handleReset()}
          disabled={resetting}
          className="ml-auto cv-btn-secondary text-xs py-1 px-3"
        >
          <RotateCcw className={`w-3.5 h-3.5 ${resetting ? 'animate-spin' : ''}`} />
          {t('demoCenter.resetDemo')}
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 space-y-4">
          <DemoVideoPanel
            settings={demoSettings.data}
            isLoading={demoSettings.isLoading}
            onExplicitSourceSelect={(sourceKey) => setExplicitSourceKey(sourceKey)}
            onEditZones={handleEditZones}
          />
          <div ref={zonePanelRef}>
            <DemoZoneInlinePanel
              cameraId={zoneCameraId}
              streamSrc={zoneStreamSrc}
              canEdit={canEditZones}
            />
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
                  {!step.href && step.onCtaClick && step.cta && (
                    <button
                      type="button"
                      onClick={step.onCtaClick}
                      className="inline-flex items-center gap-1 mt-2 text-xs font-medium text-cv-accent hover:underline"
                    >
                      {step.cta}
                      <ChevronRight className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Rules catalog — placed here (immediately below main grid) so it is reachable
          via the step-3 "Voir le catalogue" scroll button without leaving the page. */}
      <div ref={rulesCatalogRef} className="cv-card p-5">
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
          demoMode
          demoCameraIds={demoCameraIds.length ? demoCameraIds : undefined}
          onClose={() => setConfiguringTemplate(null)}
          onActivated={() => {
            setConfiguringTemplate(null);
            void rules.refetch();
          }}
        />
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <DemoFeedPanel
          title={t('demoCenter.detectionsLive')}
          icon={Activity}
          empty={t('demoCenter.emptyDetections')}
          link="/events"
          totalCount={demoEvents.length}
          maxTotal={MAX_DEMO_EVENTS}
          items={demoEvents.map((e) => ({
            id: e.id,
            primary: e.typeLabel ?? e.type,
            secondary: e.cameraName,
            time: new Date(e.timestamp).toLocaleTimeString(),
            timestamp: e.timestamp,
            eventType: e.type,
            isDemo: isDemoPayload(e.payload),
          }))}
        />
        <DemoFeedPanel
          title={t('demoCenter.alertesLive')}
          icon={Bell}
          empty={t('demoCenter.emptyAlertes')}
          link="/alerts"
          items={demoAlerts.map((a) => ({
            id: a.id,
            primary: a.message,
            secondary: a.cameraName,
            time: new Date(a.timestamp).toLocaleTimeString(),
            timestamp: a.timestamp,
            isDemo: isDemoPayload(a.metadata),
            acknowledged: a.acknowledged,
            onAck: () => void ack.mutate({ alertId: a.id }),
          }))}
        />
      </div>

      <div className="flex flex-wrap gap-3 opacity-60">
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
    }`}>
      {label}{ok ? ' ✓' : ' ✗'}
    </span>
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
