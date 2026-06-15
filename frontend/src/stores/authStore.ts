import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, UserRole } from '@/types';
import { authApi, camerasApi } from '@/api/client';
import { clearAuthSession, syncAuthSession } from '@/lib/authSession';

interface AuthStore {
  user: User | null;
  token: string | null;
  orgId: string | null;
  siteId: string | null;
  isAuthenticated: boolean;
  login: (user: User, token: string, orgId?: string | null, siteId?: string | null) => void;
  logout: () => void;
  hasRole: (...roles: UserRole[]) => boolean;
  setSiteId: (siteId: string | null) => void;
}

export function mapBackendRole(role: string): UserRole {
  switch (role) {
    case 'super_admin':
    case 'org_admin':
      return 'admin';
    case 'operator':
    case 'analyst':
    case 'supervisor':
    case 'technician':
      return 'operator';
    default:
      return 'viewer';
  }
}

export function getAuthCredentials(): { token: string | null; orgId: string | null } {
  const { token, orgId } = useAuthStore.getState();
  const stored = {
    token: localStorage.getItem('cv_token'),
    orgId: localStorage.getItem('cv_org_id'),
  };
  return {
    token: token ?? stored.token,
    orgId: orgId ?? stored.orgId,
  };
}

export async function apiLogin(
  email: string,
  password: string
): Promise<{ user: User; token: string; orgId: string | null; siteId: string | null }> {
  const { data } = await authApi.login(email, password);
  syncAuthSession(data.access_token, null, data.refresh_token, data.expires_in);
  const me = await authApi.me();
  const role = mapBackendRole(me.data.role);
  const orgId = me.data.org_id ?? null;
  syncAuthSession(data.access_token, orgId, data.refresh_token, data.expires_in);

  let siteId: string | null = null;
  if (orgId) {
    try {
      const { data: cams } = await camerasApi.list(orgId);
      const first = cams?.[0] as { site_id?: string } | undefined;
      siteId = first?.site_id ?? null;
    } catch {
      siteId = null;
    }
  }

  const user: User = {
    id: data.user.id,
    username: data.user.email.split('@')[0],
    email: data.user.email,
    role,
  };
  return { user, token: data.access_token, orgId, siteId };
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      orgId: null,
      siteId: localStorage.getItem('cv_site_id'),
      isAuthenticated: false,
      login: (user, token, orgId = null, siteId = null) => {
        syncAuthSession(token, orgId);
        if (siteId) {
          localStorage.setItem('cv_site_id', siteId);
        }
        set({ user, token, orgId, siteId, isAuthenticated: true });
      },
      logout: () => {
        clearAuthSession();
        localStorage.removeItem('cv_site_id');
        set({ user: null, token: null, orgId: null, siteId: null, isAuthenticated: false });
      },
      hasRole: (...roles) => {
        const { user } = get();
        return user ? roles.includes(user.role) : false;
      },
      setSiteId: (siteId) => {
        if (siteId) {
          localStorage.setItem('cv_site_id', siteId);
        } else {
          localStorage.removeItem('cv_site_id');
        }
        set({ siteId });
      },
    }),
    {
      name: 'cv-auth',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        orgId: state.orgId,
        siteId: state.siteId,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state) => {
        if (state?.token) {
          syncAuthSession(state.token, state.orgId);
        }
      },
    }
  )
);

if (typeof window !== 'undefined') {
  window.addEventListener('cv-token-refreshed', ((e: CustomEvent<string>) => {
    useAuthStore.setState({ token: e.detail });
  }) as EventListener);
}
