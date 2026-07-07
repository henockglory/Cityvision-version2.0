import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  PenTool, Workflow, Bell, Activity, ChevronRight, RotateCcw, Mail, Camera, AlertTriangle, Loader2,
} from 'lucide-react';
import DemoEditableHeader from '@/components/demo/DemoEditableHeader';
import DemoVideoPanel from '@/components/demo/DemoVideoPanel';
import DemoFeedPanel from '@/components/demo/DemoFeedPanel';
import CameraObservationPanel from '@/components/observation/CameraObservationPanel';
import DemoZoneInlinePanel from '@/components/demo/DemoZoneInlinePanel';
import EvidenceViewer from '@/components/evidence/EvidenceViewer';
import Modal from '@/components/ui/Modal';
import RuleCatalogPanel from '@/components/rules/RuleCatalogPanel';
import RuleActivationDialog from '@/components/rules/RuleActivationDialog';
import { demoApi, rulesApi } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useQueryClient } from '@tanstack/react-query';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import { useDialogTour } from '@/hooks/useDialogTour';
import {
  useAcknowledgeAlert,
  useAlerts,
  useCameras,
  useDemoSettings,
  useEvents,
  useRuleCatalog,
  useRules,
  queryKeys,
} from '@/hooks/api/queries';
import {
  AI_ENGINE_CAMERAS,
  AI_ENGINE_HEALTH,
  GO2RTC_STREAMS_API,
  MAILHOG_URL,
  RULES_ENGINE_HEALTH,
} from '@/config/streams';
import { evidenceQuality, evidenceThumbnailUrl, parseEvidenceSnapshot } from '@/lib/evidence';
import { ruleBindingSummary } from '@/lib/ruleExplainability';
import type { RuleCatalogTemplate } from '@/types';
import {
  demoVideoIdForCamera,
  demoVideoLabelForCamera,
  enabledRuleEventTypesForCameras,
  feedScopeCameraIds,
  filterDemoAlerts,
  filterDemoEvents,
  isVideoMismatch,
  resolvePreviewEvidence,
  ruleCameraId,
} from '@/lib/demoFeed';

