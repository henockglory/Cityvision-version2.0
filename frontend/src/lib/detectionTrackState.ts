import type { LiveDetectionBBox, LiveDetectionFrame, LiveDetectionItem } from '@/hooks/useLiveDetections';
import {
  BBOX_LERP,
  EXTRAP_FACTOR,
  LEGACY_OVERLAY_LEAD_MS,
  OVERLAY_LEAD_MS,
  OVERLAY_MAX_TRACKS,
  OVERLAY_MIN_AREA,
  OVERLAY_MIN_CONF,
  OVERLAY_NMS_IOU,
  TRACK_TTL_MS,
} from '@/lib/detectionSync';

export interface OverlayTrack {
  track_id: number;
  class_name: string;
  confidence: number;
  bbox: LiveDetectionBBox;
  opacity: number;
}

interface TrackState {
  track_id: number;
  class_name: string;
  confidence: number;
  bbox: LiveDetectionBBox;
  target: LiveDetectionBBox;
  velocity: LiveDetectionBBox;
  lastSeen: number;
  inferMs: number;
  leadMs: number;
  unified: boolean;
}

function iou(a: LiveDetectionBBox, b: LiveDetectionBBox): number {
  const ax2 = a.x + a.width;
  const ay2 = a.y + a.height;
  const bx2 = b.x + b.width;
  const by2 = b.y + b.height;
  const ix1 = Math.max(a.x, b.x);
  const iy1 = Math.max(a.y, b.y);
  const ix2 = Math.min(ax2, bx2);
  const iy2 = Math.min(ay2, by2);
  const inter = Math.max(0, ix2 - ix1) * Math.max(0, iy2 - iy1);
  const union = a.width * a.height + b.width * b.height - inter;
  return union > 0 ? inter / union : 0;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function lerpBox(from: LiveDetectionBBox, to: LiveDetectionBBox, t: number): LiveDetectionBBox {
  return {
    x: lerp(from.x, to.x, t),
    y: lerp(from.y, to.y, t),
    width: lerp(from.width, to.width, t),
    height: lerp(from.height, to.height, t),
  };
}

function addBox(a: LiveDetectionBBox, b: LiveDetectionBBox, scale: number): LiveDetectionBBox {
  return {
    x: a.x + b.x * scale,
    y: a.y + b.y * scale,
    width: Math.max(0.004, a.width + b.width * scale),
    height: Math.max(0.004, a.height + b.height * scale),
  };
}

function parseMs(raw: string | null | undefined, fallback: number): number {
  if (!raw) return fallback;
  const ms = Date.parse(raw);
  return Number.isFinite(ms) ? ms : fallback;
}

function isUnifiedFrame(frame: LiveDetectionFrame): boolean {
  return frame.pipeline_mode === 'unified';
}

function estimateLeadMs(frame: LiveDetectionFrame): number {
  if (frame.video_lead_ms != null && frame.video_lead_ms > 0) {
    return frame.video_lead_ms;
  }
  if (isUnifiedFrame(frame)) {
    return OVERLAY_LEAD_MS;
  }
  const queue = frame.queue_latency_ms ?? 0;
  return LEGACY_OVERLAY_LEAD_MS + Math.min(300, queue * 0.3);
}

function filterOverlayItems(items: LiveDetectionItem[]): LiveDetectionItem[] {
  const filtered = items.filter(
    (d) =>
      d.confidence >= OVERLAY_MIN_CONF &&
      d.bbox.width * d.bbox.height >= OVERLAY_MIN_AREA &&
      d.bbox.width > 0.008 &&
      d.bbox.height > 0.008,
  );
  filtered.sort((a, b) => b.confidence - a.confidence);
  const kept: LiveDetectionItem[] = [];
  for (const d of filtered) {
    if (kept.some((k) => iou(k.bbox, d.bbox) >= OVERLAY_NMS_IOU)) continue;
    kept.push(d);
    if (kept.length >= OVERLAY_MAX_TRACKS) break;
  }
  return kept;
}

function pickOverlayItems(frame: LiveDetectionFrame): LiveDetectionItem[] {
  const primary = filterOverlayItems(frame.overlay_detections ?? []);
  if (primary.length > 0) return primary;
  return filterOverlayItems(frame.detections);
}

export class DetectionTrackRenderer {
  private tracks = new Map<number, TrackState>();
  private lastSeq = -1;

  ingest(frame: LiveDetectionFrame | null, nowMs = Date.now()): void {
    if (!frame) return;
    const seq = frame.publish_frame_index ?? frame.frame_id;
    if (seq === this.lastSeq) return;
    this.lastSeq = seq;

    const unified = isUnifiedFrame(frame);
    const inferMs = parseMs(frame.infer_ts, parseMs(frame.capture_ts, nowMs));
    const leadMs = estimateLeadMs(frame);
    const items = pickOverlayItems(frame);
    const seen = new Set<number>();

    for (const d of items) {
      seen.add(d.track_id);
      const existing = this.tracks.get(d.track_id);
      if (existing) {
        const dt = Math.max(0.016, (nowMs - existing.lastSeen) / 1000);
        existing.velocity = {
          x: (d.bbox.x - existing.target.x) / dt,
          y: (d.bbox.y - existing.target.y) / dt,
          width: (d.bbox.width - existing.target.width) / dt,
          height: (d.bbox.height - existing.target.height) / dt,
        };
        existing.target = d.bbox;
        existing.class_name = d.class_name;
        existing.confidence = d.confidence;
        existing.lastSeen = nowMs;
        existing.inferMs = inferMs;
        existing.leadMs = leadMs;
        existing.unified = unified;
        existing.bbox = { ...d.bbox };
      } else {
        this.tracks.set(d.track_id, {
          track_id: d.track_id,
          class_name: d.class_name,
          confidence: d.confidence,
          bbox: { ...d.bbox },
          target: { ...d.bbox },
          velocity: { x: 0, y: 0, width: 0, height: 0 },
          lastSeen: nowMs,
          inferMs,
          leadMs,
          unified,
        });
      }
    }

    for (const [id, st] of this.tracks) {
      if (!seen.has(id) && nowMs - st.lastSeen > TRACK_TTL_MS) {
        this.tracks.delete(id);
      }
    }
  }

  tick(nowMs = Date.now()): OverlayTrack[] {
    const out: OverlayTrack[] = [];
    for (const [id, st] of this.tracks) {
      const age = nowMs - st.lastSeen;
      if (age > TRACK_TTL_MS) {
        this.tracks.delete(id);
        continue;
      }

      let display = st.target;
      if (!st.unified) {
        const sinceInferMs = Math.max(0, nowMs - st.inferMs);
        const lagMs = sinceInferMs + st.leadMs;
        const extrapSec = (lagMs / 1000) * EXTRAP_FACTOR;
        display = addBox(st.target, st.velocity, extrapSec);
      } else {
        const encodeLagMs = Math.max(0, nowMs - st.inferMs);
        const extrapSec = (Math.min(encodeLagMs, st.leadMs) / 1000) * EXTRAP_FACTOR;
        display = addBox(st.target, st.velocity, extrapSec);
      }

      st.bbox = lerpBox(st.bbox, display, BBOX_LERP);

      const fadeStart = TRACK_TTL_MS * 0.65;
      const fade =
        age > fadeStart ? 1 - (age - fadeStart) / (TRACK_TTL_MS - fadeStart) : 1;

      out.push({
        track_id: id,
        class_name: st.class_name,
        confidence: st.confidence,
        bbox: st.bbox,
        opacity: Math.max(0.15, Math.min(1, fade)),
      });
    }
    return out;
  }

  reset(): void {
    this.tracks.clear();
    this.lastSeq = -1;
  }
}
