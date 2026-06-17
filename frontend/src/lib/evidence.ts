import type { EvidencePolicy } from '@/lib/evidencePolicy';
import { normalizeEvidencePolicy } from '@/lib/evidencePolicy';

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
  const hasPkg = pkg && (pkg.clip?.url || pkg.clip?.asset_id || (pkg.images?.length ?? 0) > 0);
  return { ...raw, package: hasPkg ? pkg : undefined };
}

export type EvidenceQualityState = 'loading' | 'partial' | 'complete' | 'failed' | 'metadata_only';

export interface EvidenceQuality {
  state: EvidenceQualityState;
  loaded: number;
  expected: number;
  clipDurationOk: boolean;
}

export function evidenceQuality(
  snapshot: EvidenceSnapshot | Record<string, unknown> | undefined,
  orgId: string | null | undefined,
  mediaState?: {
    clip?: { loading: boolean; error: boolean; blobUrl?: string; duration?: number };
    scene?: { loading: boolean; error: boolean; blobUrl?: string };
    subject?: { loading: boolean; error: boolean; blobUrl?: string };
  },
): EvidenceQuality {
  const slots = evidenceMediaSlots(snapshot, orgId);
  const expected = slots.total;
  const hasUrls = expected > 0;

  if (!hasUrls) {
    const ev = parseEvidenceSnapshot(snapshot);
    const hasMeta = Boolean(ev.bbox || ev.confidence != null || ev.event_type);
    return { state: hasMeta ? 'metadata_only' : 'failed', loaded: 0, expected: 0, clipDurationOk: false };
  }

  const anyLoading = Boolean(
    (slots.urls.clip && mediaState?.clip?.loading)
    || (slots.urls.scene && mediaState?.scene?.loading)
    || (slots.urls.subject && mediaState?.subject?.loading),
  );
  if (anyLoading) {
    return { state: 'loading', loaded: 0, expected, clipDurationOk: false };
  }

  let loaded = 0;
  const clipDur = mediaState?.clip?.duration ?? 0;
  const clipDurationOk = !slots.urls.clip || (clipDur >= 0.5);
  if (slots.urls.clip && mediaState?.clip?.blobUrl && !mediaState.clip.error && clipDurationOk) loaded += 1;
  if (slots.urls.scene && mediaState?.scene?.blobUrl && !mediaState.scene.error) loaded += 1;
  if (slots.urls.subject && mediaState?.subject?.blobUrl && !mediaState.subject.error) loaded += 1;

  const anyError = Boolean(
    (slots.urls.clip && mediaState?.clip?.error)
    || (slots.urls.scene && mediaState?.scene?.error)
    || (slots.urls.subject && mediaState?.subject?.error),
  );

  if (loaded === expected && expected > 0) {
    return { state: 'complete', loaded, expected, clipDurationOk };
  }
  if (anyError && loaded === 0) {
    return { state: 'failed', loaded, expected, clipDurationOk };
  }
  return { state: 'partial', loaded, expected, clipDurationOk };
}

export function buildEvidenceAssetUrl(orgId: string, assetId: string): string {
  const key = assetId.startsWith('orgs/') ? assetId : assetId;
  return `/api/v1/orgs/${orgId}/evidence/asset?key=${encodeURIComponent(key)}`;
}

/** Normalize baked absolute URLs to relative API paths for authenticated fetch. */
export function normalizeEvidenceApiUrl(url: string): string {
  if (!url) return url;
  if (url.startsWith('/api/v1/')) return url;
  if (url.startsWith('/orgs/')) return `/api/v1${url}`;
  try {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      const parsed = new URL(url);
      const path = parsed.pathname + parsed.search;
      const idx = path.indexOf('/api/v1/');
      if (idx >= 0) return path.slice(idx);
      if (path.startsWith('/orgs/')) return `/api/v1${path}`;
      return path;
    }
  } catch {
    /* ignore */
  }
  return url;
}

