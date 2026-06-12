import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Navbar from './Navbar';
import MainContent from './MainContent';
import OnboardingTour from '@/components/OnboardingTour';

export default function AppLayout() {
  return (
    <div className="min-h-screen">
      <Sidebar />
      <Navbar />
      <MainContent>
        <Outlet />
      </MainContent>
      <OnboardingTour enabled />
    </div>
  );
}
