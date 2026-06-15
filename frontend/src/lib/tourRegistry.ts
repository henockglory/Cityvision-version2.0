import type { DriveStep } from 'driver.js';

export type TourId =
  | 'global'
  | 'dashboard'
  | 'map'
  | 'rules'
  | 'alerts'
  | 'videoWall'
  | 'liveView'
  | 'cameras'
  | 'zones'
  | 'events'
  | 'users'
  | 'audit'
  | 'health'
  | 'settings'
  | 'demo';

export const TOUR_LABELS: Record<TourId, string> = {
  global: 'tours.labels.global',
  dashboard: 'tours.labels.dashboard',
  map: 'tours.labels.map',
  rules: 'tours.labels.rules',
  alerts: 'tours.labels.alerts',
  videoWall: 'tours.labels.videoWall',
  liveView: 'tours.labels.liveView',
  cameras: 'tours.labels.cameras',
  zones: 'tours.labels.zones',
  events: 'tours.labels.events',
  users: 'tours.labels.users',
  audit: 'tours.labels.audit',
  health: 'tours.labels.health',
  settings: 'tours.labels.settings',
  demo: 'tours.labels.demo',
};

function step(
  element: string,
  titleKey: string,
  descKey: string,
  side: 'top' | 'bottom' | 'left' | 'right' = 'bottom',
  t: (k: string) => string,
): DriveStep {
  return {
    element,
    popover: { title: t(titleKey), description: t(descKey), side },
  };
}

export function getTourSteps(tourId: TourId, t: (k: string) => string): DriveStep[] {
  switch (tourId) {
    case 'dashboard':
      return [
        step('#dashboard-stats', 'tours.dashboard.stats', 'tours.dashboard.statsDesc', 'bottom', t),
        step('#dashboard-alerts', 'tours.dashboard.alerts', 'tours.dashboard.alertsDesc', 'right', t),
        step('#dashboard-live', 'tours.dashboard.live', 'tours.dashboard.liveDesc', 'top', t),
      ];
    case 'map':
      return [
        step('#map-mode-tabs', 'tours.map.modes', 'tours.map.modesDesc', 'bottom', t),
        step('#map-canvas', 'tours.map.canvas', 'tours.map.canvasDesc', 'left', t),
      ];
    case 'rules':
      return [
        step('#rules-catalog', 'tours.rules.catalog', 'tours.rules.catalogDesc', 'top', t),
        step('#rules-active-panel', 'tours.rules.active', 'tours.rules.activeDesc', 'top', t),
      ];
    case 'alerts':
      return [step('#alerts-filters', 'tours.alerts.filters', 'tours.alerts.filtersDesc', 'bottom', t)];
    case 'videoWall':
      return [
        step('#video-wall-layout', 'tours.videoWall.layout', 'tours.videoWall.layoutDesc', 'bottom', t),
        step('#video-wall-grid', 'tours.videoWall.grid', 'tours.videoWall.gridDesc', 'top', t),
      ];
    case 'liveView':
      return [step('#live-view-player', 'tours.liveView.player', 'tours.liveView.playerDesc', 'bottom', t)];
    case 'cameras':
      return [step('#cameras-list', 'tours.cameras.list', 'tours.cameras.listDesc', 'right', t)];
    case 'zones':
      return [step('#zone-canvas', 'tours.zones.canvas', 'tours.zones.canvasDesc', 'bottom', t)];
    case 'events':
      return [step('#events-timeline', 'tours.events.timeline', 'tours.events.timelineDesc', 'bottom', t)];
    case 'users':
      return [step('#users-table', 'tours.users.table', 'tours.users.tableDesc', 'bottom', t)];
    case 'audit':
      return [step('#audit-log', 'tours.audit.log', 'tours.audit.logDesc', 'bottom', t)];
    case 'health':
      return [step('#health-services', 'tours.health.services', 'tours.health.servicesDesc', 'bottom', t)];
    case 'settings':
      return [step('#settings-tabs', 'tours.settings.tabs', 'tours.settings.tabsDesc', 'bottom', t)];
    case 'demo':
      return [step('#demo-banner', 'tours.demo.banner', 'tours.demo.bannerDesc', 'bottom', t)];
    default:
      return [];
  }
}
