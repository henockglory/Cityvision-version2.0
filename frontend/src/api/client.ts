import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type {
  AuditEntry,
  Camera,
  DashboardSummary,
  DiscoveredDevice,
  Event,
  Rule,
  SetupResponse,
  SetupStatus,
} from '@/types';
import { slugifyOrgName } from '@/utils/setup';
import {
  clearAuthSession,
  getAuthCredentials,
  getRefreshToken,
  syncAuthSession,
} from '@/lib/authSession';

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  try {
    const { data } = await axios.post<LoginResponse>('/api/v1/auth/refresh', {
      refresh_token: refresh,
    });
    const { orgId } = getAuthCredentials();
    syncAuthSession(data.access_token, orgId, data.refresh_token, data.expires_in);
    window.dispatchEvent(new CustomEvent('cv-token-refreshed', { detail: data.access_token }));
    return data.access_token;
  } catch {
    return null;
  }
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const { token, orgId } = getAuthCredentials();
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (orgId && config.headers) {
    config.headers['X-Org-ID'] = orgId;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      }
      const token = await refreshPromise;
      if (token && original.headers) {
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      }
    }
    if (error.response?.status === 401) {
      const path = window.location.pathname;
      clearAuthSession();
      if (path !== '/login' && path !== '/setup') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
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
    api.post<SetupResponse>('/setup/complete', {
      org_name: orgName,
      org_slug: slugifyOrgName(orgName),
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
  refresh: (refreshToken: string) =>
    api.post<LoginResponse>('/auth/refresh', { refresh_token: refreshToken }),
  me: () =>
    api.get<{ user: LoginResponse['user']; role: string; org_id?: string }>('/auth/me'),
  updateMe: (body: { full_name?: string; email?: string; password?: string; locale?: string }) =>
    api.patch<{ user: LoginResponse['user'] }>('/auth/me', body),
  setupTotp: () => api.post<{ secret: string; uri: string }>('/auth/totp/setup'),
  confirmTotp: (code: string) => api.post('/auth/totp/confirm', { code }),
  logout: () => api.post('/auth/logout'),
};

export const orgApi = {
  get: (orgId: string) => api.get<OrganizationSettings>(`/orgs/${orgId}`),
  update: (orgId: string, body: Partial<OrganizationSettings>) =>
    api.patch<OrganizationSettings>(`/orgs/${orgId}`, body),
  testSmtp: (orgId: string, to: string) =>
    api.post(`/orgs/${orgId}/integrations/smtp/test`, { to }),
  resetDemo: (orgId: string) => api.post(`/orgs/${orgId}/demo/reset`),
};

export interface OrganizationSettings {
  id: string;
  name: string;
  slug: string;
  timezone: string;
  logo_url?: string;
  notification_prefs?: Record<string, unknown>;
  security_prefs?: Record<string, unknown>;
  smtp_config?: {
    host?: string;
    port?: number;
    user?: string;
    password?: string;
    from_address?: string;
    use_tls?: boolean;
  };
}

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
      rtsp_path?: string;
      stream_profile?: string;
      channel?: number;
      metadata?: Record<string, unknown>;
    }
  ) => api.post<Camera>(`/orgs/${orgId}/cameras`, body),
  discover: (orgId: string, cidr: string) =>
    api.get<DiscoveredDevice[]>(`/orgs/${orgId}/cameras/discover`, { params: { cidr } }),
  probe: (
    orgId: string,
    body: { host: string; username: string; password: string; port?: number; vendor?: string }
  ) => api.post<{
    best?: { vendor: string; profile: string; rtsp_path?: string; ok: boolean; latency_ms?: number };
    candidates: unknown[];
  }>(
    `/orgs/${orgId}/cameras/probe`,
    body
  ),
  testStream: (orgId: string, cameraId: string) =>
    api.post<{ reachable: boolean; error?: string }>(
      `/orgs/${orgId}/cameras/${cameraId}/stream/test`,
      {}
    ),
  preview: (orgId: string, cameraId: string) =>
    api.get<{ preview_hls: string; preview_webrtc: string; name: string }>(
      `/orgs/${orgId}/cameras/${cameraId}/preview`
    ),
  update: (
    orgId: string,
    cameraId: string,
    body: { metadata?: Record<string, unknown>; name?: string; is_active?: boolean }
  ) => api.patch(`/orgs/${orgId}/cameras/${cameraId}`, body),
};

