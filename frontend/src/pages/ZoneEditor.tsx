import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

import { Stage, Layer, Line, Circle, Text } from 'react-konva';

import type { KonvaEventObject } from 'konva/lib/Node';

import { useTranslation } from 'react-i18next';

import { Plus, Save, Pentagon, Shapes, Trash2, Video, Minus } from 'lucide-react';

import PageHeader from '@/components/ui/PageHeader';

import EmptyState from '@/components/EmptyState';

import LoadingState from '@/components/ui/LoadingState';

import { useCameras, useRules } from '@/hooks/api/queries';

import { useAutoPageTour } from '@/hooks/useAutoPageTour';

import { useSound } from '@/hooks/useSound';

import { useAuthStore } from '@/stores/authStore';

import { zonesApi, capabilitiesApi, type BackendZone, type BackendLine, type CapabilitiesBehaviorMenuItem } from '@/api/client';

import ConfirmDialog from '@/components/ui/ConfirmDialog';
import PremiumSelect from '@/components/ui/PremiumSelect';
import ExplanatorySelect from '@/components/ui/ExplanatorySelect';
import { getBehavior, type ZoneBehavior } from '@/lib/zoneBehaviors';
import { behaviorMenuOptions, resolveBehaviorMeta } from '@/lib/behaviorMenu';
import ZoneEdgeCalibration from '@/components/zones/ZoneEdgeCalibration';
import ZoneRuleLinkPanel from '@/components/zones/ZoneRuleLinkPanel';
import ZoneRuleSuggestions, { type SavedZoneSuggestion } from '@/components/zones/ZoneRuleSuggestions';
import { rulesLinkedToZone, type ZoneRuleLinkContext } from '@/lib/zoneRuleLinks';
import {
  derivedTravelDistanceM,
  edgeStagePoints,
  edgeVertexIndices,
  midEdgeStageCoords,
  pointsToPolygon,
  polygonFromBackend,
  polygonToPointsAndEdges,
  vertexCountFromPoints,
} from '@/lib/zoneEdgeCalibration';

import InfoTip from '@/components/ui/InfoTip';

import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';

import { go2rtcStreamSrc } from '@/config/streams';

import type { Zone } from '@/types';



const STAGE_WIDTH = 800;

const STAGE_HEIGHT = 450;



type EditMode = 'zone' | 'line';



interface DraftLine {

  id: string;

  name: string;

  start: [number, number];

  end: [number, number];

  cameraId: string;

  behavior?: string;

  behaviorConfig?: Record<string, unknown>;

}



interface SavedLine {

  id: string;

  name: string;

  points: number[];

  cameraId: string;

  behavior?: string;

  behaviorConfig?: Record<string, unknown>;

}



function backendToZone(z: BackendZone): Zone {

  const poly = polygonFromBackend(z.polygon ?? []);
  let { points, edgeDistancesM } = polygonToPointsAndEdges(poly);
  const cfg = z.behavior_config?.config as Record<string, unknown> | undefined;
  const cfgEdges = cfg?.edge_distances_m;
  if (Array.isArray(cfgEdges)) {
    edgeDistancesM = cfgEdges.map((v) => {
      const n = Number(v);
      return Number.isFinite(n) && n > 0 ? n : undefined;
    });
  }

  return {

    id: z.id,

    name: z.name,

    points,

    edgeDistancesM,

    color: z.color ?? '#00D4FF',

    cameraId: z.camera_id ?? '',

    zoneKind: z.zone_kind || undefined,

    behavior: z.behavior_config?.behavior || z.zone_kind || undefined,

    behaviorConfig: (z.behavior_config?.config as Record<string, unknown>) ?? undefined,

  };

}



function backendToLine(l: BackendLine): SavedLine {

  const sx = (l.start_point?.x ?? 0) * STAGE_WIDTH;

  const sy = (l.start_point?.y ?? 0) * STAGE_HEIGHT;

  const ex = (l.end_point?.x ?? 0) * STAGE_WIDTH;

  const ey = (l.end_point?.y ?? 0) * STAGE_HEIGHT;

  return {

    id: l.id,

    name: l.name,

    points: [sx, sy, ex, ey],

    cameraId: l.camera_id ?? '',

    behavior: l.behavior_config?.behavior || 'count_crossings',

    behaviorConfig: (l.behavior_config?.config as Record<string, unknown>) ?? undefined,

  };

}



export interface ZoneEditorProps {
  embedded?: boolean;
  fixedCameraId?: string;
  fixedStreamSrc?: string;
  onClose?: () => void;
}

