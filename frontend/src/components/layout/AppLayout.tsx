import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Navbar from './Navbar';
import MainContent from './MainContent';
import OnboardingTour from '@/components/OnboardingTour';
import DemoBanner from '@/components/DemoBanner';
import PremiumNetworkBackground from '@/components/PremiumNetworkBackground';
import { useAlertWebSocket } from '@/hooks/useAlertWebSocket';
import { useProactiveTokenRefresh } from '@/hooks/useProactiveTokenRefresh';
import { useEnsureSiteId } from '@/hooks/useEnsureSiteId';
import { useUiStore } from '@/stores/uiStore';
import { BUILD_ID } from '@/lib/buildInfo';

export default function AppLayout() {
  useAlertWebSocket();
  useProactiveTokenRefresh();
  useEnsureSiteId();
  const mobileOpen = useUiStore((s) => s.mobileSidebarOpen);
  const setMobileOpen = useUiStore((s) => s.setMobileSidebarOpen);

  return (
    <div className="min-h-screen relative bg-cv-deep">
      <PremiumNetworkBackground />
      <div className="relative z-10">
        <Sidebar />
        {mobileOpen && (
          <>
            <div className="cv-sidebar-overlay" onClick={() => setMobileOpen(false)} aria-hidden />
            <Sidebar mobile />
          </>
        )}
        <Navbar />
        <MainContent>
          <DemoBanner />
          <Outlet />
        </MainContent>
        <OnboardingTour enabled />
        {/* Build marker — hidden in production, visible only in dev */}
        {import.meta.env.DEV && (
          <span
            className="fixed bottom-2 right-2 z-[5] text-[10px] text-cv-muted/30 pointer-events-none select-none"
            aria-hidden="true"
          >
            {BUILD_ID}
          </span>
        )}
      </div>
    </div>
  );
}
