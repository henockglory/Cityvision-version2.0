import type { DriveStep } from 'driver.js';
import { buildTourDescription, filterExistingSteps } from '@/lib/tourEngine';

export type TourId =
  | 'global'
  | 'login'
  | 'setup'
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
  | 'addUser'
  | 'audit'
  | 'health'
  | 'settings'
  | 'demo'
  | 'redLightAssistant'
  | 'confirmDialog'
  | 'ruleActivation'
  | 'cameraWizard'
  | 'modelImport'
  | 'evidenceViewer';

export const TOUR_LABELS: Record<TourId, string> = {
  global: 'tours.labels.global',
  login: 'tours.labels.login',
  setup: 'tours.labels.setup',
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
  addUser: 'tours.labels.addUser',
  audit: 'tours.labels.audit',
  health: 'tours.labels.health',
  settings: 'tours.labels.settings',
  demo: 'tours.labels.demo',
  redLightAssistant: 'tours.labels.redLightAssistant',
  confirmDialog: 'tours.labels.confirmDialog',
  ruleActivation: 'tours.labels.ruleActivation',
  cameraWizard: 'tours.labels.cameraWizard',
  modelImport: 'tours.labels.modelImport',
  evidenceViewer: 'tours.labels.evidenceViewer',
};

const TOUR_GUIDE_SRC: Partial<Record<TourId, string>> = {
  rules: '/guides/rules-banner.svg',
  alerts: '/guides/alerts.svg',
  liveView: '/guides/live.svg',
  zones: '/guides/spatial.svg',
  cameras: '/guides/live.svg',
  events: '/guides/alerts.svg',
  health: '/guides/spatial.svg',
  demo: '/guides/rules-banner.svg',
};

type TFn = (key: string, opts?: Record<string, unknown>) => string;

interface StepOpts {
  side?: 'top' | 'bottom' | 'left' | 'right';
  tipKey?: string;
  stepsKey?: string;
  tourId?: TourId;
}

function richStep(
  element: string,
  titleKey: string,
  descKey: string,
  t: TFn,
  opts: StepOpts = {},
): DriveStep {
  const guide = opts.tourId ? TOUR_GUIDE_SRC[opts.tourId] : undefined;
  return {
    element,
    popover: {
      title: t(titleKey),
      description: buildTourDescription(t, descKey, {
        tipKey: opts.tipKey,
        stepsKey: opts.stepsKey,
        guideSrc: guide,
      }),
      side: opts.side ?? 'bottom',
    },
  };
}

