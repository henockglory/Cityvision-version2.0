import { Navigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import EyeLogo from '@/components/EyeLogo';
import BackendUnavailable from '@/components/BackendUnavailable';
import { useSetupStatus } from '@/hooks/api/queries';

const SETUP_FLAG = 'cv_setup_initialized';

export function markSetupInitialized() {
  localStorage.setItem(SETUP_FLAG, '1');
}

function isSetupKnown(): boolean {
  return localStorage.getItem(SETUP_FLAG) === '1';
}

interface SetupGuardProps {
  children: React.ReactNode;
}

export default function SetupGuard({ children }: SetupGuardProps) {
  const { t } = useTranslation();
  const location = useLocation();
  const { data, isLoading, isError, refetch } = useSetupStatus();
  const setupKnown = isSetupKnown();

  if (data?.initialized) {
    markSetupInitialized();
  }

  // Block only on first visit (setup never completed locally)
  if (!setupKnown) {
    if (isLoading) {
      return (
        <div className="min-h-screen flex flex-col items-center justify-center bg-cv-deep">
          <EyeLogo size={64} />
          <p className="mt-4 text-cv-muted text-sm animate-pulse">{t('setup.checking')}</p>
        </div>
      );
    }

    if (isError) {
      return <BackendUnavailable onRetry={() => void refetch()} />;
    }
  }

  const initialized = data?.initialized ?? setupKnown;
  const onSetup = location.pathname === '/setup';

  if (!initialized && !onSetup) {
    return <Navigate to="/setup" replace />;
  }

  if (initialized && onSetup) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
