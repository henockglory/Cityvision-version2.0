import { AlertTriangle, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSound } from '@/hooks/useSound';

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export default function ErrorState({ message, onRetry }: ErrorStateProps) {
  const { t } = useTranslation();
  const { playClick } = useSound();

  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center animate-fade-in">
      <div className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/30 flex items-center justify-center mb-4">
        <AlertTriangle className="w-8 h-8 text-red-400" />
      </div>
      <h3 className="font-display text-lg font-semibold text-red-400 mb-2">
        {t('errorState.title')}
      </h3>
      <p className="text-sm text-cv-muted max-w-md mb-6">
        {message ?? t('errorState.hint')}
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={() => {
            playClick();
            onRetry();
          }}
          className="cv-btn-secondary"
        >
          <RefreshCw className="w-4 h-4" />
          {t('errorState.retry')}
        </button>
      )}
    </div>
  );
}
