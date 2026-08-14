import { useCallback, useEffect, useRef } from 'react';
import {
  EARTHZOOM_INTRO_END,
  EARTHZOOM_OUTRO_END,
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
 * - intro: play 0→9s then freeze under the login form
 * - outro: resume the SAME element from the freeze (~9s) and play through to 14s
 *   (no second video / no seek-to-10 — that was aborting the outro when seek failed)
 */
export default function EarthzoomCinema({ phase, onIntroFrozen, onOutroEnded }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const introFrozenRef = useRef(false);
  const outroEndedRef = useRef(false);
  const genRef = useRef(0);
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
      // Snap to intro cut if we overshot slightly.
      if (v.currentTime < EARTHZOOM_INTRO_END - 0.05 || v.currentTime > EARTHZOOM_INTRO_END + 0.5) {
        v.currentTime = EARTHZOOM_INTRO_END;
      }
    } catch {
      /* ignore */
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
    const gen = ++genRef.current;
    const alive = () => genRef.current === gen;

    if (phase === 'intro') {
      introFrozenRef.current = false;
      outroEndedRef.current = false;
      try {
        v.currentTime = 0;
      } catch {
        /* ignore */
      }
      void v.play().catch(() => {
        if (alive()) freezeIntro();
      });
      return;
    }

    if (phase === 'frozen') {
      try {
        v.pause();
        if (Math.abs(v.currentTime - EARTHZOOM_INTRO_END) > 0.35) {
          v.currentTime = EARTHZOOM_INTRO_END;
        }
      } catch {
        /* ignore */
      }
      return;
    }

    if (phase === 'outro') {
      outroEndedRef.current = false;
      // Resume from freeze frame — do NOT seek to 10 (keyframes make that jump to 0 or fail).
      // Playing 9→14 covers the requested "second part" continuously.
      try {
        if (v.currentTime < EARTHZOOM_INTRO_END - 1) {
          v.currentTime = EARTHZOOM_INTRO_END;
        }
      } catch {
        /* ignore */
      }
      void v.play().catch(() => {
        if (alive()) finishOutro();
      });

      const failSafe = window.setTimeout(
        () => {
          if (alive()) finishOutro();
        },
        (EARTHZOOM_OUTRO_END - EARTHZOOM_INTRO_END + 4) * 1000,
      );
      return () => window.clearTimeout(failSafe);
    }
  }, [phase, freezeIntro, finishOutro]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const onTick = () => {
      if (phase === 'intro' && !introFrozenRef.current && v.currentTime >= EARTHZOOM_INTRO_END) {
        freezeIntro();
      }
      if (phase === 'outro' && !outroEndedRef.current && v.currentTime >= EARTHZOOM_OUTRO_END) {
        finishOutro();
      }
    };
    const onEnded = () => {
      if (phase === 'intro') freezeIntro();
      if (phase === 'outro') finishOutro();
    };

    const poll = window.setInterval(onTick, 80);
    v.addEventListener('timeupdate', onTick);
    v.addEventListener('ended', onEnded);
    return () => {
      window.clearInterval(poll);
      v.removeEventListener('timeupdate', onTick);
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
          phase === 'frozen' ? 'bg-black/45' : phase === 'outro' ? 'bg-black/30' : 'bg-black/15'
        }`}
      />
    </div>
  );
}
