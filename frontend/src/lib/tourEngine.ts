import { driver, type DriveStep, type Driver } from 'driver.js';

import 'driver.js/dist/driver.css';



export const TOUR_STEP_DELAY_MS = 4000;



type TFn = (key: string, opts?: Record<string, unknown>) => string;



let gateTimers: ReturnType<typeof setTimeout>[] = [];

let gateIntervals: ReturnType<typeof setInterval>[] = [];

let stepUnlockedAt = 0;



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

      const parsed = JSON.parse(muted) as { state?: { soundMuted?: boolean; soundUiEnabled?: boolean; toursEnabled?: boolean } };

      if (parsed.state?.soundMuted || parsed.state?.soundUiEnabled === false || parsed.state?.toursEnabled === false) return;

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

  } catch { /* noop */ }

}



export function buildTourDescription(

  t: TFn,

  descKey: string,

  opts?: { tipKey?: string; stepsKey?: string; guideSrc?: string; descText?: string },

): string {

  const parts: string[] = [];

  if (opts?.guideSrc) {

    parts.push(

      `<img src="${opts.guideSrc}" alt="" class="cv-tour-guide-img" />`,

    );

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



/** Compte à rebours visuel — n'utilise pas disabled pour ne pas casser driver.js. */

function gateNextButtonVisual(popover: Element, t: TFn) {

  clearGateTimers();



  const nextBtn = popover.querySelector('.driver-popover-next-btn, .driver-popover-done-btn') as HTMLButtonElement | null;

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



export function createTourDriver({ t, onDone, onDestroyStarted, prepareStep }: CreateTourDriverOptions): Driver {

  clearGateTimers();

  stepUnlockedAt = 0;



  let activeDriver: Driver | null = null;



  const runPrepare = (step: DriveStep | undefined) => {

    const sel = resolveStepSelector(step);

    if (!sel || !prepareStep) return;

    prepareStep(sel);

    requestAnimationFrame(() => {

      requestAnimationFrame(() => activeDriver?.refresh());

    });

  };



  activeDriver = driver({

    showProgress: true,

    animate: true,

    smoothScroll: true,

    allowClose: true,

    overlayColor: 'rgba(5, 10, 18, 0.88)',

    popoverClass: 'cv-driver-popover',

    stagePadding: 8,

    stageRadius: 10,

    nextBtnText: t('onboarding.next'),

    prevBtnText: t('onboarding.prev'),

    doneBtnText: t('onboarding.done'),

    progressText: t('tours.common.progress', { defaultValue: '{{current}} / {{total}}' }),

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

    onHighlighted: (_element, step) => {

      runPrepare(step);

      playTourStepSound();

      stepUnlockedAt = Date.now() + TOUR_STEP_DELAY_MS;

      requestAnimationFrame(() => {

        const popover = document.querySelector('.cv-driver-popover');

        if (popover) gateNextButtonVisual(popover, t);

      });

    },

    onDestroyed: () => {

      clearGateTimers();

      stepUnlockedAt = 0;

      onDone?.();

    },

    onDestroyStarted: () => {
      clearGateTimers();
      stepUnlockedAt = 0;
      onDestroyStarted?.();
      // driver.js v1 : onDestroyStarted intercepte la fermeture — il faut destroy() pour terminer.
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

  driverInstance.setSteps(filtered);

  driverInstance.drive();

  return true;

}


