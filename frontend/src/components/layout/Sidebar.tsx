import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  LayoutDashboard, Camera, MonitorPlay, Grid3x3, Map, PenTool, Workflow,
  Bell, Clock, Users, FileText, Activity, Settings, Sparkles,
  ChevronLeft, ChevronRight, X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import EyeLogo from '@/components/EyeLogo';
import Tooltip from '@/components/ui/Tooltip';
import { useAuthStore } from '@/stores/authStore';
import { useUiStore } from '@/stores/uiStore';
import { getNavGroupsForRole } from '@/config/navigation';
import { useSound } from '@/hooks/useSound';

const iconMap: Record<string, LucideIcon> = {
  LayoutDashboard, Camera, MonitorPlay, Grid3x3, Map, PenTool, Workflow,
  Bell, Clock, Users, FileText, Activity, Settings, Sparkles,
};

interface SidebarProps {
  mobile?: boolean;
}

export default function Sidebar({ mobile = false }: SidebarProps) {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const setMobileOpen = useUiStore((s) => s.setMobileSidebarOpen);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const { playClick } = useSound();

  const groups = user ? getNavGroupsForRole(user.role) : [];
  const isCollapsed = !mobile && collapsed;

  const closeMobile = () => setMobileOpen(false);

  return (
    <aside
      id="sidebar-nav"
      className={`fixed left-0 top-0 h-full z-40 flex flex-col bg-cv-black/95 backdrop-blur-xl border-r border-cv-border/60 transition-all duration-300 ${
        mobile ? 'w-72' : isCollapsed ? 'w-[72px]' : 'w-64'
      } ${mobile ? '' : 'hidden lg:flex'}`}
    >
      <div className={`flex items-center h-16 px-4 border-b border-cv-border/60 ${isCollapsed && !mobile ? 'justify-center' : 'gap-3'}`}>
        <EyeLogo size={32} />
        {(!isCollapsed || mobile) && (
          <div className="flex-1 overflow-hidden">
            <h1 className="font-display text-base font-bold text-cv-text whitespace-nowrap">
              {t('app.name')}
            </h1>
            <p className="text-[10px] text-cv-muted tracking-wide">Surveillance intelligente</p>
          </div>
        )}
        {mobile && (
          <button type="button" onClick={closeMobile} className="cv-btn-ghost p-2 lg:hidden">
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      <nav className="flex-1 py-4 overflow-y-auto">
        {groups.map((group) => (
          <div key={group.id} className="mb-4">
            {(!isCollapsed || mobile) && (
              <p className="px-5 mb-2 text-[10px] font-semibold uppercase tracking-wider text-cv-muted flex items-center gap-2">
                {t(group.labelKey, group.id)}
                {group.badge === 'demo' && (
                  <span className="px-1.5 py-0.5 rounded text-[9px] bg-amber-500/20 text-amber-600 dark:text-amber-400 normal-case">
                    démo
                  </span>
                )}
              </p>
            )}
            <ul className="space-y-0.5 px-3">
              {group.items.map((item) => {
                const Icon = iconMap[item.icon] ?? LayoutDashboard;
                const link = (
                  <NavLink
                    to={item.path}
                    end={item.path === '/'}
                    onClick={() => {
                      playClick();
                      if (mobile) closeMobile();
                    }}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors w-full ${
                        isActive
                          ? 'bg-cv-accent/15 text-cv-accent border border-cv-accent/20'
                          : 'text-cv-muted hover:text-cv-text hover:bg-cv-accent/5'
                      } ${isCollapsed && !mobile ? 'justify-center' : ''}`
                    }
                  >
                    <Icon className="w-[18px] h-[18px] shrink-0" />
                    {(!isCollapsed || mobile) && <span className="truncate">{t(item.labelKey)}</span>}
                  </NavLink>
                );
                return (
                  <li key={item.path}>
                    {isCollapsed && !mobile ? (
                      <Tooltip content={t(item.labelKey)} side="right">{link}</Tooltip>
                    ) : (
                      link
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {!mobile && (
        <Tooltip content={isCollapsed ? t('nav.expand', 'Déplier') : t('nav.collapse', 'Replier')}>
          <button
            type="button"
            onClick={() => { playClick(); toggleSidebar(); }}
            className="hidden lg:flex items-center justify-center h-12 w-full border-t border-cv-border/60 text-cv-muted hover:text-cv-accent transition-colors"
            aria-label={isCollapsed ? t('nav.expand', 'Déplier') : t('nav.collapse', 'Replier')}
          >
            {isCollapsed ? <ChevronRight className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
          </button>
        </Tooltip>
      )}
    </aside>
  );
}
