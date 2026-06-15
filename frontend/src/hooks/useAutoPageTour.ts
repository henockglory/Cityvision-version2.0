import { useCallback, useEffect, useRef } from 'react';
import { driver, type Driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import { useTranslation } from 'react-i18next';
import { getTourSteps, type TourId } from '@/lib/tourRegistry';
import { useUiStore } from '@/stores/uiStore';

function createDriver(t: (k: string) => string, onDone: () => void) {
  return driver({
    showProgress: true,
    animate: true,
    overlayColor: 'rgba(5, 10, 18, 0.85)',
    popoverClass: 'cv-driver-popover',
    nextBtnText: t('onboarding.next'),
    prevBtnText: t('onboarding.prev'),
    doneBtnText: t('onboarding.done'),
    progressText: '{{current}} / {{total}}',
    onDestroyed: onDone,
  });
}

export function useAutoPageTour(tourId: TourId) {
  const { t } = useTranslation();
  const toursAutoStart = useUiStore((s) => s.toursAutoStart);
  const completed = useUiStore((s) => s.completedTours[tourId]);
  const completeTour = useUiStore((s) => s.completeTour);
  const driverRef = useRef<Driver | null>(null);
  const startedRef = useRef(false);

  const startTour = useCallback(() => {
    const steps = getTourSteps(tourId, (k) => t(k));
    if (steps.length === 0) return;
    driverRef.current?.destroy();
    driverRef.current = createDriver(t, () => completeTour(tourId));
    driverRef.current.setSteps(steps);
    driverRef.current.drive();
  }, [t, tourId, completeTour]);

  useEffect(() => {
    if (!toursAutoStart || completed || startedRef.current) return;
    const steps = getTourSteps(tourId, (k) => t(k));
    if (steps.length === 0) return;
    startedRef.current = true;
    const timer = window.setTimeout(() => startTour(), 600);
    return () => window.clearTimeout(timer);
  }, [toursAutoStart, completed, tourId, startTour, t]);

  return startTour;
}

export function useRunTour() {
  const { t } = useTranslation();
  const completeTour = useUiStore((s) => s.completeTour);
  const driverRef = useRef<Driver | null>(null);

  return useCallback((tourId: TourId) => {
    const steps = getTourSteps(tourId, (k) => t(k));
    if (steps.length === 0) return;
    driverRef.current?.destroy();
    driverRef.current = createDriver(t, () => completeTour(tourId));
    driverRef.current.setSteps(steps);
    driverRef.current.drive();
  }, [t, completeTour]);
}
