import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, UserRole } from '@/types';
import { authApi } from '@/api/client';

interface AuthStore {
  user: User | null;
  token: string | null;
  orgId: string | null;
  siteId: string | null;
  isAuthenticated: boolean;
  login: (user: User, token: string, orgId?: string | null) => void;
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

export async function apiLogin(
  email: string,
  password: string
): Promise<{ user: User; token: string; orgId: string | null }> {
  const { data } = await authApi.login(email, password);
  localStorage.setItem('cv_token', data.access_token);
  const me = await authApi.me();
  const role = mapBackendRole(me.data.role);
  const orgId = me.data.org_id ?? null;
  if (orgId) {
    localStorage.setItem('cv_org_id', orgId);
  }
  const user: User = {
    id: data.user.id,
    username: data.user.email.split('@')[0],
    email: data.user.email,
    role,
  };
  return { user, token: data.access_token, orgId };
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      orgId: null,
      siteId: localStorage.getItem('cv_site_id'),
      isAuthenticated: false,
      login: (user, token, orgId = null) => {
        localStorage.setItem('cv_token', token);
        if (orgId) {
          localStorage.setItem('cv_org_id', orgId);
        }
        set({ user, token, orgId, isAuthenticated: true });
      },
      logout: () => {
        localStorage.removeItem('cv_token');
        localStorage.removeItem('cv_org_id');
        set({ user: null, token: null, orgId: null, isAuthenticated: false });
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
    }
  )
);
