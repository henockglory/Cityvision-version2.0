export interface EvidenceBBox {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
}

export interface EvidenceClip {
  url?: string;
  asset_id?: string;
  duration_sec?: number;
  mime?: string;
}

export interface EvidenceImage {
  role: 'scene' | 'subject' | 'plate' | 'face';
  url?: string;
  asset_id?: string;
  label?: string;
  mime?: string;
  bbox?: EvidenceBBox | null;
}

export interface EvidencePackage {
  version: number;
  clip?: EvidenceClip;
  images?: EvidenceImage[];
  metadata?: Record<string, unknown>;
}

export interface EvidenceSnapshot {
  package?: EvidencePackage;
  bbox?: EvidenceBBox;
  confidence?: number;
  track_id?: string | number;
  zone_id?: string;
  line_id?: string;
  class_name?: string;
  event_type?: string;
  clip_path?: string;
  [key: string]: unknown;
}

export function parseEvidenceSnapshot(raw?: Record<string, unknown> | null): EvidenceSnapshot {
  if (!raw || typeof raw !== 'object') return {};
  const pkg = raw.package as EvidencePackage | undefined;
  return { ...raw, package: pkg?.version ? pkg : (raw as EvidenceSnapshot).package };
}

export function evidenceThumbnailUrl(snapshot?: EvidenceSnapshot | Record<string, unknown> | null): string | undefined {
  const ev = parseEvidenceSnapshot(snapshot as EvidenceSnapshot | undefined);
  const scene = ev.package?.images?.find((i) => i.role === 'scene');
  if (scene?.url) return scene.url;
  const first = ev.package?.images?.[0];
  return first?.url;
}

export function evidenceCompleteness(snapshot?: EvidenceSnapshot | Record<string, unknown> | null): { total: number; have: number; complete: boolean } {
  const ev = parseEvidenceSnapshot(snapshot as EvidenceSnapshot | undefined);
  const pkg = ev.package;
  let have = 0;
  const total = 3;
  if (pkg?.clip?.url || pkg?.clip?.asset_id) have += 1;
  const scene = pkg?.images?.find((i) => i.role === 'scene');
  const subject = pkg?.images?.find((i) => i.role === 'subject');
  if (scene?.url || scene?.asset_id) have += 1;
  if (subject?.url || subject?.asset_id) have += 1;
  return { total, have, complete: have >= total };
}