export function getTourSteps(tourId: TourId, t: TFn): DriveStep[] {
  let steps: DriveStep[] = [];

  switch (tourId) {
    case 'login':
      steps = [
        richStep('#login-brand', 'tours.login.brand', 'tours.login.brandDesc', t, {
          tipKey: 'tours.login.brandTip',
        }),
        richStep('#login-form', 'tours.login.form', 'tours.login.formDesc', t, {
          tipKey: 'tours.login.formTip',
          stepsKey: 'tours.login.formSteps',
        }),
        richStep('#login-email-field', 'tours.login.email', 'tours.login.emailDesc', t, {
          tipKey: 'tours.login.emailTip',
        }),
        richStep('#login-password-field', 'tours.login.password', 'tours.login.passwordDesc', t, {
          tipKey: 'tours.login.passwordTip',
        }),
        richStep('#login-submit', 'tours.login.submit', 'tours.login.submitDesc', t, {
          tipKey: 'tours.login.submitTip',
          stepsKey: 'tours.login.submitSteps',
        }),
      ];
      break;

    case 'global':
      steps = [
        richStep('#sidebar-nav', 'tours.global.sidebar', 'tours.global.sidebarDesc', t, {
          side: 'right',
          tipKey: 'tours.global.sidebarTip',
          stepsKey: 'tours.global.sidebarSteps',
        }),
        richStep('#navbar-search', 'tours.global.search', 'tours.global.searchDesc', t, {
          side: 'bottom',
          tipKey: 'tours.global.searchTip',
          stepsKey: 'tours.global.searchSteps',
        }),
        richStep('#theme-toggle', 'tours.global.theme', 'tours.global.themeDesc', t, {
          side: 'bottom',
          tipKey: 'tours.global.themeTip',
        }),
        richStep('#main-content', 'tours.global.content', 'tours.global.contentDesc', t, {
          side: 'top',
          tipKey: 'tours.global.contentTip',
          stepsKey: 'tours.global.contentSteps',
        }),
      ];
      break;

    case 'setup':
      steps = [
        richStep('#setup-brand', 'tours.setup.brand', 'tours.setup.brandDesc', t, {
          tipKey: 'tours.setup.brandTip',
        }),
        richStep('#setup-progress', 'tours.setup.progress', 'tours.setup.progressDesc', t, {
          tipKey: 'tours.setup.progressTip',
          stepsKey: 'tours.setup.progressSteps',
        }),
        richStep('#setup-step1', 'tours.setup.step1', 'tours.setup.step1Desc', t, {
          tipKey: 'tours.setup.step1Tip',
        }),
        richStep('#setup-step2', 'tours.setup.step2', 'tours.setup.step2Desc', t, {
          tipKey: 'tours.setup.step2Tip',
          stepsKey: 'tours.setup.step2Steps',
        }),
        richStep('#setup-step3', 'tours.setup.step3', 'tours.setup.step3Desc', t, {
          tipKey: 'tours.setup.step3Tip',
          stepsKey: 'tours.setup.step3Steps',
        }),
        richStep('#setup-submit', 'tours.setup.submit', 'tours.setup.submitDesc', t, {
          tipKey: 'tours.setup.submitTip',
        }),
      ];
      break;

    case 'dashboard':
      steps = [
        richStep('#dashboard-stats', 'tours.dashboard.stats', 'tours.dashboard.statsDesc', t, {
          tipKey: 'tours.dashboard.statsTip',
          stepsKey: 'tours.dashboard.statsSteps',
        }),
        richStep('#dashboard-alerts', 'tours.dashboard.alerts', 'tours.dashboard.alertsDesc', t, {
          side: 'right',
          tipKey: 'tours.dashboard.alertsTip',
          stepsKey: 'tours.dashboard.alertsSteps',
        }),
        richStep('#dashboard-live', 'tours.dashboard.live', 'tours.dashboard.liveDesc', t, {
          side: 'top',
          tipKey: 'tours.dashboard.liveTip',
          stepsKey: 'tours.dashboard.liveSteps',
        }),
        richStep('a[href="/alerts"]', 'tours.dashboard.navAlerts', 'tours.dashboard.navAlertsDesc', t, {
          side: 'left',
          tipKey: 'tours.dashboard.navAlertsTip',
        }),
      ];
      break;

    case 'map':
      steps = [
        richStep('#map-mode-tabs', 'tours.map.modes', 'tours.map.modesDesc', t, {
          tipKey: 'tours.map.modesTip',
          stepsKey: 'tours.map.modesSteps',
        }),
        richStep('#map-canvas', 'tours.map.canvas', 'tours.map.canvasDesc', t, {
          side: 'left',
          tipKey: 'tours.map.canvasTip',
          stepsKey: 'tours.map.canvasSteps',
        }),
      ];
      break;

    case 'rules':
      steps = [
        richStep('#rules-catalog', 'tours.rules.catalog', 'tours.rules.catalogDesc', t, {
          side: 'top',
          tourId: 'rules',
          tipKey: 'tours.rules.catalogTip',
          stepsKey: 'tours.rules.catalogSteps',
        }),
        richStep('#rules-active-panel', 'tours.rules.active', 'tours.rules.activeDesc', t, {
          side: 'top',
          tourId: 'rules',
          tipKey: 'tours.rules.activeTip',
          stepsKey: 'tours.rules.activeSteps',
        }),
        richStep('button[data-tour="rules-help"]', 'tours.rules.helpBtn', 'tours.rules.helpBtnDesc', t, {
          tipKey: 'tours.rules.helpBtnTip',
        }),
      ];
      break;

    case 'alerts':
      steps = [
        richStep('#alerts-filters', 'tours.alerts.filters', 'tours.alerts.filtersDesc', t, {
          tourId: 'alerts',
          tipKey: 'tours.alerts.filtersTip',
          stepsKey: 'tours.alerts.filtersSteps',
        }),
        richStep('#alerts-list', 'tours.alerts.list', 'tours.alerts.listDesc', t, {
          tipKey: 'tours.alerts.listTip',
          stepsKey: 'tours.alerts.listSteps',
        }),
      ];
      break;

    case 'videoWall':
      steps = [
        richStep('#video-wall-layout', 'tours.videoWall.layout', 'tours.videoWall.layoutDesc', t, {
          tipKey: 'tours.videoWall.layoutTip',
          stepsKey: 'tours.videoWall.layoutSteps',
        }),
        richStep('#video-wall-grid', 'tours.videoWall.grid', 'tours.videoWall.gridDesc', t, {
          side: 'top',
          tipKey: 'tours.videoWall.gridTip',
          stepsKey: 'tours.videoWall.gridSteps',
        }),
      ];
      break;

    case 'liveView':
      steps = [
        richStep('#live-view-player', 'tours.liveView.player', 'tours.liveView.playerDesc', t, {
          tourId: 'liveView',
          tipKey: 'tours.liveView.playerTip',
          stepsKey: 'tours.liveView.playerSteps',
        }),
        richStep('#live-view-sidebar', 'tours.liveView.sidebar', 'tours.liveView.sidebarDesc', t, {
          side: 'left',
          tipKey: 'tours.liveView.sidebarTip',
        }),
      ];
      break;

    case 'cameras':
      steps = [
        richStep('#cameras-list', 'tours.cameras.list', 'tours.cameras.listDesc', t, {
          side: 'right',
          tourId: 'cameras',
          tipKey: 'tours.cameras.listTip',
          stepsKey: 'tours.cameras.listSteps',
        }),
        richStep('button[data-tour="add-camera"]', 'tours.cameras.wizard', 'tours.cameras.wizardDesc', t, {
          tourId: 'cameras',
          tipKey: 'tours.cameras.wizardTip',
          stepsKey: 'tours.cameras.wizardSteps',
        }),
      ];
      break;

    case 'cameraWizard':
      steps = [
        richStep('#camera-wizard', 'tours.cameraWizard.intro', 'tours.cameraWizard.introDesc', t, {
          tipKey: 'tours.cameraWizard.introTip',
          stepsKey: 'tours.cameraWizard.introSteps',
        }),
        richStep('#camera-wizard-step1', 'tours.cameraWizard.step1', 'tours.cameraWizard.step1Desc', t, {
          tipKey: 'tours.cameraWizard.step1Tip',
          stepsKey: 'tours.cameraWizard.step1Steps',
        }),
        richStep('#camera-wizard-step2', 'tours.cameraWizard.step2', 'tours.cameraWizard.step2Desc', t, {
          tipKey: 'tours.cameraWizard.step2Tip',
        }),
        richStep('#camera-wizard-step3', 'tours.cameraWizard.step3', 'tours.cameraWizard.step3Desc', t, {
          tipKey: 'tours.cameraWizard.step3Tip',
        }),
        richStep('#camera-wizard-step4', 'tours.cameraWizard.step4', 'tours.cameraWizard.step4Desc', t, {
          tipKey: 'tours.cameraWizard.step4Tip',
          stepsKey: 'tours.cameraWizard.step4Steps',
        }),
      ];
      break;

    case 'zones':
      steps = [
        richStep('#zone-toolbar', 'tours.zones.toolbar', 'tours.zones.toolbarDesc', t, {
          tourId: 'zones',
          tipKey: 'tours.zones.toolbarTip',
          stepsKey: 'tours.zones.toolbarSteps',
        }),
        richStep('#zone-canvas', 'tours.zones.canvas', 'tours.zones.canvasDesc', t, {
          side: 'left',
          tourId: 'zones',
          tipKey: 'tours.zones.canvasTip',
          stepsKey: 'tours.zones.canvasSteps',
        }),
        richStep('#zone-behavior-panel', 'tours.zones.behavior', 'tours.zones.behaviorDesc', t, {
          side: 'right',
          tipKey: 'tours.zones.behaviorTip',
          stepsKey: 'tours.zones.behaviorSteps',
        }),
      ];
      break;

    case 'events':
      steps = [
        richStep('#events-filters', 'tours.events.filters', 'tours.events.filtersDesc', t, {
          tourId: 'events',
          tipKey: 'tours.events.filtersTip',
          stepsKey: 'tours.events.filtersSteps',
        }),
        richStep('#events-timeline', 'tours.events.timeline', 'tours.events.timelineDesc', t, {
          tipKey: 'tours.events.timelineTip',
          stepsKey: 'tours.events.timelineSteps',
        }),
        richStep('#events-detail', 'tours.events.detail', 'tours.events.detailDesc', t, {
          side: 'left',
          tipKey: 'tours.events.detailTip',
        }),
      ];
      break;

    case 'users':
      steps = [
        richStep('#users-table', 'tours.users.table', 'tours.users.tableDesc', t, {
          tipKey: 'tours.users.tableTip',
          stepsKey: 'tours.users.tableSteps',
        }),
        richStep('button[data-tour="add-user"]', 'tours.users.add', 'tours.users.addDesc', t, {
          tipKey: 'tours.users.addTip',
          stepsKey: 'tours.users.addSteps',
        }),
      ];
      break;

    case 'addUser':
      steps = [
        richStep('#add-user-dialog', 'tours.addUser.intro', 'tours.addUser.introDesc', t, {
          tipKey: 'tours.addUser.introTip',
          stepsKey: 'tours.addUser.introSteps',
        }),
        richStep('#add-user-name', 'tours.addUser.name', 'tours.addUser.nameDesc', t, {
          tipKey: 'tours.addUser.nameTip',
        }),
        richStep('#add-user-email', 'tours.addUser.email', 'tours.addUser.emailDesc', t, {
          tipKey: 'tours.addUser.emailTip',
        }),
        richStep('#add-user-password', 'tours.addUser.password', 'tours.addUser.passwordDesc', t, {
          tipKey: 'tours.addUser.passwordTip',
          stepsKey: 'tours.addUser.passwordSteps',
        }),
        richStep('#add-user-role', 'tours.addUser.role', 'tours.addUser.roleDesc', t, {
          tipKey: 'tours.addUser.roleTip',
          stepsKey: 'tours.addUser.roleSteps',
        }),
        richStep('#add-user-submit', 'tours.addUser.submit', 'tours.addUser.submitDesc', t, {
          tipKey: 'tours.addUser.submitTip',
        }),
      ];
      break;

    case 'audit':
      steps = [
        richStep('#audit-log', 'tours.audit.log', 'tours.audit.logDesc', t, {
          tipKey: 'tours.audit.logTip',
          stepsKey: 'tours.audit.logSteps',
        }),
      ];
      break;

    case 'health':
      steps = [
        richStep('#health-services', 'tours.health.services', 'tours.health.servicesDesc', t, {
          tourId: 'health',
          tipKey: 'tours.health.servicesTip',
          stepsKey: 'tours.health.servicesSteps',
        }),
        richStep('#health-ai-models', 'tours.health.aiModels', 'tours.health.aiModelsDesc', t, {
          side: 'top',
          tipKey: 'tours.health.aiModelsTip',
          stepsKey: 'tours.health.aiModelsSteps',
        }),
        richStep('button[data-tour="import-model"]', 'tours.health.importModel', 'tours.health.importModelDesc', t, {
          tipKey: 'tours.health.importModelTip',
          stepsKey: 'tours.health.importModelSteps',
        }),
      ];
      break;

    case 'modelImport':
      steps = [
        richStep('#model-import-wizard', 'tours.modelImport.intro', 'tours.modelImport.introDesc', t, {
          tipKey: 'tours.modelImport.introTip',
          stepsKey: 'tours.modelImport.introSteps',
        }),
        richStep('#model-import-step1', 'tours.modelImport.step1', 'tours.modelImport.step1Desc', t, {
          tipKey: 'tours.modelImport.step1Tip',
        }),
        richStep('#model-import-step2', 'tours.modelImport.step2', 'tours.modelImport.step2Desc', t, {
          tipKey: 'tours.modelImport.step2Tip',
          stepsKey: 'tours.modelImport.step2Steps',
        }),
        richStep('#model-import-step3', 'tours.modelImport.step3', 'tours.modelImport.step3Desc', t, {
          tipKey: 'tours.modelImport.step3Tip',
        }),
        richStep('#model-import-step4', 'tours.modelImport.step4', 'tours.modelImport.step4Desc', t, {
          tipKey: 'tours.modelImport.step4Tip',
        }),
        richStep('#model-import-step5', 'tours.modelImport.step5', 'tours.modelImport.step5Desc', t, {
          tipKey: 'tours.modelImport.step5Tip',
          stepsKey: 'tours.modelImport.step5Steps',
        }),
      ];
      break;

    case 'settings':
      steps = [
        richStep('#settings-tabs', 'tours.settings.tabs', 'tours.settings.tabsDesc', t, {
          tipKey: 'tours.settings.tabsTip',
          stepsKey: 'tours.settings.tabsSteps',
        }),
        richStep('#settings-tours', 'tours.settings.toursPanel', 'tours.settings.toursPanelDesc', t, {
          tipKey: 'tours.settings.toursPanelTip',
          stepsKey: 'tours.settings.toursPanelSteps',
        }),
      ];
      break;

    case 'demo':
      steps = [
        richStep('#demo-status', 'tours.demo.banner', 'tours.demo.bannerDesc', t, {
          tourId: 'demo',
          tipKey: 'tours.demo.bannerTip',
          stepsKey: 'tours.demo.bannerSteps',
        }),
        richStep('#demo-video', 'tours.demo.video', 'tours.demo.videoDesc', t, {
          tipKey: 'tours.demo.videoTip',
          stepsKey: 'tours.demo.videoSteps',
        }),
        richStep('#demo-zones', 'tours.demo.zones', 'tours.demo.zonesDesc', t, {
          tipKey: 'tours.demo.zonesTip',
          stepsKey: 'tours.demo.zonesSteps',
        }),
        richStep('#demo-steps', 'tours.demo.steps', 'tours.demo.stepsDesc', t, {
          side: 'left',
          tipKey: 'tours.demo.stepsTip',
        }),
        richStep('#demo-rules-catalog', 'tours.demo.rules', 'tours.demo.rulesDesc', t, {
          tipKey: 'tours.demo.rulesTip',
          stepsKey: 'tours.demo.rulesSteps',
        }),
        richStep('#demo-feed-detections', 'tours.demo.detections', 'tours.demo.detectionsDesc', t, {
          tipKey: 'tours.demo.detectionsTip',
        }),
        richStep('#demo-feed-alerts', 'tours.demo.alertsFeed', 'tours.demo.alertsFeedDesc', t, {
          tipKey: 'tours.demo.alertsFeedTip',
          stepsKey: 'tours.demo.alertsFeedSteps',
        }),
      ];
      break;

    case 'redLightAssistant':
      steps = [
        richStep('#red-light-assistant', 'tours.redLightAssistant.intro', 'tours.redLightAssistant.introDesc', t, {
          tipKey: 'tours.redLightAssistant.introTip',
          stepsKey: 'tours.redLightAssistant.introSteps',
        }),
        richStep('#red-light-step1', 'tours.redLightAssistant.step1', 'tours.redLightAssistant.step1Desc', t, {
          tipKey: 'tours.redLightAssistant.step1Tip',
        }),
        richStep('#red-light-step2', 'tours.redLightAssistant.step2', 'tours.redLightAssistant.step2Desc', t, {
          tipKey: 'tours.redLightAssistant.step2Tip',
        }),
        richStep('#red-light-step3', 'tours.redLightAssistant.step3', 'tours.redLightAssistant.step3Desc', t, {
          tipKey: 'tours.redLightAssistant.step3Tip',
          stepsKey: 'tours.redLightAssistant.step3Steps',
        }),
      ];
      break;

    case 'confirmDialog':
      steps = [
        richStep('#confirm-dialog', 'tours.confirmDialog.intro', 'tours.confirmDialog.introDesc', t, {
          tipKey: 'tours.confirmDialog.introTip',
        }),
        richStep('#confirm-dialog-body', 'tours.confirmDialog.message', 'tours.confirmDialog.messageDesc', t, {
          tipKey: 'tours.confirmDialog.messageTip',
        }),
        richStep('#confirm-dialog-actions', 'tours.confirmDialog.actions', 'tours.confirmDialog.actionsDesc', t, {
          tipKey: 'tours.confirmDialog.actionsTip',
          stepsKey: 'tours.confirmDialog.actionsSteps',
        }),
      ];
      break;

    case 'ruleActivation':
      steps = [
        richStep('#rule-activation-dialog', 'tours.ruleActivation.intro', 'tours.ruleActivation.introDesc', t, {
          tipKey: 'tours.ruleActivation.introTip',
          stepsKey: 'tours.ruleActivation.introSteps',
        }),
        richStep('#rule-activation-step1', 'tours.ruleActivation.step1', 'tours.ruleActivation.step1Desc', t, {
          tipKey: 'tours.ruleActivation.step1Tip',
          stepsKey: 'tours.ruleActivation.step1Steps',
        }),
        richStep('#rule-activation-step2', 'tours.ruleActivation.step2', 'tours.ruleActivation.step2Desc', t, {
          tipKey: 'tours.ruleActivation.step2Tip',
        }),
        richStep('#rule-activation-step3', 'tours.ruleActivation.step3', 'tours.ruleActivation.step3Desc', t, {
          tipKey: 'tours.ruleActivation.step3Tip',
          stepsKey: 'tours.ruleActivation.step3Steps',
        }),
        richStep('#evidence-policy-panel', 'tours.ruleActivation.evidence', 'tours.ruleActivation.evidenceDesc', t, {
          tipKey: 'tours.ruleActivation.evidenceTip',
        }),
        richStep('#rule-activation-step4', 'tours.ruleActivation.step4', 'tours.ruleActivation.step4Desc', t, {
          tipKey: 'tours.ruleActivation.step4Tip',
          stepsKey: 'tours.ruleActivation.step4Steps',
        }),
      ];
      break;

    case 'evidenceViewer':
      steps = [
        richStep('#evidence-viewer', 'tours.evidenceViewer.intro', 'tours.evidenceViewer.introDesc', t, {
          tipKey: 'tours.evidenceViewer.introTip',
          stepsKey: 'tours.evidenceViewer.introSteps',
        }),
        richStep('#evidence-viewer-clip', 'tours.evidenceViewer.clip', 'tours.evidenceViewer.clipDesc', t, {
          tipKey: 'tours.evidenceViewer.clipTip',
        }),
        richStep('#evidence-viewer-images', 'tours.evidenceViewer.images', 'tours.evidenceViewer.imagesDesc', t, {
          tipKey: 'tours.evidenceViewer.imagesTip',
        }),
      ];
      break;

    default:
      steps = [];
  }

  return filterExistingSteps(steps);
}
