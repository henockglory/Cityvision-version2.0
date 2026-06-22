import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MapPin, Map, Move, Camera, Globe, LayoutGrid } from 'lucide-react';
import PageShell from '@/components/ui/PageShell';
import { MapSkeleton } from '@/components/ui/Skeleton';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import CameraMapView, {
  CameraDetailPanel,
  CameraMapLegend,
  type MapViewMode,
} from '@/components/map/CameraMapView';
import GlobeMapView from '@/components/map/GlobeMapView';
import { useCameras, useUpdateCameraMap } from '@/hooks/api/queries';
import { useAuthStore } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import type { MapPosition } from '@/lib/cameraMap';

export default function MapPage() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const startTour = useAutoPageTour('map');
  const orgId = useAuthStore((s) => s.orgId);
  const { data: cameras = [], isLoading, isError, refetch } = useCameras();
  const updateMap = useUpdateCameraMap();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [mapMode, setMapMode] = useState<MapViewMode>('real');

  const selected = cameras.find((c) => c.id === selectedId) ?? null;
  const onlineCount = cameras.filter((c) => c.status !== 'offline').length;

  const savePosition = async (
    cameraId: string,
    _pos: MapPosition,
    metadata: Record<string, unknown>,
  ) => {
    if (!orgId) return;
    await updateMap.mutateAsync({ cameraId, metadata });
  };

  if (isLoading) {
    return (
      <PageShell title={t('map.title', 'Carte')}>
        <MapSkeleton />
      </PageShell>
    );
  }

  if (isError) {
    return (
      <PageShell title={t('map.title')}>
        <ErrorState onRetry={() => void refetch()} />
      </PageShell>
    );
  }

  if (cameras.length === 0) {
    return (
      <PageShell title={t('map.title')}>
        <EmptyState title={t('map.empty')} hint={t('map.emptyHint')} icon={Map} />
      </PageShell>
    );
  }

  const subtitle =
    mapMode === 'globe'
      ? 'Globe 3D — vue cinématique de vos sites'
      : mapMode === 'real'
        ? 'Carte réelle — OpenStreetMap & satellite Esri'
        : t('map.subtitle', 'Plan du site — positionnez vos caméras');

  return (
    <PageShell
      title={t('map.title')}
      subtitle={subtitle}
      onHelpTour={startTour}
      actions={
        mapMode !== 'globe' ? (
          <button
            type="button"
            onClick={() => { playClick(); setEditMode((v) => !v); }}
            className={`cv-btn-secondary text-xs whitespace-nowrap ${editMode ? 'border-cv-accent text-cv-accent' : ''}`}
          >
            <Move className="w-3.5 h-3.5 shrink-0" />
            {editMode ? 'Édition active' : 'Placer les caméras'}
          </button>
        ) : undefined
      }
    >
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div id="map-canvas" className="lg:col-span-8 cv-card p-3 flex flex-col min-h-[460px]">
          <div id="map-mode-tabs" className="flex gap-1 mb-3 p-1 bg-cv-deep/60 rounded-lg w-fit border border-cv-border/50 flex-wrap">
            {([
              { id: 'real' as const, label: 'Carte', icon: Map },
              { id: 'schematic' as const, label: 'Plan site', icon: LayoutGrid },
              { id: 'globe' as const, label: 'Globe', icon: Globe },
            ]).map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => { playClick(); setMapMode(id); if (id === 'globe') setEditMode(false); }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  mapMode === id ? 'bg-cv-accent text-white' : 'text-cv-muted hover:text-cv-text hover:bg-cv-accent/10'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
              </button>
            ))}
          </div>

          <div className="flex-1 min-h-[400px]">
            {mapMode === 'globe' ? (
              <GlobeMapView cameras={cameras} selectedId={selectedId} onSelect={setSelectedId} />
            ) : (
              <CameraMapView
                mode={mapMode}
                cameras={cameras}
                selectedId={selectedId}
                onSelect={setSelectedId}
                editMode={editMode}
                onSavePosition={savePosition}
              />
            )}
          </div>
          <div className="mt-2 px-1">
            <CameraMapLegend count={cameras.length} online={onlineCount} />
          </div>
        </div>

        <div className="lg:col-span-4 space-y-3">
          <div className="cv-card p-4">
            <h3 className="font-display text-sm font-semibold mb-3 flex items-center gap-2">
              <MapPin className="w-4 h-4 text-cv-accent shrink-0" />
              <span className="truncate">{selected ? selected.name : 'Fiche caméra SIG'}</span>
            </h3>
            <CameraDetailPanel camera={selected} onClose={() => setSelectedId(null)} />
          </div>

          <div className="cv-card p-4">
            <h3 className="font-display text-sm font-semibold mb-2 flex items-center gap-2">
              <Camera className="w-4 h-4 text-cv-accent" />
              {t('map.cameras')}
            </h3>
            <div className="space-y-1 max-h-52 overflow-y-auto">
              {cameras.map((cam) => (
                <button
                  key={cam.id}
                  type="button"
                  onClick={() => { playClick(); setSelectedId(cam.id); }}
                  className={`w-full flex items-center gap-2 p-2 rounded-lg text-left text-sm transition-colors ${
                    selectedId === cam.id ? 'bg-cv-accent/10 border border-cv-accent/30' : 'hover:bg-cv-accent/5 border border-transparent'
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full shrink-0 ${cam.status !== 'offline' ? 'bg-metric-rules' : 'bg-severity-critical'}`} />
                  <span className="truncate font-medium">{cam.name}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
}
