import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import Panel from '@/components/ui/Panel';

/** @deprecated use ui/Panel */
export default function CyberPanel({
  title,
  children,
  icon,
  live,
}: {
  title: string;
  children: ReactNode;
  icon?: LucideIcon;
  live?: boolean;
}) {
  return (
    <Panel
      title={title}
      icon={icon}
      action={
        live ? (
          <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-500 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Live
          </span>
        ) : undefined
      }
    >
      {children}
    </Panel>
  );
}
