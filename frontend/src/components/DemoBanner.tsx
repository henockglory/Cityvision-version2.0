import { Link } from 'react-router-dom';
import { Sparkles, X } from 'lucide-react';
import { useCameras } from '@/hooks/api/queries';
import { useUiStore } from '@/stores/uiStore';

export default function DemoBanner() {
  const { data: cameras = [] } = useCameras();
  const dismissed = useUiStore((s) => s.onboardingCompleted);
  const completeOnboarding = useUiStore((s) => s.completeOnboarding);

  const hasDemo = cameras.some((c) => {
    const meta = c.metadata ?? {};
    return meta.demo === true || meta.virtual === true || c.name.toLowerCase().includes('demo');
  });

  if (!hasDemo || dismissed) return null;

  return (
    <div className="mb-4 flex items-center gap-3 px-4 py-3 rounded-xl border border-amber-500/30 bg-amber-500/10 text-sm">
      <Sparkles className="w-5 h-5 text-amber-500 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="font-medium text-cv-text">Mode démo actif</p>
        <p className="text-cv-muted text-xs mt-0.5">
          Données de démonstration (caméra virtuelle, règles seed).{' '}
          <Link to="/settings" className="text-cv-accent underline">
            Réinitialiser dans Paramètres
          </Link>
        </p>
      </div>
      <button type="button" onClick={completeOnboarding} className="cv-btn-ghost p-1.5" aria-label="Masquer">
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
