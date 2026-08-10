import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';
import { go2rtcStreamSrc } from '@/config/streams';

interface FrigateLivePlayerProps {
  cameraId: string;
  className?: string;
  label?: string;
  /** Kept for API compat — bbox uses LiveStreamPlayer SSE overlay, not Frigate SPA. */
  showBBox?: boolean;
  orgId?: string;
  src?: string;
  camera?: {
    id?: string;
    name?: string;
    streamKey?: string;
    metadata?: Record<string, unknown>;
  } | null;
}

/**
 * Compat wrapper: video-only via CiteVision go2rtc (cam-{uuid}).
 * Do not iframe Frigate /live — that injects the full Frigate UI into Vue directe.
 * Detection/evidence still run through Frigate backend independently.
 */
export default function FrigateLivePlayer({
  cameraId,
  className = 'aspect-video w-full',
  label,
  orgId,
  src,
  camera,
}: FrigateLivePlayerProps) {
  const stream = src ?? go2rtcStreamSrc(camera ?? { id: cameraId });
  return (
    <div className={`relative bg-black overflow-hidden ${className}`}>
      <Go2RtcPlayer
        className="absolute inset-0 w-full h-full"
        src={stream}
        label={label}
        orgId={orgId}
        cameraId={cameraId}
      />
    </div>
  );
}
