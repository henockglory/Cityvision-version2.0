import { useEffect, useRef, useState } from 'react';
import { AI_ENGINE_CAMERAS } from '@/config/streams';
import { DetectionTrackRenderer, type OverlayTrack } from '@/lib/detectionTrackState';
import { BACKUP_POLL_MS } from '@/lib/detectionSync';

export interface LiveDetectionBBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface LiveDetectionItem {
  track_id: number;
  class_name: string;
  confidence: number;
  bbox: LiveDetectionBBox;
  metadata?: Record<string, unknown>;
}

export interface LiveDetectionFrame {
  camera_id: string;
  timestamp: string | null;
  capture_ts?: string | null;
  infer_ts?: string | null;
  queue_latency_ms?: number;
  video_lead_ms?: number;
  frame_id: number;
  resolution: { width: number; height: number } | null;
  detections: LiveDetectionItem[];
  overlay_detections?: LiveDetectionItem[];
  overlay_only?: boolean;
  pipeline_mode?: string;
  publish_frame_index?: number;
}

const STALE_MS = 4000;
const SSE_RECONNECT_MS = 1500;

function normalizeItem(item: Record<string, unknown>, rw: number, rh: number): LiveDetectionItem {
  const bb = (item.bbox ?? {}) as Record<string, number>;
  const x = Number(bb.x ?? 0);
  const y = Number(bb.y ?? 0);
  const w = Number(bb.width ?? 0);
  const h = Number(bb.height ?? 0);
  const norm =
    rw > 0 && rh > 0
      ? { x: x / rw, y: y / rh, width: w / rw, height: h / rh }
      : { x, y, width: w, height: h };
  return {
    track_id: Number(item.track_id ?? 0),
    class_name: String(item.class_name ?? 'object'),
    confidence: Number(item.confidence ?? 0),
    bbox: norm,
    metadata: item.metadata as Record<string, unknown> | undefined,
  };
}

function normalizeList(raw: unknown, rw: number, rh: number): LiveDetectionItem[] {
  if (!Array.isArray(raw)) return [];
  return (raw as Record<string, unknown>[]).map((item) => normalizeItem(item, rw, rh));
}

export function normalizePayload(raw: unknown): LiveDetectionFrame | null {
  if (!raw || typeof raw !== 'object') return null;
  const d = raw as Record<string, unknown>;
  const res = d.resolution as { width?: number; height?: number } | null | undefined;
  const rw = res?.width ?? 0;
  const rh = res?.height ?? 0;
  return {
    camera_id: String(d.camera_id ?? ''),
    timestamp: d.timestamp != null ? String(d.timestamp) : null,
    capture_ts: d.capture_ts != null ? String(d.capture_ts) : null,
    infer_ts: d.infer_ts != null ? String(d.infer_ts) : null,
    queue_latency_ms: d.queue_latency_ms != null ? Number(d.queue_latency_ms) : undefined,
    video_lead_ms: d.video_lead_ms != null ? Number(d.video_lead_ms) : undefined,
    frame_id: Number(d.frame_id ?? 0),
    resolution: rw > 0 && rh > 0 ? { width: rw, height: rh } : null,
    detections: normalizeList(d.detections, rw, rh),
    overlay_detections: normalizeList(d.overlay_detections, rw, rh),
    overlay_only: d.overlay_only === true,
    pipeline_mode: d.pipeline_mode != null ? String(d.pipeline_mode) : undefined,
    publish_frame_index:
      d.publish_frame_index != null ? Number(d.publish_frame_index) : undefined,
  };
}

/** SSE push + RAF interpolation — overlay only, never touches RTSP/WebRTC. */
export function useLiveDetections(cameraId: string | null, enabled: boolean) {
  const [tracks, setTracks] = useState<OverlayTrack[]>([]);
  const [stale, setStale] = useState(false);
  const [resolution, setResolution] = useState<{ width: number; height: number } | null>(null);
  const rendererRef = useRef(new DetectionTrackRenderer());
  const lastFrameTs = useRef(0);
  const rafRef = useRef(0);
  const lastSeqRef = useRef(-1);

  useEffect(() => {
    if (!enabled || !cameraId) {
      rendererRef.current.reset();
      setTracks([]);
      setStale(false);
      setResolution(null);
      return;
    }

    let cancelled = false;
    let es: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let backupPollId: ReturnType<typeof setInterval> | null = null;

    const onFrame = (parsed: LiveDetectionFrame | null) => {
      if (!parsed || cancelled) return;
      const seq = parsed.publish_frame_index ?? parsed.frame_id;
      if (seq === lastSeqRef.current) return;
      lastSeqRef.current = seq;
      if (parsed.resolution) setResolution(parsed.resolution);
      rendererRef.current.ingest(parsed);
      lastFrameTs.current = Date.now();
      setStale(false);
    };

    const fetchLatest = async () => {
      if (document.hidden || cancelled) return;
      try {
        const r = await fetch(`${AI_ENGINE_CAMERAS}/${cameraId}/detections/latest`, {
          cache: 'no-store',
        });
        if (!r.ok || cancelled) return;
        onFrame(normalizePayload(await r.json()));
      } catch {
        if (!cancelled) setStale(true);
      }
    };

    const connectSse = () => {
      if (cancelled) return;
      es?.close();
      es = null;
      const streamUrl = `${AI_ENGINE_CAMERAS}/${cameraId}/detections/stream`;
      try {
        es = new EventSource(streamUrl);
        es.onmessage = (ev) => {
          try {
            onFrame(normalizePayload(JSON.parse(ev.data as string)));
          } catch {
            /* ignore */
          }
        };
        es.onerror = () => {
          es?.close();
          es = null;
          if (!cancelled) {
            reconnectTimer = setTimeout(connectSse, SSE_RECONNECT_MS);
          }
        };
      } catch {
        reconnectTimer = setTimeout(connectSse, SSE_RECONNECT_MS);
      }
    };

    connectSse();
    void fetchLatest();
    backupPollId = setInterval(() => void fetchLatest(), BACKUP_POLL_MS);

    const animate = () => {
      if (cancelled) return;
      const now = Date.now();
      setTracks(rendererRef.current.tick(now));
      if (lastFrameTs.current > 0 && now - lastFrameTs.current > STALE_MS) {
        setStale(true);
      }
      rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);

    return () => {
      cancelled = true;
      es?.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (backupPollId) clearInterval(backupPollId);
      cancelAnimationFrame(rafRef.current);
      lastSeqRef.current = -1;
      rendererRef.current.reset();
    };
  }, [cameraId, enabled]);

  return { tracks, stale, resolution };
}
