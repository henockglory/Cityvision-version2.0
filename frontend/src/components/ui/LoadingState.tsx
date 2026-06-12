import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function LoadingState() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center py-16 text-cv-muted gap-3">
      <Loader2 className="w-8 h-8 animate-spin text-cv-accent" />
      <p className="text-sm">{t('common.loading')}</p>
    </div>
  );
}
