import { useRef } from 'react';
import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';
import FrigateLivePlayer from '@/components/live/FrigateLivePlayer';
import LiveDetectionOverlay from '@/components/live/LiveDetectionOverlay';
import { useLiveDetections } from '@/hooks/useLiveDetections';
import { isVirtualCamera, shouldUseFrigateLive } from '@/config/streams';

interface LiveStreamPlayerProps {
  src?: string;
  label?: string;
  cameraId: string;
  orgId?: string;
  className?: string;
  camera?: {
    id?: string;
    name?: string;
    metadata?: Record<string, unknown>;
  } | null;
  /** HTML overlay synced via SSE (go2rtc path only — not used for Frigate live). */
  showOverlay?: boolean;
}

/** Routes live preview: Frigate (native bbox) or go2rtc + optional SSE overlay. */
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
  const useFrigate = shouldUseFrigateLive(camera ?? { id: cameraId });
  const overlayOn = showOverlay && Boolean(cameraId) && !useFrigate;
  const { tracks, stale, resolution } = useLiveDetections(cameraId, overlayOn);

  if (useFrigate) {
    return (
      <FrigateLivePlayer
        className={className}
        cameraId={cameraId}
        label={label}
        showBBox={showOverlay}
      />
    );
  }

  const virtual = isVirtualCamera(camera ?? undefined);

  return (
    <div ref={containerRef} className={`relative bg-black overflow-hidden ${className}`}>
      <Go2RtcPlayer
        className="absolute inset-0 w-full h-full"
        src={src}
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
      {virtual ? null : null}
    </div>
  );
}
