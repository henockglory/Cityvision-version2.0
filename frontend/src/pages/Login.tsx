import { isAxiosError } from 'axios';
import { useCallback, useMemo, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LogIn, Eye, EyeOff, HelpCircle } from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import EyeLogo from '@/components/EyeLogo';
import InfoTip from '@/components/ui/InfoTip';
import PremiumNetworkBackground from '@/components/PremiumNetworkBackground';
import EarthzoomCinema from '@/components/auth/EarthzoomCinema';
import { useAuthStore, apiLogin } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import { useUiStore } from '@/stores/uiStore';
import Tooltip from '@/components/ui/Tooltip';
import type { EarthzoomPhase } from '@/lib/earthzoomCinema';
import type { User } from '@/types';

type PendingAuth = {
  user: User;
  token: string;
  orgId: string | null;
  siteId: string | null;
};

function usePrefersReducedMotion(): boolean {
  return useMemo(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  );
}

export default function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const { playClick, playSonar } = useSound();
  const startTour = useAutoPageTour('login');
  const toursEnabled = useUiStore((s) => s.toursEnabled);
  const reducedMotion = usePrefersReducedMotion();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState<EarthzoomPhase>(() => (reducedMotion ? 'frozen' : 'intro'));
  const pendingAuthRef = useRef<PendingAuth | null>(null);

  const enterApp = useCallback(
    (auth: PendingAuth) => {
      login(auth.user, auth.token, auth.orgId, auth.siteId);
      playSonar();
      navigate('/');
    },
    [login, navigate, playSonar],
  );

  const onIntroFrozen = useCallback(() => {
    setPhase('frozen');
  }, []);

  const onOutroEnded = useCallback(() => {
    const auth = pendingAuthRef.current;
    if (!auth) return;
    pendingAuthRef.current = null;
    enterApp(auth);
  }, [enterApp]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    playClick();

    try {
      const result = await apiLogin(email.trim(), password);
      const auth: PendingAuth = {
        user: result.user,
        token: result.token,
        orgId: result.orgId,
        siteId: result.siteId,
      };
      if (reducedMotion) {
        enterApp(auth);
      } else {
        pendingAuthRef.current = auth;
        setPhase('outro');
      }
    } catch (err) {
      if (isAxiosError(err)) {
        if (!err.response) {
          setError(t('login.errorBackend', 'Impossible de joindre le serveur. Lancez scripts/start-linux.sh'));
        } else if (err.response.status === 503) {
          setError(
            t(
              'login.errorSessionStore',
              'Session indisponible (Redis). Relancez Start-CiteVision.ps1 ou attendez le heal automatique.',
            ),
          );
        } else if (err.response.status === 401) {
          setError(t('login.error'));
        } else {
          setError(t('login.error'));
        }
      } else {
        setError(t('login.error'));
      }
    } finally {
      setLoading(false);
    }
  };

  const showForm = reducedMotion || phase === 'frozen';
  const busy = loading || phase === 'outro';

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden bg-cv-deep">
      {reducedMotion ? (
        <PremiumNetworkBackground />
      ) : (
        <EarthzoomCinema
          phase={phase}
          onIntroFrozen={onIntroFrozen}
          onOutroEnded={onOutroEnded}
        />
      )}
      <div className="absolute top-4 right-4 z-20 flex items-center gap-2">
        {toursEnabled && (
          <Tooltip content={t('pageHeader.tourHint', 'Guide pas à pas : menus, champs et procédures expliqués simplement.')}>
            <button
              type="button"
              className="cv-btn-ghost p-2"
              onClick={startTour}
              aria-label={t('pageHeader.tourAriaLabel', 'Tutoriel guidé')}
            >
              <HelpCircle className="w-4 h-4" />
            </button>
          </Tooltip>
        )}
        <ThemeToggle />
      </div>

      {showForm && (
        <div className="relative z-10 w-full max-w-md mx-auto px-4 animate-fade-in">
          <div id="login-brand" className="text-center mb-8">
            <div className="flex justify-center mb-4">
              <EyeLogo size={64} />
            </div>
            <h1 className="font-display text-3xl font-bold text-cv-accent tracking-wider">
              {t('app.name')}
            </h1>
            <p className="text-cv-muted mt-2">{t('app.tagline')}</p>
          </div>

          <form id="login-form" onSubmit={handleSubmit} className="cv-card p-8 space-y-5 backdrop-blur-sm bg-cv-surface/80">
            <h2 className="font-display text-xl font-semibold text-center">{t('login.title')}</h2>
            <p className="text-sm text-cv-muted text-center -mt-2">{t('login.subtitle')}</p>

            {error && (
              <div className="px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm text-center">
                {error}
              </div>
            )}

            <div id="login-email-field">
              <label className="cv-label flex items-center gap-1" htmlFor="email">
                {t('login.username')}
                <InfoTip helpKey="loginEmail" content={t('login.emailHint', 'Adresse e-mail fournie par votre administrateur CitéVision.')} />
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="cv-input"
                autoComplete="username"
                required
                disabled={busy}
              />
            </div>

            <div id="login-password-field">
              <label className="cv-label flex items-center gap-1" htmlFor="password">
                {t('login.password')}
                <InfoTip helpKey="loginPassword" content={t('login.passwordHint', 'Mot de passe personnel. Cliquez sur l\'œil pour l\'afficher temporairement.')} />
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="cv-input pr-10"
                  autoComplete="current-password"
                  required
                  disabled={busy}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-cv-muted hover:text-cv-accent"
                  aria-label={showPassword ? t('login.hidePassword', 'Masquer') : t('login.showPassword', 'Afficher')}
                  disabled={busy}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button id="login-submit" type="submit" disabled={busy} className="cv-btn-primary w-full py-3">
              <LogIn className="w-4 h-4" />
              {t('login.submit')}
            </button>

            <div className="text-xs text-center text-cv-muted border-t border-cv-border pt-4 space-y-1">
              <p>{t('login.copyright')}</p>
              <p>
                {t('login.support')}{' '}
                <a href="mailto:info@hologram.cd" className="text-cv-accent hover:underline">info@hologram.cd</a>
              </p>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
