import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { Stage, Layer, Line, Circle } from 'react-konva';

import type { KonvaEventObject } from 'konva/lib/Node';

import { useTranslation } from 'react-i18next';

import { Plus, Save, Pentagon, Shapes, Trash2, Video, Minus } from 'lucide-react';

import PageHeader from '@/components/ui/PageHeader';

import EmptyState from '@/components/EmptyState';

import LoadingState from '@/components/ui/LoadingState';

import { useCameras } from '@/hooks/api/queries';

import { useAutoPageTour } from '@/hooks/useAutoPageTour';

import { useSound } from '@/hooks/useSound';

import { useAuthStore } from '@/stores/authStore';

import { zonesApi, type BackendZone, type BackendLine } from '@/api/client';

import ConfirmDialog from '@/components/ui/ConfirmDialog';

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

}



interface SavedLine {

  id: string;

  name: string;

  points: number[];

  cameraId: string;

}



function polygonToPoints(polygon: { x: number; y: number }[]): number[] {

  return polygon.flatMap((p) => [p.x * STAGE_WIDTH, p.y * STAGE_HEIGHT]);

}



function backendToZone(z: BackendZone): Zone {

  return {

    id: z.id,

    name: z.name,

    points: polygonToPoints(z.polygon ?? []),

    color: z.color ?? '#00D4FF',

    cameraId: z.camera_id ?? '',

    zoneKind: z.zone_kind || undefined,

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

  };

}



