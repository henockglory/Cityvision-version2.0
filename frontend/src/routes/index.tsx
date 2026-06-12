import { createBrowserRouter, Navigate } from 'react-router-dom';
import AppLayout from '@/components/layout/AppLayout';
import ProtectedRoute from '@/components/ProtectedRoute';
import Login from '@/pages/Login';
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
import { useAuthStore } from '@/stores/authStore';

function AuthRedirect({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (isAuthenticated) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: (
      <AuthRedirect>
        <Login />
      </AuthRedirect>
    ),
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <AppLayout />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <Dashboard /> },
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