const MAX_DEMO_EVENTS = 20;
const MAX_DEMO_ALERTS = 20;

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
  const startDemoTour = useAutoPageTour('demo');
  const demoSettings = useDemoSettings();
  const { data: cameras = [] } = useCameras();
  const [configuringTemplate, setConfiguringTemplate] = useState<RuleCatalogTemplate | null>(null);
  const [resetting, setResetting] = useState(false);
  const [explicitSourceKey, setExplicitSourceKey] = useState<string | null>(null);
  const [sourceKeySeeded, setSourceKeySeeded] = useState(false);
  const [feedPreview, setFeedPreview] = useState<{ kind: 'event' | 'alert'; id: string } | null>(null);
  const [services, setServices] = useState({
    go2rtc: false,
    ai: false,
    backend: false,
    cuda: false,
    rulesEngine: false,
    aiIngest: false,
    activeRules: 0,
  });
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
  const alerts = useAlerts({ status: 'open', includeIncomplete: true });
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
  const feedCameraIdsRef = useRef<string[]>([]);
  eventsRef.current = events;
  alertsRef.current = alerts;
  rulesRef.current = rules;
  catalogRef.current = catalog;
  demoSettingsRef.current = demoSettings;
  activeStreamRef.current = activeStream;

  const doRefresh = useCallback(async () => {
    const stream = activeStreamRef.current;
    const checks: Promise<void>[] = [
      fetch('/health')
        .then((r) => {
          setServices((s) => ({ ...s, backend: r.ok }));
        })
        .catch(() => {
          setServices((s) => ({ ...s, backend: false }));
        }),
      fetch(AI_ENGINE_HEALTH).then((r) => (r.ok ? r.json() : null)).then((a) => {
        const aiReady = a?.yolo_loaded === 'true';
        setServices((s) => ({
          ...s,
          ai: aiReady,
          cuda: a?.yolo_cuda === 'true',
          // AI up = ingest channel armed (cameras may spin up seconds later).
          aiIngest: aiReady || s.aiIngest,
        }));
      }).catch(() => {
        setServices((s) => ({ ...s, ai: false, cuda: false }));
      }),
      fetch(RULES_ENGINE_HEALTH).then((r) => (r.ok ? r.json() : null)).then((re) => {
        setServices((s) => ({
          ...s,
          rulesEngine: re?.status === 'ok',
          activeRules: typeof re?.active_rules === 'number' ? re.active_rules : 0,
        }));
      }).catch(() => {
        setServices((s) => ({ ...s, rulesEngine: false, activeRules: 0 }));
      }),
      fetch(AI_ENGINE_CAMERAS).then((r) => (r.ok ? r.json() : null)).then((payload) => {
        const runningIds = (payload?.cameras ?? [])
          .filter((c: { running?: boolean }) => c.running === true)
          .map((c: { camera_id?: string }) => String(c.camera_id ?? ''));
        const scopeIds = feedCameraIdsRef.current;
        const ingestOnScope = scopeIds.length === 0
          ? runningIds.length > 0
          : scopeIds.some((id) => runningIds.includes(id));
        setServices((s) => ({ ...s, aiIngest: ingestOnScope || s.ai }));
      }).catch(() => {
        setServices((s) => ({ ...s, aiIngest: false }));
      }),
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

  /** Observation counters: décompte camera or any enabled observation/counting rule camera. */
  const counterCameraId = useMemo(() => {
    const fromRules = rulesList
      .filter((r) => {
        if (!r.enabled) return false;
        const b = r.definition?.bindings as Record<string, unknown> | undefined;
        const actions = r.definition?.actions as Array<{ type?: string }> | undefined;
        return b?.observation_mode === true || actions?.some((a) => a.type === 'counter');
      })
      .map((r) => ruleCameraId(r))
      .find(Boolean);
    if (fromRules) return fromRules;
    const decompte = cameras.find((c) => {
      const n = c.name.toLowerCase();
      return n.includes('décompte') || n.includes('decompte');
    });
    return decompte?.id;
  }, [cameras, rulesList]);

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

  const activeStreamLabel = useMemo(() => {
    if (demoSettings.data?.source_mode === 'camera' && demoSettings.data?.active_camera_id) {
      const cam = cameras.find((c) => c.id === demoSettings.data?.active_camera_id);
      return cam?.name;
    }
    const videos = demoSettings.data?.videos ?? [];
    const active = videos.find((v) => v.id === demoSettings.data?.active_video_id);
    return active?.name;
  }, [cameras, demoSettings.data?.source_mode, demoSettings.data?.active_camera_id, demoSettings.data?.active_video_id, demoSettings.data?.videos]);

  const canEditZones = Boolean(
    zoneCameraId
    && zoneStreamSrc
    && activeSourceKey
    && explicitSourceKey === activeSourceKey,
  );

  const enabledRuleCameraIds = useMemo(
    () => rulesList
      .filter((r) => r.enabled)
      .map((r) => ruleCameraId(r))
      .filter(Boolean),
    [rulesList],
  );

  const feedCameraIds = useMemo(
    () => feedScopeCameraIds(enabledRuleCameraIds, zoneCameraId),
    [enabledRuleCameraIds, zoneCameraId],
  );
  feedCameraIdsRef.current = feedCameraIds;

  useEffect(() => {
    void doRefresh();
  }, [feedCameraIds, doRefresh]);

  const demoCameraIds = useMemo(
    () => cameras.filter((c) => isDemoCameraMeta(c.metadata)).map((c) => c.id),
    [cameras],
  );

  const enabledUserRules = useMemo(
    () => rulesList.filter((r) => {
      const origin = String((r.definition?.bindings as Record<string, unknown> | undefined)?.origin ?? '');
      return r.enabled && origin === 'user';
    }),
    [rulesList],
  );

  const dormantDemoRules = useMemo(
    () => rulesList.filter((r) => String(r.name ?? '').startsWith('Démo') && !r.enabled),
    [rulesList],
  );

  const demoEvents = useMemo(
    () => filterDemoEvents(events.data ?? [], feedCameraIds, enabledUserRules, isDemoPayload)
      .slice(0, MAX_DEMO_EVENTS),
    [events.data, feedCameraIds, enabledUserRules],
  );

  const demoAlerts = useMemo(
    () => filterDemoAlerts(alerts.data ?? [], feedCameraIds, isDemoPayload, enabledUserRules).slice(0, MAX_DEMO_ALERTS),
    [alerts.data, feedCameraIds, enabledUserRules],
  );

  const ruleEventTypes = useMemo(
    () => enabledRuleEventTypesForCameras(enabledUserRules, feedCameraIds),
    [enabledUserRules, feedCameraIds],
  );

  const hasRuleMatchingEvents = useMemo(
    () => demoEvents.some((e) => ruleEventTypes.has(e.type)),
    [demoEvents, ruleEventTypes],
  );

  /** Détections + Alertes = même signal que Serveur/Vidéo/IA/GPU (pas d'attente d'événements ni rules poll). */
  const coreServicesOk = services.backend && services.go2rtc && services.ai && services.cuda;
  const detectionsStatusOk = coreServicesOk;
  const alertsStatusOk = coreServicesOk;
  const pipelineReady = coreServicesOk && services.rulesEngine;

  const pipelineSyncSinceRef = useRef<number | null>(null);
  useEffect(() => {
    if (enabledUserRules.length > 0 && pipelineSyncSinceRef.current === null) {
      pipelineSyncSinceRef.current = Date.now();
    }
    if (enabledUserRules.length === 0) {
      pipelineSyncSinceRef.current = null;
    }
  }, [enabledUserRules.length]);

  const showPipelineSync = useMemo(() => {
    if (enabledUserRules.length === 0 || demoAlerts.length > 0 || hasRuleMatchingEvents) {
      return false;
    }
    const since = pipelineSyncSinceRef.current;
    if (since === null) return true;
    return Date.now() - since < 90_000;
  }, [enabledUserRules.length, demoAlerts.length, hasRuleMatchingEvents, demoEvents.length]);

  const videoMismatch = useMemo(
    () => isVideoMismatch(enabledRuleCameraIds, zoneCameraId),
    [enabledRuleCameraIds, zoneCameraId],
  );

  const detectionTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of demoEvents) {
      counts[e.type] = (counts[e.type] ?? 0) + 1;
    }
    return counts;
  }, [demoEvents]);

  const previewEvent = feedPreview?.kind === 'event'
    ? demoEvents.find((e) => e.id === feedPreview.id)
    : undefined;
  const previewAlert = feedPreview?.kind === 'alert'
    ? demoAlerts.find((a) => a.id === feedPreview.id)
    : undefined;

  const previewResolved = useMemo(
    () => resolvePreviewEvidence(previewEvent, previewAlert, demoAlerts),
    [previewEvent, previewAlert, demoAlerts],
  );

  const previewQuality = useMemo(
    () => evidenceQuality(previewResolved.evidence, orgId),
    [previewResolved.evidence, orgId],
  );

  const previewModalOpen = Boolean(previewEvent || previewAlert);
  useDialogTour('evidenceViewer', previewModalOpen);

  // Poll for evidence package while modal is open and media still loading.
  useEffect(() => {
    if (!previewModalOpen) return;
    if (previewQuality.state === 'complete') return;
    const started = Date.now();
    const id = setInterval(() => {
      if (Date.now() - started > 60_000) {
        clearInterval(id);
        return;
      }
      void events.refetch();
      void alerts.refetch();
    }, 3000);
    return () => clearInterval(id);
  }, [previewModalOpen, previewQuality.state, events, alerts]);

  const handleSelectVideoForRule = useCallback(async (cameraId: string) => {
    if (!orgId) return;
    const videoId = demoVideoIdForCamera(cameraId, cameras);
    if (!videoId) return;
    try {
      await demoApi.patchSettings(orgId, {
        active_video_id: videoId,
        active_camera_id: null,
        source_mode: 'video',
      });
      setExplicitSourceKey(`video:${videoId}`);
      void demoSettings.refetch();
    } catch { /* best-effort */ }
  }, [orgId, cameras, demoSettings]);

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
      <DemoEditableHeader settings={demoSettings.data} onRefresh={() => void refresh()} onHelpTour={startDemoTour} />

      <div id="demo-status" className="flex flex-wrap items-center gap-2 text-xs">
        <StatusChip label={t('demoCenter.serveur')} ok={services.backend} />
        <StatusChip label={t('demoCenter.video')} ok={services.go2rtc} />
        <StatusChip label={t('demoCenter.analyseIA')} ok={services.ai} />
        <StatusChip
          label={t('demoCenter.gpuCuda')}
          ok={services.cuda}
          title={services.cuda ? undefined : t('demoCenter.gpuCudaTip')}
        />
        <StatusChip
          label={t('demoCenter.detections')}
          ok={detectionsStatusOk}
          title={
            pipelineReady && demoEvents.length === 0
              ? t('demoCenter.detectionsPipelineReady')
              : undefined
          }
        />
        <StatusChip
          label={t('demoCenter.alertes')}
          ok={alertsStatusOk}
          title={
            pipelineReady && demoAlerts.length === 0
              ? t('demoCenter.alertesPipelineReady')
              : undefined
          }
        />
        <a
          href={MAILHOG_URL}
          target="_blank"
          rel="noreferrer"
          className="cv-btn-secondary text-xs py-1 px-3 border-cv-accent/40 bg-cv-accent/10 hover:bg-cv-accent/15"
          title={t('demoCenter.mailhogTip')}
        >
          <Mail className="w-3.5 h-3.5 text-cv-accent" />
          {t('demoCenter.mailhogInbox')}
        </a>
        <button
          type="button"
          onClick={() => void handleReset()}
          disabled={resetting}
          className="cv-btn-secondary text-xs py-1 px-3"
        >
          <RotateCcw className={`w-3.5 h-3.5 ${resetting ? 'animate-spin' : ''}`} />
          {t('demoCenter.resetDemo')}
        </button>
      </div>

      {!services.ai && (
        <div className="rounded-lg border border-metric-alerts/40 bg-metric-alerts/10 px-4 py-3 text-sm text-cv-text space-y-1">
          <p className="font-medium flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-metric-alerts shrink-0" />
            {t('demoCenter.aiEngineDown')}
          </p>
          <p className="text-xs text-cv-muted font-mono">{t('demoCenter.aiEngineStart')}</p>
        </div>
      )}

      {services.ai && !services.cuda && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-cv-text">
          <p className="font-medium flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            {t('demoCenter.cudaExpected')}
          </p>
        </div>
      )}

      {services.ai && (
        <div className="rounded-lg border border-cv-accent/25 bg-cv-accent/5 px-4 py-2.5 text-xs text-cv-muted">
          <p className="flex items-center gap-2">
            <Camera className="w-3.5 h-3.5 text-cv-accent shrink-0" />
            {t('demoCenter.monoCameraIngest', {
              defaultValue: 'Une seule caméra/vidéo démo ingère à la fois. Basculez la source active pour tester chaque scénario.',
            })}
            {activeStreamLabel && (
              <span className="text-cv-text font-medium ml-1">({activeStreamLabel})</span>
            )}
          </p>
        </div>
      )}

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


        <div className="space-y-3" id="demo-steps">
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
      <div ref={rulesCatalogRef} id="demo-rules-catalog" className="cv-card p-5">
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

      {zoneCameraId && counterCameraId && zoneCameraId === counterCameraId && (
        <CameraObservationPanel
          cameraId={counterCameraId}
          activeCameraId={zoneCameraId}
        />
      )}

      {enabledUserRules.length > 0 && (
        <div className="cv-card p-4 space-y-3 border-cv-accent/20 bg-cv-accent/5">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Workflow className="w-4 h-4 text-cv-accent" />
            {t('demoCenter.activeRulesTitle', { count: enabledUserRules.length })}
          </h3>
          <p className="text-[11px] text-cv-muted leading-relaxed">{t('demoCenter.activeRulesHint')}</p>

          {showPipelineSync && (
            <p className="text-xs text-cv-accent/90 flex items-center gap-2 px-3 py-2 rounded-lg bg-cv-accent/10 border border-cv-accent/20">
              <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
              {t('demoCenter.pipelineSyncHint')}
            </p>
          )}

          {videoMismatch && (
            <div className="flex flex-wrap items-center gap-2 text-xs px-3 py-2 rounded-lg bg-metric-alerts/10 border border-metric-alerts/30 text-metric-alerts">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              <span>{t('demoCenter.videoMismatchHint')}</span>
            </div>
          )}

          <ul className="space-y-2">
            {enabledUserRules.map((r) => {
              const camId = ruleCameraId(r);
              const videoLabel = demoVideoLabelForCamera(
                camId,
                cameras,
                demoSettings.data?.videos ?? [],
              );
              const needsSwitch = zoneCameraId !== camId && camId;
              return (
                <li key={r.id} className="text-xs flex flex-wrap items-center gap-2 p-2 rounded-lg bg-cv-surface/40 border border-cv-border/40">
                  <span className="font-medium">{r.name}</span>
                  <span className="text-cv-muted">{ruleBindingSummary(r, cameras)}</span>
                  <span className="text-cv-muted">→ {t('demoCenter.selectVideo', { name: videoLabel })}</span>
                  {needsSwitch && (
                    <button
                      type="button"
                      className="cv-btn-secondary text-[10px] py-0.5 px-2"
                      onClick={() => void handleSelectVideoForRule(camId)}
                    >
                      {t('demoCenter.switchVideo', { name: videoLabel })}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {dormantDemoRules.length > 0 && enabledUserRules.length === 0 && (
        <div className="cv-card border border-amber-500/40 bg-amber-500/10 px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-3">
          <p className="text-sm text-cv-text flex-1">
            {t('demoCenter.rulesDisabledBanner', { count: dormantDemoRules.length })}
          </p>
          <Link to="/rules" className="cv-btn-primary text-sm shrink-0">
            {t('demoCenter.rulesDisabledAction')}
          </Link>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <DemoFeedPanel
          containerId="demo-feed-detections"
          title={t('demoCenter.detectionsLive')}
          icon={Activity}
          empty={enabledUserRules.length > 0
            ? t('demoCenter.emptyDetectionsActiveRules', { count: enabledUserRules.length })
            : t('demoCenter.emptyDetections')}
          hint={t('demoCenter.detectionsHint')}
          link="/events"
          totalCount={demoEvents.length}
          maxTotal={MAX_DEMO_EVENTS}
          typeCounts={detectionTypeCounts}
          items={demoEvents.map((e) => ({
            id: e.id,
            primary: e.typeLabel ?? e.type,
            secondary: e.cameraName,
            time: new Date(e.timestamp).toLocaleTimeString(),
            timestamp: e.timestamp,
            eventType: e.type,
            isDemo: isDemoPayload(e.payload),
            thumbnailUrl: e.thumbnail ?? evidenceThumbnailUrl(parseEvidenceSnapshot(e.evidenceSnapshot), orgId),
            selected: feedPreview?.kind === 'event' && feedPreview.id === e.id,
            onSelect: () => setFeedPreview({ kind: 'event', id: e.id }),
          }))}
        />
        <DemoFeedPanel
          containerId="demo-feed-alerts"
          title={t('demoCenter.alertesLive')}
          icon={Bell}
          empty={enabledUserRules.length > 0
            ? t('demoCenter.emptyAlertesWaiting', { count: enabledUserRules.length })
            : t('demoCenter.emptyAlertes')}
          hint={t('demoCenter.alertesHint')}
          link="/alerts"
          totalCount={demoAlerts.length}
          maxTotal={MAX_DEMO_ALERTS}
          items={demoAlerts.map((a) => ({
            id: a.id,
            primary: a.message,
            secondary: a.cameraName,
            time: new Date(a.timestamp).toLocaleTimeString(),
            timestamp: a.timestamp,
            isDemo: isDemoPayload(a.metadata),
            thumbnailUrl: evidenceThumbnailUrl(parseEvidenceSnapshot(a.evidenceSnapshot), orgId),
            acknowledged: a.acknowledged,
            selected: feedPreview?.kind === 'alert' && feedPreview.id === a.id,
            onSelect: () => setFeedPreview({ kind: 'alert', id: a.id }),
            onAck: () => void ack.mutate({ alertId: a.id }),
          }))}
        />
      </div>

      <Modal
        open={previewModalOpen}
        onClose={() => setFeedPreview(null)}
        maxWidth="studio"
        title={t('demoCenter.evidencePreviewTitle')}
        footerLeft={
          previewResolved.cameraId ? (
            <Link
              to={`/live?camera=${previewResolved.cameraId}`}
              className="cv-btn-ghost text-xs py-1 inline-flex items-center gap-1"
            >
              <Camera className="w-3.5 h-3.5" />
              {t('demoCenter.openLive')}
            </Link>
          ) : null
        }
        footer={
          <>
            <Link to="/alerts" className="cv-btn-secondary text-sm">
              {t('demoCenter.step4Cta')}
            </Link>
            <button type="button" className="cv-btn-primary text-sm" onClick={() => setFeedPreview(null)}>
              {t('common.close')}
            </button>
          </>
        }
      >
        <div className="overflow-y-auto max-h-[min(75vh,820px)] pr-1 space-y-4">
          {previewResolved.title && (
            <p className="text-sm font-medium">{previewResolved.title}</p>
          )}
          {(previewEvent || previewAlert) && (
            <p className="text-xs text-cv-muted">
              {(previewEvent?.cameraName ?? previewAlert?.cameraName)}
              {previewAlert?.ruleName ? ` · ${previewAlert.ruleName}` : ''}
            </p>
          )}
          {previewQuality.state === 'loading' || previewQuality.state === 'partial' ? (
            <p className="text-xs text-cv-accent flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              {t('demoCenter.evidenceLoading')}
            </p>
          ) : null}
          <div className="p-4 rounded-xl bg-cv-surface/40 border border-cv-border/60">
            <EvidenceViewer
              evidence={previewResolved.evidence}
              cameraId={previewResolved.cameraId}
              ruleId={previewResolved.ruleId}
            />
          </div>
        </div>
      </Modal>

      <div className="flex flex-wrap gap-3">
        <QuickLink to="/zones" icon={PenTool} label={t('nav.zoneEditor')} />
        <QuickLink to="/rules?catalog=1" icon={Workflow} label={t('nav.rules')} />
        <QuickLink to="/events" icon={Activity} label={t('nav.events')} />
        <QuickLink to="/alerts" icon={Bell} label={t('nav.alerts')} />
        <a
          href={MAILHOG_URL}
          target="_blank"
          rel="noreferrer"
          className="cv-btn-secondary text-sm border-cv-accent/30"
        >
          <Mail className="w-4 h-4 text-cv-accent" />
          {t('demoCenter.mailhogInbox')}
        </a>
      </div>
    </div>
  );
}

function StatusChip({ label, ok, title }: { label: string; ok: boolean; title?: string }) {
  return (
    <span
      title={title}
      className={`px-3 py-1 rounded-full border text-xs ${
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
