import type { NavItem, UserRole } from '@/types';

export const navItems: NavItem[] = [
  { path: '/', labelKey: 'nav.dashboard', icon: 'LayoutDashboard', roles: ['admin', 'operator', 'viewer'] },
  { path: '/cameras', labelKey: 'nav.cameras', icon: 'Camera', roles: ['admin', 'operator'] },
  { path: '/live', labelKey: 'nav.liveView', icon: 'MonitorPlay', roles: ['admin', 'operator', 'viewer'] },
  { path: '/video-wall', labelKey: 'nav.videoWall', icon: 'Grid3x3', roles: ['admin', 'operator', 'viewer'] },
  { path: '/map', labelKey: 'nav.map', icon: 'Map', roles: ['admin', 'operator', 'viewer'] },
  { path: '/zones', labelKey: 'nav.zoneEditor', icon: 'PenTool', roles: ['admin', 'operator'] },
  { path: '/rules', labelKey: 'nav.rules', icon: 'Workflow', roles: ['admin', 'operator'] },
  { path: '/alerts', labelKey: 'nav.alerts', icon: 'Bell', roles: ['admin', 'operator', 'viewer'] },
  { path: '/events', labelKey: 'nav.events', icon: 'Clock', roles: ['admin', 'operator', 'viewer'] },
  { path: '/users', labelKey: 'nav.users', icon: 'Users', roles: ['admin'] },
  { path: '/audit', labelKey: 'nav.audit', icon: 'FileText', roles: ['admin'] },
  { path: '/health', labelKey: 'nav.systemHealth', icon: 'Activity', roles: ['admin', 'operator'] },
  { path: '/settings', labelKey: 'nav.settings', icon: 'Settings', roles: ['admin', 'operator', 'viewer'] },
];

export function getNavForRole(role: UserRole): NavItem[] {
  return navItems.filter((item) => item.roles.includes(role));
}
