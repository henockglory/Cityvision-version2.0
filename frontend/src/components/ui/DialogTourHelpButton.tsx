import { HelpCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useUiStore } from '@/stores/uiStore';
import Tooltip from '@/components/ui/Tooltip';

interface DialogTourHelpButtonProps {
  onClick: () => void;
  className?: string;
}

/** Bouton ? pour relancer le tutoriel d'un dialogue / wizard. */
export default function DialogTourHelpButton({
  onClick,
  className = 'cv-btn-ghost p-2 rounded-lg shrink-0',
}: DialogTourHelpButtonProps) {
  const { t } = useTranslation();
  const toursEnabled = useUiStore((s) => s.toursEnabled);
  if (!toursEnabled) return null;

  return (
    <Tooltip content={t('pageHeader.tourHint', 'Guide pas à pas : menus, champs et procédures expliqués simplement.')}>
      <button
        type="button"
        className={className}
        onClick={onClick}
        aria-label={t('pageHeader.tourAriaLabel', 'Tutoriel guidé')}
      >
        <HelpCircle className="w-4 h-4" />
      </button>
    </Tooltip>
  );
}
