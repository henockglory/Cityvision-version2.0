import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  camerasApi,
  alertsApi,
  eventsApi,
  rulesApi,
  usersApi,
  auditApi,
  healthApi,
} from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import {
  mockAlerts,
  mockAudit,
  mockCameras,
  mockEvents,
  mockHealth,
  mockRules,
  mockUsers,
} from '@/data/mock';
import type { SystemHealthMetric } from '@/types';

const STALE = 30_000;

async function withMockFallback<T>(apiCall: () => Promise<{ data: T }>, mock: T): Promise<T> {
  try {
    const { data } = await apiCall();
    return data;
  } catch {
    return mock;
  }
}

function useOrgId(): string {
  return useAuthStore((s) => s.orgId) ?? 'demo-org';
}

export const queryKeys = {
  cameras: ['cameras'] as const,
  alerts: ['alerts'] as const,
  events: ['events'] as const,
  rules: ['rules'] as const,
  users: ['users'] as const,
  audit: ['audit'] as const,
  health: ['health'] as const,
};

export function useCameras() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.cameras,
    queryFn: () => withMockFallback(() => camerasApi.list(orgId), mockCameras),
  });
}

export function useAlerts() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.alerts,
    queryFn: () => withMockFallback(() => alertsApi.list(orgId), mockAlerts),
  });
}

export function useAcknowledgeAlert() {
  const orgId = useOrgId();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => alertsApi.acknowledge(orgId, id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: queryKeys.alerts });
      const prev = qc.getQueryData<typeof mockAlerts>(queryKeys.alerts);
      qc.setQueryData(queryKeys.alerts, (old: typeof mockAlerts | undefined) =>
        old?.map((a) => (a.id === id ? { ...a, acknowledged: true } : a)) ?? prev
      );
      return { prev };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(queryKeys.alerts, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: queryKeys.alerts }),
  });
}

export function useEvents() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.events,
    queryFn: () => withMockFallback(() => eventsApi.list(orgId), mockEvents),
  });
}

export function useRules() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.rules,
    queryFn: () => withMockFallback(() => rulesApi.list(orgId), mockRules),
  });
}

export function useUsers() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.users,
    queryFn: () => withMockFallback(() => usersApi.list(orgId), mockUsers),
  });
}

export function useAudit() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: queryKeys.audit,
    queryFn: () => withMockFallback(() => auditApi.list(orgId), mockAudit),
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: async (): Promise<SystemHealthMetric[]> => {
      try {
        await healthApi.status();
        return mockHealth;
      } catch {
        return mockHealth;
      }
    },
    staleTime: STALE,
    refetchInterval: 60_000,
  });
}
