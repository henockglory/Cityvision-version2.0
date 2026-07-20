import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Search, LogOut, User, Globe, Menu } from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import MuteToggle from '@/components/MuteToggle';
import Tooltip from '@/components/ui/Tooltip';
import { useAuthStore } from '@/stores/authStore';
import { useUiStore } from '@/stores/uiStore';
import { useSound } from '@/hooks/useSound';
import { getAllNavItemsForSearch } from '@/config/navigation';
import { useAlerts, useCameras, useRules } from '@/hooks/api/queries';

export default function Navbar() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const sidebarCollapsed = useUiStore((s) => s.sidebarCollapsed);
  const setMobileOpen = useUiStore((s) => s.setMobileSidebarOpen);
  const { playClick } = useSound();
  const [search, setSearch] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);

  const { data: cameras = [] } = useCameras();
  const { data: rules = [] } = useRules();
  const { data: alerts = [] } = useAlerts();

  const searchResults = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (q.length < 2) return [];
    const nav = user ? getAllNavItemsForSearch(user.role) : [];
    const navHits = nav
      .filter((n) => t(n.labelKey).toLowerCase().includes(q))
      .map((n) => ({ type: 'page' as const, label: t(n.labelKey), path: n.path }));
    const camHits = cameras
      .filter((c) => c.name.toLowerCase().includes(q))
      .slice(0, 3)
      .map((c) => ({ type: 'camera' as const, label: c.name, path: `/cameras` }));
    const ruleHits = rules
      .filter((r) => r.name.toLowerCase().includes(q))
      .slice(0, 3)
      .map((r) => ({ type: 'rule' as const, label: r.name, path: '/rules' }));
    const alertHits = alerts
      .filter((a) => a.message.toLowerCase().includes(q))
      .slice(0, 3)
      .map((a) => ({ type: 'alert' as const, label: a.message.slice(0, 60), path: '/alerts' }));
    return [...navHits, ...camHits, ...ruleHits, ...alertHits].slice(0, 8);
  }, [search, user, t, cameras, rules, alerts]);

  const handleLogout = () => {
    playClick();
    logout();
    navigate('/login');
  };

  const toggleLang = () => {
    playClick();
    void i18n.changeLanguage(i18n.language === 'fr' ? 'en' : 'fr');
  };

  const goTo = (path: string) => {
    playClick();
    navigate(path);
    setSearch('');
    setSearchOpen(false);
  };

  return (
    <header
      className={`fixed top-0 right-0 z-30 h-16 bg-cv-black/90 backdrop-blur-xl border-b border-cv-border/60 transition-all duration-300 left-0 ${
        sidebarCollapsed ? 'lg:left-[72px]' : 'lg:left-64'
      }`}
    >
      <div className="flex items-center justify-between h-full px-4 lg:px-6 gap-3">
        <Tooltip content={t('common.menu', 'Menu')}>
          <button
            type="button"
            className="cv-btn-ghost p-2 lg:hidden shrink-0"
            onClick={() => setMobileOpen(true)}
            aria-label="Menu"
          >
            <Menu className="w-5 h-5" />
          </button>
        </Tooltip>

        <div id="navbar-search" className="relative flex-1 max-w-md min-w-0">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-cv-muted" />
          <input
            type="search"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setSearchOpen(true); }}
            onFocus={() => setSearchOpen(true)}
            onBlur={() => window.setTimeout(() => setSearchOpen(false), 150)}
            placeholder={t('common.search')}
            className="cv-input pl-10 py-2 text-sm w-full"
          />
          {searchOpen && searchResults.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 cv-card py-1 z-50 max-h-64 overflow-y-auto">
              {searchResults.map((hit, i) => (
                <button
                  key={`${hit.type}-${hit.path}-${i}`}
                  type="button"
                  className="w-full text-left px-4 py-2 text-sm hover:bg-cv-accent/5 flex items-center gap-2"
                  onMouseDown={() => goTo(hit.path)}
                >
                  <span className="text-[10px] uppercase text-cv-muted w-14">{hit.type}</span>
                  <span className="truncate text-cv-text">{hit.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0 min-w-0">
          <Tooltip content={t('settings.language', 'Changer la langue')}>
            <button type="button" onClick={toggleLang} className="cv-btn-ghost p-2 rounded-lg hidden sm:flex items-center gap-1 shrink-0">
              <Globe className="w-4 h-4 shrink-0" />
              <span className="text-xs font-medium uppercase">{i18n.language}</span>
            </button>
          </Tooltip>
          <MuteToggle />
          <ThemeToggle />

          {user && (
            <div className="flex items-center gap-2 ml-2 pl-2 border-l border-cv-border min-w-0">
              <Tooltip content={t('nav.settings', 'Paramètres')}>
                <button
                  type="button"
                  onClick={() => goTo('/settings')}
                  className="hidden sm:flex items-center gap-2 cv-btn-ghost py-1.5 px-2 min-w-0 max-w-[180px]"
                >
                  <div className="w-8 h-8 rounded-full bg-cv-accent/15 border border-cv-accent/25 flex items-center justify-center shrink-0">
                    <User className="w-4 h-4 text-cv-accent" />
                  </div>
                  <div className="text-left min-w-0">
                    <p className="text-sm font-medium text-cv-text leading-tight truncate">{user.username}</p>
                    <p className="text-[10px] text-cv-muted uppercase truncate">{t(`roles.${user.role}`)}</p>
                  </div>
                </button>
              </Tooltip>
              <Tooltip content={t('nav.logout')}>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="cv-btn-ghost p-2 rounded-lg text-cv-muted hover:text-red-500 shrink-0"
                  aria-label={t('nav.logout')}
                >
                  <LogOut className="w-5 h-5" />
                </button>
              </Tooltip>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
