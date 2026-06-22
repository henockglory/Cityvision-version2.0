/** Normalized map position (0–1) stored in camera.metadata.map_x / map_y */

export interface MapPosition {
  x: number;
  y: number;
}

export interface GeoPosition {
  lat: number;
  lng: number;
}

/** Default map center — Kinshasa */
export const DEFAULT_GEO_CENTER: GeoPosition = { lat: -4.3217, lng: 15.3125 };

export function getCameraMapPosition(
  metadata: Record<string, unknown> | undefined,
  index: number,
): MapPosition {
  const meta = metadata ?? {};
  const mx = meta.map_x;
  const my = meta.map_y;
  if (typeof mx === 'number' && typeof my === 'number') {
    return { x: clamp(mx), y: clamp(my) };
  }
  return defaultMapPosition(index);
}

export function defaultMapPosition(index: number): MapPosition {
  return {
    x: 0.12 + ((index * 0.19) % 0.76),
    y: 0.15 + ((index * 0.27) % 0.7),
  };
}

function clamp(n: number): number {
  return Math.max(0.05, Math.min(0.95, n));
}

export function mergeMapMetadata(
  metadata: Record<string, unknown> | undefined,
  pos: MapPosition,
): Record<string, unknown> {
  return {
    ...(metadata ?? {}),
    map_x: pos.x,
    map_y: pos.y,
  };
}

export function getCameraGeoPosition(
  metadata: Record<string, unknown> | undefined,
  index: number,
): GeoPosition {
  const meta = metadata ?? {};
  const lat = meta.lat;
  const lng = meta.lng;
  if (typeof lat === 'number' && typeof lng === 'number') {
    return { lat, lng };
  }
  return defaultGeoPosition(index);
}

export function defaultGeoPosition(index: number): GeoPosition {
  const angle = (index * 2.399963) % (2 * Math.PI);
  const radius = 0.002 + (index % 5) * 0.0008;
  return {
    lat: DEFAULT_GEO_CENTER.lat + Math.sin(angle) * radius,
    lng: DEFAULT_GEO_CENTER.lng + Math.cos(angle) * radius,
  };
}

export function mergeGeoMetadata(
  metadata: Record<string, unknown> | undefined,
  pos: GeoPosition,
): Record<string, unknown> {
  return {
    ...(metadata ?? {}),
    lat: pos.lat,
    lng: pos.lng,
  };
}

export function getGeoMapCenter(
  positions: GeoPosition[],
  metadataList: (Record<string, unknown> | undefined)[],
): GeoPosition {
  const placed = positions.filter((_, i) => {
    const meta = metadataList[i] ?? {};
    return typeof meta.lat === 'number' && typeof meta.lng === 'number';
  });
  if (placed.length === 0) return DEFAULT_GEO_CENTER;
  const lat = placed.reduce((s, p) => s + p.lat, 0) / placed.length;
  const lng = placed.reduce((s, p) => s + p.lng, 0) / placed.length;
  return { lat, lng };
}