export default function ZoneEditor(props: ZoneEditorProps = {}) {
  const embedded = props.embedded ?? false;

  const { t, i18n } = useTranslation();
  const lang: 'fr' | 'en' = i18n.language?.startsWith('en') ? 'en' : 'fr';
  const navigate = useNavigate();

  const { playClick, playSonar } = useSound();

  const startTour = useAutoPageTour('zones');

  const orgId = useAuthStore((s) => s.orgId);
  const authSiteId = useAuthStore((s) => s.siteId);

  const { data: cameras = [], isLoading } = useCameras();
  const { data: rules = [] } = useRules();

  const [editMode, setEditMode] = useState<EditMode>('zone');

  const [savedZones, setSavedZones] = useState<Zone[]>([]);

  const [draftZones, setDraftZones] = useState<Zone[]>([]);

  const [savedLines, setSavedLines] = useState<SavedLine[]>([]);

  const [draftLines, setDraftLines] = useState<DraftLine[]>([]);

  const [lineDraftStart, setLineDraftStart] = useState<[number, number] | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [savingName, setSavingName] = useState(false);

  const [drawing, setDrawing] = useState<number[]>([]);

  const [saving, setSaving] = useState(false);

  const [loadingSpatial, setLoadingSpatial] = useState(false);

  const [message, setMessage] = useState('');

  const [deleteConfirm, setDeleteConfirm] = useState<{ type: 'zone' | 'line'; id: string; name: string } | null>(null);
  const [highlightedEdgeIndex, setHighlightedEdgeIndex] = useState<number | null>(null);
  const [capabilityBehaviors, setCapabilityBehaviors] = useState<CapabilitiesBehaviorMenuItem[]>([]);
  const [savedZoneSuggestions, setSavedZoneSuggestions] = useState<SavedZoneSuggestion[]>([]);

  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const edgeCalibrationRef = useRef<HTMLDivElement>(null);
  const [layout, setLayout] = useState({ width: STAGE_WIDTH, height: STAGE_HEIGHT });

  useEffect(() => {
    // Observe the container (outer wrapper) rather than the canvas itself to avoid
    // measuring the stage's own width, which causes a circular resize loop.
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      // Subtract card padding (p-4 = 16px each side = 32px total).
      const available = Math.floor((el.clientWidth || STAGE_WIDTH) - 32);
      const w = Math.max(280, Math.min(STAGE_WIDTH, available));
      const h = Math.round(w * 9 / 16);  // strict 16:9
      setLayout({ width: w, height: h });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    window.addEventListener('resize', update);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', update);
    };
  }, [embedded]);



  const [searchParams, setSearchParams] = useSearchParams();

  const selectedCamera = props.fixedCameraId
    ? cameras.find((c) => c.id === props.fixedCameraId)
    : cameras.find((c) => c.id === searchParams.get('camera'))
    ?? cameras.find(
      (c) => {
        const meta = c.metadata as Record<string, unknown> | undefined;
        return meta?.demo === true || meta?.demo === 'true';
      },
    ) ?? (embedded ? undefined : cameras[0]);

  const siteId = authSiteId ?? selectedCamera?.siteId;

  const streamSrc = embedded
    ? (props.fixedStreamSrc ?? '')
    : (props.fixedStreamSrc ?? go2rtcStreamSrc(selectedCamera) ?? '');

  const scaleX = layout.width / STAGE_WIDTH;
  const scaleY = layout.height / STAGE_HEIGHT;

  const loadSpatial = useCallback(async () => {

    if (!orgId || !selectedCamera) return;

    setLoadingSpatial(true);

    try {

      const [zRes, lRes] = await Promise.all([

        zonesApi.list(orgId, selectedCamera.id),

        zonesApi.listLines(orgId, selectedCamera.id),

      ]);

      const zList = (Array.isArray(zRes.data) ? zRes.data : []) as BackendZone[];

      const lList = (Array.isArray(lRes.data) ? lRes.data : []) as BackendLine[];

      setSavedZones(zList.map(backendToZone));

      setSavedLines(lList.map(backendToLine));

    } catch {

      setMessage(t('zoneEditor.loadFailed'));

    } finally {

      setLoadingSpatial(false);

    }

  }, [orgId, selectedCamera, t]);



  useEffect(() => {

    void loadSpatial();

  }, [loadSpatial]);

  useEffect(() => {
    setDrawing([]);
    setLineDraftStart(null);
    setSelectedId(null);
    setDraftZones([]);
    setDraftLines([]);
  }, [selectedCamera?.id, streamSrc]);



  const allZones = [...savedZones, ...draftZones];

  const allLines = [...savedLines, ...draftLines.map((d) => ({

    id: d.id,

    name: d.name,

    points: [...d.start, ...d.end],

    cameraId: d.cameraId,

    behavior: d.behavior ?? 'count_crossings',

    behaviorConfig: d.behaviorConfig,

  }))];

  useEffect(() => {
    if (!orgId) return;
    void capabilitiesApi.menu(orgId)
      .then((r) => setCapabilityBehaviors(r.data.behaviors ?? []))
      .catch(() => setCapabilityBehaviors([]));
  }, [orgId]);

  const zoneRuleLinkContext = useMemo((): ZoneRuleLinkContext => ({
    zones: allZones.map((z) => ({ name: z.name, behavior: z.behavior })),
    lines: allLines.map((l) => ({ name: l.name, behavior: l.behavior ?? 'count_crossings' })),
    capabilityBehaviors,
  }), [allZones, allLines, capabilityBehaviors]);

  const zoneBehaviorOptions = useMemo(
    () => behaviorMenuOptions(capabilityBehaviors, 'zone', lang, { includeStandard: true }),
    [capabilityBehaviors, lang],
  );

  const lineBehaviorOptions = useMemo(
    () => behaviorMenuOptions(capabilityBehaviors, 'line', lang),
    [capabilityBehaviors, lang],
  );

  useEffect(() => {
    if (!selectedId) {
      setEditName('');
      return;
    }
    if (editMode === 'zone') {
      const z = allZones.find((x) => x.id === selectedId);
      setEditName(z?.name ?? '');
    } else {
      const l = allLines.find((x) => x.id === selectedId);
      setEditName(l?.name ?? '');
    }
  }, [selectedId, editMode, savedZones, draftZones, savedLines, draftLines]);

  useEffect(() => {
    setHighlightedEdgeIndex(null);
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId || editMode !== 'zone') return;
    const timer = window.setTimeout(() => {
      edgeCalibrationRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [selectedId, editMode]);

  const zoneKindLabel = (kind?: string) => {
    if (!kind) return null;
    const labels: Record<string, string> = {
      perimeter: t('zoneEditor.zoneKindPerimeter'),
      controlled_exit: t('zoneEditor.zoneKindExit'),
      corridor: t('zoneEditor.zoneKindCorridor'),
      parking: t('zoneEditor.zoneKindParking'),
    };
    return labels[kind] ?? kind;
  };

  const saveSelectedName = async () => {
    if (!selectedId) return;
    const name = editName.trim();
    if (!name) {
      const current = editMode === 'zone'
        ? allZones.find((x) => x.id === selectedId)
        : allLines.find((x) => x.id === selectedId);
      setEditName(current?.name ?? '');
      return;
    }
    const isDraft = selectedId.startsWith('draft-') || selectedId.startsWith('draft-line-');
    const current = editMode === 'zone'
      ? allZones.find((x) => x.id === selectedId)
      : allLines.find((x) => x.id === selectedId);
    if (!current || current.name === name) return;

    if (isDraft) {
      if (editMode === 'zone') {
        setDraftZones((prev) => prev.map((z) => (z.id === selectedId ? { ...z, name } : z)));
      } else {
        setDraftLines((prev) => prev.map((l) => (l.id === selectedId ? { ...l, name } : l)));
      }
      return;
    }
    if (!orgId) return;
    setSavingName(true);
    try {
      if (editMode === 'zone') {
        await zonesApi.update(orgId, selectedId, { name });
        setSavedZones((prev) => prev.map((z) => (z.id === selectedId ? { ...z, name } : z)));
      } else {
        await zonesApi.updateLine(orgId, selectedId, { name });
        setSavedLines((prev) => prev.map((l) => (l.id === selectedId ? { ...l, name } : l)));
      }
    } catch {
      setMessage(t('zoneEditor.renameFailed'));
    } finally {
      setSavingName(false);
    }
  };

  // Persist the AI behavior assigned to the selected zone. Resets the per-behavior
  // config to the catalog defaults so the new behavior starts coherent.
  const saveSelectedBehavior = async (behaviorId: string) => {
    if (!selectedId || editMode !== 'zone') return;
    const behavior = behaviorId || undefined;
    const def = resolveBehaviorMeta(behaviorId, capabilityBehaviors, lang) ?? getBehavior(behaviorId);
    const defaults: Record<string, unknown> = {};
    for (const f of def?.config_fields ?? []) {
      if (f.default !== undefined) defaults[f.key] = f.default;
    }
    if (selectedId.startsWith('draft-')) {
      const n = vertexCountFromPoints(
        allZones.find((z) => z.id === selectedId)?.points ?? [],
      );
      setDraftZones((prev) =>
        prev.map((z) =>
          z.id === selectedId
            ? {
                ...z,
                behavior,
                behaviorConfig: defaults,
                edgeDistancesM: behavior === 'speed_measurement'
                  ? Array.from({ length: n }, () => undefined)
                  : z.edgeDistancesM,
              }
            : z,
        ),
      );
      return;
    }
    if (!orgId) return;
    try {
      await zonesApi.update(orgId, selectedId, {
        behavior_config: behavior ? { behavior, config: defaults } : {},
      });
      setSavedZones((prev) =>
        prev.map((z) => (z.id === selectedId ? { ...z, behavior, behaviorConfig: defaults } : z)),
      );
    } catch {
      setMessage(t('zoneEditor.renameFailed'));
    }
  };

  // Persist a single config value for the selected zone's current behavior.
  const saveSelectedBehaviorConfig = async (key: string, value: unknown) => {
    if (!selectedId || editMode !== 'zone' || !selectedZone) return;
    const behavior = selectedZone.behavior;
    if (!behavior) return;
    const nextConfig = { ...(selectedZone.behaviorConfig ?? {}), [key]: value };
    if (selectedId.startsWith('draft-')) {
      setDraftZones((prev) =>
        prev.map((z) => (z.id === selectedId ? { ...z, behaviorConfig: nextConfig } : z)),
      );
      return;
    }
    if (!orgId) return;
    try {
      await zonesApi.update(orgId, selectedId, {
        behavior_config: { behavior, config: nextConfig },
      });
      setSavedZones((prev) =>
        prev.map((z) => (z.id === selectedId ? { ...z, behaviorConfig: nextConfig } : z)),
      );
    } catch {
      setMessage(t('zoneEditor.renameFailed'));
    }
  };

  const saveSelectedEdgeDistance = async (edgeIndex: number, metres: number | undefined) => {
    if (!selectedId || editMode !== 'zone' || !selectedZone) return;
    const n = vertexCountFromPoints(selectedZone.points);
    const nextEdges = [...(selectedZone.edgeDistancesM ?? Array.from({ length: n }, () => undefined))];
    while (nextEdges.length < n) nextEdges.push(undefined);
    nextEdges[edgeIndex] = metres;
    const polygon = pointsToPolygon(selectedZone.points, nextEdges);
    const derived = derivedTravelDistanceM(selectedZone.points, nextEdges);
    const behavior = selectedZone.behavior ?? 'speed_measurement';
    const nextConfig = { ...(selectedZone.behaviorConfig ?? {}) } as Record<string, unknown>;
    if (derived != null) nextConfig.distance_m = derived;
    else delete nextConfig.distance_m;
    nextConfig.edge_distances_m = nextEdges.map((d) => (d != null && d > 0 ? d : null));

    if (selectedId.startsWith('draft-')) {
      setDraftZones((prev) =>
        prev.map((z) =>
          z.id === selectedId
            ? { ...z, edgeDistancesM: nextEdges, behaviorConfig: nextConfig }
            : z,
        ),
      );
      return;
    }
    if (!orgId) return;
    try {
      await zonesApi.update(orgId, selectedId, {
        polygon,
        behavior_config: { behavior, config: nextConfig },
      });
      setSavedZones((prev) =>
        prev.map((z) =>
          z.id === selectedId
            ? { ...z, edgeDistancesM: nextEdges, behaviorConfig: nextConfig }
            : z,
        ),
      );
    } catch {
      setMessage(t('zoneEditor.renameFailed'));
    }
  };

  const selectedZone = editMode === 'zone' && selectedId
    ? allZones.find((z) => z.id === selectedId)
    : undefined;

  const selectedLine = editMode === 'line' && selectedId
    ? allLines.find((l) => l.id === selectedId)
    : undefined;

  const saveSelectedLineBehavior = async (behaviorId: string) => {
    if (!selectedId || editMode !== 'line' || !selectedLine) return;
    const behavior = behaviorId || 'count_crossings';
    const def = resolveBehaviorMeta(behaviorId, capabilityBehaviors, lang) ?? getBehavior(behaviorId);
    const defaults: Record<string, unknown> = {};
    for (const f of def?.config_fields ?? []) {
      if (f.default !== undefined) defaults[f.key] = f.default;
    }
    if (selectedId.startsWith('draft-line-')) {
      setDraftLines((prev) =>
        prev.map((l) => (l.id === selectedId ? { ...l, behavior, behaviorConfig: defaults } : l)),
      );
      return;
    }
    if (!orgId) return;
    try {
      await zonesApi.updateLine(orgId, selectedId, {
        behavior_config: { behavior, config: defaults },
      });
      setSavedLines((prev) =>
        prev.map((l) => (l.id === selectedId ? { ...l, behavior, behaviorConfig: defaults } : l)),
      );
    } catch {
      setMessage(t('zoneEditor.renameFailed'));
    }
  };

  const saveSelectedLineBehaviorConfig = async (key: string, value: unknown) => {
    if (!selectedId || editMode !== 'line' || !selectedLine?.behavior) return;
    const nextConfig = { ...(selectedLine.behaviorConfig ?? {}), [key]: value };
    if (selectedId.startsWith('draft-line-')) {
      setDraftLines((prev) =>
        prev.map((l) => (l.id === selectedId ? { ...l, behaviorConfig: nextConfig } : l)),
      );
      return;
    }
    if (!orgId) return;
    try {
      await zonesApi.updateLine(orgId, selectedId, {
        behavior_config: { behavior: selectedLine.behavior, config: nextConfig },
      });
      setSavedLines((prev) =>
        prev.map((l) => (l.id === selectedId ? { ...l, behaviorConfig: nextConfig } : l)),
      );
    } catch {
      setMessage(t('zoneEditor.renameFailed'));
    }
  };

  const handleStageClick = (e: KonvaEventObject<MouseEvent>) => {

    const stage = e.target.getStage();

    if (!stage) return;

    const pos = stage.getPointerPosition();

    if (!pos) return;

    const x = pos.x / scaleX;

    const y = pos.y / scaleY;

    playClick();



    if (editMode === 'line') {

      if (!lineDraftStart) {

        setLineDraftStart([x, y]);

        return;

      }

      const id = `draft-line-${Date.now()}`;

      setDraftLines((prev) => [

        ...prev,

        {

          id,

          name: `Ligne ${savedLines.length + prev.length + 1}`,

          start: lineDraftStart,

          end: [x, y],

          cameraId: selectedCamera?.id ?? '',

        },

      ]);

      setLineDraftStart(null);

      setSelectedId(id);

      return;

    }



    setDrawing((prev) => [...prev, x, y]);

  };



  const finishPolygon = () => {

    if (drawing.length < 6) return;

    playClick();

    const id = `draft-${Date.now()}`;

    setDraftZones((prev) => [

      ...prev,

      {

        id,

        name: `Zone ${savedZones.length + prev.length + 1}`,

        points: drawing,

        color: '#00D4FF',

        cameraId: selectedCamera?.id ?? '',

      },

    ]);

    setDrawing([]);

    setSelectedId(id);

  };



  const saveAll = async () => {

    if (!orgId || !siteId || !selectedCamera) {

      setMessage(t('zoneEditor.noSite'));

      return;

    }

    if (editMode === 'zone' && draftZones.length === 0) {

      setMessage(t('zoneEditor.saveError'));

      return;

    }

    if (editMode === 'line' && draftLines.length === 0) {

      setMessage(t('zoneEditor.lineSaveError'));

      return;

    }

    setSaving(true);

    setMessage('');

    const zonesToSuggest: SavedZoneSuggestion[] = editMode === 'zone'
      ? draftZones.map((z) => ({
          name: z.name,
          behavior: z.behavior,
          cameraId: selectedCamera.id,
        }))
      : [];

    try {

      if (editMode === 'zone') {

        for (const zone of draftZones) {

          const polygon = pointsToPolygon(zone.points, zone.edgeDistancesM);
          const derived = derivedTravelDistanceM(zone.points, zone.edgeDistancesM);
          let behaviorConfig = zone.behaviorConfig ?? {};
          if (zone.behavior === 'speed_measurement' && derived != null) {
            behaviorConfig = { ...behaviorConfig, distance_m: derived };
          }

          await zonesApi.create(orgId, {

            site_id: siteId,

            camera_id: selectedCamera.id,

            name: zone.name,

            polygon,

            color: zone.color,

            zone_kind: zone.zoneKind || '',

            behavior_config: zone.behavior
              ? { behavior: zone.behavior, config: behaviorConfig }
              : {},

          });

        }

        setDraftZones([]);

      } else {

        for (const line of draftLines) {

          await zonesApi.createLine(orgId, {

            site_id: siteId,

            camera_id: selectedCamera.id,

            name: line.name,

            start_point: { x: line.start[0] / STAGE_WIDTH, y: line.start[1] / STAGE_HEIGHT },

            end_point: { x: line.end[0] / STAGE_WIDTH, y: line.end[1] / STAGE_HEIGHT },

            direction: 'both',

          });

        }

        setDraftLines([]);

      }

      playSonar();

      setMessage(t('zoneEditor.saved'));

      if (zonesToSuggest.length > 0) {
        setSavedZoneSuggestions(zonesToSuggest);
      }

      await loadSpatial();

      // Auto-clear success message after reload so the UI stays clean.
      setMessage('');

    } catch {

      setMessage(t('zoneEditor.saveFailed'));

    } finally {

      setSaving(false);

    }

  };



  const switchMode = (mode: EditMode) => {

    playClick();

    setEditMode(mode);

    setDrawing([]);

    setLineDraftStart(null);

    setSelectedId(null);

  };



  if (isLoading) return <LoadingState />;



  if (!selectedCamera) {

    return (

      <div>

        {!embedded && <PageHeader title={t('zoneEditor.title')} onHelpTour={startTour} />}

        <EmptyState

          title={embedded ? t('demoCenter.zoneInlineNeedStream') : t('zoneEditor.noCamera')}

          hint={embedded ? t('demoCenter.emptyStreamBody') : t('zoneEditor.noCameraHint')}

          icon={Video}

        />

      </div>

    );

  }



  return (

    <div>

      {!embedded && (
      <PageHeader

        title={t('zoneEditor.title')}

        subtitle={selectedCamera?.name}

        onHelpTour={startTour}

        actions={
          <div className="flex items-center gap-2">
            <label className="text-xs text-cv-muted shrink-0">{t('zoneEditor.cameraLabel')}</label>
            <PremiumSelect
              value={selectedCamera?.id ?? ''}
              onChange={(id) => {
                playClick();
                setSearchParams({ camera: id });
              }}
              options={cameras.map((c) => ({ value: c.id, label: c.name }))}
              triggerClassName="min-w-[200px]"
              minWidth={260}
            />
          </div>
        }

      />
      )}

      <div id="zone-toolbar" className="flex gap-2 flex-wrap mb-4">
            <button
              type="button"
              onClick={() => switchMode('zone')}
              className={`cv-btn-secondary text-xs ${editMode === 'zone' ? 'border-cv-accent' : ''}`}
            >
              <Pentagon className="w-3 h-3" />
              {t('zoneEditor.modeZone')}
            </button>
            <button
              type="button"
              onClick={() => switchMode('line')}
              className={`cv-btn-secondary text-xs ${editMode === 'line' ? 'border-cv-accent' : ''}`}
            >
              <Minus className="w-3 h-3" />
              {t('zoneEditor.modeLine')}
            </button>
            {editMode === 'zone' && (
              <button type="button" onClick={finishPolygon} disabled={drawing.length < 6} className="cv-btn-secondary text-xs">
                <Pentagon className="w-3 h-3" />
                {t('zoneEditor.finishPolygon')}
              </button>
            )}
            <button
              type="button"
              onClick={() => void saveAll()}
              disabled={saving || (editMode === 'zone' ? draftZones.length === 0 : draftLines.length === 0)}
              className="cv-btn-primary text-xs"
            >
              <Save className="w-3 h-3" />
              {saving ? '…' : t('zoneEditor.save')}
            </button>
      </div>



      {message && <p className="text-sm text-center mb-4 text-cv-accent">{message}</p>}

      {savedZoneSuggestions.length > 0 && (
        <ZoneRuleSuggestions
          savedZones={savedZoneSuggestions}
          onDismiss={() => setSavedZoneSuggestions([])}
          onConfigureTemplate={(templateId) => {
            navigate('/rules', { state: { configureTemplateId: templateId } });
          }}
        />
      )}

      <p className="text-sm text-cv-muted mb-4 max-w-2xl">

        {editMode === 'zone'

          ? t('zoneEditor.instructionsZone')

          : t('zoneEditor.instructionsLine')}

      </p>



      <div className={`grid grid-cols-1 gap-6 ${embedded ? '' : 'lg:grid-cols-4'}`}>

        <div ref={containerRef} className={`cv-card p-4 overflow-x-auto ${embedded ? '' : 'lg:col-span-3'}`}>

          <div
            ref={canvasRef}
            id="zone-canvas"
            className="relative rounded-lg overflow-hidden border border-cv-border mx-auto"
            style={{ width: layout.width, height: layout.height }}
          >

            <Go2RtcPlayer
              src={streamSrc || undefined}
              bare
              friendlyErrors={embedded}
              objectFit="fill"
              className="absolute inset-0 w-full h-full pointer-events-none"
            />

            <Stage

              width={layout.width}

              height={layout.height}

              onClick={handleStageClick}

              className="absolute inset-0 z-10 cursor-crosshair"

              style={{ background: 'transparent' }}

            >

              <Layer scaleX={scaleX} scaleY={scaleY}>

                {editMode === 'zone' && allZones.map((zone) => (

                  <Line

                    key={zone.id}

                    points={zone.points}

                    closed

                    stroke={zone.color}

                    strokeWidth={2}

                    fill={`${zone.color}33`}

                  />

                ))}

                {editMode === 'zone' && selectedZone && vertexCountFromPoints(selectedZone.points) >= 3 && (() => {
                  const n = vertexCountFromPoints(selectedZone.points);
                  const hi = highlightedEdgeIndex;
                  const hiVerts = hi != null ? edgeVertexIndices(hi, n) : null;
                  return (
                    <>
                      {Array.from({ length: n }, (_, vi) => {
                        const x = selectedZone.points[vi * 2];
                        const y = selectedZone.points[vi * 2 + 1];
                        const isEndpoint = hiVerts != null && (vi === hiVerts[0] || vi === hiVerts[1]);
                        return (
                          <Circle
                            key={`sel-v-${vi}`}
                            x={x}
                            y={y}
                            radius={isEndpoint ? 9 : 6}
                            fill={isEndpoint ? '#FFD54F' : '#FFFFFF'}
                            stroke={isEndpoint ? '#FF9800' : selectedZone.color}
                            strokeWidth={isEndpoint ? 3 : 2}
                            shadowBlur={isEndpoint ? 14 : 6}
                            shadowColor={isEndpoint ? '#FF9800' : selectedZone.color}
                            listening={false}
                          />
                        );
                      })}
                      {Array.from({ length: n }, (_, vi) => {
                        const x = selectedZone.points[vi * 2];
                        const y = selectedZone.points[vi * 2 + 1];
                        const isEndpoint = hiVerts != null && (vi === hiVerts[0] || vi === hiVerts[1]);
                        return (
                          <Text
                            key={`sel-vl-${vi}`}
                            x={x + 10}
                            y={y - 18}
                            text={`P${vi + 1}`}
                            fontSize={isEndpoint ? 14 : 12}
                            fontStyle="bold"
                            fill={isEndpoint ? '#FFD54F' : '#FFFFFF'}
                            stroke="#000000"
                            strokeWidth={0.75}
                            listening={false}
                          />
                        );
                      })}
                      {hi != null && (
                        <>
                          <Line
                            key="hi-edge"
                            points={edgeStagePoints(selectedZone.points, hi)}
                            stroke="#FFD54F"
                            strokeWidth={7}
                            lineCap="round"
                            shadowBlur={16}
                            shadowColor="#FF9800"
                            listening={false}
                          />
                          <Text
                            key="hi-edge-label"
                            x={midEdgeStageCoords(selectedZone.points, hi).x}
                            y={midEdgeStageCoords(selectedZone.points, hi).y - 10}
                            text={`P${hi + 1}→P${((hi + 1) % n) + 1}`}
                            fontSize={14}
                            fontStyle="bold"
                            fill="#FFD54F"
                            stroke="#000000"
                            strokeWidth={1}
                            align="center"
                            offsetX={24}
                            listening={false}
                          />
                        </>
                      )}
                    </>
                  );
                })()}

                {editMode === 'zone' && selectedZone?.behavior === 'speed_measurement'
                  && Array.from(
                    { length: vertexCountFromPoints(selectedZone.points) },
                    (_, i) => {
                      const d = selectedZone.edgeDistancesM?.[i];
                      if (d == null || d <= 0) return null;
                      const mid = midEdgeStageCoords(selectedZone.points, i);
                      return (
                        <Text
                          key={`edge-label-${i}`}
                          x={mid.x}
                          y={mid.y - 8}
                          text={`${d} m`}
                          fontSize={12}
                          fill="#FFFFFF"
                          stroke="#000000"
                          strokeWidth={0.5}
                          listening={false}
                        />
                      );
                    },
                  )}

                {editMode === 'line' && allLines.map((line) => (

                  <Line

                    key={line.id}

                    points={line.points}

                    stroke="#FF6B35"

                    strokeWidth={3}

                    dash={[8, 4]}

                  />

                ))}

                {editMode === 'line' && lineDraftStart && (

                  <Circle x={lineDraftStart[0]} y={lineDraftStart[1]} radius={6} fill="#FF6B35" shadowBlur={10} />

                )}

                {editMode === 'zone' && drawing.length > 0 && (

                  <>

                    <Line points={drawing} stroke="#00FFFF" strokeWidth={2} dash={[6, 4]} />

                    {drawing.reduce<number[][]>((acc, _, i) => {

                      if (i % 2 === 0) acc.push([drawing[i], drawing[i + 1]]);

                      return acc;

                    }, []).map(([x, y], i) => (

                      <Circle key={i} x={x} y={y} radius={5} fill="#00FFFF" shadowBlur={8} />

                    ))}

                  </>

                )}

              </Layer>

            </Stage>

          </div>

        </div>



        <div id="zone-behavior-panel" className="cv-card p-4">

          <div className="flex items-center justify-between mb-3">

            <h3 className="font-display text-sm font-semibold">

              {editMode === 'zone' ? t('zoneEditor.zoneLabel') : t('zoneEditor.lineLabel')}

            </h3>

            {loadingSpatial && <span className="text-xs text-cv-muted">…</span>}

          </div>

          {editMode === 'zone' ? (

            allZones.length === 0 && drawing.length === 0 ? (

              <EmptyState title={t('zoneEditor.empty')} hint={t('zoneEditor.emptyHint')} icon={Shapes} />

            ) : (

              <SpatialList

                items={allZones.map((z) => {
                  const beh = getBehavior(z.behavior);
                  const kindLabel = beh && beh.id
                    ? (lang === 'fr' ? beh.label_fr : beh.label_en)
                    : zoneKindLabel(z.zoneKind);
                  return {
                    id: z.id,
                    name: z.name,
                    detail: `${z.points.length / 2} pts${kindLabel ? ` · ${kindLabel}` : ''} · ${z.id.startsWith('draft-') ? t('zoneEditor.draftBadge') : t('zoneEditor.savedBadge')}`,
                    isDraft: z.id.startsWith('draft-'),
                  };
                })}

                selectedId={selectedId}

                onSelect={setSelectedId}

                onDelete={(id, isDraft) => {
                  playClick();
                  if (isDraft) {
                    setDraftZones((p) => p.filter((z) => z.id !== id));
                  } else if (orgId) {
                    const z = savedZones.find((x) => x.id === id);
                    setDeleteConfirm({ type: 'zone', id, name: z?.name ?? id });
                  }
                }}

              />

            )

          ) : allLines.length === 0 && !lineDraftStart ? (

            <EmptyState title={t('zoneEditor.lineEmpty')} hint={t('zoneEditor.lineEmptyHint')} icon={Minus} />

          ) : (

            <SpatialList

              items={allLines.map((l) => ({

                id: l.id,

                name: l.name,

                detail: l.id.startsWith('draft-line-') ? t('zoneEditor.draftBadge') : t('zoneEditor.savedBadge'),

                isDraft: l.id.startsWith('draft-line-'),

              }))}

              selectedId={selectedId}

              onSelect={setSelectedId}

              onDelete={(id, isDraft) => {
                playClick();
                if (isDraft) {
                  setDraftLines((p) => p.filter((l) => l.id !== id));
                } else if (orgId) {
                  const l = savedLines.find((x) => x.id === id);
                  setDeleteConfirm({ type: 'line', id, name: l?.name ?? id });
                }
              }}

            />

          )}

          {selectedId && (
            <div className="mt-3 pt-3 border-t border-cv-border space-y-3">
              <div className="space-y-1.5">
                <label className="text-xs text-cv-muted">
                  {editMode === 'zone' ? t('zoneEditor.zoneName') : t('zoneEditor.lineName')}
                </label>
                <input
                  className="cv-input w-full text-sm"
                  value={editName}
                  disabled={savingName}
                  placeholder={t('zoneEditor.namePlaceholder')}
                  onChange={(e) => setEditName(e.target.value)}
                  onBlur={() => void saveSelectedName()}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') e.currentTarget.blur();
                    if (e.key === 'Escape') {
                      const current = editMode === 'zone'
                        ? allZones.find((x) => x.id === selectedId)
                        : allLines.find((x) => x.id === selectedId);
                      setEditName(current?.name ?? '');
                      e.currentTarget.blur();
                    }
                  }}
                />
                <p className="text-[10px] text-cv-muted leading-relaxed">{t('zoneEditor.renameHint')}</p>
              </div>

              {editMode === 'zone' && selectedZone && (() => {
                const selectedBehavior = resolveBehaviorMeta(selectedZone.behavior, capabilityBehaviors, lang)
                  ?? getBehavior(selectedZone.behavior);
                const needsTrafficLightZone =
                  selectedZone.behavior === 'red_light_observation'
                  && !allZones.some(
                    (z) => z.id !== selectedZone.id && z.behavior === 'traffic_light_color',
                  );
                return (
                  <div className="space-y-1.5">
                    <label className="text-xs text-cv-muted flex items-center gap-1">
                      {t('zoneEditor.behaviorLabel')}
                      <InfoTip helpKey="zoneBehavior" content={t('zoneEditor.behaviorTipDynamic', { defaultValue: 'Liste dynamique : catalogue + modèles org importés. Grisé = prérequis manquants (modèle non chargé).' })} />
                    </label>
                    <ExplanatorySelect
                      value={selectedZone.behavior ?? ''}
                      onChange={(v) => void saveSelectedBehavior(v)}
                      options={zoneBehaviorOptions}
                      searchable
                    />
                    {selectedZone.behavior === 'speed_measurement'
                      && vertexCountFromPoints(selectedZone.points) >= 3 && (
                      <div ref={edgeCalibrationRef}>
                        <ZoneEdgeCalibration
                          points={selectedZone.points}
                          edgeDistancesM={
                            selectedZone.edgeDistancesM
                            ?? Array.from(
                              { length: vertexCountFromPoints(selectedZone.points) },
                              () => undefined,
                            )
                          }
                          onChange={(i, m) => void saveSelectedEdgeDistance(i, m)}
                          readOnlyDistanceM={
                            typeof selectedZone.behaviorConfig?.distance_m === 'number'
                              ? selectedZone.behaviorConfig.distance_m
                              : null
                          }
                          requiresSpeedBehavior={false}
                          activeEdgeIndex={highlightedEdgeIndex}
                          onEdgeHighlight={setHighlightedEdgeIndex}
                          entryEdgeIndex={
                            typeof selectedZone.behaviorConfig?.entry_edge_index === 'number'
                              ? selectedZone.behaviorConfig.entry_edge_index
                              : null
                          }
                          exitEdgeIndex={
                            typeof selectedZone.behaviorConfig?.exit_edge_index === 'number'
                              ? selectedZone.behaviorConfig.exit_edge_index
                              : null
                          }
                          onEntryEdgeChange={(i) => void saveSelectedBehaviorConfig('entry_edge_index', i)}
                          onExitEdgeChange={(i) => void saveSelectedBehaviorConfig('exit_edge_index', i)}
                        />
                      </div>
                    )}
                    {selectedBehavior && (
                      <BehaviorDetail
                        behavior={selectedBehavior}
                        lang={lang}
                        config={selectedZone.behaviorConfig ?? {}}
                        onConfigChange={(k, v) => void saveSelectedBehaviorConfig(k, v)}
                        capabilityLabel={t(`zoneEditor.capability_${selectedBehavior.capability}`)}
                      />
                    )}
                    {needsTrafficLightZone && (
                      <p className="text-xs text-amber-400/90 border border-amber-500/30 rounded-md px-2.5 py-2 bg-amber-500/5">
                        {t('zoneEditor.redLightSynergyWarning')}
                      </p>
                    )}
                    <ZoneRuleLinkPanel
                      zoneName={selectedZone.name}
                      links={rulesLinkedToZone(selectedZone.name, rules, zoneRuleLinkContext)}
                    />
                  </div>
                );
              })()}

              {editMode === 'line' && selectedLine && (() => {
                const selectedBehavior = resolveBehaviorMeta(selectedLine.behavior, capabilityBehaviors, lang)
                  ?? getBehavior(selectedLine.behavior);
                return (
                  <div className="space-y-1.5">
                    <label className="text-xs text-cv-muted flex items-center gap-1">
                      {t('zoneEditor.lineBehaviorLabel', { defaultValue: 'Comportement IA (ligne)' })}
                      <InfoTip helpKey="lineBehavior" content={t('zoneEditor.lineBehaviorTip', { defaultValue: 'Comptage natif ou comportements org compatibles ligne. Liste synchronisée avec capabilities/menu.' })} />
                    </label>
                    <ExplanatorySelect
                      value={selectedLine.behavior ?? 'count_crossings'}
                      onChange={(v) => void saveSelectedLineBehavior(v)}
                      options={lineBehaviorOptions}
                      searchable
                    />
                    {selectedBehavior && (
                      <BehaviorDetail
                        behavior={selectedBehavior}
                        lang={lang}
                        config={selectedLine.behaviorConfig ?? {}}
                        onConfigChange={(k, v) => void saveSelectedLineBehaviorConfig(k, v)}
                        capabilityLabel={t(`zoneEditor.capability_${selectedBehavior.capability}`)}
                      />
                    )}
                  </div>
                );
              })()}
            </div>
          )}

          <button

            type="button"

            className="cv-btn-secondary w-full mt-3 text-xs"

            onClick={() => {

              playClick();

              setSelectedId(null);

              setDrawing([]);

              setLineDraftStart(null);

            }}

          >

            <Plus className="w-3 h-3" />

            {editMode === 'zone' ? t('zoneEditor.newZone') : t('zoneEditor.newLine')}

          </button>

        </div>

      </div>

      <ConfirmDialog
        open={deleteConfirm != null}
        title={deleteConfirm?.type === 'zone' ? t('zoneEditor.deleteZoneTitle') : t('zoneEditor.deleteLineTitle')}
        message={t('zoneEditor.deleteConfirmMsg', { name: deleteConfirm?.name ?? '' })}
        confirmLabel={t('common.delete')}
        danger
        onConfirm={() => {
          if (!orgId || !deleteConfirm) return;
          const run = deleteConfirm.type === 'zone'
            ? zonesApi.delete(orgId, deleteConfirm.id)
            : zonesApi.deleteLine(orgId, deleteConfirm.id);
          void run.then(() => loadSpatial()).finally(() => setDeleteConfirm(null));
        }}
        onCancel={() => setDeleteConfirm(null)}
      />
    </div>
  );
}



