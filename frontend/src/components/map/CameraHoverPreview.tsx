import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
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

  // Portal to <body>: the map lives inside a .cv-card (backdrop-blur creates a
  // stacking context) which would otherwise trap this fixed overlay under the
  // sibling right-hand panels.
  const left = Math.min(position.x + 12, window.innerWidth - 196);
  const top = Math.max(8, Math.min(position.y - 8, window.innerHeight - 180));

  return createPortal(
    <div
      className="fixed z-[1200] pointer-events-none animate-fade-in"
      style={{ left, top }}
    >
      <div className="cv-card p-2 shadow-glow border-metric-cameras/30 w-[180px]">
        <p className="text-[10px] font-semibold truncate mb-1">{camera.name}</p>
        <div className="rounded overflow-hidden border border-cv-border aspect-video bg-black">
          <Go2RtcPlayer src={stream} bare className="w-full h-full min-h-0" />
        </div>
        <p className="text-[9px] text-cv-muted mt-1">Aperçu live</p>
      </div>
    </div>,
    document.body,
  );
}
