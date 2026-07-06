import { HelpCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useUiStore } from '@/stores/uiStore';
import Tooltip from '@/components/ui/Tooltip';

interface TourHelpButtonProps {
  onClick: () => void;
  /** Valeur de data-tour pour les guides qui ciblent ce bouton (ex. rules-help). */
  dataTour?: string;
  className?: string;
}

export default function TourHelpButton({ onClick, dataTour, className = 'cv-btn-ghost p-2' }: TourHelpButtonProps) {
  const { t } = useTranslation();
  const toursEnabled = useUiStore((s) => s.toursEnabled);
  if (!toursEnabled) return null;

  return (
    <Tooltip content={t('pageHeader.tourHint', 'Guide pas à pas : menus, champs et procédures expliqués simplement.')}>
      <button
        type="button"
        className={className}
        onClick={onClick}
        data-tour={dataTour}
        aria-label={t('pageHeader.tourAriaLabel', 'Tutoriel guidé')}
      >
        <HelpCircle className="w-4 h-4" />
      </button>
    </Tooltip>
  );
}
