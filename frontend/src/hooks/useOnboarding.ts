import { useEffect, useRef } from 'react';
import { driver, type DriveStep, type Driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import { useTranslation } from 'react-i18next';
import { useUiStore } from '@/stores/uiStore';

export function useOnboarding(enabled: boolean) {
  const { t } = useTranslation();
  const onboardingCompleted = useUiStore((s) => s.onboardingCompleted);
  const completeOnboarding = useUiStore((s) => s.completeOnboarding);
  const driverRef = useRef<Driver | null>(null);

  useEffect(() => {
    if (!enabled || onboardingCompleted) return;

    const steps: DriveStep[] = [
      {
        element: '#sidebar-nav',
        popover: {
          title: t('onboarding.sidebar.title'),
          description: t('onboarding.sidebar.description'),
          side: 'right',
        },
      },
      {
        element: '#navbar-search',
        popover: {
          title: t('onboarding.search.title'),
          description: t('onboarding.search.description'),
          side: 'bottom',
        },
      },
      {
        element: '#theme-toggle',
        popover: {
          title: t('onboarding.theme.title'),
          description: t('onboarding.theme.description'),
          side: 'bottom',
        },
      },
      {
        element: '#main-content',
        popover: {
          title: t('onboarding.content.title'),
          description: t('onboarding.content.description'),
          side: 'top',
        },
      },
    ];

    const timer = setTimeout(() => {
      driverRef.current = driver({
        showProgress: true,
        animate: true,
        overlayColor: 'rgba(5, 10, 18, 0.85)',
        popoverClass: 'cv-driver-popover',
        nextBtnText: t('onboarding.next'),
        prevBtnText: t('onboarding.prev'),
        doneBtnText: t('onboarding.done'),
        progressText: '{{current}} / {{total}}',
        steps,
        onDestroyStarted: () => {
          completeOnboarding();
          driverRef.current?.destroy();
        },
      });
      driverRef.current.drive();
    }, 800);

    return () => {
      clearTimeout(timer);
      driverRef.current?.destroy();
    };
  }, [enabled, onboardingCompleted, completeOnboarding, t]);

  const skipOnboarding = () => {
    completeOnboarding();
    driverRef.current?.destroy();
  };

  return { skipOnboarding, onboardingCompleted };
}
