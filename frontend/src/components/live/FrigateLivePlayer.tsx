import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Go2RtcWebRtcPlayer, type Go2RtcPlayerState } from '@/lib/go2rtc-webrtc';
import { FRIGATE_GO2RTC_ORIGIN, frigateCameraId, frigateLiveIframeUrl } from '@/config/streams';

interface FrigateLivePlayerProps {
  cameraId: string;
  className?: string;
  label?: string;
  /** Native Frigate detection overlay (not SSE from ai-engine). */
  showBBox?: boolean;
}

/**
 * Live player via Frigate embedded go2rtc (WebRTC) or native iframe with bbox.
 * Frigate LPR/OCR text is ignored for alerts — live zoom only.
 */
export default function FrigateLivePlayer({
  cameraId,
  className = 'aspect-video w-full',
  label,
  showBBox = false,
}: FrigateLivePlayerProps) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<Go2RtcWebRtcPlayer | null>(null);
  const [state, setState] = useState<Go2RtcPlayerState>('idle');
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const frigateId = frigateCameraId(cameraId);

  useEffect(() => {
    if (showBBox) return undefined;
    const el = videoRef.current;
    if (!el || !frigateId) return undefined;

    const player = new Go2RtcWebRtcPlayer(
      {
        src: frigateId,
        origins: [FRIGATE_GO2RTC_ORIGIN],
        onState: (s, detail) => {
          setState(s);
          setErrorDetail(detail ?? null);
        },
      },
      el,
    );
    playerRef.current = player;
    player.start();
    return () => {
      player.stop();
      playerRef.current = null;
    };
  }, [frigateId, showBBox]);

  if (showBBox) {
    const iframeSrc = frigateLiveIframeUrl(frigateId, true);
    return (
      <div className={`relative bg-black overflow-hidden ${className}`}>
        <iframe
          title={label ?? t('liveView.frigateLive', 'Live Frigate')}
          src={iframeSrc}
          className="absolute inset-0 w-full h-full border-0"
          allow="autoplay; fullscreen"
        />
      </div>
    );
  }

  return (
    <div className={`relative bg-black overflow-hidden ${className}`}>
      <video
        ref={videoRef}
        className="absolute inset-0 w-full h-full object-contain bg-black"
        playsInline
        muted
        autoPlay
      />
      {state !== 'live' && state !== 'idle' ? (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-cv-muted font-mono p-4 text-center">
          {errorDetail ?? t('liveView.streamLoading', 'Connexion…')}
        </div>
      ) : null}
    </div>
  );
}
