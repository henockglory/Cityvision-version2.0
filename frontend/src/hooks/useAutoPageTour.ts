import { useCallback, useEffect, useRef } from 'react';

import { type Driver } from 'driver.js';

import { useTranslation } from 'react-i18next';

import { createTourDriver, runTour } from '@/lib/tourEngine';

import { getTourSteps, type TourId } from '@/lib/tourRegistry';

import { useUiStore } from '@/stores/uiStore';



interface AutoPageTourOptions {

  prepareStep?: (selector: string) => void;

}



export function useAutoPageTour(tourId: TourId, options?: AutoPageTourOptions) {

  const { t } = useTranslation();

  const toursEnabled = useUiStore((s) => s.toursEnabled);

  const toursAutoStart = useUiStore((s) => s.toursAutoStart);

  const completed = useUiStore((s) => s.completedTours[tourId]);

  const completeTour = useUiStore((s) => s.completeTour);

  const driverRef = useRef<Driver | null>(null);

  const startedRef = useRef(false);

  const prepareStep = options?.prepareStep;



  const startTour = useCallback(() => {

    if (!toursEnabled) return;

    const steps = getTourSteps(tourId, (k) => t(k));

    driverRef.current?.destroy();

    driverRef.current = createTourDriver({

      t,

      onDone: () => completeTour(tourId),

      prepareStep,

    });

    runTour(driverRef.current, steps);

  }, [t, tourId, completeTour, toursEnabled, prepareStep]);



  useEffect(() => {

    if ((window as unknown as { __CV_E2E__?: boolean }).__CV_E2E__) return;

    if (!toursEnabled || !toursAutoStart || completed || startedRef.current) return;

    const steps = getTourSteps(tourId, (k) => t(k));

    if (steps.length === 0) return;

    startedRef.current = true;

    const timer = window.setTimeout(() => startTour(), 800);

    return () => window.clearTimeout(timer);

  }, [toursEnabled, toursAutoStart, completed, tourId, startTour, t]);



  useEffect(() => () => {

    driverRef.current?.destroy();

  }, []);



  return startTour;

}



export function useRunTour() {

  const { t } = useTranslation();

  const toursEnabled = useUiStore((s) => s.toursEnabled);

  const completeTour = useUiStore((s) => s.completeTour);

  const driverRef = useRef<Driver | null>(null);



  return useCallback((tourId: TourId, options?: AutoPageTourOptions) => {

    if (!toursEnabled) return;

    const steps = getTourSteps(tourId, (k) => t(k));

    driverRef.current?.destroy();

    driverRef.current = createTourDriver({

      t,

      onDone: () => completeTour(tourId),

      prepareStep: options?.prepareStep,

    });

    runTour(driverRef.current, steps);

  }, [t, completeTour, toursEnabled]);

}


