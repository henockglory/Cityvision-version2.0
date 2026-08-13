/** go2rtc — WebRTC/MSE direct port 1984 (live preview for demo + IP cameras). */
const GO2RTC_PORT = 1984;
/** Frigate UI (external link / admin only — never embed /live in CiteVision players). */
const FRIGATE_PORT = 5000;

function envFlag(name: string): boolean {
  const v = (import.meta.env[name] as string | undefined)?.trim();
  return v === '1' || v === 'true';
}

/** Master + live flags from Vite env (mirror .env FRIGATE_*). */
export const FRIGATE_LIVE_ENABLED =
  envFlag('VITE_FRIGATE_ENABLED') && envFlag('VITE_FRIGATE_LIVE');

function resolveDirectOrigin(port: number): string {
  if (typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:${port}`;
  }
  return `http://localhost:${port}`;
}

export const GO2RTC_ORIGIN = (() => {
  const fromEnv = import.meta.env.VITE_GO2RTC_ORIGIN as string | undefined;
  if (fromEnv?.trim()) return fromEnv.trim().replace(/\/$/, '');
  return resolveDirectOrigin(GO2RTC_PORT);
})();

export const FRIGATE_ORIGIN = (() => {
  const fromEnv = import.meta.env.VITE_FRIGATE_ORIGIN as string | undefined;
  if (fromEnv?.trim()) return fromEnv.trim().replace(/\/$/, '');
  return resolveDirectOrigin(FRIGATE_PORT);
})();

/** @deprecated live preview uses CiteVision go2rtc :1984 — kept for IntegrationsStatusPanel. */
export const FRIGATE_GO2RTC_ORIGIN = (() => {
  const fromEnv = import.meta.env.VITE_FRIGATE_GO2RTC_ORIGIN as string | undefined;
  if (fromEnv?.trim()) return fromEnv.trim().replace(/\/$/, '');
  return `${FRIGATE_ORIGIN}/api/go2rtc`;
})();

export function frigateCameraId(cameraUuid: string): string {
  return `cv_${cameraUuid}`;
}

/** Frigate detect MJPEG with burned-in bbox (proxy /frigate → :5000). Never embed Frigate SPA. */
export function frigateDetectMjpegUrl(cameraUuid: string): string {
  return `/frigate/api/${encodeURIComponent(frigateCameraId(cameraUuid))}?bbox=1`;
}

/** External Frigate UI link only — do not use as CiteVision player iframe src. */
export function frigateLiveIframeUrl(frigateId: string, bbox: boolean): string {
  const bboxParam = bbox ? '1' : '0';
  return `${FRIGATE_ORIGIN}/live?camera=${encodeURIComponent(frigateId)}&bbox=${bboxParam}`;
}

/**
 * Live preview never embeds Frigate SPA (full UI regression).
 * Always false — LiveStreamPlayer uses go2rtc video-only for demo + IP.
 * Frigate remains enabled for ingest/evidence when FRIGATE_* backend flags are on.
 */
export function shouldUseFrigateLive(_camera?: {
  name?: string;
  metadata?: Record<string, unknown>;
} | null): boolean {
  void _camera;
  void FRIGATE_LIVE_ENABLED;
  return false;
}
/** @deprecated legacy demo stream name — use metadata.go2rtc_src from uploaded videos. */
export const DEFAULT_STREAM = 'benedicte';

export function isVirtualCamera(camera?: {
  name?: string;
  metadata?: Record<string, unknown>;
} | null): boolean {
  const meta = camera?.metadata;
  if (meta?.virtual === true || meta?.demo === true || meta?.demo === 'true') return true;
  const name = camera?.name?.toLowerCase() ?? '';
  return name.includes('virtual') || name.startsWith('démo') || name.startsWith('demo');
}

export function go2rtcStreamSrc(camera?: {
  id?: string;
  streamKey?: string;
  streamUrl?: string;
  name?: string;
  metadata?: Record<string, unknown>;
} | null): string | undefined {
  if (!camera) return undefined;
  if (camera.streamKey) return camera.streamKey;
  const meta = camera.metadata as { go2rtc_src?: string; virtual?: boolean; demo?: boolean | string } | undefined;
  if (meta?.go2rtc_src) return meta.go2rtc_src;
  if (camera.id) return `cam-${camera.id}`;
  return undefined;
}

export function go2rtcPlayerUrl(src: string = DEFAULT_STREAM): string {
  return `${GO2RTC_ORIGIN}/stream.html?src=${encodeURIComponent(src)}&mode=webrtc`;
}

/** @deprecated use go2rtcPlayerUrl() */
export const GO2RTC_STREAM = DEFAULT_STREAM;
export const GO2RTC_PLAYER_IFRAME = go2rtcPlayerUrl(DEFAULT_STREAM);

/** Statut streams — HTTP via proxy Vite (fetch OK) ; WebRTC utilise GO2RTC_ORIGIN direct. */
export const GO2RTC_STREAMS_API = '/go2rtc/api/streams';
export const AI_ENGINE_HEALTH = '/ai-engine/health';
export const AI_ENGINE_CAMERAS = '/ai-engine/cameras';
export const RULES_ENGINE_HEALTH = '/rules-engine/health';

/** MailHog inbox (demo/test email preview). Override via VITE_MAILHOG_URL. */
export const MAILHOG_URL =
  (import.meta.env.VITE_MAILHOG_URL as string | undefined)?.trim().replace(/\/$/, '') ||
  (typeof window !== 'undefined'
    ? `${window.location.protocol}//${window.location.hostname}:8025`
    : 'http://localhost:8025');
