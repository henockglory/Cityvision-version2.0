import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Camera, GripVertical, Save } from 'lucide-react';
import { Link } from 'react-router-dom';
import L from 'leaflet';
import {
  LayersControl,
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
} from 'react-leaflet';
import type { Camera as CameraType } from '@/types';
import {
  getCameraGeoPosition,
  getCameraMapPosition,
  getGeoMapCenter,
  mergeGeoMetadata,
  mergeMapMetadata,
  type GeoPosition,
  type MapPosition,
} from '@/lib/cameraMap';
import { useSound } from '@/hooks/useSound';
import CameraHoverPreview from '@/components/map/CameraHoverPreview';

export type MapViewMode = 'real' | 'schematic' | 'globe';

interface PinState {
  cameraId: string;
  pos: MapPosition;
}

interface GeoPinState {
  cameraId: string;
  pos: GeoPosition;
}

interface CameraMapViewProps {
  cameras: CameraType[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  editMode: boolean;
  mode: MapViewMode;
  onSavePosition: (cameraId: string, pos: MapPosition, metadata: Record<string, unknown>) => Promise<void>;
}

function cameraDivIcon(isOnline: boolean, isSelected: boolean): L.DivIcon {
  const color = isOnline ? 'rgb(59 130 246)' : 'rgb(248 113 113)';
  const ring = isSelected ? 'box-shadow:0 0 0 2px rgb(12 20 36),0 0 0 4px rgb(59 130 246);' : '';
  return L.divIcon({
    className: '',
    html: `<div style="width:36px;height:36px;border-radius:9999px;border:2px solid ${color};background:${isOnline ? 'rgba(59,130,246,0.25)' : 'rgba(248,113,113,0.2)'};display:flex;align-items:center;justify-content:center;${ring}">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/></svg>
    </div>`,
    iconSize: [36, 36],
    iconAnchor: [18, 18],
    popupAnchor: [0, -18],
  });
}

function MapBoundsFitter({ cameras }: { cameras: CameraType[] }) {
  const map = useMap();
  const positions = useMemo(
    () => cameras.map((c, i) => getCameraGeoPosition(c.metadata, i)),
    [cameras],
  );

  useEffect(() => {
    if (positions.length === 0) return;
    if (positions.length === 1) {
      map.setView([positions[0].lat, positions[0].lng], 16);
      return;
    }
    const bounds = L.latLngBounds(positions.map((p) => [p.lat, p.lng] as [number, number]));
    map.fitBounds(bounds.pad(0.2));
  }, [map, positions]);

  return null;
}

function SchematicMapView({
  cameras,
  selectedId,
  onSelect,
  editMode,
  onSavePosition,
}: Omit<CameraMapViewProps, 'mode'>) {
  const { playClick } = useSound();
  const containerRef = useRef<HTMLDivElement>(null);
  const [pins, setPins] = useState<PinState[]>(() =>
    cameras.map((c, i) => ({
      cameraId: c.id,
      pos: getCameraMapPosition(c.metadata, i),
    })),
  );
  const [dragging, setDragging] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [dirty, setDirty] = useState<Set<string>>(new Set());

  const syncPins = useCallback(() => {
    setPins(
      cameras.map((c, i) => ({
        cameraId: c.id,
        pos: getCameraMapPosition(c.metadata, i),
      })),
    );
    setDirty(new Set());
  }, [cameras]);

  useEffect(() => {
    syncPins();
  }, [syncPins]);

  const handlePointerDown = (cameraId: string) => {
    if (!editMode) {
      playClick();
      onSelect(cameraId);
      return;
    }
    setDragging(cameraId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!dragging || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    const pos = {
      x: Math.max(0.04, Math.min(0.96, x)),
      y: Math.max(0.04, Math.min(0.96, y)),
    };
    setPins((prev) =>
      prev.map((p) => (p.cameraId === dragging ? { ...p, pos } : p)),
    );
    setDirty((d) => new Set(d).add(dragging));
  };

  const handlePointerUp = () => setDragging(null);

  const savePin = async (cameraId: string) => {
    const cam = cameras.find((c) => c.id === cameraId);
    const pin = pins.find((p) => p.cameraId === cameraId);
    if (!cam || !pin) return;
    setSaving(cameraId);
    playClick();
    try {
      await onSavePosition(cameraId, pin.pos, mergeMapMetadata(cam.metadata, pin.pos));
      setDirty((d) => {
        const n = new Set(d);
        n.delete(cameraId);
        return n;
      });
    } finally {
      setSaving(null);
    }
  };

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full min-h-[420px] overflow-hidden rounded-lg select-none touch-none"
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerUp}
    >
      <div
        className="absolute inset-0 bg-cover bg-center opacity-40"
        style={{ backgroundImage: 'url(/bg-premium-network.png)' }}
      />
      <div className="absolute inset-0 bg-gradient-to-br from-cv-deep/90 via-cv-navy/80 to-cv-deep/95" />
      <svg className="absolute inset-0 w-full h-full opacity-25 pointer-events-none">
        <defs>
          <pattern id="siteGrid" width="48" height="48" patternUnits="userSpaceOnUse">
            <path d="M 48 0 L 0 0 0 48" fill="none" stroke="rgb(var(--cv-accent))" strokeWidth="0.4" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#siteGrid)" />
      </svg>

      {pins.map((pin) => {
        const cam = cameras.find((c) => c.id === pin.cameraId);
        if (!cam) return null;
        const isOnline = cam.status !== 'offline';
        const isSelected = selectedId === cam.id;
        const isDirty = dirty.has(cam.id);
        return (
          <div
            key={cam.id}
            className="absolute transform -translate-x-1/2 -translate-y-1/2 z-10"
            style={{ left: `${pin.pos.x * 100}%`, top: `${pin.pos.y * 100}%` }}
          >
            <button
              type="button"
              onPointerDown={(e) => {
                e.currentTarget.setPointerCapture(e.pointerId);
                handlePointerDown(cam.id);
              }}
              className={`group relative flex items-center gap-1 transition-transform ${
                editMode ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer hover:scale-110'
              } ${isSelected ? 'scale-110' : ''}`}
            >
              <div
                className={`relative p-2.5 rounded-full border-2 shadow-glow ${
                  isOnline
                    ? 'border-cv-accent bg-cv-accent/25'
                    : 'border-red-400/60 bg-red-400/15'
                } ${isSelected ? 'ring-2 ring-cv-accent ring-offset-2 ring-offset-cv-deep' : ''}`}
              >
                <Camera className={`w-4 h-4 ${isOnline ? 'text-cv-accent' : 'text-red-400'}`} />
                {isOnline && (
                  <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse border border-cv-deep" />
                )}
              </div>
              {editMode && (
                <GripVertical className="w-3 h-3 text-cv-muted opacity-60" />
              )}
            </button>
            <div
              className={`absolute top-full left-1/2 -translate-x-1/2 mt-1 px-2 py-1 rounded-md text-[10px] whitespace-nowrap border transition-opacity ${
                isSelected || editMode ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
              } bg-cv-surface border-cv-border`}
            >
              <p className="font-medium">{cam.name}</p>
              <p className="text-cv-muted">{cam.ip}</p>
              {editMode && isDirty && (
                <button
                  type="button"
                  disabled={saving === cam.id}
                  onClick={() => void savePin(cam.id)}
                  className="mt-1 cv-btn-primary text-[9px] py-0.5 px-2 w-full"
                >
                  <Save className="w-2.5 h-2.5 inline mr-1" />
                  {saving === cam.id ? '…' : 'Enregistrer position'}
                </button>
              )}
            </div>
          </div>
        );
      })}

      {cameras.length === 0 && (
        <p className="absolute inset-0 flex items-center justify-center text-cv-muted text-sm">
          Aucune caméra à afficher
        </p>
      )}
    </div>
  );
}

