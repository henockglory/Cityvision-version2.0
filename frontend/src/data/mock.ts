import type { Alert, AuditEntry, Camera, Event, Rule, SystemHealthMetric, User } from '@/types';

export const mockCameras: Camera[] = [
  { id: 'cam-1', name: 'Entrée principale', ip: '192.168.1.101', status: 'online', location: 'Hall A', model: 'Axis P3245' },
  { id: 'cam-2', name: 'Parking Nord', ip: '192.168.1.102', status: 'recording', location: 'Extérieur', model: 'Hikvision DS-2CD2' },
  { id: 'cam-3', name: 'Couloir B2', ip: '192.168.1.103', status: 'online', location: 'Étage 2', model: 'Dahua IPC-HFW' },
  { id: 'cam-4', name: 'Quai chargement', ip: '192.168.1.104', status: 'offline', location: 'Logistique', model: 'Axis M3046' },
  { id: 'cam-5', name: 'Réception', ip: '192.168.1.105', status: 'online', location: 'Hall B', model: 'Bosch DINION' },
  { id: 'cam-6', name: 'Toit technique', ip: '192.168.1.106', status: 'online', location: 'Toit', model: 'Axis Q6155' },
  { id: 'cam-7', name: 'Salle serveurs', ip: '192.168.1.107', status: 'recording', location: 'Sous-sol', model: 'Hikvision DS-2DE4' },
  { id: 'cam-8', name: 'Périmètre Est', ip: '10.0.0.48', status: 'online', location: 'Clôture', model: 'Dahua SD5A' },
  { id: 'cam-9', name: 'Hall C', ip: '192.168.1.109', status: 'online', location: 'Hall C', model: 'Axis P3245' },
  { id: 'cam-10', name: 'Ascenseur 1', ip: '192.168.1.110', status: 'online', location: 'Étage 1-5', model: 'Hikvision DS-2CD2' },
  { id: 'cam-11', name: 'Cafétéria', ip: '192.168.1.111', status: 'recording', location: 'RDC', model: 'Dahua IPC-HFW' },
  { id: 'cam-12', name: 'Sortie secours', ip: '192.168.1.112', status: 'online', location: 'Nord', model: 'Bosch DINION' },
  { id: 'cam-13', name: 'Local technique', ip: '192.168.1.113', status: 'offline', location: 'Sous-sol', model: 'Axis M3046' },
  { id: 'cam-14', name: 'Périmètre Ouest', ip: '192.168.1.114', status: 'online', location: 'Clôture', model: 'Dahua SD5A' },
  { id: 'cam-15', name: 'Bureau direction', ip: '192.168.1.115', status: 'online', location: 'Étage 3', model: 'Axis Q6155' },
  { id: 'cam-16', name: 'Quai Sud', ip: '192.168.1.116', status: 'recording', location: 'Logistique', model: 'Hikvision DS-2DE4' },
];

export const mockAlerts: Alert[] = [
  { id: 'a1', type: 'intrusion', severity: 'critical', cameraId: 'cam-1', cameraName: 'Entrée principale', message: 'Intrusion détectée zone A', timestamp: '2026-06-12T14:32:00Z', acknowledged: false },
  { id: 'a2', type: 'motion', severity: 'medium', cameraId: 'cam-2', cameraName: 'Parking Nord', message: 'Mouvement nocturne détecté', timestamp: '2026-06-12T13:15:00Z', acknowledged: false },
  { id: 'a3', type: 'line_cross', severity: 'high', cameraId: 'cam-8', cameraName: 'Périmètre Est', message: 'Franchissement de ligne', timestamp: '2026-06-12T12:48:00Z', acknowledged: true },
  { id: 'a4', type: 'zone_entry', severity: 'low', cameraId: 'cam-5', cameraName: 'Réception', message: 'Entrée zone restreinte', timestamp: '2026-06-12T11:20:00Z', acknowledged: true },
];

