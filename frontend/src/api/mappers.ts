import type { Alert, AuditEntry, Camera, Event, Rule, RuleCatalogTemplate, User } from '@/types';
import { go2rtcStreamSrc } from '@/config/streams';
import { evidenceThumbnailUrl, parseEvidenceSnapshot } from '@/lib/evidence';
import { mapBackendRole } from '@/stores/authStore';
import { labelForEventType } from '@/lib/eventLabels';

interface BackendCamera {
  id: string;
  name: string;
  host: string;
  status?: string;
  vendor?: string;
  site_id?: string;
  is_active?: boolean;
  rtsp_path?: string;
  metadata?: Record<string, unknown>;
}

interface BackendAlert {
  id: string;
  type?: string;
  severity?: string;
  camera_id?: string;
  camera_name?: string;
  rule_id?: string;
  rule_name?: string;
  message?: string;
  title?: string;
  created_at?: string;
  status?: string;
  archived_at?: string;
  archive_comment?: string;
  evidence_snapshot?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

interface BackendEvent {
  id: string;
  event_type?: string;
  type?: string;
  camera_id?: string;
  camera_name?: string;
  rule_name?: string;
  label_fr?: string;
  confidence?: number;
  description?: string;
  payload?: { description?: string };
  evidence_snapshot?: Record<string, unknown>;
  occurred_at?: string;
  created_at?: string;
}

interface BackendRule {
  id: string;
  name: string;
  description?: string;
  category?: string;
  severity?: string;
  is_enabled?: boolean;
  enabled?: boolean;
  camera_ids?: string[];
  definition?: Record<string, unknown> & {
    conditions?: Rule['conditions'];
    actions?: Rule['actions'];
    camera_id?: string;
    bindings?: Record<string, unknown>;
  };
}

interface BackendAudit {
  id: string | number;
  user_id?: string;
  user_email?: string;
  user_name?: string;
  action: string;
  resource_type?: string;
  resource_id?: string;
  created_at?: string;
  ip_address?: string;
}

interface BackendUser {
  id: string;
  email: string;
  full_name?: string;
  role?: string;
  last_login_at?: string;
}

interface BackendMember {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

function mapCameraStatus(status?: string, isActive?: boolean): Camera['status'] {
  if (status === 'online' || status === 'recording') return status;
  if (status === 'offline') return 'offline';
  return isActive === false ? 'offline' : 'online';
}

export function mapCamera(raw: BackendCamera): Camera {
  const meta = raw.metadata ?? {};
  const rtspMeta = typeof meta.rtsp_url === 'string' ? meta.rtsp_url : undefined;
  return {
    id: raw.id,
    name: raw.name,
    ip: raw.host,
    status: mapCameraStatus(raw.status, raw.is_active),
    location: raw.site_id ?? '—',
    siteId: raw.site_id,
    model: raw.vendor,
    streamUrl: rtspMeta ?? raw.rtsp_path,
    streamKey: go2rtcStreamSrc({ streamUrl: rtspMeta, name: raw.name, metadata: meta }),
    metadata: meta,
  };
}

export function mapAlert(raw: BackendAlert): Alert {
  const severity = (raw.severity ?? 'medium') as Alert['severity'];
  const type = (raw.type ?? 'system') as Alert['type'];
  const meta = raw.metadata ?? {};
  const evidence = raw.evidence_snapshot
    ?? (meta.evidence_snapshot as Record<string, unknown> | undefined)
    ?? {};
  return {
    id: raw.id,
    type,
    severity,
    status: raw.status,
    cameraId: raw.camera_id ?? String(meta.camera_id ?? ''),
    cameraName: raw.camera_name ?? '—',
    ruleId: raw.rule_id,
    ruleName: raw.rule_name,
    message: raw.message ?? raw.title ?? '—',
    timestamp: raw.created_at ?? new Date().toISOString(),
    acknowledged: raw.status === 'archived',
    archivedAt: raw.archived_at,
    archiveComment: raw.archive_comment,
    evidenceSnapshot: evidence,
    metadata: meta,
  };
}

export function mapEvent(raw: BackendEvent): Event {
  const type = raw.event_type ?? raw.type ?? 'event';
  const evidence = raw.evidence_snapshot ?? {};
  const ev = parseEvidenceSnapshot(evidence);
  return {
    id: raw.id,
    type,
    typeLabel: labelForEventType(type, raw.label_fr),
    cameraId: raw.camera_id ?? '',
    cameraName: raw.camera_name ?? '—',
    ruleName: raw.rule_name,
    confidence: raw.confidence,
    description: raw.description ?? raw.payload?.description ?? labelForEventType(type, raw.label_fr),
    timestamp: raw.occurred_at ?? raw.created_at ?? new Date().toISOString(),
    evidenceSnapshot: evidence,
    thumbnail: evidenceThumbnailUrl(ev),
    payload: raw.payload,
  };
}

export function mapRuleCatalogItem(raw: RuleCatalogTemplate): RuleCatalogTemplate {
  return {
    id: raw.id,
    name: raw.name,
    category: raw.category,
    severity: raw.severity,
    description: raw.description,
    definition: raw.definition,
    configSchema: raw.configSchema,
    supported: raw.supported,
    capability_id: raw.capability_id,
    human_description: raw.human_description,
    tutorial: raw.tutorial,
    prerequisites: raw.prerequisites,
    unsupported_message_fr: raw.unsupported_message_fr,
  };
}

function conditionsFromDefinition(def: Record<string, unknown>): Rule['conditions'] {
  const condition = (def.condition ?? def.conditions) as { op?: string; field?: string; children?: unknown[] } | undefined;
  if (!condition) return [];
  const nodes: Rule['conditions'] = [];
  const walk = (node: { op?: string; field?: string; value?: unknown; children?: typeof node[] }) => {
    const op = String(node.op ?? '').toUpperCase();
    if (['ET', 'AND', 'OU', 'OR', 'NON', 'NOT'].includes(op)) {
      for (const c of node.children ?? []) walk(c as typeof node);
      return;
    }
    nodes.push({
      id: `${node.field ?? 'cond'}-${nodes.length}`,
      type: (node.field?.includes('zone') ? 'zone' : node.field?.includes('line') ? 'line' : 'motion') as Rule['conditions'][0]['type'],
      params: { op: node.op ?? '', field: node.field ?? '', value: String(node.value ?? '') },
    });
  };
  walk(condition as Parameters<typeof walk>[0]);
  return nodes;
}

export function mapRule(raw: BackendRule): Rule {
  const def = raw.definition ?? {};
  const bindings = (def.bindings ?? {}) as Record<string, unknown>;
  const cameraId =
    (typeof def.camera_id === 'string' ? def.camera_id : undefined) ??
    (typeof bindings.camera_id === 'string' ? bindings.camera_id : undefined);
  return {
    id: raw.id,
    name: raw.name,
    enabled: raw.is_enabled ?? raw.enabled ?? false,
    cameraIds: cameraId ? [cameraId] : (raw.camera_ids ?? []),
    conditions: conditionsFromDefinition(def),
    actions: ((def.actions as Rule['actions']) ?? []).map((a, i) => ({
      ...a,
      id: a.id ?? `action-${i}`,
    })),
    category: raw.category,
    severity: raw.severity,
    description: raw.description,
    definition: def,
  };
}

export function mapAudit(raw: BackendAudit): AuditEntry {
  const resource = [raw.resource_type, raw.resource_id].filter(Boolean).join('/');
  const username =
    (raw.user_name && raw.user_name !== '' ? raw.user_name : null) ??
    raw.user_email ??
    '—';
  return {
    id: String(raw.id),
    userId: raw.user_id ?? '',
    username,
    action: raw.action.toUpperCase(),
    resource: resource || '—',
    timestamp: raw.created_at ?? new Date().toISOString(),
    ip: raw.ip_address ?? '—',
  };
}

export function mapUser(raw: BackendUser | BackendMember): User {
  const email = raw.email ?? '';
  const fullName = 'full_name' in raw && raw.full_name ? raw.full_name : email.split('@')[0];
  const roleStr = raw.role ?? 'viewer';
  return {
    id: raw.id,
    username: fullName,
    email,
    role: mapBackendRole(roleStr),
    lastLogin: 'last_login_at' in raw ? raw.last_login_at : undefined,
    isActive: 'is_active' in raw ? raw.is_active : true,
  };
}

export function ensureArray<T>(data: T[] | null | undefined): T[] {
  return Array.isArray(data) ? data : [];
}
