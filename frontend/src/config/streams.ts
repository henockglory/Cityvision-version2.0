/** go2rtc — WebRTC direct port 1984 (WebSocket ne passe pas toujours via proxy Vite). */
const GO2RTC_PORT = 1984;

function resolveDirectOrigin(): string {
  const fromEnv = import.meta.env.VITE_GO2RTC_ORIGIN as string | undefined;
  if (fromEnv?.trim()) return fromEnv.trim().replace(/\/$/, '');
  if (typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:${GO2RTC_PORT}`;
  }
  return `http://localhost:${GO2RTC_PORT}`;
}

export const GO2RTC_ORIGIN = resolveDirectOrigin();
export const DEFAULT_STREAM = 'benedicte';

export function go2rtcStreamSrc(camera?: {
  id?: string;
  streamKey?: string;
  streamUrl?: string;
  name?: string;
  metadata?: Record<string, unknown>;
} | null): string {
  if (camera?.streamKey) return camera.streamKey;
  const meta = camera?.metadata as { go2rtc_src?: string; source?: string; virtual?: boolean } | undefined;
  if (meta?.go2rtc_src) return meta.go2rtc_src;
  if (camera?.id) return `cam-${camera.id}`;
  if (meta?.source === 'benedicte.mp4') return DEFAULT_STREAM;
  const url = camera?.streamUrl ?? '';
  if (url.includes('benedicte') || url.includes('8554/benedicte')) return DEFAULT_STREAM;
  const name = camera?.name?.toLowerCase() ?? '';
  if (name.includes('benedicte') || name.includes('virtual')) return DEFAULT_STREAM;
  return DEFAULT_STREAM;
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
