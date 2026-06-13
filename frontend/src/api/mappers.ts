import type { Alert, AuditEntry, Camera, Event, Rule, User } from '@/types';
import { mapBackendRole } from '@/stores/authStore';

interface BackendCamera {
  id: string;
  name: string;
  host: string;
  status?: string;
  vendor?: string;
  site_id?: string;
  is_active?: boolean;
}

interface BackendAlert {
  id: string;
  type?: string;
  severity?: string;
  camera_id?: string;
  camera_name?: string;
  message?: string;
  title?: string;
  created_at?: string;
  status?: string;
}

interface BackendEvent {
  id: string;
  event_type?: string;
  type?: string;
  camera_id?: string;
  camera_name?: string;
  description?: string;
  payload?: { description?: string };
  occurred_at?: string;
  created_at?: string;
}

interface BackendRule {
  id: string;
  name: string;
  is_enabled?: boolean;
  enabled?: boolean;
  camera_ids?: string[];
  definition?: { conditions?: Rule['conditions']; actions?: Rule['actions'] };
}

interface BackendAudit {
  id: string;
  user_id?: string;
  action: string;
  resource_type?: string;
  resource_id?: string;
  created_at?: string;
  ip_address?: string;
  user_email?: string;
}

interface BackendUser {
  id: string;
  email: string;
  full_name?: string;
  role?: string;
  last_login_at?: string;
}

function mapCameraStatus(status?: string, isActive?: boolean): Camera['status'] {
  if (status === 'online' || status === 'recording') return status;
  if (status === 'offline') return 'offline';
  return isActive === false ? 'offline' : 'online';
}

export function mapCamera(raw: BackendCamera): Camera {
  return {
    id: raw.id,
    name: raw.name,
    ip: raw.host,
    status: mapCameraStatus(raw.status, raw.is_active),
    location: raw.site_id ?? '—',
    model: raw.vendor,
  };
}

export function mapAlert(raw: BackendAlert): Alert {
  const severity = (raw.severity ?? 'medium') as Alert['severity'];
  const type = (raw.type ?? 'system') as Alert['type'];
  return {
    id: raw.id,
    type,
    severity,
    cameraId: raw.camera_id ?? '',
    cameraName: raw.camera_name ?? '—',
    message: raw.message ?? raw.title ?? '—',
    timestamp: raw.created_at ?? new Date().toISOString(),
    acknowledged: raw.status !== 'open',
  };
}

export function mapEvent(raw: BackendEvent): Event {
  return {
    id: raw.id,
    type: raw.event_type ?? raw.type ?? 'event',
    cameraId: raw.camera_id ?? '',
    cameraName: raw.camera_name ?? '—',
    description: raw.description ?? raw.payload?.description ?? raw.type ?? '—',
    timestamp: raw.occurred_at ?? raw.created_at ?? new Date().toISOString(),
  };
}

export function mapRule(raw: BackendRule): Rule {
  return {
    id: raw.id,
    name: raw.name,
    enabled: raw.is_enabled ?? raw.enabled ?? false,
    cameraIds: raw.camera_ids ?? [],
    conditions: raw.definition?.conditions ?? [],
    actions: raw.definition?.actions ?? [],
  };
}

export function mapAudit(raw: BackendAudit): AuditEntry {
  const resource = [raw.resource_type, raw.resource_id].filter(Boolean).join('/');
  return {
    id: raw.id,
    userId: raw.user_id ?? '',
    username: raw.user_email ?? '—',
    action: raw.action.toUpperCase(),
    resource: resource || '—',
    timestamp: raw.created_at ?? new Date().toISOString(),
    ip: raw.ip_address ?? '—',
  };
}

export function mapUser(raw: BackendUser): User {
  return {
    id: raw.id,
    username: raw.full_name ?? raw.email.split('@')[0],
    email: raw.email,
    role: mapBackendRole(raw.role ?? 'viewer'),
    lastLogin: raw.last_login_at,
  };
}

export function ensureArray<T>(data: T[] | null | undefined): T[] {
  return Array.isArray(data) ? data : [];
}
