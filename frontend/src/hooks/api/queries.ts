import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  camerasApi,
  alertsApi,
  eventsApi,
  rulesApi,
  usersApi,
  auditApi,
  healthApi,
  aiHealthApi,
  dashboardApi,
  setupApi,
  demoApi,
} from '@/api/client';
import {
  mapCamera,
  mapAlert,
  mapEvent,
  mapRule,
  mapAudit,
  mapUser,
  ensureArray,
} from '@/api/mappers';
import { useAuthStore, getAuthCredentials } from '@/stores/authStore';
import type { AlertFilters, DashboardSummary, SystemHealthMetric } from '@/types';
import { isAuthError } from '@/lib/apiErrors';

const STALE = 30_000;

function resolveOrgId(): string | null {
  return useAuthStore.getState().orgId ?? getAuthCredentials().orgId;
}

function useOrgId(): string | null {
  const storeOrg = useAuthStore((s) => s.orgId);
  if (storeOrg) return storeOrg;
  return getAuthCredentials().orgId;
}

export const queryKeys = {
  setup: ['setup', 'status'] as const,
  cameras: ['cameras'] as const,
  alerts: ['alerts'] as const,
  events: ['events'] as const,
  rules: ['rules'] as const,
  users: ['users'] as const,
  audit: ['audit'] as const,
  health: ['health'] as const,
  dashboard: ['dashboard'] as const,
  demoSettings: ['demo', 'settings'] as const,
};

export function useSetupStatus() {
  return useQuery({
    queryKey: queryKeys.setup,
    queryFn: async () => {
      const { data } = await setupApi.status();
      if (data.initialized) {
        localStorage.setItem('cv_setup_initialized', '1');
      }
      return data;
    },
    retry: (failureCount, error) => {
      if (isAuthError(error)) return false;
      return failureCount < 3;
    },
    retryDelay: (attempt) => Math.min(500 * 2 ** attempt, 5_000),
    staleTime: 60_000,
    networkMode: 'always',
  });
}

export function useInitializeSetup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: { orgName: string; adminEmail: string; adminPassword: string }) =>
      setupApi.initialize(params.orgName, params.adminEmail, params.adminPassword),
    onSuccess: () => {
      localStorage.setItem('cv_setup_initialized', '1');
      void qc.invalidateQueries({ queryKey: queryKeys.setup });
    },
  });
}

export function useCameras() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.cameras,
    queryFn: async () => {
      if (!orgId) throw new Error('No organization');
      const { data } = await camerasApi.list(orgId);
      return ensureArray(data).map((c) => mapCamera(c as unknown as Parameters<typeof mapCamera>[0]));
    },
    enabled: !!orgId,
  });
}

export function useCreateCamera() {
  const orgId = useOrgId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof camerasApi.create>[1]) => {
      if (!orgId) throw new Error('No organization');
      return camerasApi.create(orgId, body);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.cameras });
    },
  });
}

export function useDeleteCamera() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (cameraId: string) => {
      const orgId = resolveOrgId();
      if (!orgId) throw new Error('No organization');
      const { data } = await camerasApi.delete(orgId, cameraId);
      return data;
    },
    onSuccess: (_data, cameraId) => {
      qc.setQueryData(queryKeys.cameras, (old: ReturnType<typeof mapCamera>[] | undefined) =>
        old ? old.filter((c) => c.id !== cameraId) : old,
      );
      void qc.invalidateQueries({ queryKey: queryKeys.cameras });
    },
  });
}

export function useUpdateCamera() {
  const orgId = useOrgId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      cameraId,
      body,
    }: {
      cameraId: string;
      body: Parameters<typeof camerasApi.update>[2];
    }) => {
      if (!orgId) throw new Error('No organization');
      return camerasApi.update(orgId, cameraId, body);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.cameras });
    },
  });
}

export function useDiscoverCameras() {
  const orgId = useOrgId();
  return useMutation({
    mutationFn: (cidr: string) => {
      if (!orgId) throw new Error('No organization');
      return camerasApi.discover(orgId, cidr);
    },
  });
}

