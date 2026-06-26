import { Navigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { getAuthCredentials } from '@/lib/authSession';
import { useAuthHydrated } from '@/hooks/useAuthHydrated';
import type { UserRole } from '@/types';

interface ProtectedRouteProps {
  children: React.ReactNode;
  roles?: UserRole[];
}

export default function ProtectedRoute({ children, roles }: ProtectedRouteProps) {
  const { t } = useTranslation();
  const hydrated = useAuthHydrated();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const token = useAuthStore((s) => s.token);
  const hasRole = useAuthStore((s) => s.hasRole);

  if (!hydrated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cv-deep">
        <p className="text-sm text-cv-muted animate-pulse">{t('common.loading')}</p>
      </div>
    );
  }

  const stored = getAuthCredentials();
  const authed = (isAuthenticated && token) || !!stored.token;

  if (!authed) {
    return <Navigate to="/login" replace />;
  }

  if (roles && !hasRole(...roles)) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
