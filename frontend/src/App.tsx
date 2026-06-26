import { RouterProvider } from 'react-router-dom';
import { QueryClient, QueryClientProvider, keepPreviousData } from '@tanstack/react-query';
import ErrorBoundary from '@/components/ErrorBoundary';
import { TooltipProvider } from '@/components/ui/Tooltip';
import { router } from '@/routes';
import { isAuthError, isTransientApiError } from '@/lib/apiErrors';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) => {
        if (isAuthError(error)) return false;
        if (isTransientApiError(error)) return failureCount < 8;
        return failureCount < 4;
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 15_000),
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
      networkMode: 'always',
      placeholderData: keepPreviousData,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <TooltipProvider>
          <RouterProvider router={router} />
        </TooltipProvider>
      </ErrorBoundary>
    </QueryClientProvider>
  );
}