function SpatialList({

  items,

  selectedId,

  onSelect,

  onDelete,

}: {

  items: { id: string; name: string; detail: string; isDraft: boolean }[];

  selectedId: string | null;

  onSelect: (id: string | null) => void;

  onDelete: (id: string, isDraft: boolean) => void;

}) {

  const { t } = useTranslation();

  return (

    <div className="space-y-2 max-h-80 overflow-y-auto">

      {items.map((item) => (

        <div

          key={item.id}

          className={`p-3 rounded-lg border cursor-pointer transition-colors ${

            selectedId === item.id ? 'border-cv-accent bg-cv-accent/5 ring-1 ring-cv-accent/30' : 'border-cv-border hover:border-cv-accent/30'

          }`}

          onClick={() => onSelect(item.id === selectedId ? null : item.id)}

          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onSelect(item.id === selectedId ? null : item.id);
            }
          }}

          role="button"

          tabIndex={0}

        >

          <div className="flex items-start justify-between gap-2">

            <div className="min-w-0 flex-1">

              <p className="font-medium text-sm">{item.name}</p>

              <p className="text-xs text-cv-muted">{item.detail}</p>

            </div>

            <button
              type="button"
              className="cv-btn-ghost p-1.5 text-red-400 shrink-0 self-center"
              title={item.isDraft ? undefined : t('common.delete')}
              onClick={(e) => {
                e.stopPropagation();
                onDelete(item.id, item.isDraft);
              }}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>

          </div>

        </div>

      ))}

    </div>

  );

}