export function useTestCameraStream() {
  const orgId = useOrgId();
  return useMutation({
    mutationFn: (cameraId: string) => {
      if (!orgId) throw new Error('No organization');
      return camerasApi.testStream(orgId, cameraId);
    },
  });
}

export function useProbeCamera() {
  const orgId = useOrgId();
  return useMutation({
    mutationFn: (body: Parameters<typeof camerasApi.probe>[1]) => {
      if (!orgId) throw new Error('No organization');
      return camerasApi.probe(orgId, body);
    },
  });
}

export function useCameraPreview() {
  const orgId = useOrgId();
  return useMutation({
    mutationFn: (cameraId: string) => {
      if (!orgId) throw new Error('No organization');
      return camerasApi.preview(orgId, cameraId);
    },
  });
}

export function useAlerts(filters: AlertFilters | string = 'open') {
  const orgId = useOrgId();
  const resolved: AlertFilters = typeof filters === 'string'
    ? (filters === 'all' ? {} : { status: filters })
    : filters;
  const key = JSON.stringify(resolved);
  return useQuery({
    queryKey: [...queryKeys.alerts, key] as const,
    queryFn: async () => {
      if (!orgId) throw new Error('No organization');
      const { data } = await alertsApi.list(orgId, resolved);
      return ensureArray(data).map((a) => mapAlert(a as Parameters<typeof mapAlert>[0]));
    },
    enabled: !!orgId,
  });
}

export function useEvents(filters?: { eventType?: string; cameraId?: string; ruleLinked?: boolean; showAll?: boolean }) {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...queryKeys.events, filters?.eventType ?? '', filters?.cameraId ?? '', filters?.ruleLinked ?? '', filters?.showAll ?? ''] as const,
    queryFn: async () => {
      if (!orgId) throw new Error('No organization');
      const { data } = await eventsApi.list(orgId, {
        event_type: filters?.eventType,
        camera_id: filters?.cameraId,
        rule_linked: filters?.showAll ? undefined : true,
        include_incomplete: filters?.showAll ? true : undefined,
      });
      return ensureArray(data).map((e) => mapEvent(e as Parameters<typeof mapEvent>[0]));
    },
    enabled: !!orgId,
  });
}

export function useRules() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.rules,
    queryFn: async () => {
      if (!orgId) throw new Error('No organization');
      const { data } = await rulesApi.list(orgId);
      return ensureArray(data).map((r) => mapRule(r as Parameters<typeof mapRule>[0]));
    },
    enabled: !!orgId,
  });
}

export function useRuleCatalog() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...queryKeys.rules, 'catalog'] as const,
    queryFn: async () => {
      if (!orgId) throw new Error('No organization');
      const { data } = await rulesApi.catalog(orgId);
      return ensureArray(data);
    },
    enabled: !!orgId,
  });
}

export function useArchiveAlert() {
  const orgId = useOrgId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      alertId,
      comment,
      evidenceSnapshot,
    }: {
      alertId: string;
      comment?: string;
      evidenceSnapshot?: Record<string, unknown>;
    }) => {
      if (!orgId) throw new Error('No organization');
      return alertsApi.archive(orgId, alertId, {
        comment,
        evidence_snapshot: evidenceSnapshot,
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.alerts });
    },
  });
}

/** @deprecated use useArchiveAlert */
export const useAcknowledgeAlert = useArchiveAlert;

export function useUsers() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.users,
    queryFn: async () => {
      if (!orgId) throw new Error('No organization');
      const { data } = await usersApi.list(orgId);
      return ensureArray(data).map((u) => mapUser(u as Parameters<typeof mapUser>[0]));
    },
    enabled: !!orgId,
  });
}

export function useAudit(actionFilter?: string) {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...queryKeys.audit, actionFilter ?? ''] as const,
    queryFn: async () => {
      if (!orgId) throw new Error('No organization');
      const { data } = await auditApi.list(orgId, actionFilter ? { action: actionFilter } : undefined);
      return ensureArray(data).map((a) => mapAudit(a as Parameters<typeof mapAudit>[0]));
    },
    enabled: !!orgId,
  });
}

