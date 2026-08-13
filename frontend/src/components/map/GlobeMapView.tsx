import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import type { Alert, Camera } from '@/types';
import { DEFAULT_GEO_CENTER, getCameraGeoPosition } from '@/lib/cameraMap';
import LoadingState from '@/components/ui/LoadingState';

const Globe = lazy(() => import('react-globe.gl'));

interface GlobePoint {
  lat: number;
  lng: number;
  size: number;
  color: string;
  cameraId: string;
  name: string;
  status: string;
}

interface GlobeRing {
  lat: number;
  lng: number;
  maxR: number;
  propagationSpeed: number;
  repeatPeriod: number;
  color: (t: number) => string;
}

interface GlobeArc {
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
  color: string[];
}

interface GlobeLabel {
  lat: number;
  lng: number;
  text: string;
  color: string;
  size: number;
  cameraId: string;
}

interface GlobeMapViewProps {
  cameras: Camera[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  alerts?: Alert[];
}

function severityColor(sev: string | undefined): string {
  switch (sev) {
    case 'critical':
      return 'rgba(248,113,113,0.85)';
    case 'high':
      return 'rgba(251,146,60,0.8)';
    case 'medium':
      return 'rgba(250,204,21,0.75)';
    default:
      return 'rgba(96,165,250,0.7)';
  }
}

export default function GlobeMapView({
  cameras,
  selectedId,
  onSelect,
  alerts = [],
}: GlobeMapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globeRef = useRef<any>(undefined);
  const [size, setSize] = useState({ w: 800, h: 420 });
  const [ready, setReady] = useState(false);
  const reducedMotion = useMemo(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const geoByCamera = useMemo(() => {
    const m = new Map<string, { lat: number; lng: number; name: string; online: boolean }>();
    cameras.forEach((c, i) => {
      const pos = getCameraGeoPosition(c.metadata, i);
      m.set(c.id, {
        lat: pos.lat,
        lng: pos.lng,
        name: c.name,
        online: c.status !== 'offline',
      });
    });
    return m;
  }, [cameras]);

  const points = useMemo<GlobePoint[]>(
    () =>
      cameras.map((c, i) => {
        const pos = getCameraGeoPosition(c.metadata, i);
        const selected = selectedId === c.id;
        return {
          lat: pos.lat,
          lng: pos.lng,
          size: selected ? 0.55 : c.status !== 'offline' ? 0.28 : 0.18,
          color: selected
            ? 'rgb(52, 211, 153)'
            : c.status !== 'offline'
              ? 'rgb(59, 130, 246)'
              : 'rgb(248, 113, 113)',
          cameraId: c.id,
          name: c.name,
          status: c.status ?? 'unknown',
        };
      }),
    [cameras, selectedId],
  );

  const labels = useMemo<GlobeLabel[]>(
    () =>
      points.map((p) => ({
        lat: p.lat,
        lng: p.lng,
        text: p.name,
        color: p.color,
        size: selectedId === p.cameraId ? 1.15 : 0.85,
        cameraId: p.cameraId,
      })),
    [points, selectedId],
  );

  const rings = useMemo<GlobeRing[]>(() => {
    if (reducedMotion) return [];
    const recent = alerts.slice(0, 24);
    const out: GlobeRing[] = [];
    for (const a of recent) {
      const geo = geoByCamera.get(a.cameraId);
      if (!geo) continue;
      const base = severityColor(a.severity);
      out.push({
        lat: geo.lat,
        lng: geo.lng,
        maxR: a.severity === 'critical' || a.severity === 'high' ? 3.2 : 2.2,
        propagationSpeed: 2.4,
        repeatPeriod: a.severity === 'critical' ? 900 : 1400,
        color: (t: number) => base.replace(/[\d.]+\)$/, `${Math.max(0.05, 1 - t)})`),
      });
    }
    // Soft pulse on selected camera even without alerts
    if (selectedId) {
      const geo = geoByCamera.get(selectedId);
      if (geo) {
        out.push({
          lat: geo.lat,
          lng: geo.lng,
          maxR: 2.8,
          propagationSpeed: 1.6,
          repeatPeriod: 1800,
          color: (t: number) => `rgba(52,211,153,${Math.max(0.05, 0.85 * (1 - t))})`,
        });
      }
    }
    return out;
  }, [alerts, geoByCamera, selectedId, reducedMotion]);

  const arcs = useMemo<GlobeArc[]>(() => {
    const online = points.filter((p) => p.status !== 'offline');
    if (online.length === 0) return [];
    const hub = selectedId
      ? points.find((p) => p.cameraId === selectedId) ?? online[0]
      : null;
    if (hub) {
      return online
        .filter((p) => p.cameraId !== hub.cameraId)
        .slice(0, 12)
        .map((p) => ({
          startLat: hub.lat,
          startLng: hub.lng,
          endLat: p.lat,
          endLng: p.lng,
          color: ['rgba(52,211,153,0.15)', 'rgba(96,165,250,0.65)'],
        }));
    }
    return online.slice(0, 10).map((p) => ({
      startLat: DEFAULT_GEO_CENTER.lat,
      startLng: DEFAULT_GEO_CENTER.lng,
      endLat: p.lat,
      endLng: p.lng,
      color: ['rgba(59,130,246,0.1)', 'rgba(147,197,253,0.55)'],
    }));
  }, [points, selectedId]);

  const clusterCenter = useMemo(() => {
    if (points.length === 0) return DEFAULT_GEO_CENTER;
    const lat = points.reduce((s, p) => s + p.lat, 0) / points.length;
    const lng = points.reduce((s, p) => s + p.lng, 0) / points.length;
    return { lat, lng };
  }, [points]);

  useEffect(() => {
    // Fallback if onGlobeReady never fires (older react-globe.gl builds).
    if (ready) return;
    const t = window.setTimeout(() => setReady(true), 600);
    return () => window.clearTimeout(t);
  }, [ready, size.w, size.h]);

  useEffect(() => {
    if (!ready || !globeRef.current) return;
    const g = globeRef.current;
    g.pointOfView({ lat: clusterCenter.lat, lng: clusterCenter.lng, altitude: 1.65 }, 900);
    if (!reducedMotion) {
      const ctrl = g.controls?.();
      if (ctrl) {
        ctrl.autoRotate = true;
        ctrl.autoRotateSpeed = 0.85;
        ctrl.enableDamping = true;
      }
    }
  }, [ready, clusterCenter.lat, clusterCenter.lng, reducedMotion, size.w, size.h]);

  useEffect(() => {
    if (!ready || !globeRef.current || !selectedId) return;
    const p = points.find((x) => x.cameraId === selectedId);
    if (!p) return;
    globeRef.current.pointOfView({ lat: p.lat, lng: p.lng, altitude: 1.15 }, reducedMotion ? 0 : 700);
  }, [selectedId, ready, points, reducedMotion]);

  return (
    <div ref={containerRef} className="h-full min-h-[480px] w-full rounded-lg overflow-hidden border border-cv-border bg-cv-deep">
      <Suspense fallback={<LoadingState />}>
        <Globe
          ref={globeRef}
          width={size.w}
          height={size.h}
          globeImageUrl="//unpkg.com/three-globe/example/img/earth-night.jpg"
          bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
          backgroundImageUrl="//unpkg.com/three-globe/example/img/night-sky.png"
          showAtmosphere
          atmosphereColor="rgba(56, 189, 248, 0.55)"
          atmosphereAltitude={0.18}
          pointsData={points}
          pointLat="lat"
          pointLng="lng"
          pointColor="color"
          pointAltitude="size"
          pointRadius={0.45}
          pointLabel={(d: object) => {
            const p = d as GlobePoint;
            return `<div style="padding:4px 8px;font:12px/1.3 sans-serif"><b>${p.name}</b><br/><span style="opacity:.75">${p.status}</span></div>`;
          }}
          onPointClick={(p: object) => onSelect((p as GlobePoint).cameraId)}
          labelsData={labels}
          labelLat="lat"
          labelLng="lng"
          labelText="text"
          labelColor="color"
          labelSize="size"
          labelDotRadius={0.35}
          labelAltitude={0.02}
          labelResolution={2}
          onLabelClick={(d: object) => onSelect((d as GlobeLabel).cameraId)}
          arcsData={arcs}
          arcColor="color"
          arcAltitude={0.18}
          arcStroke={0.45}
          arcDashLength={0.45}
          arcDashGap={0.3}
          arcDashAnimateTime={reducedMotion ? 0 : 2800}
          ringsData={rings}
          ringLat="lat"
          ringLng="lng"
          ringColor="color"
          ringMaxRadius="maxR"
          ringPropagationSpeed="propagationSpeed"
          ringRepeatPeriod="repeatPeriod"
          onGlobeReady={() => setReady(true)}
        />
      </Suspense>
    </div>
  );
}
