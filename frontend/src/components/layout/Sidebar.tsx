import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  LayoutDashboard, Camera, MonitorPlay, Grid3x3, Map, PenTool, Workflow,
  Bell, Clock, Users, FileText, Activity, Settings, ChevronLeft, ChevronRight,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import EyeLogo from '@/components/EyeLogo';
import { useAuthStore } from '@/stores/authStore';
import { useUiStore } from '@/stores/uiStore';
import { getNavForRole } from '@/config/navigation';
import { useSound } from '@/hooks/useSound';

const iconMap: Record<string, LucideIcon> = {
  LayoutDashboard, Camera, MonitorPlay, Grid3x3, Map, PenTool, Workflow,
  Bell, Clock, Users, FileText, Activity, Settings,
};

export default function Sidebar() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const { playClick } = useSound();

  const items = user ? getNavForRole(user.role) : [];

  return (
    <aside
      id="sidebar-nav"
      className={`fixed left-0 top-0 h-full z-40 flex flex-col bg-cv-navy/95 backdrop-blur-md border-r border-cv-border transition-all duration-300 ${
        collapsed ? 'w-[72px]' : 'w-64'
      }`}
    >
      <div className={`flex items-center h-16 px-4 border-b border-cv-border ${collapsed ? 'justify-center' : 'gap-3'}`}>
        <EyeLogo size={32} />
        {!collapsed && (
          <div className="overflow-hidden">
            <h1 className="font-display text-lg font-bold tracking-wider text-cv-accent whitespace-nowrap">
              {t('app.name')}
            </h1>
            <p className="text-[10px] text-cv-muted tracking-widest uppercase">v2.0</p>
          </div>
        )}
      </div>

      <nav className="flex-1 py-4 overflow-y-auto">
        <ul className="space-y-1 px-3">
          {items.map((item) => {
            const Icon = iconMap[item.icon] ?? LayoutDashboard;
            return (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  end={item.path === '/'}
                  onClick={() => playClick()}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                      isActive
                        ? 'bg-cv-accent/10 text-cv-accent border border-cv-accent/20 shadow-glow'
                        : 'text-cv-muted hover:text-[var(--cv-text)] hover:bg-cv-accent/5'
                    } ${collapsed ? 'justify-center' : ''}`
                  }
                  title={collapsed ? t(item.labelKey) : undefined}
                >
                  <Icon className="w-5 h-5 shrink-0" />
                  {!collapsed && <span className="truncate">{t(item.labelKey)}</span>}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="p-3 border-t border-cv-border">
        <button
          type="button"
          onClick={() => {
            playClick();
            toggleSidebar();
          }}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-cv-muted hover:text-cv-accent hover:bg-cv-accent/5 transition-colors"
        >
          {collapsed ? <ChevronRight className="w-5 h-5" /> : (
            <>
              <ChevronLeft className="w-5 h-5" />
              <span className="text-sm">{t('nav.collapse')}</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
