import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  camerasApi,
  alertsApi,
  eventsApi,
  rulesApi,
  usersApi,
  auditApi,
  healthApi,
  dashboardApi,
  setupApi,
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
import { useAuthStore } from '@/stores/authStore';
import type { DashboardSummary, SystemHealthMetric } from '@/types';

const STALE = 30_000;

function useOrgId(): string | null {
  return useAuthStore((s) => s.orgId);
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
};

export function useSetupStatus() {
  return useQuery({
    queryKey: queryKeys.setup,
    queryFn: async () => {
      const { data } = await setupApi.status();
      return data;
    },
    retry: 1,
    staleTime: 60_000,
  });
}

export function useInitializeSetup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: { orgName: string; adminEmail: string; adminPassword: string }) =>
      setupApi.initialize(params.orgName, params.adminEmail, params.adminPassword),
    onSuccess: () => {
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

export function useAlerts() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.alerts,
    queryFn: async () => {
      if (!orgId) throw new Error('No organization');
      const { data } = await alertsApi.list(orgId);
      return ensureArray(data).map((a) => mapAlert(a as Parameters<typeof mapAlert>[0]));
    },
    enabled: !!orgId,
  });
}

export function useEvents() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.events,
    queryFn: async () => {
      if (!orgId) throw new Error('No organization');
      const { data } = await eventsApi.list(orgId);
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

export function useAudit() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.audit,
    queryFn: async () => {
      if (!orgId) throw new Error('No organization');
      const { data } = await auditApi.list(orgId);
      return ensureArray(data).map((a) => mapAudit(a as Parameters<typeof mapAudit>[0]));
    },
    enabled: !!orgId,
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

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: async (): Promise<SystemHealthMetric[]> => {
      const { data } = await healthApi.ready();
      const checks = data.checks ?? {};
      return Object.entries(checks).map(([name, check]) => ({
        name,
        status: check.status === 'ok' ? 'healthy' as const : check.status === 'degraded' ? 'warning' as const : 'critical' as const,
        value: check.status,
      }));
    },
    staleTime: STALE,
    refetchInterval: 60_000,
  });
}
