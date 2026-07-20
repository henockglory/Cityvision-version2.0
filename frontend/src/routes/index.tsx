import { Suspense, lazy } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import AppLayout from '@/components/layout/AppLayout';
import ProtectedRoute from '@/components/ProtectedRoute';
import SetupGuard from '@/components/SetupGuard';
import Setup from '@/pages/Setup';
import Login from '@/pages/Login';
import Dashboard from '@/pages/Dashboard';
import Cameras from '@/pages/Cameras';
import Users from '@/pages/Users';
import Alerts from '@/pages/Alerts';
import Events from '@/pages/Events';
import LiveView from '@/pages/LiveView';
import Settings from '@/pages/Settings';
import Audit from '@/pages/Audit';
import LoadingState from '@/components/ui/LoadingState';
import { RouteErrorPage } from '@/components/ErrorBoundary';
import { useAuthStore } from '@/stores/authStore';

const Rules = lazy(() => import('@/pages/Rules'));
const Map = lazy(() => import('@/pages/Map'));
const ZoneEditor = lazy(() => import('@/pages/ZoneEditor'));
const VideoWall = lazy(() => import('@/pages/VideoWall'));
const SystemHealth = lazy(() => import('@/pages/SystemHealth'));
const DemoCenter = lazy(() => import('@/pages/DemoCenter'));

function LazyPage({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LoadingState />}>{children}</Suspense>;
}

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
      { path: 'demo', element: <LazyPage><DemoCenter /></LazyPage> },
      {
        path: 'cameras',
        element: (
          <ProtectedRoute roles={['admin', 'operator']}>
            <Cameras />
          </ProtectedRoute>
        ),
      },
      { path: 'live', element: <LiveView /> },
      { path: 'video-wall', element: <LazyPage><VideoWall /></LazyPage> },
      { path: 'map', element: <LazyPage><Map /></LazyPage> },
      {
        path: 'zones',
        element: (
          <ProtectedRoute roles={['admin', 'operator']}>
            <LazyPage><ZoneEditor /></LazyPage>
          </ProtectedRoute>
        ),
      },
      {
        path: 'rules',
        element: (
          <ProtectedRoute roles={['admin', 'operator']}>
            <LazyPage><Rules /></LazyPage>
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
            <LazyPage><SystemHealth /></LazyPage>
          </ProtectedRoute>
        ),
      },
      { path: 'settings', element: <Settings /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]);
