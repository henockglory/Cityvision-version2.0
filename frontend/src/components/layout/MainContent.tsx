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
      <div className="p-5 md:p-7 lg:p-9 max-w-[1920px] mx-auto flex flex-col gap-6 md:gap-8">{children}</div>
    </main>
  );
}
