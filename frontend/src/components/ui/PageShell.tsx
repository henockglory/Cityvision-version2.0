import type { ReactNode } from 'react';
import PageHeader from '@/components/ui/PageHeader';

interface PageShellProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  toolbar?: ReactNode;
  onHelpTour?: () => void;
  tourTriggerAttr?: string;
  className?: string;
  /** Bind page to viewport height so child split panes can scroll independently. */
  fillViewport?: boolean;
  children: ReactNode;
}

export default function PageShell({
  title,
  subtitle,
  actions,
  toolbar,
  onHelpTour,
  tourTriggerAttr,
  className = '',
  fillViewport = false,
  children,
}: PageShellProps) {
  return (
    <div
      className={`animate-fade-in ${
        fillViewport
          ? 'flex flex-col h-[calc(100dvh-7rem)] max-h-[calc(100dvh-7rem)] overflow-hidden gap-5'
          : 'space-y-5'
      } ${className}`}
    >
      <div className={fillViewport ? 'shrink-0' : undefined}>
        <PageHeader
          title={title}
          subtitle={subtitle}
          actions={actions}
          onHelpTour={onHelpTour}
          tourTriggerAttr={tourTriggerAttr}
        />
        {toolbar && <div className="flex flex-wrap items-center gap-3 mt-5">{toolbar}</div>}
      </div>
      <div className={fillViewport ? 'flex flex-col flex-1 min-h-0 overflow-hidden gap-5' : undefined}>{children}</div>
    </div>
  );
}
