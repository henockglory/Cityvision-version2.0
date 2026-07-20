import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, WifiOff } from 'lucide-react';

interface BackendUnavailableProps {
  onRetry: () => void;
}

/** Shown when setup/status cannot reach the API (backend restart). */
export default function BackendUnavailable({ onRetry }: BackendUnavailableProps) {
  const { t } = useTranslation();
  const [autoTick, setAutoTick] = useState(0);

  useEffect(() => {
    const delays = [3_000, 6_000, 12_000, 20_000];
    let step = 0;
    let timer = 0;
    const schedule = () => {
      if (step >= delays.length) return;
      timer = window.setTimeout(() => {
        onRetry();
        setAutoTick((n) => n + 1);
        step += 1;
        schedule();
      }, delays[step]);
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, [onRetry]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center cv-grid-bg px-6 text-center">
      <div className="w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center mb-4">
        <WifiOff className="w-8 h-8 text-amber-400" />
      </div>
      <h1 className="font-display text-xl font-semibold text-cv-text mb-2">
        {t('errorState.backendUnavailableTitle')}
      </h1>
      <p className="text-sm text-cv-muted max-w-md mb-6">
        {t('errorState.backendUnavailableHint')}
      </p>
      <button type="button" onClick={onRetry} className="cv-btn-secondary">
        <RefreshCw className="w-4 h-4" />
        {t('errorState.retry')}
      </button>
      {autoTick > 0 && (
        <p className="mt-4 text-xs text-cv-muted/70">{t('errorState.autoRetrying')}</p>
      )}
    </div>
  );
}
