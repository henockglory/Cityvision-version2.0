import { Navigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import EyeLogo from '@/components/EyeLogo';
import { useSetupStatus } from '@/hooks/api/queries';

interface SetupGuardProps {
  children: React.ReactNode;
}

export default function SetupGuard({ children }: SetupGuardProps) {
  const { t } = useTranslation();
  const location = useLocation();
  const { data, isLoading, isError } = useSetupStatus();

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center cv-grid-bg">
        <EyeLogo size={64} />
        <p className="mt-4 text-cv-muted text-sm animate-pulse">{t('setup.checking')}</p>
      </div>
    );
  }

  const initialized = isError ? false : (data?.initialized ?? false);
  const onSetup = location.pathname === '/setup';

  if (!initialized && !onSetup) {
    return <Navigate to="/setup" replace />;
  }

  if (initialized && onSetup) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