/** Resolve fetch URL: prefer package url, else build from asset_id + orgId. */
export function resolveEvidenceMediaUrl(
  url: string | undefined,
  assetId: string | undefined,
  orgId: string | null | undefined,
): string | undefined {
  if (url) return normalizeEvidenceApiUrl(url);
  if (assetId && orgId) return buildEvidenceAssetUrl(orgId, assetId);
  return undefined;
}

export function evidenceThumbnailUrl(
  snapshot?: EvidenceSnapshot | Record<string, unknown> | null,
  orgId?: string | null,
): string | undefined {
  const ev = parseEvidenceSnapshot(snapshot as EvidenceSnapshot | undefined);
  const scene = ev.package?.images?.find((i) => i.role === 'scene');
  if (scene) {
    const u = resolveEvidenceMediaUrl(scene.url, scene.asset_id, orgId);
    if (u) return u;
  }
  const first = ev.package?.images?.[0];
  if (first) return resolveEvidenceMediaUrl(first.url, first.asset_id, orgId);
  const clip = ev.package?.clip;
  if (clip) return resolveEvidenceMediaUrl(clip.url, clip.asset_id, orgId);
  return undefined;
}

export function requiredEvidenceSlots(policy?: Partial<EvidencePolicy> | null): number {
  const p = normalizeEvidencePolicy(policy);
  if (!p.enabled) return 0;
  let n = 0;
  if (p.clip_seconds > 0) n += 1;
  n += p.images.length;
  return n;
}

/** Count expected media slots that have a resolvable URL (not asset_id alone). */
export function evidenceMediaSlots(
  snapshot?: EvidenceSnapshot | Record<string, unknown> | null,
  orgId?: string | null,
  policy?: Partial<EvidencePolicy> | null,
): {
  total: number;
  have: number;
  urls: { clip?: string; scene?: string; subject?: string };
} {
  const p = normalizeEvidencePolicy(policy);
  const ev = parseEvidenceSnapshot(snapshot as EvidenceSnapshot | undefined);
  const pkg = ev.package;
  const scene = pkg?.images?.find((i) => i.role === 'scene');
  const subject = pkg?.images?.find((i) => i.role === 'subject');
  const clipUrl = p.clip_seconds > 0 ? resolveEvidenceMediaUrl(pkg?.clip?.url, pkg?.clip?.asset_id, orgId) : undefined;
  const sceneUrl = p.images.some((i) => i.role === 'scene')
    ? resolveEvidenceMediaUrl(scene?.url, scene?.asset_id, orgId)
    : undefined;
  const subjectUrl = p.images.some((i) => i.role === 'subject')
    ? resolveEvidenceMediaUrl(subject?.url, subject?.asset_id, orgId)
    : undefined;
  const have = [clipUrl, sceneUrl, subjectUrl].filter(Boolean).length;
  return {
    total: requiredEvidenceSlots(p),
    have,
    urls: { clip: clipUrl, scene: sceneUrl, subject: subjectUrl },
  };
}

export function evidenceCompleteness(
  snapshot?: EvidenceSnapshot | Record<string, unknown> | null,
  policy?: Partial<EvidencePolicy> | null,
): { total: number; have: number; complete: boolean } {
  const p = normalizeEvidencePolicy(policy);
  const total = requiredEvidenceSlots(p);
  if (total === 0) return { total: 0, have: 0, complete: true };
  const ev = parseEvidenceSnapshot(snapshot as EvidenceSnapshot | undefined);
  const pkg = ev.package;
  let have = 0;
  if (p.clip_seconds > 0 && (pkg?.clip?.url || pkg?.clip?.asset_id)) have += 1;
  for (const spec of p.images) {
    const img = pkg?.images?.find((i) => i.role === spec.role);
    if (img?.url || img?.asset_id) have += 1;
  }
  return { total, have, complete: have >= total };
}
