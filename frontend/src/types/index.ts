export type UserRole = 'admin' | 'operator' | 'viewer';

export interface User {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  avatar?: string;
  lastLogin?: string;
  isActive?: boolean;
}

export interface Camera {
  id: string;
  name: string;
  ip: string;
  status: 'online' | 'offline' | 'recording';
  location: string;
  siteId?: string;
  model?: string;
  streamUrl?: string;
  streamKey?: string;
  metadata?: Record<string, unknown>;
}

export interface DiscoveredDevice {
  ip: string;
  port?: number;
  reachable?: boolean;
  rtsp_port?: number;
  has_rtsp?: boolean;
  vendor?: string;
  model?: string;
}

export type { EvidenceBBox, EvidenceClip, EvidenceImage, EvidencePackage, EvidenceSnapshot } from '@/lib/evidence';

export interface Alert {
  id: string;
  type: 'intrusion' | 'motion' | 'line_cross' | 'zone_entry' | 'system';
  severity: 'low' | 'medium' | 'high' | 'critical';
  status?: string;
  cameraId: string;
  cameraName: string;
  ruleId?: string;
  ruleName?: string;
  message: string;
  timestamp: string;
  acknowledged: boolean;
  archivedAt?: string;
  archiveComment?: string;
  evidenceSnapshot?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface AlertFilters {
  status?: string;
  severity?: string;
  ruleId?: string;
  cameraId?: string;
  from?: string;
  to?: string;
  limit?: number;
  includeIncomplete?: boolean;
}

export interface Event {
  id: string;
  type: string;
  typeLabel?: string;
  cameraId: string;
  cameraName: string;
  ruleName?: string;
  confidence?: number;
  description: string;
  timestamp: string;
  thumbnail?: string;
  evidenceSnapshot?: Record<string, unknown>;
  payload?: Record<string, unknown>;
}

export interface Rule {
  id: string;
  name: string;
  enabled: boolean;
  cameraIds: string[];
  conditions: RuleCondition[];
  actions: RuleAction[];
  category?: string;
  severity?: string;
  description?: string;
  definition?: Record<string, unknown>;
}

export interface RuleCatalogTemplate {
  id: string;
  name: string;
  category: string;
  severity: string;
  description?: string;
  definition: Record<string, unknown>;
  configSchema?: RuleConfigSchema;
  supported?: boolean;
  capability_id?: string;
  human_description?: string;
  role_summary_fr?: string;
  illustration?: string;
  deployment_scopes?: string[];
  tutorial?: string;
  prerequisites?: string[];
  unsupported_message_fr?: string;
  partial_status?: "full" | "requires_calibration" | "requires_ocr" | "requires_face_ai" | "partial_aggregate";
  partial_reason_fr?: string;
}

export interface RuleCondition {
  id: string;
  type: 'motion' | 'zone' | 'line' | 'schedule' | 'object';
  params: Record<string, string | number | boolean>;
}

export interface RuleAction {
  id: string;
  type: 'alert' | 'record' | 'notify' | 'relay';
  params: Record<string, string | number | boolean>;
}

export interface AuditEntry {
  id: string;
  userId: string;
  username: string;
  action: string;
  resource: string;
  timestamp: string;
  ip: string;
}

export interface SystemHealthMetric {
  name: string;
  status: 'healthy' | 'warning' | 'critical';
  value: string;
  unit?: string;
}

export interface DashboardSummary {
  cameras_active: number;
  cameras_total: number;
  open_alerts: number;
  events_last_24h: number;
  rules_enabled: number;
  users_total: number;
}

export interface SetupStatus {
  initialized: boolean;
}

export interface SetupResponse {
  org_id: string;
  site_id?: string;
}

export interface NavItem {
  path: string;
  labelKey: string;
  icon: string;
  roles: UserRole[];
}

export interface NavGroup {
  id: string;
  labelKey: string;
  badge?: 'demo';
  items: NavItem[];
}

export type ConfigFieldType =
  | 'camera'
  | 'zone'
  | 'line'
  | 'number'
  | 'schedule'
  | 'watchlist'
  | 'plate_list'
  | 'threshold'
  | 'enum'
  | 'class_filter';

export interface ConfigSchemaField {
  key: string;
  type: ConfigFieldType;
  label?: string;
  required?: boolean;
  min?: number;
  max?: number;
  default?: number | string;
  hint?: string;
  options?: Array<{ value: string; label: string } | string>;
}

export interface RuleConfigSchema {
  fields: ConfigSchemaField[];
}

export interface Zone {
  id: string;
  name: string;
  points: number[];
  color: string;
  cameraId: string;
  /** perimeter | controlled_exit | corridor | parking | … (API spatial) */
  zoneKind?: string;
}
