import { useState, type FormEvent, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Building2, UserPlus, CheckCircle, ChevronRight, ChevronLeft, Loader2, HelpCircle,
} from 'lucide-react';
import EyeLogo from '@/components/EyeLogo';
import PremiumNetworkBackground from '@/components/PremiumNetworkBackground';
import ThemeToggle from '@/components/ThemeToggle';
import Tooltip from '@/components/ui/Tooltip';
import { useInitializeSetup } from '@/hooks/api/queries';
import { useAuthStore } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';
import { useAutoPageTour } from '@/hooks/useAutoPageTour';
import { useUiStore } from '@/stores/uiStore';
import { isPasswordStrongEnough } from '@/utils/setup';
import { isAxiosError } from 'axios';

type Step = 1 | 2 | 3;

export default function Setup() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { playClick, playSonar } = useSound();
  const setSiteId = useAuthStore((s) => s.setSiteId);
  const initMutation = useInitializeSetup();
  const toursEnabled = useUiStore((s) => s.toursEnabled);

  const [step, setStep] = useState<Step>(1);
  const [orgName, setOrgName] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');

  const prepareTourStep = useCallback((selector: string) => {
    const map: Record<string, Step> = {
      '#setup-step1': 1,
      '#setup-step2': 2,
      '#setup-step3': 3,
    };
    const n = map[selector];
    if (n) setStep(n);
  }, []);

  const startTour = useAutoPageTour('setup', { prepareStep: prepareTourStep });

  const handleFinish = async () => {
    setError('');
    playClick();
    try {
      const { data } = await initMutation.mutateAsync({
        orgName: orgName.trim(),
        adminEmail: adminEmail.trim(),
        adminPassword,
      });
      if (data.org_id) {
        localStorage.setItem('cv_org_id', data.org_id);
      }
      if (data.site_id) {
        setSiteId(data.site_id);
      }
      playSonar();
      navigate('/login');
    } catch (err) {
      if (isAxiosError(err)) {
        if (!err.response) {
          setError(t('setup.errorBackend', 'Impossible de joindre le serveur. Lancez scripts/start-windows.ps1'));
        } else {
          const msg = (err.response.data as { error?: string })?.error;
          setError(msg || t('setup.error'));
        }
      } else {
        setError(t('setup.error'));
      }
    }
  };

  const handleNext = (e: FormEvent) => {
    e.preventDefault();
    setError('');
    playClick();

    if (step === 2) {
      if (adminPassword !== confirmPassword) {
        setError(t('setup.passwordMismatch'));
        return;
      }
      if (!isPasswordStrongEnough(adminPassword)) {
        setError(t('setup.passwordWeak', 'Mot de passe: 12 caracteres minimum, majuscule, minuscule et chiffre'));
        return;
      }
    }

    if (step < 3) {
      setStep((s) => (s + 1) as Step);
    } else {
      void handleFinish();
    }
  };

  const steps = [
    { n: 1, label: t('setup.step1'), icon: Building2 },
    { n: 2, label: t('setup.step2'), icon: UserPlus },
    { n: 3, label: t('setup.step3'), icon: CheckCircle },
  ];

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden bg-[var(--cv-deep)]">
      <PremiumNetworkBackground />
      <div className="absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-black/60 pointer-events-none" />

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

      <div className="relative z-10 w-full max-w-lg mx-auto px-4 animate-fade-in">
        <div id="setup-brand" className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <EyeLogo size={64} />
          </div>
          <h1 className="font-display text-3xl font-bold text-cv-accent tracking-wider">
            {t('setup.title')}
          </h1>
          <p className="text-cv-muted mt-2">{t('setup.subtitle')}</p>
        </div>

        <div id="setup-progress" className="flex items-center justify-center gap-3 mb-6">
          {steps.map((s, i) => (
            <div key={s.n} className="flex items-center gap-2">
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm ${
                step === s.n ? 'border-cv-accent bg-cv-accent/10 text-cv-accent' :
                step > s.n ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400' :
                'border-cv-border text-cv-muted'
              }`}>
                <s.icon className="w-4 h-4" />
                <span className="hidden sm:inline">{s.label}</span>
              </div>
              {i < 2 && <ChevronRight className="w-4 h-4 text-cv-muted" />}
            </div>
          ))}
        </div>

        <form id="setup-form" onSubmit={handleNext} className="cv-card p-8 space-y-5">
          {error && (
            <div className="px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm text-center">
              {error}
            </div>
          )}

          {step === 1 && (
            <div id="setup-step1">
              <label className="cv-label" htmlFor="orgName">{t('setup.orgName')}</label>
              <input
                id="orgName"
                type="text"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                className="cv-input"
                required
                autoFocus
              />
            </div>
          )}

          {step === 2 && (
            <div id="setup-step2" className="space-y-4">
              <div>
                <label className="cv-label" htmlFor="adminEmail">{t('setup.adminEmail')}</label>
                <input
                  id="adminEmail"
                  type="email"
                  value={adminEmail}
                  onChange={(e) => setAdminEmail(e.target.value)}
                  className="cv-input"
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="cv-label" htmlFor="adminPassword">{t('setup.adminPassword')}</label>
                <input
                  id="adminPassword"
                  type="password"
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  className="cv-input"
                  required
                  minLength={12}
                />
              </div>
              <div>
                <label className="cv-label" htmlFor="confirmPassword">{t('setup.confirmPassword')}</label>
                <input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="cv-input"
                  required
                  minLength={8}
                />
              </div>
            </div>
          )}

          {step === 3 && (
            <div id="setup-step3" className="space-y-4">
              <div className="p-4 rounded-lg bg-cv-deep/50 border border-cv-border">
                <p className="text-xs text-cv-muted uppercase tracking-wider mb-1">{t('setup.summaryOrg')}</p>
                <p className="font-medium">{orgName}</p>
              </div>
              <div className="p-4 rounded-lg bg-cv-deep/50 border border-cv-border">
                <p className="text-xs text-cv-muted uppercase tracking-wider mb-1">{t('setup.summaryEmail')}</p>
                <p className="font-medium">{adminEmail}</p>
              </div>
            </div>
          )}

          <div className="flex justify-between pt-2">
            <button
              type="button"
              onClick={() => {
                playClick();
                if (step > 1) setStep((s) => (s - 1) as Step);
              }}
              disabled={step === 1}
              className="cv-btn-secondary"
            >
              <ChevronLeft className="w-4 h-4" />
              {t('setup.back')}
            </button>
            <button id="setup-submit" type="submit" disabled={initMutation.isPending} className="cv-btn-primary">
              {initMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : step === 3 ? (
                <CheckCircle className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
              {step === 3 ? t('setup.finish') : t('setup.next')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
