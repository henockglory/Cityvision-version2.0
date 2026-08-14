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
    const timer = window.setTimeout(finish, 700);
    try {
      v.currentTime = t;
    } catch {
      finish();
    }
  });
}

/**
 * Full-bleed muted Earthzoom clip for login:
 * - intro video: play 0→9s then freeze (login form overlays)
 * - outro video: separate element + media fragment #t=10.71,14 so playback
 *   never rewinds to 0 when credentials succeed
 */
export default function EarthzoomCinema({ phase, onIntroFrozen, onOutroEnded }: Props) {
  const introRef = useRef<HTMLVideoElement>(null);
  const outroRef = useRef<HTMLVideoElement>(null);
  const introFrozenRef = useRef(false);
  const outroEndedRef = useRef(false);
  const genRef = useRef(0);
  const onIntroFrozenRef = useRef(onIntroFrozen);
  const onOutroEndedRef = useRef(onOutroEnded);
  onIntroFrozenRef.current = onIntroFrozen;
  onOutroEndedRef.current = onOutroEnded;

  const freezeIntro = useCallback(async () => {
    const v = introRef.current;
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
    const v = outroRef.current;
    if (v) {
      try {
        v.pause();
      } catch {
        /* ignore */
      }
    }
    onOutroEndedRef.current();
  }, []);

  // Intro / freeze on the primary element.
  useEffect(() => {
    const v = introRef.current;
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
    }
  }, [phase, freezeIntro]);

  // Outro on a dedicated element so we never fight the intro timeline.
  useEffect(() => {
    if (phase !== 'outro') return;
    const v = outroRef.current;
    if (!v) return;

    outroEndedRef.current = false;
    let cancelled = false;

    const startOutro = async () => {
      // Media fragment already targets 10.71–14; still force currentTime as belt-and-braces.
      try {
        if (v.readyState < 1) {
          await new Promise<void>((resolve) => {
            v.addEventListener('loadedmetadata', () => resolve(), { once: true });
            window.setTimeout(() => resolve(), 800);
          });
        }
        if (cancelled) return;
        await seekVideo(v, EARTHZOOM_OUTRO_START);
        if (cancelled || outroEndedRef.current) return;
        if (v.currentTime < EARTHZOOM_OUTRO_START - 0.5) {
          v.currentTime = EARTHZOOM_OUTRO_START;
          await seekVideo(v, EARTHZOOM_OUTRO_START);
        }
        if (cancelled || outroEndedRef.current) return;
        await v.play();
      } catch {
        if (!cancelled) finishOutro();
      }
    };

    void startOutro();

    const onTime = () => {
      if (cancelled || outroEndedRef.current) return;
      if (v.currentTime >= EARTHZOOM_OUTRO_END) finishOutro();
    };
    const onEnded = () => {
      if (!cancelled) finishOutro();
    };
    const poll = window.setInterval(onTime, 80);
    const failSafe = window.setTimeout(
      () => {
        if (!cancelled) finishOutro();
      },
      (EARTHZOOM_OUTRO_END - EARTHZOOM_OUTRO_START + 3) * 1000,
    );
    v.addEventListener('timeupdate', onTime);
    v.addEventListener('ended', onEnded);

    return () => {
      cancelled = true;
      window.clearInterval(poll);
      window.clearTimeout(failSafe);
      v.removeEventListener('timeupdate', onTime);
      v.removeEventListener('ended', onEnded);
      try {
        v.pause();
      } catch {
        /* ignore */
      }
    };
  }, [phase, finishOutro]);

  // Intro cut at 9s.
  useEffect(() => {
    const v = introRef.current;
    if (!v || phase !== 'intro') return;
    const onTick = () => {
      if (!introFrozenRef.current && v.currentTime >= EARTHZOOM_INTRO_END) {
        void freezeIntro();
      }
    };
    const onEnded = () => void freezeIntro();
    const poll = window.setInterval(onTick, 80);
    v.addEventListener('timeupdate', onTick);
    v.addEventListener('ended', onEnded);
    return () => {
      window.clearInterval(poll);
      v.removeEventListener('timeupdate', onTick);
      v.removeEventListener('ended', onEnded);
    };
  }, [phase, freezeIntro]);

  const showOutro = phase === 'outro';
  const outroSrc = `${EARTHZOOM_SRC}#t=${EARTHZOOM_OUTRO_START},${EARTHZOOM_OUTRO_END}`;

  return (
    <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none" aria-hidden>
      <video
        ref={introRef}
        className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-300 ${
          showOutro ? 'opacity-0' : 'opacity-100'
        }`}
        src={EARTHZOOM_SRC}
        muted
        playsInline
        preload="auto"
        disablePictureInPicture
      />
      <video
        ref={outroRef}
        className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-300 ${
          showOutro ? 'opacity-100' : 'opacity-0'
        }`}
        src={outroSrc}
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