export const identityApi = {
  list: (orgId: string, listType?: string) =>
    api.get<SurveillanceList[]>(`/orgs/${orgId}/surveillance-lists`, {
      params: listType ? { list_type: listType } : undefined,
    }),
  create: (
    orgId: string,
    body: { name: string; list_type: string; entries?: unknown[] }
  ) => api.post<SurveillanceList>(`/orgs/${orgId}/surveillance-lists`, body),
  addEntry: (orgId: string, listId: string, entry: Record<string, unknown>) =>
    api.post<SurveillanceList>(`/orgs/${orgId}/surveillance-lists/${listId}/entries`, entry),
  delete: (orgId: string, listId: string) =>
    api.delete(`/orgs/${orgId}/surveillance-lists/${listId}`),
};

export interface SurveillanceList {
  id: string;
  name: string;
  list_type: 'face_watchlist' | 'plate_block' | 'plate_allow';
  entries: unknown[];
  is_active: boolean;
}

export const rulesApi = {
  list: (orgId: string) => api.get<Rule[]>(`/orgs/${orgId}/rules`),
  catalog: (orgId: string) => api.get<import('@/types').RuleCatalogTemplate[]>(`/orgs/${orgId}/rules/catalog`),
  create: (
    orgId: string,
    body: {
      name: string;
      definition: Record<string, unknown>;
      priority?: number;
      site_id?: string;
      description?: string;
    }
  ) => api.post<Rule>(`/orgs/${orgId}/rules`, body),
  disable: (orgId: string, ruleId: string) =>
    api.patch<Rule>(`/orgs/${orgId}/rules/${ruleId}`, { is_enabled: false }),
  enable: (orgId: string, ruleId: string) =>
    api.patch<Rule>(`/orgs/${orgId}/rules/${ruleId}`, { is_enabled: true }),
  update: (
    orgId: string,
    ruleId: string,
    body: {
      is_enabled?: boolean;
      name?: string;
      description?: string;
      definition?: Record<string, unknown>;
    },
  ) => api.patch<Rule>(`/orgs/${orgId}/rules/${ruleId}`, body),
  delete: (orgId: string, ruleId: string) =>
    api.delete(`/orgs/${orgId}/rules/${ruleId}`),
};

export const alertsApi = {
  list: (orgId: string, filters?: import('@/types').AlertFilters) => {
    const params: Record<string, string | number> = {};
    if (filters?.status) params.status = filters.status;
    if (filters?.severity) params.severity = filters.severity;
    if (filters?.ruleId) params.rule_id = filters.ruleId;
    if (filters?.cameraId) params.camera_id = filters.cameraId;
    if (filters?.from) params.from = filters.from;
    if (filters?.to) params.to = filters.to;
    if (filters?.limit) params.limit = filters.limit;
    if (filters?.includeIncomplete) params.include_incomplete = 'true';
    return api.get<import('@/types').Alert[]>(`/orgs/${orgId}/alerts`, {
      params: Object.keys(params).length ? params : undefined,
    });
  },
  archive: (orgId: string, alertId: string, body: { comment?: string; evidence_snapshot?: Record<string, unknown> }) =>
    api.patch<import('@/types').Alert>(`/orgs/${orgId}/alerts/${alertId}/archive`, body),
  forward: (
    orgId: string,
    alertId: string,
    body: { email?: string; webhook_url?: string; webhook_preset?: string },
  ) => api.post<{ status: string }>(`/orgs/${orgId}/alerts/${alertId}/forward`, body),
};

export interface RoutingRule {
  id: string;
  org_id: string;
  name: string;
  enabled: boolean;
  priority: number;
  match: Record<string, unknown>;
  channels: Record<string, unknown>;
}

export const routingApi = {
  list: (orgId: string) => api.get<RoutingRule[]>(`/orgs/${orgId}/routing-rules`),
  create: (
    orgId: string,
    body: { name: string; priority?: number; match: Record<string, unknown>; channels: Record<string, unknown> },
  ) => api.post<RoutingRule>(`/orgs/${orgId}/routing-rules`, body),
  update: (
    orgId: string,
    ruleId: string,
    body: Partial<{ name: string; enabled: boolean; priority: number; match: Record<string, unknown>; channels: Record<string, unknown> }>,
  ) => api.patch<RoutingRule>(`/orgs/${orgId}/routing-rules/${ruleId}`, body),
  delete: (orgId: string, ruleId: string) => api.delete(`/orgs/${orgId}/routing-rules/${ruleId}`),
  test: (
    orgId: string,
    body: { plate_number?: string; face_label?: string; event_type?: string; severity?: string },
  ) => api.post<{ matched: RoutingRule[]; count: number }>(`/orgs/${orgId}/routing-rules/test`, body),
};