function RealMapView({
  cameras,
  selectedId,
  onSelect,
  editMode,
  onSavePosition,
}: Omit<CameraMapViewProps, 'mode'>) {
  const { playClick } = useSound();
  const [hoverCam, setHoverCam] = useState<CameraType | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);
  const [pins, setPins] = useState<GeoPinState[]>(() =>
    cameras.map((c, i) => ({
      cameraId: c.id,
      pos: getCameraGeoPosition(c.metadata, i),
    })),
  );
  const [saving, setSaving] = useState<string | null>(null);
  const [dirty, setDirty] = useState<Set<string>>(new Set());

  const syncPins = useCallback(() => {
    setPins(
      cameras.map((c, i) => ({
        cameraId: c.id,
        pos: getCameraGeoPosition(c.metadata, i),
      })),
    );
    setDirty(new Set());
  }, [cameras]);

  useEffect(() => {
    syncPins();
  }, [syncPins]);

  const center = useMemo(
    () =>
      getGeoMapCenter(
        pins.map((p) => p.pos),
        cameras.map((c) => c.metadata),
      ),
    [pins, cameras],
  );

  const savePin = async (cameraId: string) => {
    const cam = cameras.find((c) => c.id === cameraId);
    const pin = pins.find((p) => p.cameraId === cameraId);
    if (!cam || !pin) return;
    setSaving(cameraId);
    playClick();
    try {
      await onSavePosition(
        cameraId,
        { x: pin.pos.lat, y: pin.pos.lng },
        mergeGeoMetadata(cam.metadata, pin.pos),
      );
      setDirty((d) => {
        const n = new Set(d);
        n.delete(cameraId);
        return n;
      });
    } finally {
      setSaving(null);
    }
  };

  return (
    <>
    <CameraHoverPreview camera={hoverCam} position={hoverPos} />
    <MapContainer
      center={[center.lat, center.lng]}
      zoom={15}
      className="h-full min-h-[420px] w-full rounded-lg z-0"
      scrollWheelZoom
    >
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked name="OpenStreetMap">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Satellite Esri">
          <TileLayer
            attribution="Tiles &copy; Esri"
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          />
        </LayersControl.BaseLayer>
      </LayersControl>

      <MapBoundsFitter cameras={cameras} />

      {pins.map((pin) => {
        const cam = cameras.find((c) => c.id === pin.cameraId);
        if (!cam) return null;
        const isOnline = cam.status !== 'offline';
        const isSelected = selectedId === cam.id;
        const isDirty = dirty.has(cam.id);
        return (
          <Marker
            key={cam.id}
            position={[pin.pos.lat, pin.pos.lng]}
            icon={cameraDivIcon(isOnline, isSelected)}
            draggable={editMode}
            eventHandlers={{
              click: () => {
                playClick();
                onSelect(cam.id);
              },
              mouseover: (e) => {
                setHoverCam(cam);
                const pt = e.originalEvent as MouseEvent;
                setHoverPos({ x: pt.clientX, y: pt.clientY });
              },
              mouseout: () => {
                setHoverCam(null);
                setHoverPos(null);
              },
              dragend: (e) => {
                const { lat, lng } = e.target.getLatLng();
                const pos = { lat, lng };
                setPins((prev) =>
                  prev.map((p) => (p.cameraId === cam.id ? { ...p, pos } : p)),
                );
                setDirty((d) => new Set(d).add(cam.id));
              },
            }}
          >
            <Popup className="cv-leaflet-popup">
              <div className="text-xs min-w-[140px] text-cv-text">
                <p className="font-semibold">{cam.name}</p>
                <p className="text-cv-muted">{cam.ip}</p>
                <p className="text-cv-muted mt-1 tabular-nums">
                  {pin.pos.lat.toFixed(5)}, {pin.pos.lng.toFixed(5)}
                </p>
                {editMode && isDirty && (
                  <button
                    type="button"
                    disabled={saving === cam.id}
                    onClick={() => void savePin(cam.id)}
                    className="mt-2 w-full cv-btn-primary text-[10px] py-1 disabled:opacity-50"
                  >
                    {saving === cam.id ? '…' : 'Enregistrer position'}
                  </button>
                )}
              </div>
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
    </>
  );
}

export default function CameraMapView({
  mode,
  cameras,
  selectedId,
  onSelect,
  editMode,
  onSavePosition,
}: CameraMapViewProps) {
  if (mode === 'real') {
    return (
      <RealMapView
        cameras={cameras}
        selectedId={selectedId}
        onSelect={onSelect}
        editMode={editMode}
        onSavePosition={onSavePosition}
      />
    );
  }

  return (
    <SchematicMapView
      cameras={cameras}
      selectedId={selectedId}
      onSelect={onSelect}
      editMode={editMode}
      onSavePosition={onSavePosition}
    />
  );
}

export function CameraMapLegend({ count, online }: { count: number; online: number }) {
  return (
    <div className="flex gap-4 text-xs text-cv-muted">
      <span>{count} caméra(s)</span>
      <span className="text-emerald-400">{online} en ligne</span>
    </div>
  );
}

export function CameraDetailPanel({
  camera,
  onClose,
}: {
  camera: CameraType | null;
  onClose: () => void;
}) {
  if (!camera) {
    return (
      <p className="text-sm text-cv-muted py-8 text-center">
        Sélectionnez une caméra sur la carte
      </p>
    );
  }

  const lat = camera.metadata?.lat;
  const lng = camera.metadata?.lng;

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-display font-semibold">{camera.name}</h3>
          <p className="text-xs text-cv-muted">{camera.location}</p>
        </div>
        <button type="button" onClick={onClose} className="cv-btn-ghost text-xs py-1">
          ×
        </button>
      </div>
      <dl className="text-sm space-y-1.5">
        <div className="flex justify-between">
          <dt className="text-cv-muted">IP</dt>
          <dd className="font-mono">{camera.ip}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-cv-muted">Statut</dt>
          <dd className={camera.status !== 'offline' ? 'text-emerald-400' : 'text-red-400'}>
            {camera.status}
          </dd>
        </div>
        {typeof lat === 'number' && typeof lng === 'number' && (
          <div className="flex justify-between gap-2">
            <dt className="text-cv-muted">GPS</dt>
            <dd className="font-mono text-xs text-right">
              {lat.toFixed(5)}, {lng.toFixed(5)}
            </dd>
          </div>
        )}
        {camera.model && (
          <div className="flex justify-between">
            <dt className="text-cv-muted">Modèle</dt>
            <dd>{camera.model}</dd>
          </div>
        )}
      </dl>
      <Link to={`/live?camera=${camera.id}`} className="cv-btn-primary w-full text-xs mt-2">
        Voir le flux live
      </Link>
    </div>
  );
}
