import { useCallback, useEffect, useRef, useState } from 'react';
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

function seekVideo(v: HTMLVideoElement, t: number): Promise<number> {
  return new Promise((resolve) => {
    if (Math.abs(v.currentTime - t) <= 0.12) {
      resolve(v.currentTime);
      return;
    }
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      v.removeEventListener('seeked', finish);
      window.clearTimeout(timer);
      resolve(v.currentTime);
    };
    v.addEventListener('seeked', finish);
    const timer = window.setTimeout(finish, 900);
    try {
      v.currentTime = t;
    } catch {
      finish();
    }
  });
}

/**
 * Full-bleed muted Earthzoom clip for login:
 * - intro: 0→9s then freeze under the login form
 * - outro: dedicated video, revealed only after seek lands near 10.71s
 *   (never flash t=0 while "Connexion à Citévision…" is shown)
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

  // Outro layer stays hidden until currentTime is confirmed past the outro keyframe.
  const [outroReady, setOutroReady] = useState(false);

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

  useEffect(() => {
    if (phase !== 'outro') setOutroReady(false);
  }, [phase]);

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

  // Outro: seek FIRST while intro freeze stays visible, then reveal + play.
  useEffect(() => {
    if (phase !== 'outro') return;
    const v = outroRef.current;
    if (!v) return;

    outroEndedRef.current = false;
    setOutroReady(false);
    let cancelled = false;

    const startOutro = async () => {
      try {
        try {
          v.pause();
        } catch {
          /* ignore */
        }

        if (v.readyState < 1) {
          await new Promise<void>((resolve) => {
            v.addEventListener('loadedmetadata', () => resolve(), { once: true });
            window.setTimeout(() => resolve(), 1000);
          });
        }
        if (cancelled) return;

        // Retry seek until we are clearly in the outro window (not near t=0).
        let landed = 0;
        for (let attempt = 0; attempt < 4; attempt++) {
          landed = await seekVideo(v, EARTHZOOM_OUTRO_START);
          if (cancelled) return;
          if (landed >= EARTHZOOM_OUTRO_START - 0.4) break;
          await new Promise((r) => window.setTimeout(r, 120));
        }

        if (cancelled || outroEndedRef.current) return;

        // Still near start → do not reveal a t≈0 frame; skip cinema and enter app.
        if (v.currentTime < EARTHZOOM_OUTRO_START - 0.4) {
          finishOutro();
          return;
        }

        // Reveal only now — intro freeze remains underneath until this flips.
        setOutroReady(true);
        await v.play();
      } catch {
        if (!cancelled) finishOutro();
      }
    };

    void startOutro();

    const onTime = () => {
      if (cancelled || outroEndedRef.current) return;
      // If browser rewound after reveal, hide again and abort rather than show t=0.
      if (v.currentTime < 5) {
        setOutroReady(false);
        finishOutro();
        return;
      }
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
      (EARTHZOOM_OUTRO_END - EARTHZOOM_OUTRO_START + 4) * 1000,
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

  const showOutro = phase === 'outro' && outroReady;

  return (
    <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none" aria-hidden>
      <video
        ref={introRef}
        className={`absolute inset-0 h-full w-full object-cover ${showOutro ? 'opacity-0' : 'opacity-100'}`}
        src={EARTHZOOM_SRC}
        muted
        playsInline
        preload="auto"
        disablePictureInPicture
      />
      <video
        ref={outroRef}
        className={`absolute inset-0 h-full w-full object-cover ${showOutro ? 'opacity-100' : 'opacity-0'}`}
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
