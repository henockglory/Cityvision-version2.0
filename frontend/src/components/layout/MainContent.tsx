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
      className={`pt-16 min-h-screen transition-all duration-300 pl-0 ${
        collapsed ? 'lg:pl-[72px]' : 'lg:pl-64'
      }`}
    >
      <div className="p-3 md:p-4 lg:p-5 max-w-[1920px] mx-auto space-y-4">{children}</div>
    </main>
  );
}
