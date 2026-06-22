import { Component, type ErrorInfo, type ReactNode } from 'react';
import { useRouteError, Link } from 'react-router-dom';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary:', error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-[50vh] flex items-center justify-center p-6">
          <div className="cv-card max-w-lg w-full p-8 text-center">
            <AlertTriangle className="w-12 h-12 text-metric-alerts mx-auto mb-4" />
            <h1 className="font-display text-xl font-semibold text-cv-text mb-2">
              {this.props.fallbackTitle ?? 'Une erreur est survenue'}
            </h1>
            <p className="text-sm text-cv-muted mb-4">
              {this.state.error.message || 'Erreur inattendue de l&apos;interface.'}
            </p>
            <button
              type="button"
              className="cv-btn-primary"
              onClick={() => window.location.reload()}
            >
              <RefreshCw className="w-4 h-4" />
              Recharger la page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export function RouteErrorPage() {
  const err = useRouteError() as Error | { statusText?: string; message?: string };
  const message = err instanceof Error ? err.message : (err?.message ?? err?.statusText ?? 'Page indisponible');

  return (
    <div className="min-h-[60vh] flex items-center justify-center p-6">
      <div className="cv-card max-w-lg w-full p-8 text-center">
        <AlertTriangle className="w-12 h-12 text-metric-alerts mx-auto mb-4" />
        <h1 className="font-display text-xl font-semibold mb-2">Impossible d&apos;afficher cette page</h1>
        <p className="text-sm text-cv-muted mb-6">{message}</p>
        <div className="flex gap-3 justify-center flex-wrap">
          <Link to="/" className="cv-btn-primary">
            <Home className="w-4 h-4" />
            Accueil
          </Link>
          <button type="button" className="cv-btn-secondary" onClick={() => window.location.reload()}>
            <RefreshCw className="w-4 h-4" />
            Recharger
          </button>
        </div>
      </div>
    </div>
  );
}
