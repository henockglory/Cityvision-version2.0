import { useEffect, useRef, useState } from 'react';
import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';
import LiveDetectionOverlay from '@/components/live/LiveDetectionOverlay';
import { useLiveDetections } from '@/hooks/useLiveDetections';
import {
  frigateDetectMjpegUrl,
  go2rtcStreamSrc,
  isVirtualCamera,
} from '@/config/streams';

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
  /** Cadres: Frigate MJPEG (IP) or SSE YOLO (demo). */
  showOverlay?: boolean;
}

/**
 * Live preview — go2rtc by default; IP "Cadres ON" uses Frigate detect MJPEG (burned-in boxes).
 * Never embed Frigate SPA /live.
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
  const demoOrVirtual = isVirtualCamera(camera);
  const wantFrigateMjpeg = showOverlay && !demoOrVirtual && Boolean(cameraId);
  const [frigateFailed, setFrigateFailed] = useState(false);

  useEffect(() => {
    setFrigateFailed(false);
  }, [cameraId, showOverlay]);

  const useFrigate = wantFrigateMjpeg && !frigateFailed;
  const sseOverlayOn = showOverlay && demoOrVirtual && Boolean(cameraId);
  const { tracks, stale, resolution } = useLiveDetections(cameraId, sseOverlayOn);
  const stream = src ?? go2rtcStreamSrc(camera ?? { id: cameraId });
  const mjpegSrc = cameraId ? frigateDetectMjpegUrl(cameraId) : '';

  return (
    <div ref={containerRef} className={`relative bg-black overflow-hidden ${className}`}>
      {useFrigate ? (
        <>
          <img
            src={mjpegSrc}
            alt={label ? `${label} — Frigate detect` : 'Frigate detect'}
            className="absolute inset-0 w-full h-full object-contain"
            onError={() => setFrigateFailed(true)}
          />
          <div className="absolute top-2 left-2 z-10 px-2 py-0.5 rounded text-[10px] font-mono bg-black/60 text-emerald-300 border border-emerald-500/30">
            Frigate · bbox
          </div>
        </>
      ) : (
        <>
          <Go2RtcPlayer
            className="absolute inset-0 w-full h-full"
            src={stream}
            label={label}
            orgId={orgId}
            cameraId={cameraId}
          />
          {sseOverlayOn ? (
            <LiveDetectionOverlay
              containerRef={containerRef}
              tracks={tracks}
              resolution={resolution}
              stale={stale}
            />
          ) : null}
          {wantFrigateMjpeg && frigateFailed ? (
            <div className="absolute bottom-2 left-2 z-10 px-2 py-0.5 rounded text-[10px] font-mono bg-black/70 text-amber-300 border border-amber-500/30">
              Frigate indisponible — flux go2rtc
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
