import { createBrowserRouter, Navigate } from 'react-router-dom';
import AppLayout from '@/components/layout/AppLayout';
import ProtectedRoute from '@/components/ProtectedRoute';
import SetupGuard from '@/components/SetupGuard';
import Setup from '@/pages/Setup';
import Login from '@/pages/Login';
import DemoCenter from '@/pages/DemoCenter';
import Dashboard from '@/pages/Dashboard';
import Cameras from '@/pages/Cameras';
import Users from '@/pages/Users';
import Rules from '@/pages/Rules';
import Alerts from '@/pages/Alerts';
import Events from '@/pages/Events';
import LiveView from '@/pages/LiveView';
import VideoWall from '@/pages/VideoWall';
import Map from '@/pages/Map';
import ZoneEditor from '@/pages/ZoneEditor';
import Settings from '@/pages/Settings';
import Audit from '@/pages/Audit';
import SystemHealth from '@/pages/SystemHealth';
import { RouteErrorPage } from '@/components/ErrorBoundary';
import { useAuthStore } from '@/stores/authStore';

function AuthRedirect({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const token = useAuthStore((s) => s.token);
  if (isAuthenticated && token) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function GuardedApp({ children }: { children: React.ReactNode }) {
  return <SetupGuard>{children}</SetupGuard>;
}

export const router = createBrowserRouter([
  {
    path: '/setup',
    element: (
      <GuardedApp>
        <Setup />
      </GuardedApp>
    ),
  },
  {
    path: '/login',
    element: (
      <GuardedApp>
        <AuthRedirect>
          <Login />
        </AuthRedirect>
      </GuardedApp>
    ),
  },
  {
    path: '/',
    element: (
      <GuardedApp>
        <ProtectedRoute>
          <AppLayout />
        </ProtectedRoute>
      </GuardedApp>
    ),
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'demo', element: <DemoCenter /> },
      {
        path: 'cameras',
        element: (
          <ProtectedRoute roles={['admin', 'operator']}>
            <Cameras />
          </ProtectedRoute>
        ),
      },
      { path: 'live', element: <LiveView /> },
      { path: 'video-wall', element: <VideoWall /> },
      { path: 'map', element: <Map /> },
      {
        path: 'zones',
        element: (
          <ProtectedRoute roles={['admin', 'operator']}>
            <ZoneEditor />
          </ProtectedRoute>
        ),
      },
      {
        path: 'rules',
        element: (
          <ProtectedRoute roles={['admin', 'operator']}>
            <Rules />
          </ProtectedRoute>
        ),
      },
      { path: 'alerts', element: <Alerts /> },
      { path: 'events', element: <Events /> },
      {
        path: 'users',
        element: (
          <ProtectedRoute roles={['admin']}>
            <Users />
          </ProtectedRoute>
        ),
      },
      {
        path: 'audit',
        element: (
          <ProtectedRoute roles={['admin']}>
            <Audit />
          </ProtectedRoute>
        ),
      },
      {
        path: 'health',
        element: (
          <ProtectedRoute roles={['admin', 'operator']}>
            <SystemHealth />
          </ProtectedRoute>
        ),
      },
      { path: 'settings', element: <Settings /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]);
