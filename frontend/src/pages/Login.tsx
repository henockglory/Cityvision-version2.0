import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LogIn, Shield, Eye, EyeOff } from 'lucide-react';
import EyeLogo from '@/components/EyeLogo';
import { useAuthStore, demoLogin, apiLogin } from '@/stores/authStore';
import { useSound } from '@/hooks/useSound';

export default function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const { playClick, playSonar } = useSound();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    playClick();

    try {
      const identifier = email.trim();
      const isEmail = identifier.includes('@');
      let result = isEmail ? await apiLogin(identifier, password) : null;

      if (!result && !isEmail) {
        const demo = demoLogin(identifier, password);
        if (demo) {
          result = { ...demo, orgId: null };
        }
      }

      if (!result && isEmail) {
        const demo = demoLogin(identifier.split('@')[0], password);
        if (demo) {
          result = { ...demo, orgId: null };
        }
      }

      if (result) {
        login(result.user, result.token, result.orgId);
        playSonar();
        navigate('/');
      } else {
        setError(t('login.error'));
      }
    } finally {
      setLoading(false);
    }
  };

  const demoAccounts = [
    { user: 'admin@citevision.local', pass: 'Citevision123!', role: 'admin' },
    { user: 'admin', pass: 'admin', role: 'demo' },
  ];

  return (
    <div className="min-h-screen flex items-center justify-center cv-grid-bg relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-cv-deep via-cv-navy to-cv-deep" />
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-cv-accent/5 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-cv-accent/5 rounded-full blur-3xl" />

      <div className="relative z-10 w-full max-w-md px-4 animate-fade-in">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <EyeLogo size={64} />
          </div>
          <h1 className="font-display text-3xl font-bold text-cv-accent tracking-wider">
            {t('app.name')}
          </h1>
          <p className="text-cv-muted mt-2">{t('app.tagline')}</p>
        </div>

        <form onSubmit={handleSubmit} className="cv-card p-8 space-y-5">
          <h2 className="font-display text-xl font-semibold text-center">{t('login.title')}</h2>
          <p className="text-sm text-cv-muted text-center -mt-2">{t('login.subtitle')}</p>

          {error && (
            <div className="px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm text-center">
              {error}
            </div>
          )}

          <div>
            <label className="cv-label" htmlFor="email">{t('login.username')}</label>
            <input
              id="email"
              type="text"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="cv-input"
              autoComplete="username"
              placeholder="admin@citevision.local"
              required
            />
          </div>

          <div>
            <label className="cv-label" htmlFor="password">{t('login.password')}</label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="cv-input pr-10"
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-cv-muted hover:text-cv-accent"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <button type="submit" disabled={loading} className="cv-btn-primary w-full py-3">
            <LogIn className="w-4 h-4" />
            {t('login.submit')}
          </button>
        </form>

        <div className="mt-6 cv-card p-4">
          <p className="text-xs text-cv-muted text-center mb-3 flex items-center justify-center gap-1">
            <Shield className="w-3 h-3" />
            {t('login.demo')}
          </p>
          <div className="grid grid-cols-2 gap-2">
            {demoAccounts.map((acc) => (
              <button
                key={acc.user}
                type="button"
                onClick={() => {
                  playClick();
                  setEmail(acc.user);
                  setPassword(acc.pass);
                }}
                className="cv-btn-secondary py-2 text-xs"
              >
                {acc.role}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
