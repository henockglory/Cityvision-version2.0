import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UiStore {
  theme: 'dark' | 'light';
  sidebarCollapsed: boolean;
  soundMuted: boolean;
  onboardingCompleted: boolean;
  toggleTheme: () => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSound: () => void;
  completeOnboarding: () => void;
}

export const useUiStore = create<UiStore>()(
  persist(
    (set) => ({
      theme: 'dark',
      sidebarCollapsed: false,
      soundMuted: false,
      onboardingCompleted: false,
      toggleTheme: () =>
        set((s) => {
          const next = s.theme === 'dark' ? 'light' : 'dark';
          document.documentElement.classList.toggle('dark', next === 'dark');
          document.documentElement.classList.toggle('light', next === 'light');
          return { theme: next };
        }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      toggleSound: () => set((s) => ({ soundMuted: !s.soundMuted })),
      completeOnboarding: () => set({ onboardingCompleted: true }),
    }),
    {
      name: 'cv-ui',
      onRehydrateStorage: () => (state) => {
        if (state) {
          document.documentElement.classList.toggle('dark', state.theme === 'dark');
          document.documentElement.classList.toggle('light', state.theme === 'light');
        }
      },
    }
  )
);
