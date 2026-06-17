import type { LucideIcon } from 'lucide-react';
import { Inbox } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import GuideIllustration from '@/components/ui/GuideIllustration';

interface EmptyStateProps {
  title?: string;
  hint?: string;
  icon?: LucideIcon;
  action?: React.ReactNode;
  guideVariant?: 'rules' | 'spatial' | 'alerts' | 'live' | 'default';
}

export default function EmptyState({
  title,
  hint,
  icon: Icon = Inbox,
  action,
  guideVariant,
}: EmptyStateProps) {
  const { t } = useTranslation();

  if (guideVariant) {
    return (
      <div className="py-10 px-6 animate-fade-in">
        <GuideIllustration
          variant={guideVariant}
          title={title ?? t('emptyState.defaultTitle')}
          caption={hint ?? t('emptyState.defaultHint')}
          className="max-w-lg mx-auto"
        />
        {action && <div className="mt-6 flex justify-center">{action}</div>}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center animate-fade-in">
      <div className="w-16 h-16 rounded-2xl bg-cv-accent/10 border border-cv-accent/20 flex items-center justify-center mb-4">
        <Icon className="w-8 h-8 text-cv-accent/70" />
      </div>
      <h3 className="font-display text-lg font-semibold text-cv-text mb-2">
        {title ?? t('emptyState.defaultTitle')}
      </h3>
      <p className="text-sm text-cv-muted max-w-md">
        {hint ?? t('emptyState.defaultHint')}
      </p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
