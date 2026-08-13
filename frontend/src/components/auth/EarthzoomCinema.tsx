import { useCallback, useEffect, useRef } from 'react';
import {
  EARTHZOOM_INTRO_END,
  EARTHZOOM_OUTRO_END,
  EARTHZOOM_OUTRO_START,
  EARTHZOOM_SRC,
  type EarthzoomPhase,
} from '@/lib/earthzoomCinema';

type Props = {
  phase: EarthzoomPhase;
  onIntroFrozen: () => void;
  onOutroEnded: () => void;
};

/**
 * Full-bleed muted Earthzoom clip for login:
 * intro 0→9s then freeze; outro 10→14s after successful auth.
 */
export default function EarthzoomCinema({ phase, onIntroFrozen, onOutroEnded }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const introFrozenRef = useRef(false);
  const outroEndedRef = useRef(false);
  const onIntroFrozenRef = useRef(onIntroFrozen);
  const onOutroEndedRef = useRef(onOutroEnded);
  onIntroFrozenRef.current = onIntroFrozen;
  onOutroEndedRef.current = onOutroEnded;

  const freezeIntro = useCallback(() => {
    const v = videoRef.current;
    if (!v || introFrozenRef.current) return;
    introFrozenRef.current = true;
    try {
      v.pause();
      if (v.currentTime < EARTHZOOM_INTRO_END - 0.05) {
        v.currentTime = EARTHZOOM_INTRO_END;
      }
    } catch {
      /* seek may fail before metadata */
    }
    onIntroFrozenRef.current();
  }, []);

  const finishOutro = useCallback(() => {
    if (outroEndedRef.current) return;
    outroEndedRef.current = true;
    const v = videoRef.current;
    if (v) {
      try {
        v.pause();
      } catch {
        /* ignore */
      }
    }
    onOutroEndedRef.current();
  }, []);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    if (phase === 'intro') {
      introFrozenRef.current = false;
      outroEndedRef.current = false;
      const start = () => {
        try {
          v.currentTime = 0;
        } catch {
          /* ignore */
        }
        void v.play().catch(() => {
          // Autoplay blocked — jump to frozen form.
          freezeIntro();
        });
      };
      if (v.readyState >= 1) start();
      else v.addEventListener('loadedmetadata', start, { once: true });
      return;
    }

    if (phase === 'frozen') {
      try {
        v.pause();
        if (Math.abs(v.currentTime - EARTHZOOM_INTRO_END) > 0.15) {
          v.currentTime = EARTHZOOM_INTRO_END;
        }
      } catch {
        /* ignore */
      }
      return;
    }

    if (phase === 'outro') {
      outroEndedRef.current = false;
      const startOutro = () => {
        try {
          v.currentTime = EARTHZOOM_OUTRO_START;
        } catch {
          /* ignore */
        }
        void v.play().catch(() => {
          finishOutro();
        });
      };
      if (v.readyState >= 1) startOutro();
      else v.addEventListener('loadedmetadata', startOutro, { once: true });

      // Safety net if timeupdate / ended never fire.
      const failSafe = window.setTimeout(finishOutro, (EARTHZOOM_OUTRO_END - EARTHZOOM_OUTRO_START + 2) * 1000);
      return () => window.clearTimeout(failSafe);
    }
  }, [phase, freezeIntro, finishOutro]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const onTimeUpdate = () => {
      if (phase === 'intro' && v.currentTime >= EARTHZOOM_INTRO_END) {
        freezeIntro();
      }
      if (phase === 'outro' && v.currentTime >= EARTHZOOM_OUTRO_END) {
        finishOutro();
      }
    };

    const onEnded = () => {
      if (phase === 'intro') freezeIntro();
      if (phase === 'outro') finishOutro();
    };

    v.addEventListener('timeupdate', onTimeUpdate);
    v.addEventListener('ended', onEnded);
    return () => {
      v.removeEventListener('timeupdate', onTimeUpdate);
      v.removeEventListener('ended', onEnded);
    };
  }, [phase, freezeIntro, finishOutro]);

  return (
    <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none" aria-hidden>
      <video
        ref={videoRef}
        className="absolute inset-0 h-full w-full object-cover"
        src={EARTHZOOM_SRC}
        muted
        playsInline
        preload="auto"
        disablePictureInPicture
      />
      <div
        className={`absolute inset-0 transition-colors duration-500 ${
          phase === 'frozen' ? 'bg-black/45' : phase === 'outro' ? 'bg-black/25' : 'bg-black/20'
        }`}
      />
    </div>
  );
}
