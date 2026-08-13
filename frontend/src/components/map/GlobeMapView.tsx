import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Crosshair, Layers, LocateFixed } from 'lucide-react';
import type { Alert, Camera } from '@/types';
import {
  DEFAULT_GEO_CENTER,
  cameraSiteKey,
  defaultSiteGeoPosition,
  getCameraGeoPosition,
  hasRealGeo,
} from '@/lib/cameraMap';
import LoadingState from '@/components/ui/LoadingState';

const Globe = lazy(() => import('react-globe.gl'));

type GlobeLayer = 'sites' | 'cameras';

interface SiteNode {
  id: string;
  label: string;
  lat: number;
  lng: number;
  cameraIds: string[];
  online: number;
  offline: number;
  alertCount: number;
  criticalAlerts: number;
  hasRealGeo: boolean;
  size: number;
  color: string;
}

interface CameraNode {
  lat: number;
  lng: number;
  size: number;
  color: string;
  cameraId: string;
  name: string;
  status: string;
  siteId: string;
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
  id: string;
  kind: 'site' | 'camera';
}

interface GlobeMapViewProps {
  cameras: Camera[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  alerts?: Alert[];
}

function siteTone(online: number, total: number, alerts: number, critical: number): string {
  if (critical > 0) return 'rgb(248, 113, 113)';
  if (alerts > 0) return 'rgb(251, 146, 60)';
  if (online === 0) return 'rgb(248, 113, 113)';
  if (online < total) return 'rgb(250, 204, 21)';
  return 'rgb(52, 211, 153)';
}

function severityColor(sev: string | undefined): string {
  switch (sev) {
    case 'critical':
      return 'rgba(248,113,113,0.9)';
    case 'high':
      return 'rgba(251,146,60,0.85)';
    case 'medium':
      return 'rgba(250,204,21,0.8)';
    default:
      return 'rgba(59,130,246,0.75)';
  }
}

function buildSites(cameras: Camera[], alerts: Alert[]): SiteNode[] {
  const groups = new Map<string, Camera[]>();
  cameras.forEach((c) => {
    const key = cameraSiteKey(c);
    const list = groups.get(key) ?? [];
    list.push(c);
    groups.set(key, list);
  });

  const alertsByCam = new Map<string, Alert[]>();
  for (const a of alerts) {
    const list = alertsByCam.get(a.cameraId) ?? [];
    list.push(a);
    alertsByCam.set(a.cameraId, list);
  }

  const keys = Array.from(groups.keys());
  return keys.map((key, siteIndex) => {
    const cams = groups.get(key) ?? [];
    const real = cams.filter((c) => hasRealGeo(c.metadata));
    let lat: number;
    let lng: number;
    let realGeo = false;
    if (real.length > 0) {
      lat = real.reduce((s, c) => s + getCameraGeoPosition(c.metadata, 0).lat, 0) / real.length;
      lng = real.reduce((s, c) => s + getCameraGeoPosition(c.metadata, 0).lng, 0) / real.length;
      realGeo = true;
    } else {
      const fallback = defaultSiteGeoPosition(siteIndex);
      lat = fallback.lat;
      lng = fallback.lng;
    }

    const online = cams.filter((c) => c.status !== 'offline').length;
    const offline = cams.length - online;
    let alertCount = 0;
    let criticalAlerts = 0;
    for (const c of cams) {
      const list = alertsByCam.get(c.id) ?? [];
      alertCount += list.length;
      criticalAlerts += list.filter((a) => a.severity === 'critical' || a.severity === 'high').length;
    }

    const label =
      cams[0]?.location && cams[0].location !== '—'
        ? cams[0].location
        : cams[0]?.siteId
          ? `Site ${cams[0].siteId.slice(0, 8)}`
          : cams.length === 1
            ? cams[0].name
            : `Site ${siteIndex + 1}`;

    return {
      id: key,
      label,
      lat,
      lng,
      cameraIds: cams.map((c) => c.id),
      online,
      offline,
      alertCount,
      criticalAlerts,
      hasRealGeo: realGeo,
      size: Math.min(1.1, 0.35 + cams.length * 0.08 + (alertCount > 0 ? 0.12 : 0)),
      color: siteTone(online, cams.length, alertCount, criticalAlerts),
    };
  });
}

export default function GlobeMapView({
  cameras,
  selectedId,
  onSelect,
  alerts = [],
}: GlobeMapViewProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globeRef = useRef<any>(undefined);
  const [size, setSize] = useState({ w: 800, h: 420 });
  const [ready, setReady] = useState(false);
  const [layer, setLayer] = useState<GlobeLayer>('sites');
  const [focusSiteId, setFocusSiteId] = useState<string | null>(null);
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

  const sites = useMemo(() => buildSites(cameras, alerts), [cameras, alerts]);
  const missingGps = useMemo(
    () => cameras.filter((c) => !hasRealGeo(c.metadata)).length,
    [cameras],
  );

  const selectedSite = useMemo(() => {
    if (!selectedId) return focusSiteId ? sites.find((s) => s.id === focusSiteId) ?? null : null;
    return sites.find((s) => s.cameraIds.includes(selectedId)) ?? null;
  }, [sites, selectedId, focusSiteId]);

  const cameraNodes = useMemo<CameraNode[]>(() => {
    const site = selectedSite;
    const list =
      layer === 'cameras' && site
        ? cameras.filter((c) => site.cameraIds.includes(c.id))
        : layer === 'cameras'
          ? cameras
          : [];
    return list.map((c, i) => {
      const siteKey = cameraSiteKey(c);
      const siteNode = sites.find((s) => s.id === siteKey);
      const base = hasRealGeo(c.metadata)
        ? getCameraGeoPosition(c.metadata, i)
        : siteNode
          ? { lat: siteNode.lat, lng: siteNode.lng }
          : getCameraGeoPosition(c.metadata, i);
      // Tiny jitter so co-located cameras remain clickable when no real GPS.
      const jitter = hasRealGeo(c.metadata)
        ? 0
        : 0.02 + (i % 5) * 0.008;
      const angle = (i * 2.2) % (2 * Math.PI);
      const selected = selectedId === c.id;
      return {
        lat: base.lat + Math.sin(angle) * jitter,
        lng: base.lng + Math.cos(angle) * jitter,
        size: selected ? 0.5 : c.status !== 'offline' ? 0.26 : 0.18,
        color: selected
          ? 'rgb(52, 211, 153)'
          : c.status !== 'offline'
            ? 'rgb(59, 130, 246)'
            : 'rgb(248, 113, 113)',
        cameraId: c.id,
        name: c.name,
        status: c.status ?? 'unknown',
        siteId: siteKey,
      };
    });
  }, [cameras, layer, selectedSite, sites, selectedId]);

  const points = layer === 'sites' ? sites : cameraNodes;

  const labels = useMemo<GlobeLabel[]>(() => {
    if (layer === 'sites') {
      return sites.map((s) => ({
        lat: s.lat,
        lng: s.lng,
        text: `${s.label} · ${s.cameraIds.length}`,
        color: s.color,
        size: selectedSite?.id === s.id ? 1.25 : 0.95,
        id: s.id,
        kind: 'site' as const,
      }));
    }
    return cameraNodes.map((p) => ({
      lat: p.lat,
      lng: p.lng,
      text: p.name,
      color: p.color,
      size: selectedId === p.cameraId ? 1.1 : 0.8,
      id: p.cameraId,
      kind: 'camera' as const,
    }));
  }, [layer, sites, cameraNodes, selectedSite, selectedId]);

  const rings = useMemo<GlobeRing[]>(() => {
    if (reducedMotion) return [];
    const out: GlobeRing[] = [];
    if (layer === 'sites') {
      for (const s of sites) {
        if (s.alertCount <= 0) continue;
        const base = s.criticalAlerts > 0 ? severityColor('critical') : severityColor('high');
        out.push({
          lat: s.lat,
          lng: s.lng,
          maxR: s.criticalAlerts > 0 ? 4.2 : 3.2,
          propagationSpeed: 2.2,
          repeatPeriod: s.criticalAlerts > 0 ? 900 : 1400,
          color: (t: number) => base.replace(/[\d.]+\)$/, `${Math.max(0.05, 1 - t)})`),
        });
      }
    } else {
      for (const a of alerts.slice(0, 24)) {
        const cam = cameraNodes.find((c) => c.cameraId === a.cameraId);
        if (!cam) continue;
        const base = severityColor(a.severity);
        out.push({
          lat: cam.lat,
          lng: cam.lng,
          maxR: a.severity === 'critical' || a.severity === 'high' ? 3 : 2.2,
          propagationSpeed: 2.4,
          repeatPeriod: a.severity === 'critical' ? 900 : 1400,
          color: (t: number) => base.replace(/[\d.]+\)$/, `${Math.max(0.05, 1 - t)})`),
        });
      }
    }
    return out;
  }, [layer, sites, alerts, cameraNodes, reducedMotion]);

  /** Arcs = topology between sites that share open-alert pressure or selected focus. */
  const arcs = useMemo<GlobeArc[]>(() => {
    if (sites.length < 2) return [];
    const hot = sites.filter((s) => s.alertCount > 0).sort((a, b) => b.alertCount - a.alertCount);
    const hub = selectedSite ?? hot[0] ?? sites[0];
    const targets = sites
      .filter((s) => s.id !== hub.id)
      .sort((a, b) => b.alertCount - a.alertCount || b.cameraIds.length - a.cameraIds.length)
      .slice(0, 8);
    return targets.map((s) => ({
      startLat: hub.lat,
      startLng: hub.lng,
      endLat: s.lat,
      endLng: s.lng,
      color:
        s.alertCount > 0 || hub.alertCount > 0
          ? ['rgba(251,146,60,0.15)', 'rgba(248,113,113,0.7)']
          : ['rgba(59,130,246,0.12)', 'rgba(52,211,153,0.55)'],
    }));
  }, [sites, selectedSite]);

  const fleetCenter = useMemo(() => {
    if (sites.length === 0) return DEFAULT_GEO_CENTER;
    const lat = sites.reduce((s, p) => s + p.lat, 0) / sites.length;
    const lng = sites.reduce((s, p) => s + p.lng, 0) / sites.length;
    return { lat, lng };
  }, [sites]);

  const fleetAltitude = sites.length <= 1 ? 1.35 : sites.length <= 3 ? 1.7 : 2.15;

  useEffect(() => {
    if (ready) return;
    const t = window.setTimeout(() => setReady(true), 600);
    return () => window.clearTimeout(t);
  }, [ready, size.w, size.h]);

  useEffect(() => {
    if (!ready || !globeRef.current) return;
    const g = globeRef.current;
    g.pointOfView({ lat: fleetCenter.lat, lng: fleetCenter.lng, altitude: fleetAltitude }, 900);
    const ctrl = g.controls?.();
    if (ctrl) {
      ctrl.autoRotate = !reducedMotion;
      ctrl.autoRotateSpeed = 0.85;
      ctrl.enableDamping = true;
    }
  }, [ready, fleetCenter.lat, fleetCenter.lng, fleetAltitude, reducedMotion, size.w, size.h]);

  useEffect(() => {
    if (!ready || !globeRef.current) return;
    if (selectedSite) {
      globeRef.current.pointOfView(
        { lat: selectedSite.lat, lng: selectedSite.lng, altitude: layer === 'cameras' ? 0.85 : 1.15 },
        reducedMotion ? 0 : 700,
      );
    }
  }, [selectedSite, layer, ready, reducedMotion]);

  const flyFleet = () => {
    if (!globeRef.current) return;
    setFocusSiteId(null);
    setLayer('sites');
    globeRef.current.pointOfView(
      { lat: fleetCenter.lat, lng: fleetCenter.lng, altitude: fleetAltitude },
      reducedMotion ? 0 : 800,
    );
  };

  const onPointClick = (p: object) => {
    if (layer === 'sites') {
      const site = p as SiteNode;
      setFocusSiteId(site.id);
      setLayer('cameras');
      const pick =
        site.cameraIds.find((id) => cameras.find((c) => c.id === id)?.status !== 'offline') ??
        site.cameraIds[0];
      if (pick) onSelect(pick);
      return;
    }
    onSelect((p as CameraNode).cameraId);
  };

  const onLabelClick = (d: object) => {
    const lab = d as GlobeLabel;
    if (lab.kind === 'site') {
      const site = sites.find((s) => s.id === lab.id);
      if (site) onPointClick(site);
      return;
    }
    onSelect(lab.id);
  };

  const siteStats = useMemo(() => {
    const withAlerts = sites.filter((s) => s.alertCount > 0).length;
    const offlineSites = sites.filter((s) => s.online === 0).length;
    return { withAlerts, offlineSites, total: sites.length };
  }, [sites]);

  return (
    <div className="relative h-full min-h-[480px] w-full rounded-lg overflow-hidden border border-cv-border bg-sky-950/40">
      <div className="absolute top-3 left-3 z-10 flex flex-wrap gap-2 max-w-[min(100%,28rem)]">
        <div className="flex gap-1 p-1 rounded-lg bg-cv-surface/90 border border-cv-border/70 backdrop-blur-md shadow-soft">
          <button
            type="button"
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium ${
              layer === 'sites' ? 'bg-cv-accent text-white' : 'text-cv-muted hover:text-cv-text'
            }`}
            onClick={() => setLayer('sites')}
          >
            <Layers className="w-3.5 h-3.5" />
            {t('map.globe.sitesLayer', 'Sites')}
          </button>
          <button
            type="button"
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium ${
              layer === 'cameras' ? 'bg-cv-accent text-white' : 'text-cv-muted hover:text-cv-text'
            }`}
            onClick={() => setLayer('cameras')}
          >
            <Crosshair className="w-3.5 h-3.5" />
            {t('map.globe.camerasLayer', 'Caméras')}
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium text-cv-muted hover:text-cv-text"
            onClick={flyFleet}
            title={t('map.globe.recenter', 'Recentrer la flotte')}
          >
            <LocateFixed className="w-3.5 h-3.5" />
            {t('map.globe.fleet', 'Flotte')}
          </button>
        </div>
        <div className="px-2.5 py-1.5 rounded-lg bg-cv-surface/90 border border-cv-border/70 backdrop-blur-md text-[11px] text-cv-muted shadow-soft">
          {t('map.globe.stats', {
            sites: siteStats.total,
            alerts: siteStats.withAlerts,
            offline: siteStats.offlineSites,
            defaultValue: `${siteStats.total} site(s) · ${siteStats.withAlerts} avec alertes · ${siteStats.offlineSites} hors ligne`,
          })}
        </div>
      </div>

      {missingGps > 0 && (
        <div className="absolute bottom-3 left-3 right-3 z-10 flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-[11px] text-amber-100 backdrop-blur-md">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span>
            {t('map.globe.gpsHint', {
              count: missingGps,
              defaultValue: `${missingGps} caméra(s) sans GPS réel — placez-les en mode Carte pour un positionnement exact. Les sites sans GPS sont estimés pour la vue flotte.`,
            })}
          </span>
        </div>
      )}

      <div ref={containerRef} className="h-full w-full">
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
            pointRadius={layer === 'sites' ? 0.65 : 0.42}
            pointLabel={(d: object) => {
              if (layer === 'sites') {
                const s = d as SiteNode;
                return `<div style="padding:6px 10px;font:12px/1.35 sans-serif;max-width:220px">
                  <b>${s.label}</b><br/>
                  <span style="opacity:.8">${s.cameraIds.length} cam · ${s.online} online · ${s.offline} off</span><br/>
                  <span style="opacity:.8">${s.alertCount} alerte(s)${s.hasRealGeo ? '' : ' · GPS estimé'}</span>
                </div>`;
              }
              const p = d as CameraNode;
              return `<div style="padding:6px 10px;font:12px/1.35 sans-serif"><b>${p.name}</b><br/><span style="opacity:.75">${p.status}</span></div>`;
            }}
            onPointClick={onPointClick}
            labelsData={labels}
            labelLat="lat"
            labelLng="lng"
            labelText="text"
            labelColor="color"
            labelSize="size"
            labelDotRadius={0.28}
            labelAltitude={0.018}
            labelResolution={2}
            onLabelClick={onLabelClick}
            arcsData={arcs}
            arcColor="color"
            arcAltitude={0.22}
            arcStroke={0.5}
            arcDashLength={0.4}
            arcDashGap={0.35}
            arcDashAnimateTime={reducedMotion ? 0 : 3200}
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
    </div>
  );
}
