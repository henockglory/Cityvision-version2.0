import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { TourId } from '@/lib/tourRegistry';

function applyTheme(theme: 'dark' | 'light') {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  document.documentElement.classList.toggle('light', theme === 'light');
}

const ZONE_EDITOR_CAMERA_KEY = (orgId: string) => `citevision.zoneEditor.camera.${orgId}`;

export function readZoneEditorCameraFromStorage(orgId: string): string | null {
  try {
    return localStorage.getItem(ZONE_EDITOR_CAMERA_KEY(orgId));
  } catch {
    return null;
  }
}

/** Read camera from cv-ui JSON before Zustand rehydration completes. */
export function readZoneEditorCameraFromCvUi(orgId: string): string | null {
  try {
    const raw = localStorage.getItem('cv-ui');
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { state?: { zoneEditorCameraByOrg?: Record<string, string> } };
    return parsed.state?.zoneEditorCameraByOrg?.[orgId] ?? null;
  } catch {
    return null;
  }
}

export function resolvePersistedZoneEditorCameraId(
  orgId: string | null | undefined,
  fromStore?: string,
): string | null {
  try {
    const last = localStorage.getItem('citevision.zoneEditor.lastCameraId');
    if (last) return last;
  } catch {
    /* ignore */
  }
  if (!orgId) return null;
  return fromStore ?? readZoneEditorCameraFromStorage(orgId) ?? readZoneEditorCameraFromCvUi(orgId);
}

function writeZoneEditorCameraToStorage(orgId: string, cameraId: string) {
  try {
    localStorage.setItem(ZONE_EDITOR_CAMERA_KEY(orgId), cameraId);
    localStorage.setItem('citevision.zoneEditor.lastCameraId', cameraId);
  } catch {
    /* ignore quota / private mode */
  }
}

export function writeZoneEditorCameraSelection(orgId: string | null | undefined, cameraId: string) {
  if (orgId) {
    writeZoneEditorCameraToStorage(orgId, cameraId);
    return;
  }
  try {
    localStorage.setItem('citevision.zoneEditor.lastCameraId', cameraId);
  } catch {
    /* ignore */
  }
}

interface UiStore {
  theme: 'dark' | 'light';
  sidebarCollapsed: boolean;
  mobileSidebarOpen: boolean;
  soundMuted: boolean;
  soundUiEnabled: boolean;
  soundAlertsEnabled: boolean;
  tooltipsEnabled: boolean;
  networkEffectEnabled: boolean;
  onboardingCompleted: boolean;
  toursEnabled: boolean;
  toursAutoStart: boolean;
  completedTours: Partial<Record<TourId, boolean>>;
  /** Last Zone Editor camera per org — only updated on explicit user pick */
  zoneEditorCameraByOrg: Record<string, string>;
  toggleTheme: () => void;
  setTheme: (theme: 'dark' | 'light') => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setMobileSidebarOpen: (open: boolean) => void;
  toggleSound: () => void;
  toggleSoundUi: () => void;
  toggleSoundAlerts: () => void;
  toggleTooltips: () => void;
  toggleNetworkEffect: () => void;
  completeOnboarding: () => void;
  completeTour: (tourId: TourId) => void;
  resetTour: (tourId: TourId) => void;
  resetAllTours: () => void;
  toggleToursEnabled: () => void;
  toggleToursAutoStart: () => void;
  setZoneEditorCamera: (orgId: string, cameraId: string) => void;
}

export const useUiStore = create<UiStore>()(
  persist(
    (set) => ({
      theme: 'dark',
      sidebarCollapsed: false,
      mobileSidebarOpen: false,
      soundMuted: false,
      soundUiEnabled: true,
      soundAlertsEnabled: true,
      tooltipsEnabled: true,
      networkEffectEnabled: false,
      onboardingCompleted: false,
      toursEnabled: true,
      toursAutoStart: true,
      completedTours: {},
      zoneEditorCameraByOrg: {},
      toggleTheme: () =>
        set((s) => {
          const next = s.theme === 'dark' ? 'light' : 'dark';
          applyTheme(next);
          return { theme: next };
        }),
      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      setMobileSidebarOpen: (open) => set({ mobileSidebarOpen: open }),
      toggleSound: () => set((s) => ({ soundMuted: !s.soundMuted })),
      toggleSoundUi: () => set((s) => ({ soundUiEnabled: !s.soundUiEnabled })),
      toggleSoundAlerts: () => set((s) => ({ soundAlertsEnabled: !s.soundAlertsEnabled })),
      toggleTooltips: () => set((s) => ({ tooltipsEnabled: !s.tooltipsEnabled })),
      toggleNetworkEffect: () => set((s) => ({ networkEffectEnabled: !s.networkEffectEnabled })),
      completeOnboarding: () => set({ onboardingCompleted: true }),
      completeTour: (tourId) =>
        set((s) => ({ completedTours: { ...s.completedTours, [tourId]: true } })),
      resetTour: (tourId) =>
        set((s) => {
          const next = { ...s.completedTours };
          delete next[tourId];
          return { completedTours: next };
        }),
      resetAllTours: () => set({ completedTours: {} }),
      toggleToursEnabled: () => set((s) => ({ toursEnabled: !s.toursEnabled })),
      toggleToursAutoStart: () => set((s) => ({ toursAutoStart: !s.toursAutoStart })),
      setZoneEditorCamera: (orgId, cameraId) => {
        writeZoneEditorCameraToStorage(orgId, cameraId);
        set((s) => ({
          zoneEditorCameraByOrg: { ...s.zoneEditorCameraByOrg, [orgId]: cameraId },
        }));
      },
    }),
    {
      name: 'cv-ui',
      partialize: (state) => ({
        theme: state.theme,
        sidebarCollapsed: state.sidebarCollapsed,
        mobileSidebarOpen: state.mobileSidebarOpen,
        soundMuted: state.soundMuted,
        soundUiEnabled: state.soundUiEnabled,
        soundAlertsEnabled: state.soundAlertsEnabled,
        tooltipsEnabled: state.tooltipsEnabled,
        networkEffectEnabled: state.networkEffectEnabled,
        onboardingCompleted: state.onboardingCompleted,
        toursEnabled: state.toursEnabled,
        toursAutoStart: state.toursAutoStart,
        completedTours: state.completedTours,
        zoneEditorCameraByOrg: state.zoneEditorCameraByOrg,
      }),
      merge: (persisted, current) => ({
        ...current,
        ...(persisted as object),
        zoneEditorCameraByOrg: {
          ...current.zoneEditorCameraByOrg,
          ...((persisted as { zoneEditorCameraByOrg?: Record<string, string> })?.zoneEditorCameraByOrg ?? {}),
        },
      }),
      onRehydrateStorage: () => (state) => {
        if (state) applyTheme(state.theme);
      },
    },
  ),
);
