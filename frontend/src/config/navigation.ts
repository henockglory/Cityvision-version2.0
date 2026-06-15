import type { NavItem, NavGroup, UserRole } from '@/types';

export const navGroups: NavGroup[] = [
  {
    id: 'overview',
    labelKey: 'nav.groups.overview',
    items: [
      { path: '/', labelKey: 'nav.dashboard', icon: 'LayoutDashboard', roles: ['admin', 'operator', 'viewer'] },
    ],
  },
  {
    id: 'video',
    labelKey: 'nav.groups.video',
    items: [
      { path: '/cameras', labelKey: 'nav.cameras', icon: 'Camera', roles: ['admin', 'operator'] },
      { path: '/live', labelKey: 'nav.liveView', icon: 'MonitorPlay', roles: ['admin', 'operator', 'viewer'] },
      { path: '/video-wall', labelKey: 'nav.videoWall', icon: 'Grid3x3', roles: ['admin', 'operator', 'viewer'] },
      { path: '/map', labelKey: 'nav.map', icon: 'Map', roles: ['admin', 'operator', 'viewer'] },
    ],
  },
  {
    id: 'security',
    labelKey: 'nav.groups.security',
    items: [
      { path: '/zones', labelKey: 'nav.zoneEditor', icon: 'PenTool', roles: ['admin', 'operator'] },
      { path: '/rules', labelKey: 'nav.rules', icon: 'Workflow', roles: ['admin', 'operator'] },
      { path: '/alerts', labelKey: 'nav.alerts', icon: 'Bell', roles: ['admin', 'operator', 'viewer'] },
      { path: '/events', labelKey: 'nav.events', icon: 'Clock', roles: ['admin', 'operator', 'viewer'] },
    ],
  },
  {
    id: 'admin',
    labelKey: 'nav.groups.admin',
    items: [
      { path: '/users', labelKey: 'nav.users', icon: 'Users', roles: ['admin'] },
      { path: '/audit', labelKey: 'nav.audit', icon: 'FileText', roles: ['admin'] },
      { path: '/health', labelKey: 'nav.systemHealth', icon: 'Activity', roles: ['admin', 'operator'] },
    ],
  },
  {
    id: 'account',
    labelKey: 'nav.groups.account',
    items: [
      { path: '/settings', labelKey: 'nav.settings', icon: 'Settings', roles: ['admin', 'operator', 'viewer'] },
    ],
  },
  {
    id: 'demo',
    labelKey: 'nav.groups.demo',
    badge: 'demo',
    items: [
      { path: '/demo', labelKey: 'nav.demo', icon: 'Sparkles', roles: ['admin', 'operator'] },
    ],
  },
];

/** @deprecated use navGroups */
export const navItems: NavItem[] = navGroups.flatMap((g) => g.items);

export function getNavGroupsForRole(role: UserRole): NavGroup[] {
  return navGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => item.roles.includes(role)),
    }))
    .filter((group) => group.items.length > 0);
}

export function getNavForRole(role: UserRole): NavItem[] {
  return getNavGroupsForRole(role).flatMap((g) => g.items);
}

export function getAllNavItemsForSearch(role: UserRole): NavItem[] {
  return getNavForRole(role);
}
