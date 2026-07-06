import { useEffect, useRef } from 'react';
import { type Driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import { useTranslation } from 'react-i18next';
import { createTourDriver, runTour } from '@/lib/tourEngine';
import { getTourSteps } from '@/lib/tourRegistry';
import { useUiStore } from '@/stores/uiStore';

export function useOnboarding(enabled: boolean) {
  const { t } = useTranslation();
  const onboardingCompleted = useUiStore((s) => s.onboardingCompleted);
  const toursEnabled = useUiStore((s) => s.toursEnabled);
  const toursAutoStart = useUiStore((s) => s.toursAutoStart);
  const completeOnboarding = useUiStore((s) => s.completeOnboarding);
  const driverRef = useRef<Driver | null>(null);

  useEffect(() => {
    if (!enabled || !toursEnabled || !toursAutoStart || onboardingCompleted) return;

    const timer = setTimeout(() => {
      const steps = getTourSteps('global', (k) => t(k));
      driverRef.current?.destroy();
      driverRef.current = createTourDriver({
        t,
        onDone: () => completeOnboarding(),
      });
      runTour(driverRef.current, steps);
    }, 800);

    return () => {
      clearTimeout(timer);
      driverRef.current?.destroy();
    };
  }, [enabled, toursEnabled, toursAutoStart, onboardingCompleted, completeOnboarding, t]);

  const skipOnboarding = () => {
    completeOnboarding();
    driverRef.current?.destroy();
  };

  return { skipOnboarding, onboardingCompleted };
}
