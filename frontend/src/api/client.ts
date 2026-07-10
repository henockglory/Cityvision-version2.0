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
import { isTransientApiError } from '@/lib/apiErrors';

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

let refreshPromise: Promise<RefreshResult> | null = null;

type RefreshResult = { token: string | null; authFailed: boolean };

async function refreshAccessToken(): Promise<RefreshResult> {
  const refresh = getRefreshToken();
  if (!refresh) return { token: null, authFailed: true };
  try {
    const { data } = await axios.post<LoginResponse>('/api/v1/auth/refresh', {
      refresh_token: refresh,
    });
    const { orgId } = getAuthCredentials();
    syncAuthSession(data.access_token, orgId, data.refresh_token, data.expires_in);
    window.dispatchEvent(new CustomEvent('cv-token-refreshed', { detail: data.access_token }));
    return { token: data.access_token, authFailed: false };
  } catch (err) {
    const authFailed =
      axios.isAxiosError(err) &&
      err.response != null &&
      (err.response.status === 401 || err.response.status === 403);
    return { token: null, authFailed };
  }
}

/** Single-flight refresh used by the interceptor and proactive refresh hook. */
export function refreshSession(): Promise<RefreshResult> {
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

function logoutToLogin() {
  const path = window.location.pathname;
  clearAuthSession();
  if (path !== '/login' && path !== '/setup') {
    window.location.href = '/login';
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
    // Backend restart / proxy blip — never treat as logout.
    if (isTransientApiError(error)) {
      return Promise.reject(error);
    }

    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      const { token, authFailed } = await refreshSession();
      if (token && original.headers) {
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      }
      if (authFailed) {
        logoutToLogin();
      }
      return Promise.reject(error);
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
    api.get<{ user: LoginResponse['user']; role: string; org_id?: string; site_id?: string }>('/auth/me'),
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

export interface IntegrationPreset {
  id: string;
  label: string;
  category: 'automation' | 'chat' | string;
  description: string;
  docs_url: string;
}

export interface DeliveryLogEntry {
  timestamp?: string;
  alert_id?: string;
  alert_title?: string;
  channels?: string[];
  webhook_url?: string;
  webhook_preset?: string;
  webhook_error?: string;
  email?: string;
  source?: string;
  routing_rule_name?: string;
  [k: string]: unknown;
}

export const integrationsApi = {
  presets: (orgId: string) =>
    api.get<{ presets: IntegrationPreset[]; signing_enabled: boolean }>(
      `/orgs/${orgId}/integrations/presets`,
    ),
  testWebhook: (orgId: string, body: { url: string; preset?: string }) =>
    api.post<{ ok: boolean; error?: string }>(
      `/orgs/${orgId}/integrations/webhook/test`,
      body,
    ),
  deliveryLog: (orgId: string, limit = 100) =>
    api.get<{ entries: DeliveryLogEntry[] }>(
      `/orgs/${orgId}/integrations/delivery-log`,
      { params: { limit } },
    ),
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
    api.get<DiscoveredDevice[]>(`/orgs/${orgId}/cameras/discover`, {
      params: { cidr: cidr.trim() },
      timeout: 90_000,
    }),
  probe: (
    orgId: string,
    body: { host: string; username: string; password: string; port?: number; vendor?: string }
  ) => api.post<{
    best?: { vendor: string; profile: string; rtsp_path?: string; ok: boolean; latency_ms?: number };
    candidates: unknown[];
  }>(
    `/orgs/${orgId}/cameras/probe`,
    body,
    { timeout: 60_000 },
  ),
  testStream: (orgId: string, cameraId: string) =>
    api.post<{ reachable: boolean; video_ok?: boolean; error?: string }>(
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
    body: {
      metadata?: Record<string, unknown>;
      name?: string;
      is_active?: boolean;
      host?: string;
      port?: number;
      channel?: number;
      username?: string;
      password?: string;
      vendor?: string;
      rtsp_path?: string;
      stream_profile?: string;
    }
  ) => api.patch<Camera>(`/orgs/${orgId}/cameras/${cameraId}`, body),
  delete: (orgId: string, cameraId: string) =>
    api.delete<{ deleted: boolean; id: string }>(`/orgs/${orgId}/cameras/${cameraId}`, {
      timeout: 20_000,
    }),
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

export interface CapabilitiesBehaviorMenuItem {
  id: string;
  group: string;
  applies_to: string;
  label_fr: string;
  label_en: string;
  capability: string;
  human_description_fr: string;
  emits: string[];
  requires: string[];
  config_fields?: Record<string, unknown>;
  ready: boolean;
  ready_reason_fr?: string;
  compatible_templates?: string[];
  observation_capable?: boolean;
}

export interface CapabilitiesMenuResponse {
  behaviors: CapabilitiesBehaviorMenuItem[];
  health: Record<string, string>;
}

export interface SceneIntentValidation {
  valid: boolean;
  errors?: string[];
  warnings?: string[];
}

export const capabilitiesApi = {
  menu: (orgId: string) =>
    api.get<CapabilitiesMenuResponse>(`/orgs/${orgId}/capabilities/menu`),
  validateIntent: (orgId: string, definition: Record<string, unknown>) =>
    api.post<SceneIntentValidation>(`/orgs/${orgId}/scene-intent/validate`, { definition }),
};

export interface ModelPackEntry {
  id: string;
  health_key: string;
  kind: string;
  required: boolean;
  label_fr: string;
  label_en: string;
  behavior?: string;
  event_type?: string;
  file?: string;
  loaded: boolean;
  notes?: string;
}

export interface ModelPackResponse {
  version: number;
  install_command: string;
  verify_command: string;
  gpu_health_key?: string;
  gpu_loaded: boolean;
  models: ModelPackEntry[];
  health: Record<string, string>;
}

export const modelPackApi = {
  get: (orgId: string) => api.get<ModelPackResponse>(`/orgs/${orgId}/ai/model-pack`),
};

export interface OrgModelRow {
  id: string;
  task: string;
  file: string;
  classes: string[];
  positive_classes: string[];
  behavior: string;
  event_type: string;
  label_fr: string;
  label_en?: string;
  applies_to?: string;
  input_source?: string;
  input_size?: number;
  capability?: string;
  human_description_fr?: string;
  probe_ok: boolean;
  health_key: string;
  loaded: boolean;
  rule_template_id: string;
}

export interface OrgModelsListResponse {
  models: OrgModelRow[];
  health: Record<string, string>;
}

export interface UploadOrgModelResponse {
  id: string;
  sha256: string;
  file: string;
  probe_ok: boolean;
  health_key: string;
  behavior: string;
  event_type: string;
  rule_template_id: string;
  applies_to: string;
  input_source: string;
  label_fr: string;
  label_en: string;
  ai_reload_ok: boolean;
  ai_reload_message?: string;
}

export interface ModelUploadPayload {
  id: string;
  task: 'classification' | 'detection';
  event_type: string;
  label_fr: string;
  label_en: string;
  human_description_fr: string;
  human_description_en?: string;
  applies_to: 'zone' | 'line' | 'both';
  input_source: 'crop_vehicle' | 'crop_zone' | 'full_frame';
  input_size: number;
  capability: string;
  behavior?: string;
  classes: string[];
  positive_classes: string[];
  file?: File;
  download_url?: string;
}

export const orgModelsApi = {
  list: (orgId: string) => api.get<OrgModelsListResponse>(`/orgs/${orgId}/ai/models`),
  upload: (orgId: string, payload: ModelUploadPayload) => {
    const form = new FormData();
    form.append('id', payload.id);
    form.append('task', payload.task);
    form.append('event_type', payload.event_type);
    form.append('label_fr', payload.label_fr);
    form.append('label_en', payload.label_en);
    form.append('human_description_fr', payload.human_description_fr);
    if (payload.human_description_en) form.append('human_description_en', payload.human_description_en);
    form.append('applies_to', payload.applies_to);
    form.append('input_source', payload.input_source);
    form.append('input_size', String(payload.input_size));
    form.append('capability', payload.capability);
    if (payload.behavior) form.append('behavior', payload.behavior);
    form.append('classes', JSON.stringify(payload.classes));
    form.append('positive_classes', JSON.stringify(payload.positive_classes));
    if (payload.file) form.append('model', payload.file);
    if (payload.download_url) form.append('download_url', payload.download_url);
    return api.post<UploadOrgModelResponse>(`/orgs/${orgId}/ai/models`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 600_000,
    });
  },
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
  update: (
    orgId: string,
    zoneId: string,
    body: {
      name?: string;
      zone_kind?: string;
      behavior_config?: Record<string, unknown>;
      polygon?: { x: number; y: number; distance_to_next_m?: number }[];
    },
  ) => api.patch<BackendZone>(`/orgs/${orgId}/zones/${zoneId}`, body),
  delete: (orgId: string, zoneId: string) =>
    api.delete(`/orgs/${orgId}/zones/${zoneId}`),
  createLine: (orgId: string, body: Record<string, unknown>) =>
    api.post(`/orgs/${orgId}/lines`, body),
  listLines: (orgId: string, cameraId?: string) =>
    api.get<BackendLine[]>(`/orgs/${orgId}/lines`, {
      params: cameraId ? { camera_id: cameraId } : undefined,
    }),
  updateLine: (orgId: string, lineId: string, body: {
    name?: string;
    behavior_config?: { behavior?: string; config?: Record<string, unknown> };
  }) =>
    api.patch<BackendLine>(`/orgs/${orgId}/lines/${lineId}`, body),
  deleteLine: (orgId: string, lineId: string) =>
    api.delete(`/orgs/${orgId}/lines/${lineId}`),
  lineCounters: (orgId: string, cameraId?: string) =>
    api.get<LineCounter[]>(`/orgs/${orgId}/lines/counters`, {
      params: cameraId ? { camera_id: cameraId } : undefined,
    }),
  resetLineCounters: (orgId: string, cameraId?: string) =>
    api.delete(`/orgs/${orgId}/lines/counters`, {
      params: cameraId ? { camera_id: cameraId } : undefined,
    }),
};

export interface ObservationCounter {
  id: string;
  kind: string;
  label_fr: string;
  label_en: string;
  legend_fr: string;
  legend_en: string;
  count: number;
  count_in?: number;
  count_out?: number;
  last_class?: string;
  scope?: Record<string, string>;
  source_rule_id?: string;
  updated_at: string;
}

export const observationApi = {
  listCounters: (orgId: string, cameraId?: string) =>
    api.get<ObservationCounter[]>(`/orgs/${orgId}/observations/counters`, {
      params: cameraId ? { camera_id: cameraId } : undefined,
    }),
  resetCounters: (orgId: string, opts?: { cameraId?: string; kind?: string; id?: string }) =>
    api.delete(`/orgs/${orgId}/observations/counters`, {
      params: {
        ...(opts?.cameraId ? { camera_id: opts.cameraId } : {}),
        ...(opts?.kind ? { kind: opts.kind } : {}),
        ...(opts?.id ? { id: opts.id } : {}),
      },
    }),
};

export interface LineCounter {
  line_id: string;
  class_filter?: string;
  camera_id?: string;
  count_in: number;
  count_out: number;
  count_total: number;
  last_class: string;
  updated_at: string;
}

export interface BackendLine {
  id: string;
  name: string;
  camera_id?: string;
  start_point?: { x: number; y: number };
  end_point?: { x: number; y: number };
  behavior_config?: { behavior?: string; config?: Record<string, unknown> };
}

export interface BackendZone {
  id: string;
  name: string;
  polygon: { x: number; y: number; distance_to_next_m?: number }[];
  color?: string;
  camera_id?: string;
  zone_kind?: string;
  behavior_config?: { behavior?: string; config?: Record<string, unknown> };
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
  app_running: boolean;
  service_state?: string;
  service_account?: string;
  service_needs_repair: boolean;
  start_mode: string;
  start_mode_effective?: string;
  service_name: string;
}

export interface SetStartModeResult {
  ok: boolean;
  start_mode: string;
  start_mode_effective: string;
  service_registered: boolean;
  message: string;
}

export interface SystemStreamEvent {
  event: string;
  message: string;
  ok?: boolean;
}

export type UninstallMode = 'restart' | 'soft' | 'standard' | 'full' | 'nuclear';

export interface DemoVideo {
  id: string;
  org_id: string;
  name: string;
  status: 'uploading' | 'processing' | 'ready' | 'failed';
  progress: number;
  go2rtc_src?: string;
  size_bytes: number;
  duration_sec?: number;
  error_message?: string;
  created_at: string;
}

export interface DemoSettings {
  context_label: string;
  title: string;
  subtitle: string;
  nav_label: string;
  source_mode: 'video' | 'camera';
  active_video_id?: string;
  active_camera_id?: string;
  active_go2rtc_src?: string;
  videos: DemoVideo[];
}

export const demoApi = {
  getSettings: (orgId: string) => api.get<DemoSettings>(`/orgs/${orgId}/demo/settings`),
  patchSettings: (orgId: string, body: Partial<{
    context_label: string;
    title: string;
    subtitle: string;
    nav_label: string;
    source_mode: string;
    active_video_id: string | null;
    active_camera_id: string | null;
  }>) => api.patch<DemoSettings>(`/orgs/${orgId}/demo/settings`, body),
  uploadVideo: (orgId: string, file: File, name?: string, onProgress?: (pct: number) => void) => {
    const fd = new FormData();
    fd.append('video', file);
    if (name) fd.append('name', name);
    return api.post<DemoVideo>(`/orgs/${orgId}/demo/videos`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 3_000_000,
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          onProgress(Math.round((e.loaded / e.total) * 30));
        }
      },
    });
  },
  getVideoStatus: (orgId: string, videoId: string) =>
    api.get<DemoVideo>(`/orgs/${orgId}/demo/videos/${videoId}/status`),
  renameVideo: (orgId: string, videoId: string, name: string) =>
    api.patch<DemoVideo>(`/orgs/${orgId}/demo/videos/${videoId}`, { name }),
  deleteVideo: (orgId: string, videoId: string) =>
    api.delete(`/orgs/${orgId}/demo/videos/${videoId}`),
  retryVideo: (orgId: string, videoId: string) =>
    api.post<DemoVideo>(`/orgs/${orgId}/demo/videos/${videoId}/retry`),
  reset: (orgId: string) => api.post(`/orgs/${orgId}/demo/reset`),
};

export const systemApi = {
  status: () => api.get<SystemStatus>('/system/status'),
  setStartMode: (mode: 'auto' | 'manual') =>
    api.put<SetStartModeResult>('/system/start-mode', { mode }),
  serviceAction: (action: 'start' | 'stop') =>
    api.post<SetStartModeResult>('/system/service-action', { action }),
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
