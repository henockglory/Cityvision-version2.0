import { useEffect } from 'react';
import { authApi } from '@/api/client';
import { getRefreshToken, isTokenExpiringSoon, syncAuthSession } from '@/lib/authSession';
import { useAuthStore } from '@/stores/authStore';

/** Refresh JWT before expiry so sessions stay alive beyond 15 min. */
export function useProactiveTokenRefresh() {
  const orgId = useAuthStore((s) => s.orgId);

  useEffect(() => {
    const tick = async () => {
      if (!isTokenExpiringSoon(120_000)) return;
      const refresh = getRefreshToken();
      if (!refresh) return;
      try {
        const { data } = await authApi.refresh(refresh);
        syncAuthSession(data.access_token, orgId, data.refresh_token, data.expires_in);
        useAuthStore.setState({ token: data.access_token });
        window.dispatchEvent(new CustomEvent('cv-token-refreshed', { detail: data.access_token }));
      } catch {
        /* 401 interceptor handles hard logout */
      }
    };
    const id = window.setInterval(() => void tick(), 60_000);
    void tick();
    return () => window.clearInterval(id);
  }, [orgId]);
}
