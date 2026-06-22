import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import type { Camera } from '@/types';
import { getCameraGeoPosition } from '@/lib/cameraMap';
import LoadingState from '@/components/ui/LoadingState';

const Globe = lazy(() => import('react-globe.gl'));

interface GlobePoint {
  lat: number;
  lng: number;
  size: number;
  color: string;
  cameraId: string;
  name: string;
}

interface GlobeMapViewProps {
  cameras: Camera[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function GlobeMapView({ cameras, selectedId, onSelect }: GlobeMapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globeRef = useRef<any>(undefined);
  const [size, setSize] = useState({ w: 800, h: 420 });
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

  const points = useMemo<GlobePoint[]>(
    () =>
      cameras.map((c, i) => {
        const pos = getCameraGeoPosition(c.metadata, i);
        return {
          lat: pos.lat,
          lng: pos.lng,
          size: selectedId === c.id ? 0.35 : 0.2,
          color: c.status !== 'offline' ? 'rgb(59, 130, 246)' : 'rgb(248, 113, 113)',
          cameraId: c.id,
          name: c.name,
        };
      }),
    [cameras, selectedId],
  );

  useEffect(() => {
    if (reducedMotion) return;
    const ctrl = globeRef.current?.controls?.();
    if (ctrl) {
      ctrl.autoRotate = true;
      ctrl.autoRotateSpeed = 0.4;
    }
  }, [size, reducedMotion]);

  return (
    <div ref={containerRef} className="h-full min-h-[400px] w-full rounded-lg overflow-hidden border border-cv-border bg-cv-deep">
      <Suspense fallback={<LoadingState />}>
        <Globe
          ref={globeRef}
          width={size.w}
          height={size.h}
          globeImageUrl="//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
          bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
          backgroundImageUrl="//unpkg.com/three-globe/example/img/night-sky.png"
          pointsData={points}
          pointLat="lat"
          pointLng="lng"
          pointColor="color"
          pointAltitude="size"
          pointLabel={(d: object) => (d as GlobePoint).name}
          onPointClick={(p: object) => onSelect((p as GlobePoint).cameraId)}
        />
      </Suspense>
    </div>
  );
}
