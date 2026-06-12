import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Search, LogOut, User, Globe } from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import MuteToggle from '@/components/MuteToggle';
import { useAuthStore } from '@/stores/authStore';
import { useUiStore } from '@/stores/uiStore';
import { useSound } from '@/hooks/useSound';

export default function Navbar() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const sidebarCollapsed = useUiStore((s) => s.sidebarCollapsed);
  const { playClick } = useSound();
  const [search, setSearch] = useState('');

  const handleLogout = () => {
    playClick();
    logout();
    navigate('/login');
  };

  const toggleLang = () => {
    playClick();
    const next = i18n.language === 'fr' ? 'en' : 'fr';
    void i18n.changeLanguage(next);
  };

  return (
    <header
      className={`fixed top-0 right-0 z-30 h-16 bg-cv-navy/80 backdrop-blur-md border-b border-cv-border transition-all duration-300 ${
        sidebarCollapsed ? 'left-[72px]' : 'left-64'
      }`}
    >
      <div className="flex items-center justify-between h-full px-6">
        <div id="navbar-search" className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-cv-muted" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('common.search')}
            className="cv-input pl-10 py-2 text-sm"
          />
        </div>

        <div className="flex items-center gap-1 ml-4">
          <button type="button" onClick={toggleLang} className="cv-btn-ghost p-2 rounded-lg" title="Language">
            <Globe className="w-5 h-5" />
            <span className="text-xs font-medium uppercase">{i18n.language}</span>
          </button>
          <MuteToggle />
          <ThemeToggle />

          {user && (
            <div className="flex items-center gap-3 ml-3 pl-3 border-l border-cv-border">
              <div className="hidden sm:flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-cv-accent/20 border border-cv-accent/30 flex items-center justify-center">
                  <User className="w-4 h-4 text-cv-accent" />
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-[var(--cv-text)]">{user.username}</p>
                  <p className="text-[10px] text-cv-muted uppercase tracking-wider">{t(`roles.${user.role}`)}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={handleLogout}
                className="cv-btn-ghost p-2 rounded-lg text-cv-muted hover:text-red-400"
                title={t('nav.logout')}
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