export default function ZoneEditor() {

  const { t } = useTranslation();

  const { playClick, playSonar } = useSound();

  const startTour = useAutoPageTour('zones');

  const orgId = useAuthStore((s) => s.orgId);

  const authSiteId = useAuthStore((s) => s.siteId);

  const { data: cameras = [], isLoading } = useCameras();

  const [editMode, setEditMode] = useState<EditMode>('zone');

  const [savedZones, setSavedZones] = useState<Zone[]>([]);

  const [draftZones, setDraftZones] = useState<Zone[]>([]);

  const [savedLines, setSavedLines] = useState<SavedLine[]>([]);

  const [draftLines, setDraftLines] = useState<DraftLine[]>([]);

  const [lineDraftStart, setLineDraftStart] = useState<[number, number] | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [drawing, setDrawing] = useState<number[]>([]);

  const [saving, setSaving] = useState(false);

  const [loadingSpatial, setLoadingSpatial] = useState(false);

  const [message, setMessage] = useState('');

  const [deleteConfirm, setDeleteConfirm] = useState<{ type: 'zone' | 'line'; id: string; name: string } | null>(null);



  const [searchParams, setSearchParams] = useSearchParams();

  const selectedCamera = cameras.find((c) => c.id === searchParams.get('camera'))
    ?? cameras.find(
      (c) => c.name.toLowerCase().includes('virtual') || c.name.toLowerCase().includes('benedicte'),
    ) ?? cameras[0];

  const siteId = authSiteId ?? selectedCamera?.siteId;

  const streamSrc = go2rtcStreamSrc(selectedCamera);



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

      setMessage(t('zoneEditor.loadFailed', 'Impossible de charger les zones.'));

    } finally {

      setLoadingSpatial(false);

    }

  }, [orgId, selectedCamera, t]);



  useEffect(() => {

    void loadSpatial();

  }, [loadSpatial]);



  const allZones = [...savedZones, ...draftZones];

  const allLines = [...savedLines, ...draftLines.map((d) => ({

    id: d.id,

    name: d.name,

    points: [...d.start, ...d.end],

    cameraId: d.cameraId,

  }))];



  const handleStageClick = (e: KonvaEventObject<MouseEvent>) => {

    const stage = e.target.getStage();

    if (!stage) return;

    const pos = stage.getPointerPosition();

    if (!pos) return;

    playClick();



    if (editMode === 'line') {

      if (!lineDraftStart) {

        setLineDraftStart([pos.x, pos.y]);

        return;

      }

      const id = `draft-line-${Date.now()}`;

      setDraftLines((prev) => [

        ...prev,

        {

          id,

          name: `Ligne ${savedLines.length + prev.length + 1}`,

          start: lineDraftStart,

          end: [pos.x, pos.y],

          cameraId: selectedCamera?.id ?? '',

        },

      ]);

      setLineDraftStart(null);

      setSelectedId(id);

      return;

    }



    setDrawing((prev) => [...prev, pos.x, pos.y]);

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

      setMessage(t('zoneEditor.noSite', 'Site introuvable — reconnectez-vous.'));

      return;

    }

    if (editMode === 'zone' && draftZones.length === 0) {

      setMessage(t('zoneEditor.saveError', 'Dessinez au moins une zone (3 clics, puis « Fermer polygone »).'));

      return;

    }

    if (editMode === 'line' && draftLines.length === 0) {

      setMessage(t('zoneEditor.lineSaveError'));

      return;

    }

    setSaving(true);

    setMessage('');

    try {

      if (editMode === 'zone') {

        for (const zone of draftZones) {

          const polygon = [];

          for (let i = 0; i < zone.points.length; i += 2) {

            polygon.push({

              x: zone.points[i] / STAGE_WIDTH,

              y: zone.points[i + 1] / STAGE_HEIGHT,

            });

          }

          await zonesApi.create(orgId, {

            site_id: siteId,

            camera_id: selectedCamera.id,

            name: zone.name,

            polygon,

            color: zone.color,

            zone_kind: zone.zoneKind || '',

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

      setMessage(t('zoneEditor.saved', 'Enregistré — rechargement…'));

      await loadSpatial();

    } catch {

      setMessage(t('zoneEditor.saveFailed', 'Échec enregistrement — vérifiez la connexion.'));

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

        <PageHeader title={t('zoneEditor.title')} onHelpTour={startTour} />

        <EmptyState

          title={t('zoneEditor.noCamera')}

          hint={t('zoneEditor.noCameraHint')}

          icon={Video}

        />

      </div>

    );

  }



  return (

    <div>

      <PageHeader

        title={t('zoneEditor.title')}

        subtitle={selectedCamera?.name}

        onHelpTour={startTour}

        actions={
          <div className="flex items-center gap-2">
            <label className="text-xs text-cv-muted shrink-0">{t('zoneEditor.cameraLabel')}</label>
            <select
              className="cv-input text-sm max-w-[220px]"
              value={selectedCamera?.id ?? ''}
              onChange={(e) => {
                playClick();
                setSearchParams({ camera: e.target.value });
              }}
            >
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
        }

      />

      <div className="flex gap-2 flex-wrap mb-4">
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



      <p className="text-sm text-cv-muted mb-4 max-w-2xl">

        {editMode === 'zone'

          ? t('zoneEditor.instructionsZone')

          : t('zoneEditor.instructionsLine')}

      </p>



      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">

        <div className="lg:col-span-3 cv-card p-4 overflow-x-auto">

          <div id="zone-canvas" className="relative rounded-lg overflow-hidden border border-cv-border mx-auto" style={{ width: STAGE_WIDTH, height: STAGE_HEIGHT, minWidth: STAGE_WIDTH }}>

            <Go2RtcPlayer src={streamSrc} bare className="absolute inset-0 w-full h-full pointer-events-none" />

            <Stage

              width={STAGE_WIDTH}

              height={STAGE_HEIGHT}

              onClick={handleStageClick}

              className="absolute inset-0 z-10"

              style={{ background: 'transparent' }}

            >

              <Layer>

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



        <div className="cv-card p-4">

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
                  const kindLabel = z.zoneKind
                    ? t(`zoneEditor.zoneKind${z.zoneKind.charAt(0).toUpperCase() + z.zoneKind.slice(1).replace('_', '')}` as never, z.zoneKind)
                    : null;
                  return {
                    id: z.id,
                    name: z.name,
                    detail: `${z.points.length / 2} pts${kindLabel ? ` · ${kindLabel}` : ''}${z.id.startsWith('draft-') ? ' · brouillon' : ' · enregistrée'}`,
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

                detail: l.id.startsWith('draft-line-') ? 'brouillon' : 'enregistrée',

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

          {editMode === 'zone' && selectedId?.startsWith('draft-') && (() => {
            const draft = draftZones.find((z) => z.id === selectedId);
            if (!draft) return null;
            return (
              <div className="mt-3 pt-3 border-t border-cv-border space-y-2">
                <label className="text-xs text-cv-muted flex items-center gap-1">
                  {t('zoneEditor.zoneKind')}
                  <InfoTip content="Le type sémantique indique à l'IA comment interpréter cette zone. « Périmètre » → intrusion. « Sortie contrôlée » → alerte sortie non autorisée. « Stationnement » → illicite si véhicule immobilisé. « Auto » = déduit du nom de la zone." />
                </label>
                <select
                  className="cv-input w-full text-sm"
                  value={draft.zoneKind ?? ''}
                  onChange={(e) => {
                    const v = e.target.value;
                    setDraftZones((prev) =>
                      prev.map((z) => (z.id === selectedId ? { ...z, zoneKind: v || undefined } : z)),
                    );
                  }}
                >
                  <option value="">{t('zoneEditor.zoneKindAuto')}</option>
                  <option value="perimeter">{t('zoneEditor.zoneKindPerimeter')}</option>
                  <option value="controlled_exit">{t('zoneEditor.zoneKindExit')}</option>
                  <option value="corridor">{t('zoneEditor.zoneKindCorridor')}</option>
                  <option value="parking">{t('zoneEditor.zoneKindParking')}</option>
                </select>
              </div>
            );
          })()}

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
        title={deleteConfirm?.type === 'zone' ? 'Supprimer cette zone ?' : 'Supprimer cette ligne ?'}
        message={`« ${deleteConfirm?.name ?? ''} » sera supprimée définitivement.`}
        confirmLabel="Supprimer"
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

  return (

    <div className="space-y-2 max-h-80 overflow-y-auto">

      {items.map((item) => (

        <div

          key={item.id}

          className={`p-3 rounded-lg border cursor-pointer transition-colors ${

            selectedId === item.id ? 'border-cv-accent bg-cv-accent/5' : 'border-cv-border'

          }`}

          onClick={() => onSelect(item.id === selectedId ? null : item.id)}

        >

          <div className="flex items-center justify-between gap-2">

            <div>

              <p className="font-medium text-sm">{item.name}</p>

              <p className="text-xs text-cv-muted">{item.detail}</p>

            </div>

            {item.isDraft ? (
              <button
                type="button"
                className="cv-btn-ghost p-1.5 text-red-400"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(item.id, true);
                }}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                type="button"
                className="cv-btn-ghost p-1.5 text-red-400"
                title="Supprimer"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(item.id, false);
                }}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}

          </div>

        </div>

      ))}

    </div>

  );

}


