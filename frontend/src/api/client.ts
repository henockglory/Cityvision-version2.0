import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
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
      localStorage.removeItem('cv_token');
      localStorage.removeItem('cv_org_id');
      if (window.location.pathname !== '/login') {
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
  user: {
    id: string;
    email: string;
    full_name: string;
  };
}

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
  list: (orgId: string) =>
    api.get<import('@/types').Camera[]>(`/orgs/${orgId}/cameras`),
  discover: (orgId: string, cidr?: string) =>
    api.get<{ devices: { ip: string; vendor?: string; model?: string }[] }>(
      `/orgs/${orgId}/cameras/discover`,
      { params: cidr ? { cidr } : undefined }
    ),
  testStream: (
    orgId: string,
    cameraId: string,
    body?: { username?: string; password?: string }
  ) => api.post(`/orgs/${orgId}/cameras/${cameraId}/stream/test`, body ?? {}),
};

export const alertsApi = {
  list: (orgId: string) => api.get<import('@/types').Alert[]>(`/orgs/${orgId}/alerts`),
  acknowledge: (orgId: string, id: string) =>
    api.patch(`/orgs/${orgId}/alerts/${id}`, { acknowledged: true }),
};

export const usersApi = {
  list: (orgId: string) => api.get<import('@/types').User[]>(`/orgs/${orgId}/users`),
};

export const eventsApi = {
  list: (orgId: string, params?: { from?: string; to?: string }) =>
    api.get<import('@/types').Event[]>(`/orgs/${orgId}/events`, { params }),
};

export const rulesApi = {
  list: (orgId: string) => api.get<import('@/types').Rule[]>(`/orgs/${orgId}/rules`),
};

export const dashboardApi = {
  summary: (orgId: string) => api.get(`/orgs/${orgId}/dashboard/summary`),
};

export const auditApi = {
  list: (orgId: string) => api.get<import('@/types').AuditEntry[]>(`/orgs/${orgId}/audit`),
};

export const healthApi = {
  status: () => api.get('/health'),
};
