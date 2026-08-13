import { useCallback, useEffect, useRef } from 'react';
import {
  DEFAULT_ALERT_SOUND_ID,
  customAlertSoundKey,
  findBundledAlertSound,
  isCustomAlertSoundId,
} from '@/lib/alertSounds';
import { playAudioUrl, playCustomAlertSound } from '@/lib/customAlertSounds';
import { useUiStore } from '@/stores/uiStore';

function playSoftClick(ctx: AudioContext) {
  const now = ctx.currentTime;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.type = 'sine';
  osc.frequency.setValueAtTime(880, now);
  osc.frequency.exponentialRampToValueAtTime(660, now + 0.03);
  gain.gain.setValueAtTime(0.04, now);
  gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
  osc.start(now);
  osc.stop(now + 0.05);
}

function playSoftAlert(ctx: AudioContext, volume: number) {
  const now = ctx.currentTime;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.type = 'triangle';
  osc.frequency.setValueAtTime(520, now);
  osc.frequency.linearRampToValueAtTime(780, now + 0.12);
  const peak = Math.max(0.001, Math.min(1, volume) * 0.12);
  gain.gain.setValueAtTime(0, now);
  gain.gain.linearRampToValueAtTime(peak, now + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
  osc.start(now);
  osc.stop(now + 0.36);
}

export function useSound() {
  const soundMuted = useUiStore((s) => s.soundMuted);
  const soundUiEnabled = useUiStore((s) => s.soundUiEnabled);
  const soundAlertsEnabled = useUiStore((s) => s.soundAlertsEnabled);
  const alertSoundId = useUiStore((s) => s.alertSoundId);
  const alertSoundVolume = useUiStore((s) => s.alertSoundVolume);
  const ctxRef = useRef<AudioContext | null>(null);
  const lastAlertRef = useRef(0);

  const getContext = useCallback(() => {
    if (soundMuted) return null;
    if (!ctxRef.current) ctxRef.current = new AudioContext();
    if (ctxRef.current.state === 'suspended') void ctxRef.current.resume();
    return ctxRef.current;
  }, [soundMuted]);

  useEffect(() => {
    if (soundMuted && ctxRef.current?.state === 'running') {
      void ctxRef.current.suspend();
    }
  }, [soundMuted]);

  const playClick = useCallback(() => {
    if (soundMuted || !soundUiEnabled) return;
    try {
      const ctx = getContext();
      if (ctx) playSoftClick(ctx);
    } catch { /* noop */ }
  }, [soundMuted, soundUiEnabled, getContext]);

  /** @deprecated use visual feedback only */
  const playSonar = useCallback(() => {
    /* intentionally silent — premium UX */
  }, []);

  const playAlertTone = useCallback(async (soundId?: string, volume?: number) => {
    if (soundMuted) return;
    const id = soundId ?? alertSoundId ?? DEFAULT_ALERT_SOUND_ID;
    const vol = volume ?? alertSoundVolume ?? 0.85;
    try {
      if (isCustomAlertSoundId(id)) {
        const key = customAlertSoundKey(id);
        if (key) {
          await playCustomAlertSound(key, vol);
          return;
        }
      }
      const bundled = findBundledAlertSound(id) ?? findBundledAlertSound(DEFAULT_ALERT_SOUND_ID);
      if (bundled) {
        await playAudioUrl(bundled.src, vol);
        return;
      }
      const ctx = getContext();
      if (ctx) playSoftAlert(ctx, vol);
    } catch {
      try {
        const ctx = getContext();
        if (ctx) playSoftAlert(ctx, vol);
      } catch { /* noop */ }
    }
  }, [soundMuted, alertSoundId, alertSoundVolume, getContext]);

  const playDetection = useCallback(() => {
    if (soundMuted || !soundAlertsEnabled) return;
    const now = Date.now();
    if (now - lastAlertRef.current < 2000) return;
    lastAlertRef.current = now;
    void playAlertTone();
  }, [soundMuted, soundAlertsEnabled, playAlertTone]);

  return { playClick, playSonar, playDetection, playAlertTone };
}
