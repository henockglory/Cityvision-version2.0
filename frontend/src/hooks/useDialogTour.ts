import { useCallback, useEffect, useRef } from 'react';
import { type Driver } from 'driver.js';
import { useTranslation } from 'react-i18next';
import { createTourDriver, runTour } from '@/lib/tourEngine';
import { getTourSteps, type TourId } from '@/lib/tourRegistry';
import { useUiStore } from '@/stores/uiStore';

/**
 * Lance un tutoriel guidé quand un dialogue / wizard s'ouvre.
 * Respecte toursEnabled + toursAutoStart et ne rejoue pas si déjà complété.
 */
export function useDialogTour(
  tourId: TourId,
  open: boolean,
  options?: { force?: boolean; prepareStep?: (selector: string) => void },
) {
  const { t } = useTranslation();
  const toursEnabled = useUiStore((s) => s.toursEnabled);
  const toursAutoStart = useUiStore((s) => s.toursAutoStart);
  const completed = useUiStore((s) => s.completedTours[tourId]);
  const completeTour = useUiStore((s) => s.completeTour);
  const driverRef = useRef<Driver | null>(null);
  const startedRef = useRef(false);

  const startTour = useCallback(() => {
    if (!toursEnabled) return;
    const steps = getTourSteps(tourId, (k) => t(k));
    driverRef.current?.destroy();
    driverRef.current = createTourDriver({
      t,
      onDone: () => completeTour(tourId),
      prepareStep: options?.prepareStep,
    });
    runTour(driverRef.current, steps);
  }, [t, tourId, completeTour, toursEnabled, options?.prepareStep]);

  useEffect(() => {
    if ((window as unknown as { __CV_E2E__?: boolean }).__CV_E2E__) return;
    if (!open) {
      startedRef.current = false;
      return;
    }
    if (!toursEnabled) return;
    if (!options?.force && (!toursAutoStart || completed || startedRef.current)) return;

    const steps = getTourSteps(tourId, (k) => t(k));
    if (steps.length === 0) return;

    startedRef.current = true;
    const timer = window.setTimeout(() => {
      requestAnimationFrame(() => startTour());
    }, 700);
    return () => window.clearTimeout(timer);
  }, [open, toursEnabled, toursAutoStart, completed, tourId, startTour, t, options?.force]);

  useEffect(() => () => {
    driverRef.current?.destroy();
  }, []);

  return startTour;
}
