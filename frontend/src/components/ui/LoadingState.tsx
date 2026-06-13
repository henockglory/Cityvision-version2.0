import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function LoadingState() {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-center justify-center py-24 animate-fade-in">
      <Loader2 className="w-8 h-8 text-cv-accent animate-spin mb-3" />
      <p className="text-sm text-cv-muted">{t('common.loading')}</p>
    </div>
  );
}
