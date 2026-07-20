import { useTranslation } from 'react-i18next';

import { FRIGATE_ORIGIN, frigateCameraId, frigateLiveIframeUrl } from '@/config/streams';

interface FrigateLivePlayerProps {
  cameraId: string;
  className?: string;
  label?: string;
  /** Native Frigate detection overlay (not SSE from ai-engine). */
  showBBox?: boolean;
}

/**
 * Live player via Frigate UI iframe (WebRTC + optional native bbox).
 * Avoids broken direct go2rtc WS — Frigate exposes streams only through its UI/API plane.
 */
export default function FrigateLivePlayer({
  cameraId,
  className = 'aspect-video w-full',
  label,
  showBBox = false,
}: FrigateLivePlayerProps) {
  const { t } = useTranslation();
  const frigateId = frigateCameraId(cameraId);
  const iframeSrc = frigateLiveIframeUrl(frigateId, showBBox);

  return (
    <div className={`relative bg-black overflow-hidden ${className}`}>
      <iframe
        title={label ?? t('liveView.frigateLive', 'Live Frigate')}
        src={iframeSrc}
        className="absolute inset-0 w-full h-full border-0"
        allow="autoplay; fullscreen"
      />
      <a
        href={`${FRIGATE_ORIGIN}/live?camera=${encodeURIComponent(frigateId)}`}
        target="_blank"
        rel="noopener noreferrer"
        className="absolute bottom-2 right-2 text-[10px] text-white/50 hover:text-white/80 bg-black/40 px-2 py-0.5 rounded"
      >
        Frigate
      </a>
    </div>
  );
}