export const usersApi = {
  list: (orgId: string) => api.get<BackendMember[]>(`/orgs/${orgId}/users`),
  create: (
    orgId: string,
    body: { email: string; full_name: string; password: string; role: string }
  ) => api.post<BackendMember>(`/orgs/${orgId}/users`, body),
  update: (
    orgId: string,
    userId: string,
    body: { role?: string; is_active?: boolean }
  ) => api.patch<BackendMember>(`/orgs/${orgId}/users/${userId}`, body),
};

export interface BackendMember {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

export const eventsApi = {
  list: (
    orgId: string,
    params?: { event_type?: string; camera_id?: string; rule_linked?: boolean; include_incomplete?: boolean },
  ) => api.get<Event[]>(`/orgs/${orgId}/events`, { params }),
};

export const dashboardApi = {
  summary: (orgId: string) => api.get<DashboardSummary>(`/orgs/${orgId}/dashboard/summary`),
};

export const auditApi = {
  list: (orgId: string, params?: { action?: string; limit?: number; offset?: number }) =>
    api.get<AuditEntry[]>(`/orgs/${orgId}/audit`, { params }),
  verify: (orgId: string) =>
    api.get<{ valid: boolean }>(`/orgs/${orgId}/audit/verify`),
};

export const zonesApi = {
  list: (orgId: string, cameraId?: string) =>
    api.get<BackendZone[]>(`/orgs/${orgId}/zones`, {
      params: cameraId ? { camera_id: cameraId } : undefined,
    }),
  create: (orgId: string, body: Record<string, unknown>) =>
    api.post(`/orgs/${orgId}/zones`, body),
  delete: (orgId: string, zoneId: string) =>
    api.delete(`/orgs/${orgId}/zones/${zoneId}`),
  createLine: (orgId: string, body: Record<string, unknown>) =>
    api.post(`/orgs/${orgId}/lines`, body),
  listLines: (orgId: string, cameraId?: string) =>
    api.get<BackendLine[]>(`/orgs/${orgId}/lines`, {
      params: cameraId ? { camera_id: cameraId } : undefined,
    }),
  deleteLine: (orgId: string, lineId: string) =>
    api.delete(`/orgs/${orgId}/lines/${lineId}`),
};

export interface BackendLine {
  id: string;
  name: string;
  camera_id?: string;
  start_point?: { x: number; y: number };
  end_point?: { x: number; y: number };
}

export interface BackendZone {
  id: string;
  name: string;
  polygon: { x: number; y: number }[];
  color?: string;
  camera_id?: string;
  zone_kind?: string;
}

export const healthApi = {
  ready: () =>
    api.get<{ status?: string; checks?: Record<string, { status: string }>; database?: string; redis?: string }>(
      '/health/ready',
      { baseURL: '' }
    ),
  live: () => api.get<{ status?: string }>('/health', { baseURL: '' }),
};

export const aiHealthApi = {
  health: () =>
    api.get<{
      status?: string;
      yolo_loaded?: string;
      yolo_provider?: string;
      yolo_cuda?: string;
      face_loaded?: string;
      plate_loaded?: string;
      ffmpeg_available?: string;
    }>('/ai-engine/health', { baseURL: '' }),
};

export interface SystemStatus {
  platform: string;
  service_registered: boolean;
  service_running: boolean;
  start_mode: string;
  service_name: string;
}

export interface SystemStreamEvent {
  event: string;
  message: string;
  ok?: boolean;
}

export type UninstallMode = 'restart' | 'soft' | 'standard' | 'full' | 'nuclear';

export const systemApi = {
  status: () => api.get<SystemStatus>('/system/status'),
  async *streamUninstall(mode: UninstallMode, signal?: AbortSignal): AsyncGenerator<SystemStreamEvent> {
    const { token } = getAuthCredentials();
    const res = await fetch(`/api/v1/system/uninstall/stream?mode=${mode}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal,
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const reader = res.body?.getReader();
    if (!reader) {
      throw new Error('streaming not supported');
    }
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() ?? '';
      for (const part of parts) {
        for (const line of part.split('\n')) {
          if (line.startsWith('data: ')) {
            yield JSON.parse(line.slice(6)) as SystemStreamEvent;
          }
        }
      }
    }
  },
};