export function useVerifyAuditChain() {
  const orgId = useOrgId();
  return useMutation({
    mutationFn: () => {
      if (!orgId) throw new Error('No organization');
      return auditApi.verify(orgId);
    },
  });
}

export function useCreateUser() {
  const orgId = useOrgId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; full_name: string; password: string; role: string }) => {
      if (!orgId) throw new Error('No organization');
      return usersApi.create(orgId, body);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.users }),
  });
}

export function useUpdateUser() {
  const orgId = useOrgId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      userId,
      body,
    }: {
      userId: string;
      body: { role?: string; is_active?: boolean };
    }) => {
      if (!orgId) throw new Error('No organization');
      return usersApi.update(orgId, userId, body);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.users }),
  });
}

export function useUpdateCameraMap() {
  const orgId = useOrgId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      cameraId,
      metadata,
    }: {
      cameraId: string;
      metadata: Record<string, unknown>;
    }) => {
      if (!orgId) throw new Error('No organization');
      return camerasApi.update(orgId, cameraId, { metadata });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.cameras }),
  });
}

export function useDashboardSummary() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: async () => {
      if (!orgId) throw new Error('No organization');
      const { data } = await dashboardApi.summary(orgId);
      return data as DashboardSummary;
    },
    enabled: !!orgId,
  });
}

export interface AiModelStatus {
  yolo: boolean;
  face: boolean;
  plate: boolean;
  provider: string;
  cuda: boolean;
  ffmpeg: boolean;
  reachable: boolean;
}

export function useAiHealth() {
  return useQuery({
    queryKey: ['ai-health'],
    queryFn: async (): Promise<AiModelStatus> => {
      try {
        const { data } = await aiHealthApi.health();
        return {
          yolo: data.yolo_loaded === 'true',
          face: data.face_loaded === 'true',
          plate: data.plate_loaded === 'true',
          provider: data.yolo_provider ?? 'unknown',
          cuda: data.yolo_cuda === 'true',
          ffmpeg: data.ffmpeg_available === 'true',
          reachable: true,
        };
      } catch {
        return { yolo: false, face: false, plate: false, provider: 'unknown', cuda: false, ffmpeg: false, reachable: false };
      }
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: async (): Promise<SystemHealthMetric[]> => {
      const { data } = await healthApi.ready();
      if (data.checks && Object.keys(data.checks).length > 0) {
        return Object.entries(data.checks).map(([name, check]) => ({
          name,
          status:
            check.status === 'ok'
              ? ('healthy' as const)
              : check.status === 'degraded'
                ? ('warning' as const)
                : ('critical' as const),
          value: check.status,
        }));
      }
      const metrics: SystemHealthMetric[] = [];
      if (data.status) {
        metrics.push({
          name: 'API',
          status: data.status === 'ok' ? 'healthy' : 'warning',
          value: data.status,
        });
      }
      if (data.database) {
        metrics.push({
          name: 'PostgreSQL',
          status: data.database === 'ok' ? 'healthy' : 'critical',
          value: data.database,
        });
      }
      if (data.redis) {
        metrics.push({
          name: 'Redis',
          status: data.redis === 'ok' ? 'healthy' : 'critical',
          value: data.redis,
        });
      }
      return metrics;
    },
    staleTime: STALE,
    refetchInterval: 60_000,
  });
}

export function useDemoSettings() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.demoSettings,
    queryFn: async () => {
      if (!orgId) throw new Error('No organization');
      const { data } = await demoApi.getSettings(orgId);
      return data;
    },
    enabled: !!orgId,
    staleTime: 0,
    refetchInterval: (query) => {
      const videos = query.state.data?.videos ?? [];
      const processing = videos.some((v) => v.status === 'uploading' || v.status === 'processing');
      return processing ? 2_000 : 15_000;
    },
  });
}
