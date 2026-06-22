import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import Card from './Card';

interface PanelProps {
  title: string;
  children: ReactNode;
  icon?: LucideIcon;
  action?: ReactNode;
  className?: string;
}

export default function Panel({ title, children, icon: Icon, action, className = '' }: PanelProps) {
  return (
    <Card className={`p-5 ${className}`}>
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="w-5 h-5 text-cv-accent" />}
          <h2 className="font-display text-lg font-semibold text-cv-text">{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </Card>
  );
}
