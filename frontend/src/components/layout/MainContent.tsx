import type { ReactNode } from 'react';
import { useUiStore } from '@/stores/uiStore';

interface MainContentProps {
  children: ReactNode;
}

export default function MainContent({ children }: MainContentProps) {
  const sidebarCollapsed = useUiStore((s) => s.sidebarCollapsed);

  return (
    <main
      id="main-content"
      className={`min-h-screen pt-16 transition-all duration-300 cv-grid-bg ${
        sidebarCollapsed ? 'pl-[72px]' : 'pl-64'
      }`}
    >
      <div className="p-6 max-w-[1600px] mx-auto animate-fade-in">{children}</div>
    </main>
  );
}
