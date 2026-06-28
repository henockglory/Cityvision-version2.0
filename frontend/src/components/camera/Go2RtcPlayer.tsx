import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Go2RtcWebRtcPlayer, type Go2RtcPlayerState } from '@/lib/go2rtc-webrtc';

interface Go2RtcPlayerProps {
  className?: string;
  src?: string;
  bare?: boolean;
  label?: string;
  /** Show a short user-facing message instead of raw WebRTC/RTSP errors. */
  friendlyErrors?: boolean;
  objectFit?: 'contain' | 'cover' | 'fill';
}

export default function Go2RtcPlayer({
  className = '',
  src,
  bare = false,
  label,
  friendlyErrors = false,
  objectFit = 'contain',
}: Go2RtcPlayerProps) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<Go2RtcWebRtcPlayer | null>(null);
  const [state, setState] = useState<Go2RtcPlayerState>('idle');
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [modeLabel, setModeLabel] = useState('WebRTC');

  useEffect(() => {
    const el = videoRef.current;
    if (!el || !src) return;

    const player = new Go2RtcWebRtcPlayer(
      {
        src,
        onState: (s, detail) => {
          setState(s);
          setErrorDetail(detail ?? null);
          if (s === 'live') setModeLabel((m) => (m === 'MSE' ? 'MSE' : 'WebRTC'));
          if (s === 'fallback-mse') {
            setModeLabel('MSE');
          }
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
  }, [src]);

  if (!src) {
    return (
      <div className={`relative bg-black overflow-hidden flex items-center justify-center ${className}`}>
        <p className="text-sm text-white/70 text-center px-4">
          {t('liveView.connectingStream', 'Connexion au flux…')}
        </p>
      </div>
    );
  }

  const live = state === 'live';
  const connecting = state === 'connecting' || state === 'fallback-mse';

  return (
    <div className={`relative bg-black overflow-hidden ${className}`}>
      <video
        ref={videoRef}
        className={`absolute inset-0 w-full h-full bg-black ${
          objectFit === 'cover' ? 'object-cover' : objectFit === 'fill' ? 'object-fill' : 'object-contain'
        }`}
        playsInline
        muted
        autoPlay
      />
      {!live && state !== 'idle' && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/80 pointer-events-none">
          <p className="text-sm text-white/80 text-center px-4">
            {connecting && (state === 'fallback-mse' ? t('liveView.fallbackMse', 'Repli MSE…') : t('liveView.connectingStream', 'Connexion vidéo…'))}
            {state === 'error' && (
              friendlyErrors
                ? t('demoCenter.streamUnavailable', 'Flux vidéo indisponible — importez ou sélectionnez une source active.')
                : (errorDetail ?? t('liveView.streamError', "Impossible d'afficher l'image"))
            )}
          </p>
        </div>
      )}
      {!bare && (
        <div className="absolute top-3 left-3 flex items-center gap-2 pointer-events-none">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-black/70 text-white border border-white/10">
            <span
              className={`w-2 h-2 rounded-full ${live ? 'bg-red-500 animate-pulse' : 'bg-amber-500'}`}
            />
            {live ? 'LIVE' : connecting ? '…' : 'OFF'}
          </span>
          {label && (
            <span className="px-2 py-1 rounded-md text-[10px] bg-black/50 text-white/80 max-w-[180px] truncate">
              {label}
            </span>
          )}
          <span className="px-2 py-1 rounded-md text-[10px] font-mono bg-black/50 text-white/70">
            {modeLabel}
          </span>
        </div>
      )}
    </div>
  );
}
