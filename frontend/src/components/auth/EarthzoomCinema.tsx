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

function seekVideo(v: HTMLVideoElement, t: number): Promise<void> {
  return new Promise((resolve) => {
    if (Math.abs(v.currentTime - t) <= 0.12) {
      resolve();
      return;
    }
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      v.removeEventListener('seeked', finish);
      window.clearTimeout(timer);
      resolve();
    };
    v.addEventListener('seeked', finish);
    const timer = window.setTimeout(finish, 600);
    try {
      const anyV = v as HTMLVideoElement & { fastSeek?: (time: number) => void };
      if (typeof anyV.fastSeek === 'function') anyV.fastSeek(t);
      else v.currentTime = t;
    } catch {
      finish();
    }
  });
}

/**
 * Full-bleed muted Earthzoom clip for login:
 * - intro: play 0→9s then freeze on that frame (login form overlays)
 * - outro: play 10→14s after successful auth (fake loading), then hand off to app
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

  const freezeIntro = useCallback(async () => {
    const v = videoRef.current;
    if (!v || introFrozenRef.current) return;
    introFrozenRef.current = true;
    try {
      v.pause();
    } catch {
      /* ignore */
    }
    await seekVideo(v, EARTHZOOM_INTRO_END);
    try {
      v.pause();
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
      void (async () => {
        await seekVideo(v, 0);
        if (!alive()) return;
        try {
          await v.play();
        } catch {
          if (alive()) void freezeIntro();
        }
      })();
      return;
    }

    if (phase === 'frozen') {
      try {
        v.pause();
      } catch {
        /* ignore */
      }
      void seekVideo(v, EARTHZOOM_INTRO_END);
      return;
    }

    if (phase === 'outro') {
      outroEndedRef.current = false;
      void (async () => {
        try {
          v.pause();
        } catch {
          /* ignore */
        }
        // Critical: wait for seek to ~10s BEFORE play(), otherwise browsers restart at 0.
        await seekVideo(v, EARTHZOOM_OUTRO_START);
        if (!alive() || outroEndedRef.current) return;

        // Hard verify — never start playback near t=0 during outro.
        if (v.currentTime < EARTHZOOM_OUTRO_START - 0.35) {
          await seekVideo(v, EARTHZOOM_OUTRO_START);
          if (!alive() || outroEndedRef.current) return;
        }

        try {
          await v.play();
        } catch {
          if (alive()) finishOutro();
          return;
        }

        // If the engine still rewound, snap back once without restarting the whole clip.
        window.setTimeout(() => {
          if (!alive() || outroEndedRef.current || !videoRef.current) return;
          if (videoRef.current.currentTime < EARTHZOOM_OUTRO_START - 0.35) {
            try {
              videoRef.current.currentTime = EARTHZOOM_OUTRO_START;
            } catch {
              /* ignore */
            }
          }
        }, 120);
      })();

      const failSafe = window.setTimeout(
        () => {
          if (alive()) finishOutro();
        },
        (EARTHZOOM_OUTRO_END - EARTHZOOM_OUTRO_START + 3) * 1000,
      );
      return () => window.clearTimeout(failSafe);
    }
  }, [phase, freezeIntro, finishOutro]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const onTick = () => {
      if (phase === 'intro' && !introFrozenRef.current && v.currentTime >= EARTHZOOM_INTRO_END) {
        void freezeIntro();
      }
      if (phase === 'outro' && !outroEndedRef.current) {
        // Keep outro pinned in the 10→14 window if the browser jumps backward.
        if (v.currentTime < EARTHZOOM_OUTRO_START - 0.5 && v.currentTime < 5) {
          try {
            v.currentTime = EARTHZOOM_OUTRO_START;
          } catch {
            /* ignore */
          }
          return;
        }
        if (v.currentTime >= EARTHZOOM_OUTRO_END) finishOutro();
      }
    };

    const onEnded = () => {
      if (phase === 'intro') void freezeIntro();
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
