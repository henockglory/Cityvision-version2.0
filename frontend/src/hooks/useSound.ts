import { useCallback, useRef } from 'react';
import { useUiStore } from '@/stores/uiStore';

function createOscillatorSound(ctx: AudioContext, type: 'click' | 'sonar'): void {
  const now = ctx.currentTime;

  if (type === 'click') {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'square';
    osc.frequency.setValueAtTime(1800, now);
    osc.frequency.exponentialRampToValueAtTime(400, now + 0.04);
    gain.gain.setValueAtTime(0.08, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.06);
    osc.start(now);
    osc.stop(now + 0.06);
  } else {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(600, now);
    osc.frequency.exponentialRampToValueAtTime(1200, now + 0.3);
    osc.frequency.exponentialRampToValueAtTime(300, now + 0.8);
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.12, now + 0.05);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.9);
    osc.start(now);
    osc.stop(now + 0.9);
  }
}

export function useSound() {
  const soundMuted = useUiStore((s) => s.soundMuted);
  const ctxRef = useRef<AudioContext | null>(null);

  const getContext = useCallback(() => {
    if (!ctxRef.current) {
      ctxRef.current = new AudioContext();
    }
    if (ctxRef.current.state === 'suspended') {
      void ctxRef.current.resume();
    }
    return ctxRef.current;
  }, []);

  const playClick = useCallback(() => {
    if (soundMuted) return;
    try {
      createOscillatorSound(getContext(), 'click');
    } catch {
      /* audio unavailable */
    }
  }, [soundMuted, getContext]);

  const playSonar = useCallback(() => {
    if (soundMuted) return;
    try {
      createOscillatorSound(getContext(), 'sonar');
    } catch {
      /* audio unavailable */
    }
  }, [soundMuted, getContext]);

  return { playClick, playSonar, soundMuted };
}
