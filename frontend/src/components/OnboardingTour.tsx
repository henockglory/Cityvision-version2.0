import { useTranslation } from 'react-i18next';
import { useOnboarding } from '@/hooks/useOnboarding';
import { useSound } from '@/hooks/useSound';

interface OnboardingTourProps {
  enabled: boolean;
}

export default function OnboardingTour({ enabled }: OnboardingTourProps) {
  const { t } = useTranslation();
  const { skipOnboarding, onboardingCompleted } = useOnboarding(enabled);
  const { playClick } = useSound();

  if (!enabled || onboardingCompleted) return null;

  return (
    <button
      type="button"
      onClick={() => {
        playClick();
        skipOnboarding();
      }}
      className="fixed bottom-6 right-6 z-50 cv-btn-secondary text-xs shadow-glow animate-fade-in"
    >
      {t('common.skipTour')}
    </button>
  );
}
