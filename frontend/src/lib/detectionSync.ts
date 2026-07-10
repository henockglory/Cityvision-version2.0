/** Unified pipeline: minimal lead (same decode path as go2rtc preview). */
export const OVERLAY_LEAD_MS = 100;

/** Legacy double-RTSP fallback lead. */
export const LEGACY_OVERLAY_LEAD_MS = 850;

/** Forward extrapolation — low in unified mode. */
export const EXTRAP_FACTOR = 0.35;

/** Fade out tracks not updated within this duration. */
export const TRACK_TTL_MS = 1200;

/** 1.0 = snap to predicted position. */
export const BBOX_LERP = 1.0;

/** Minimum confidence for overlay tracks. */
export const OVERLAY_MIN_CONF = 0.45;

/** Minimum normalized bbox area (fraction of frame). */
export const OVERLAY_MIN_AREA = 0.0003;

/** IoU threshold for client-side NMS dedup. */
export const OVERLAY_NMS_IOU = 0.42;

/** Max simultaneous overlay tracks. */
export const OVERLAY_MAX_TRACKS = 16;

/** Backup poll while SSE is connected (ms). */
export const BACKUP_POLL_MS = 250;
