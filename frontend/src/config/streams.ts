/** go2rtc — WebRTC direct port 1984 (WebSocket ne passe pas toujours via proxy Vite). */
const GO2RTC_PORT = 1984;
const FRIGATE_PORT = 5000;
const FRIGATE_GO2RTC_PORT = 8557;

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

function resolveProxiedOrigin(pathPrefix: string): string {
  if (typeof window !== 'undefined') {
    return `${window.location.origin}${pathPrefix}`;
  }
  return pathPrefix;
}

export const GO2RTC_ORIGIN = (() => {
  const fromEnv = import.meta.env.VITE_GO2RTC_ORIGIN as string | undefined;
  if (fromEnv?.trim()) return fromEnv.trim().replace(/\/$/, '');
  return resolveDirectOrigin(GO2RTC_PORT);
})();

export const FRIGATE_ORIGIN = (() => {
  const fromEnv = import.meta.env.VITE_FRIGATE_ORIGIN as string | undefined;
  if (fromEnv?.trim()) return fromEnv.trim().replace(/\/$/, '');
  return resolveProxiedOrigin('/frigate');
})();

/** Frigate embedded go2rtc (WebRTC) — proxied in dev via Vite. */
export const FRIGATE_GO2RTC_ORIGIN = (() => {
  const fromEnv = import.meta.env.VITE_FRIGATE_GO2RTC_ORIGIN as string | undefined;
  if (fromEnv?.trim()) return fromEnv.trim().replace(/\/$/, '');
  return resolveProxiedOrigin('/frigate-go2rtc');
})();

export function frigateCameraId(cameraUuid: string): string {
  return `cv_${cameraUuid}`;
}

export function frigateLiveIframeUrl(frigateId: string, bbox: boolean): string {
  const bboxParam = bbox ? '1' : '0';
  return `${FRIGATE_ORIGIN}/live?camera=${encodeURIComponent(frigateId)}&bbox=${bboxParam}`;
}

export function shouldUseFrigateLive(camera?: {
  name?: string;
  metadata?: Record<string, unknown>;
} | null): boolean {
  if (!FRIGATE_LIVE_ENABLED) return false;
  return !isVirtualCamera(camera);
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
