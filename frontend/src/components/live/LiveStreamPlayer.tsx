import { useRef } from 'react';
import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';
import LiveDetectionOverlay from '@/components/live/LiveDetectionOverlay';
import { useLiveDetections } from '@/hooks/useLiveDetections';
import { go2rtcStreamSrc } from '@/config/streams';

interface LiveStreamPlayerProps {
  src?: string;
  label?: string;
  cameraId: string;
  orgId?: string;
  className?: string;
  camera?: {
    id?: string;
    name?: string;
    streamKey?: string;
    streamUrl?: string;
    metadata?: Record<string, unknown>;
  } | null;
  /** SSE YOLO overlay (CitéVision) — works for demo + IP via go2rtc. */
  showOverlay?: boolean;
}

/**
 * Live preview — always CiteVision go2rtc video player (never Frigate SPA iframe).
 * Frigate stays the ingest/evidence backend; embedding /live embeds the full UI and regresses UX.
 */
export default function LiveStreamPlayer({
  src,
  label,
  cameraId,
  orgId,
  className = 'aspect-video w-full',
  camera,
  showOverlay = false,
}: LiveStreamPlayerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const overlayOn = showOverlay && Boolean(cameraId);
  const { tracks, stale, resolution } = useLiveDetections(cameraId, overlayOn);
  const stream = src ?? go2rtcStreamSrc(camera ?? { id: cameraId });

  return (
    <div ref={containerRef} className={`relative bg-black overflow-hidden ${className}`}>
      <Go2RtcPlayer
        className="absolute inset-0 w-full h-full"
        src={stream}
        label={label}
        orgId={orgId}
        cameraId={cameraId}
      />
      {overlayOn ? (
        <LiveDetectionOverlay
          containerRef={containerRef}
          tracks={tracks}
          resolution={resolution}
          stale={stale}
        />
      ) : null}
    </div>
  );
}
