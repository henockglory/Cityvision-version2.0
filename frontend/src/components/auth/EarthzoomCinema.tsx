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
 * - intro: play 0→9s then freeze on that frame (login form overlays)
 * - outro: play 10→14s after successful auth (fake loading), then hand off to app
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
    let settled = false;
    const settle = () => {
      if (settled) return;
      settled = true;
      try {
        v.pause();
      } catch {
        /* ignore */
      }
      onIntroFrozenRef.current();
    };
    try {
      if (Math.abs(v.currentTime - EARTHZOOM_INTRO_END) > 0.08) {
        const onSeeked = () => {
          v.removeEventListener('seeked', onSeeked);
          settle();
        };
        v.addEventListener('seeked', onSeeked);
        v.currentTime = EARTHZOOM_INTRO_END;
        window.setTimeout(() => {
          v.removeEventListener('seeked', onSeeked);
          settle();
        }, 200);
        return;
      }
    } catch {
      /* seek may fail before metadata */
    }
    settle();
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

  const playFrom = useCallback((startAt: number, onFail: () => void) => {
    const v = videoRef.current;
    if (!v) {
      onFail();
      return;
    }

    let started = false;
    const tryPlay = () => {
      if (started) return;
      started = true;
      void v.play().catch(() => {
        started = false;
        // One retry after canplay — don't abort cinema on the first rejection.
        const retry = () => {
          if (started) return;
          started = true;
          void v.play().catch(() => onFail());
        };
        v.addEventListener('canplay', retry, { once: true });
        window.setTimeout(() => {
          v.removeEventListener('canplay', retry);
          if (!started) onFail();
        }, 1500);
      });
    };

    const seekThenPlay = () => {
      const onSeeked = () => {
        v.removeEventListener('seeked', onSeeked);
        tryPlay();
      };
      v.addEventListener('seeked', onSeeked);
      try {
        v.currentTime = startAt;
      } catch {
        v.removeEventListener('seeked', onSeeked);
        tryPlay();
        return;
      }
      // Already at target (or seek completed sync).
      window.setTimeout(() => {
        if (Math.abs(v.currentTime - startAt) < 0.25) {
          v.removeEventListener('seeked', onSeeked);
          tryPlay();
        }
      }, 80);
    };

    if (v.readyState >= 1) seekThenPlay();
    else v.addEventListener('loadedmetadata', seekThenPlay, { once: true });
  }, []);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    if (phase === 'intro') {
      introFrozenRef.current = false;
      outroEndedRef.current = false;
      playFrom(0, () => {
        // Autoplay hard-blocked: still land on the intended freeze frame + form.
        freezeIntro();
      });
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
      playFrom(EARTHZOOM_OUTRO_START, finishOutro);
      const failSafe = window.setTimeout(
        finishOutro,
        (EARTHZOOM_OUTRO_END - EARTHZOOM_OUTRO_START + 2.5) * 1000,
      );
      return () => window.clearTimeout(failSafe);
    }
  }, [phase, playFrom, freezeIntro, finishOutro]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const onTimeUpdate = () => {
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

    // Poll: timeupdate can be sparse near the cut points.
    const poll = window.setInterval(onTimeUpdate, 100);

    v.addEventListener('timeupdate', onTimeUpdate);
    v.addEventListener('ended', onEnded);
    return () => {
      window.clearInterval(poll);
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
          phase === 'frozen' ? 'bg-black/45' : phase === 'outro' ? 'bg-black/30' : 'bg-black/15'
        }`}
      />
    </div>
  );
}
