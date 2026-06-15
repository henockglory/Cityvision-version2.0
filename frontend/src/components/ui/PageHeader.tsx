import type { ReactNode } from 'react';
import { HelpCircle } from 'lucide-react';
import Tooltip from '@/components/ui/Tooltip';

interface PageHeaderProps {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  onHelpTour?: () => void;
}

export default function PageHeader({ title, subtitle, actions, onHelpTour }: PageHeaderProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
      <div className="min-w-0">
        <h1 className="cv-page-title">{title}</h1>
        {subtitle && <p className="text-sm text-cv-muted mt-1">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-2 shrink-0 flex-wrap">
        {onHelpTour && (
          <Tooltip content="Lancer le tutoriel de cette page">
            <button type="button" className="cv-btn-ghost p-2" onClick={onHelpTour} aria-label="Tutoriel">
              <HelpCircle className="w-4 h-4" />
            </button>
          </Tooltip>
        )}
        {actions}
      </div>
    </div>
  );
}