/** Renders the description, capability badge, prerequisites and config fields of a zone behavior. */
function BehaviorDetail({
  behavior,
  lang,
  config,
  onConfigChange,
  capabilityLabel,
}: {
  behavior: ZoneBehavior;
  lang: 'fr' | 'en';
  config: Record<string, unknown>;
  onConfigChange: (key: string, value: unknown) => void;
  capabilityLabel: string;
}) {
  const { t } = useTranslation();
  const desc = lang === 'fr' ? behavior.human_description_fr : behavior.human_description_en;
  const capClass =
    behavior.capability === 'real'
      ? 'cv-behavior-cap--real'
      : behavior.capability === 'partial'
      ? 'cv-behavior-cap--partial'
      : 'cv-behavior-cap--beta';
  return (
    <div className="mt-2 space-y-2 rounded-lg border border-cv-border/60 bg-cv-bg/40 p-2.5">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`cv-behavior-cap ${capClass}`}>{capabilityLabel}</span>
        {behavior.requires.length > 0 && (
          <span className="text-[10px] text-cv-muted/80">
            {t('zoneEditor.behaviorRequires')}: {behavior.requires.join(', ')}
          </span>
        )}
      </div>
      <p className="text-[11px] text-cv-muted leading-relaxed">{desc}</p>
      {behavior.config_fields.length > 0 && (
        <div className="space-y-2 pt-1">
          {behavior.config_fields.map((f) => {
            const value = config[f.key] ?? f.default ?? '';
            const label = lang === 'fr' ? f.label_fr : f.label_en;
            const hint = lang === 'fr' ? f.hint_fr : f.hint_en;
            return (
              <div key={f.key} className="space-y-1">
                <label className="text-[11px] text-cv-muted">{label}</label>
                {f.type === 'class_filter' || f.type === 'enum' ? (
                  <input
                    className="cv-input w-full text-sm"
                    value={String(value)}
                    onChange={(e) => onConfigChange(f.key, e.target.value)}
                  />
                ) : (
                  <input
                    type="number"
                    className="cv-input w-full text-sm"
                    value={String(value)}
                    min={f.min}
                    max={f.max}
                    step={f.step}
                    onChange={(e) => onConfigChange(f.key, Number(e.target.value))}
                  />
                )}
                {hint && <p className="text-[10px] text-cv-muted/70 leading-relaxed">{hint}</p>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


