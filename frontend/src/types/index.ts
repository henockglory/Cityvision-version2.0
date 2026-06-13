export type UserRole = 'admin' | 'operator' | 'viewer';

export interface User {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  avatar?: string;
  lastLogin?: string;
}

export interface Camera {
  id: string;
  name: string;
  ip: string;
  status: 'online' | 'offline' | 'recording';
  location: string;
  model?: string;
  streamUrl?: string;
}

export interface DiscoveredDevice {
  ip: string;
  port?: number;
  reachable?: boolean;
  rtsp_port?: number;
  vendor?: string;
  model?: string;
}

export interface Alert {
  id: string;
  type: 'intrusion' | 'motion' | 'line_cross' | 'zone_entry' | 'system';
  severity: 'low' | 'medium' | 'high' | 'critical';
  cameraId: string;
  cameraName: string;
  message: string;
  timestamp: string;
  acknowledged: boolean;
}

export interface Event {
  id: string;
  type: string;
  cameraId: string;
  cameraName: string;
  description: string;
  timestamp: string;
  thumbnail?: string;
}

export interface Rule {
  id: string;
  name: string;
  enabled: boolean;
  cameraIds: string[];
  conditions: RuleCondition[];
  actions: RuleAction[];
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

export interface Zone {
  id: string;
  name: string;
  points: number[];
  color: string;
  cameraId: string;
}
