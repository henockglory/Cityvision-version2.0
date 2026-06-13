import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type {
  Alert,
  AuditEntry,
  Camera,
  DashboardSummary,
  DiscoveredDevice,
  Event,
  Rule,
  SetupResponse,
  SetupStatus,
  User,
} from '@/types';

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('cv_token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  const orgId = localStorage.getItem('cv_org_id');
  if (orgId && config.headers) {
    config.headers['X-Org-ID'] = orgId;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      const path = window.location.pathname;
      if (path !== '/login' && path !== '/setup') {
        localStorage.removeItem('cv_token');
        localStorage.removeItem('cv_org_id');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: { id: string; email: string; full_name: string };
}

export const setupApi = {
  status: () => api.get<SetupStatus>('/setup/status'),
  initialize: (orgName: string, adminEmail: string, adminPassword: string) =>
    api.post<SetupResponse>('/setup', {
      org_name: orgName,
      admin_email: adminEmail,
      admin_password: adminPassword,
    }),
};

export const authApi = {
  login: (email: string, password: string, totpCode?: string) =>
    api.post<LoginResponse>('/auth/login', {
      email,
      password,
      totp_code: totpCode ?? '',
    }),
  me: () =>
    api.get<{ user: LoginResponse['user']; role: string; org_id?: string }>('/auth/me'),
  logout: () => api.post('/auth/logout'),
};

export const camerasApi = {
  list: (orgId: string) => api.get<Camera[]>(`/orgs/${orgId}/cameras`),
  create: (
    orgId: string,
    body: {
      site_id: string;
      name: string;
      host: string;
      username: string;
      password: string;
      vendor?: string;
      port?: number;
    }
  ) => api.post<Camera>(`/orgs/${orgId}/cameras`, body),
  discover: (orgId: string, cidr: string) =>
    api.get<DiscoveredDevice[]>(`/orgs/${orgId}/cameras/discover`, { params: { cidr } }),
  testStream: (orgId: string, cameraId: string) =>
    api.post<{ reachable: boolean; error?: string }>(
      `/orgs/${orgId}/cameras/${cameraId}/stream/test`,
      {}
    ),
};

export const alertsApi = {
  list: (orgId: string) => api.get<Alert[]>(`/orgs/${orgId}/alerts`),
};

export const usersApi = {
  list: (orgId: string) => api.get<User[]>(`/orgs/${orgId}/users`),
};

export const eventsApi = {
  list: (orgId: string) => api.get<Event[]>(`/orgs/${orgId}/events`),
};

export const rulesApi = {
  list: (orgId: string) => api.get<Rule[]>(`/orgs/${orgId}/rules`),
};

export const dashboardApi = {
  summary: (orgId: string) => api.get<DashboardSummary>(`/orgs/${orgId}/dashboard/summary`),
};

export const auditApi = {
  list: (orgId: string) => api.get<AuditEntry[]>(`/orgs/${orgId}/audit`),
};

export const zonesApi = {
  list: (orgId: string) => api.get<unknown[]>(`/orgs/${orgId}/zones`),
};

export const healthApi = {
  ready: () => api.get<{ status?: string; checks?: Record<string, { status: string }> }>('/health/ready', { baseURL: '' }),
  live: () => api.get<{ status?: string }>('/health', { baseURL: '' }),
};