export const mockEvents: Event[] = [
  { id: 'e1', type: 'motion', cameraId: 'cam-1', cameraName: 'Entrée principale', description: 'Mouvement détecté', timestamp: '2026-06-12T14:30:00Z' },
  { id: 'e2', type: 'recording_start', cameraId: 'cam-2', cameraName: 'Parking Nord', description: 'Enregistrement démarré', timestamp: '2026-06-12T14:28:00Z' },
  { id: 'e3', type: 'person', cameraId: 'cam-3', cameraName: 'Couloir B2', description: 'Personne identifiée', timestamp: '2026-06-12T14:25:00Z' },
  { id: 'e4', type: 'vehicle', cameraId: 'cam-2', cameraName: 'Parking Nord', description: 'Véhicule détecté', timestamp: '2026-06-12T14:20:00Z' },
  { id: 'e5', type: 'connection_lost', cameraId: 'cam-4', cameraName: 'Quai chargement', description: 'Connexion perdue', timestamp: '2026-06-12T14:15:00Z' },
  { id: 'e6', type: 'motion', cameraId: 'cam-7', cameraName: 'Salle serveurs', description: 'Mouvement détecté', timestamp: '2026-06-12T14:10:00Z' },
];

export const mockUsers: User[] = [
  { id: '1', username: 'admin', email: 'admin@citevision.local', role: 'admin', lastLogin: '2026-06-12T08:00:00Z' },
  { id: '2', username: 'operator', email: 'operator@citevision.local', role: 'operator', lastLogin: '2026-06-12T09:30:00Z' },
  { id: '3', username: 'viewer', email: 'viewer@citevision.local', role: 'viewer', lastLogin: '2026-06-11T16:45:00Z' },
  { id: '4', username: 'jdupont', email: 'j.dupont@citevision.local', role: 'operator', lastLogin: '2026-06-12T07:15:00Z' },
];

export const mockRules: Rule[] = [
  {
    id: 'r1',
    name: 'Intrusion périmètre',
    enabled: true,
    cameraIds: ['cam-8'],
    conditions: [{ id: 'c1', type: 'zone', params: { zoneId: 'z1', sensitivity: 80 } }],
    actions: [{ id: 'a1', type: 'alert', params: { severity: 'critical' } }, { id: 'a2', type: 'record', params: { duration: 60 } }],
  },
  {
    id: 'r2',
    name: 'Mouvement parking nuit',
    enabled: true,
    cameraIds: ['cam-2'],
    conditions: [{ id: 'c2', type: 'motion', params: { threshold: 50 } }, { id: 'c3', type: 'schedule', params: { start: '22:00', end: '06:00' } }],
    actions: [{ id: 'a3', type: 'notify', params: { channel: 'email' } }],
  },
  {
    id: 'r3',
    name: 'Franchissement ligne entrée',
    enabled: false,
    cameraIds: ['cam-1'],
    conditions: [{ id: 'c4', type: 'line', params: { direction: 'in' } }],
    actions: [{ id: 'a4', type: 'alert', params: { severity: 'medium' } }],
  },
];

export const mockAudit: AuditEntry[] = [
  { id: 'au1', userId: '1', username: 'admin', action: 'LOGIN', resource: 'auth', timestamp: '2026-06-12T08:00:00Z', ip: '10.0.0.15' },
  { id: 'au2', userId: '1', username: 'admin', action: 'CREATE', resource: 'rule/r1', timestamp: '2026-06-12T08:15:00Z', ip: '10.0.0.15' },
  { id: 'au3', userId: '2', username: 'operator', action: 'ACKNOWLEDGE', resource: 'alert/a3', timestamp: '2026-06-12T09:00:00Z', ip: '10.0.0.22' },
  { id: 'au4', userId: '1', username: 'admin', action: 'UPDATE', resource: 'camera/cam-4', timestamp: '2026-06-12T10:30:00Z', ip: '10.0.0.15' },
];

export const mockHealth: SystemHealthMetric[] = [
  { name: 'CPU', status: 'healthy', value: '34', unit: '%' },
  { name: 'Mémoire', status: 'healthy', value: '62', unit: '%' },
  { name: 'Disque', status: 'warning', value: '78', unit: '%' },
  { name: 'Réseau', status: 'healthy', value: '1.2', unit: 'Gbps' },
  { name: 'NVR Service', status: 'healthy', value: 'Running' },
  { name: 'AI Engine', status: 'healthy', value: 'Running' },
  { name: 'Stream Proxy', status: 'warning', value: 'Degraded' },
];

export const mockScanDevices = [
  { ip: '192.168.1.101', model: 'Axis P3245-V' },
  { ip: '192.168.1.102', model: 'Hikvision DS-2CD2T47G2' },
  { ip: '192.168.1.109', model: 'Dahua IPC-HFW5831E' },
  { ip: '192.168.1.110', model: 'Unknown ONVIF Device' },
];
