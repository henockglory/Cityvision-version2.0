import { driver, type DriveStep, type Driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import {
  clearTourAtmosphere,
  ensureTourAtmosphere,
  updateTourAtmosphereCutout,
} from '@/lib/tourAtmosphere';

export const TOUR_STEP_DELAY_MS = 4000;

type TFn = (key: string, opts?: Record<string, unknown>) => string;

let gateTimers: ReturnType<typeof setTimeout>[] = [];
let gateIntervals: ReturnType<typeof setInterval>[] = [];
let stepUnlockedAt = 0;
let resizeHandler: (() => void) | null = null;
let lastHighlightEl: Element | null = null;

function clearGateTimers() {
  gateTimers.forEach(clearTimeout);
  gateIntervals.forEach(clearInterval);
  gateTimers = [];
  gateIntervals = [];
}

function isStepLocked() {
  return Date.now() < stepUnlockedAt;
}

function playTourStepSound() {
  try {
    const muted = localStorage.getItem('cv-ui');
    if (muted) {
      const parsed = JSON.parse(muted) as {
        state?: { soundMuted?: boolean; soundUiEnabled?: boolean; toursEnabled?: boolean };
      };
      if (
        parsed.state?.soundMuted ||
        parsed.state?.soundUiEnabled === false ||
        parsed.state?.toursEnabled === false
      ) {
        return;
      }
    }
    const ctx = new AudioContext();
    if (ctx.state === 'suspended') void ctx.resume();
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(640, now);
    osc.frequency.exponentialRampToValueAtTime(520, now + 0.06);
    gain.gain.setValueAtTime(0.025, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
    osc.start(now);
    osc.stop(now + 0.09);
    setTimeout(() => void ctx.close(), 200);
  } catch {
    /* noop */
  }
}

export function buildTourDescription(
  t: TFn,
  descKey: string,
  opts?: { tipKey?: string; stepsKey?: string; guideSrc?: string; descText?: string },
): string {
  const parts: string[] = [];
  if (opts?.guideSrc) {
    parts.push(`<img src="${opts.guideSrc}" alt="" class="cv-tour-guide-img" />`);
  }
  const desc = opts?.descText ?? (descKey ? t(descKey) : '');
  if (desc) parts.push(`<p class="cv-tour-desc">${desc}</p>`);
  if (opts?.tipKey) {
    parts.push(
      `<div class="cv-tour-tip"><span class="cv-tour-tip-label">${t('tours.common.tip')}</span> ${t(opts.tipKey)}</div>`,
    );
  }
  if (opts?.stepsKey) {
    const steps = t(opts.stepsKey, { returnObjects: true });
    if (Array.isArray(steps) && steps.length > 0) {
      const items = steps.map((s) => `<li>${String(s)}</li>`).join('');
      parts.push(
        `<div class="cv-tour-procedure"><span class="cv-tour-procedure-label">${t('tours.common.procedure')}</span><ol class="cv-tour-steps">${items}</ol></div>`,
      );
    }
  }
  return parts.join('');
}

function gateNextButtonVisual(popover: Element, t: TFn) {
  clearGateTimers();

  const nextBtn = popover.querySelector(
    '.driver-popover-next-btn, .driver-popover-done-btn',
  ) as HTMLButtonElement | null;
  if (!nextBtn) return;

  nextBtn.classList.add('cv-tour-next-wait');
  nextBtn.setAttribute('aria-disabled', 'true');

  let remaining = Math.ceil(TOUR_STEP_DELAY_MS / 1000);
  let countdownEl = popover.querySelector('.cv-tour-countdown') as HTMLSpanElement | null;
  if (!countdownEl) {
    countdownEl = document.createElement('span');
    countdownEl.className = 'cv-tour-countdown';
    const footer = popover.querySelector('.driver-popover-footer');
    if (footer) footer.insertBefore(countdownEl, footer.firstChild);
  }
  countdownEl.textContent = t('tours.common.waitSeconds', { n: remaining });

  const unlock = () => {
    nextBtn.classList.remove('cv-tour-next-wait');
    nextBtn.removeAttribute('aria-disabled');
    if (countdownEl) countdownEl.textContent = '';
    stepUnlockedAt = 0;
  };

  const interval = setInterval(() => {
    remaining -= 1;
    if (remaining <= 0) {
      clearInterval(interval);
      unlock();
    } else {
      countdownEl!.textContent = t('tours.common.waitSeconds', { n: remaining });
    }
  }, 1000);
  gateIntervals.push(interval);

  const timer = setTimeout(() => {
    clearInterval(interval);
    unlock();
  }, TOUR_STEP_DELAY_MS);
  gateTimers.push(timer);
}

function bindAtmosphereResize() {
  if (resizeHandler) return;
  resizeHandler = () => updateTourAtmosphereCutout(lastHighlightEl);
  window.addEventListener('resize', resizeHandler);
  window.addEventListener('scroll', resizeHandler, true);
}

function unbindAtmosphereResize() {
  if (!resizeHandler) return;
  window.removeEventListener('resize', resizeHandler);
  window.removeEventListener('scroll', resizeHandler, true);
  resizeHandler = null;
}

function enhancePopoverChrome(popover: Element, t: TFn) {
  if (popover.querySelector('.cv-tour-popover-accent')) return;
  const accent = document.createElement('div');
  accent.className = 'cv-tour-popover-accent';
  accent.setAttribute('aria-hidden', 'true');
  popover.prepend(accent);

  const closeBtn = popover.querySelector('.driver-popover-close-btn');
  if (closeBtn && !closeBtn.getAttribute('aria-label')) {
    closeBtn.setAttribute('aria-label', t('common.close', { defaultValue: 'Fermer' }));
  }
}

export interface CreateTourDriverOptions {
  t: TFn;
  onDone?: () => void;
  onDestroyStarted?: () => void;
  /** Synchronise l'UI (wizard, onglet…) avant de surligner une étape. */
  prepareStep?: (selector: string) => void;
}

function resolveStepSelector(step: DriveStep | undefined): string | null {
  const el = step?.element;
  return typeof el === 'string' ? el : null;
}

export function createTourDriver({
  t,
  onDone,
  onDestroyStarted,
  prepareStep,
}: CreateTourDriverOptions): Driver {
  clearGateTimers();
  stepUnlockedAt = 0;
  lastHighlightEl = null;

  let activeDriver: Driver | null = null;

  const runPrepare = (step: DriveStep | undefined) => {
    const sel = resolveStepSelector(step);
    if (!sel || !prepareStep) return;
    prepareStep(sel);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => activeDriver?.refresh());
    });
  };

  const teardownAtmosphere = () => {
    unbindAtmosphereResize();
    lastHighlightEl = null;
    clearTourAtmosphere();
  };

  activeDriver = driver({
    showProgress: true,
    animate: true,
    smoothScroll: true,
    allowClose: true,
    // Soft SVG dim — blur/dark handled by cv-tour-atmosphere cutout layer.
    overlayColor: 'rgb(2, 6, 16)',
    overlayOpacity: 0.35,
    popoverClass: 'cv-driver-popover',
    stagePadding: 12,
    stageRadius: 14,
    popoverOffset: 14,
    nextBtnText: t('onboarding.next'),
    prevBtnText: t('onboarding.prev'),
    doneBtnText: t('onboarding.done'),
    progressText: t('tours.common.progress', { defaultValue: '{{current}} / {{total}}' }),
    onPopoverRender: (popover) => {
      enhancePopoverChrome(popover.wrapper, t);
    },
    onNextClick: (_element, _step, { driver: drv }) => {
      if (isStepLocked()) return;
      clearGateTimers();
      stepUnlockedAt = 0;
      drv.moveNext();
    },
    onPrevClick: (_element, _step, { driver: drv }) => {
      clearGateTimers();
      stepUnlockedAt = 0;
      drv.movePrevious();
    },
    onCloseClick: (_element, _step, { driver: drv }) => {
      clearGateTimers();
      stepUnlockedAt = 0;
      drv.destroy();
    },
    onHighlighted: (element, step) => {
      ensureTourAtmosphere();
      bindAtmosphereResize();
      lastHighlightEl = element ?? null;
      updateTourAtmosphereCutout(element);
      runPrepare(step);
      playTourStepSound();
      stepUnlockedAt = Date.now() + TOUR_STEP_DELAY_MS;
      requestAnimationFrame(() => {
        const popover = document.querySelector('.cv-driver-popover');
        if (popover) {
          enhancePopoverChrome(popover, t);
          gateNextButtonVisual(popover, t);
        }
        updateTourAtmosphereCutout(element);
      });
    },
    onDestroyed: () => {
      clearGateTimers();
      stepUnlockedAt = 0;
      teardownAtmosphere();
      onDone?.();
    },
    onDestroyStarted: () => {
      clearGateTimers();
      stepUnlockedAt = 0;
      teardownAtmosphere();
      onDestroyStarted?.();
      activeDriver?.destroy();
    },
  });

  return activeDriver;
}

export function filterExistingSteps(steps: DriveStep[]): DriveStep[] {
  return steps.filter((s) => {
    if (!s.element) return true;
    if (typeof s.element === 'string') {
      try {
        return document.querySelector(s.element) != null;
      } catch {
        return false;
      }
    }
    return true;
  });
}

export function runTour(driverInstance: Driver, steps: DriveStep[]) {
  const filtered = filterExistingSteps(steps);
  if (filtered.length === 0) return false;
  ensureTourAtmosphere();
  bindAtmosphereResize();
  driverInstance.setSteps(filtered);
  driverInstance.drive();
  return true;
}
