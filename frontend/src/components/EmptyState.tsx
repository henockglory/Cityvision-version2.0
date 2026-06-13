import type { LucideIcon } from 'lucide-react';
import { Inbox } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface EmptyStateProps {
  title?: string;
  hint?: string;
  icon?: LucideIcon;
  action?: React.ReactNode;
}

export default function EmptyState({
  title,
  hint,
  icon: Icon = Inbox,
  action,
}: EmptyStateProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center animate-fade-in">
      <div className="w-16 h-16 rounded-2xl bg-cv-accent/10 border border-cv-accent/20 flex items-center justify-center mb-4 shadow-glow">
        <Icon className="w-8 h-8 text-cv-accent/70" />
      </div>
      <h3 className="font-display text-lg font-semibold text-[var(--cv-text)] mb-2">
        {title ?? t('emptyState.defaultTitle')}
      </h3>
      <p className="text-sm text-cv-muted max-w-md">
        {hint ?? t('emptyState.defaultHint')}
      </p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
