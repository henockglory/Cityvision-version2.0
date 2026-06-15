import type { ReactNode } from 'react';
import PageHeader from '@/components/ui/PageHeader';

interface PageShellProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  toolbar?: ReactNode;
  onHelpTour?: () => void;
  className?: string;
  children: ReactNode;
}

export default function PageShell({
  title,
  subtitle,
  actions,
  toolbar,
  onHelpTour,
  className = '',
  children,
}: PageShellProps) {
  return (
    <div className={`space-y-5 animate-fade-in ${className}`}>
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={actions}
        onHelpTour={onHelpTour}
      />
      {toolbar && <div className="flex flex-wrap items-center gap-3">{toolbar}</div>}
      {children}
    </div>
  );
}
