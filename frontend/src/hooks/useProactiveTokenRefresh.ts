import { useEffect } from 'react';
import { refreshSession } from '@/api/client';
import { getRefreshToken, isTokenExpiringSoon } from '@/lib/authSession';
import { useAuthStore } from '@/stores/authStore';

/** Refresh JWT before expiry so sessions stay alive beyond 15 min. */
export function useProactiveTokenRefresh() {
  const orgId = useAuthStore((s) => s.orgId);

  useEffect(() => {
    const tick = async () => {
      if (!isTokenExpiringSoon(180_000)) return;
      if (!getRefreshToken()) return;
      const { token, authFailed } = await refreshSession();
      if (token) {
        useAuthStore.setState({ token });
      } else if (authFailed) {
        /* hard logout only when refresh token is rejected — axios interceptor */
      }
    };
    const id = window.setInterval(() => void tick(), 30_000);
    void tick();
    return () => window.clearInterval(id);
  }, [orgId]);
}
