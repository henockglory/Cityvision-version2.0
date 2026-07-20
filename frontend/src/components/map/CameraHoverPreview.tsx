import { useEffect, useState } from 'react';
import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';
import { go2rtcStreamSrc } from '@/config/streams';
import type { Camera } from '@/types';

interface CameraHoverPreviewProps {
  camera: Camera | null;
  position: { x: number; y: number } | null;
}

export default function CameraHoverPreview({ camera, position }: CameraHoverPreviewProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!camera || !position) {
      setVisible(false);
      return;
    }
    const t = setTimeout(() => setVisible(true), 400);
    return () => {
      clearTimeout(t);
      setVisible(false);
    };
  }, [camera?.id, position?.x, position?.y]);

  if (!camera || !position || !visible) return null;

  const stream = go2rtcStreamSrc(camera);

  return (
    <div
      className="fixed z-[500] pointer-events-none animate-fade-in"
      style={{ left: position.x + 12, top: position.y - 8 }}
    >
      <div className="cv-card p-2 shadow-glow border-metric-cameras/30 w-[180px]">
        <p className="text-[10px] font-semibold truncate mb-1">{camera.name}</p>
        <div className="rounded overflow-hidden border border-cv-border aspect-video bg-black">
          <Go2RtcPlayer src={stream} bare className="w-full h-full min-h-0" />
        </div>
        <p className="text-[9px] text-cv-muted mt-1">Aperçu live</p>
      </div>
    </div>
  );
}
