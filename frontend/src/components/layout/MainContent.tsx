import type { ReactNode } from 'react';
import { useUiStore } from '@/stores/uiStore';

interface MainContentProps {
  children: ReactNode;
}

export default function MainContent({ children }: MainContentProps) {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);

  return (
    <main
      id="main-content"
      className={`pt-16 min-h-screen transition-all duration-300 ${
        collapsed ? 'pl-[72px]' : 'pl-64'
      }`}
    >
      <div className="p-6 max-w-[1600px] mx-auto">{children}</div>
    </main>
  );
}
