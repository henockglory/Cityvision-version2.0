import type { LucideIcon } from 'lucide-react';
import { Inbox } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import GuideIllustration from '@/components/ui/GuideIllustration';
import { RULES_EMPTY_STATE_IMAGE } from '@/components/rules/RuleGuideImage';

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

  if (guideVariant === 'rules') {
    return (
      <div className="py-10 px-6 animate-fade-in">
        <div className="max-w-lg mx-auto flex gap-4 items-center rounded-xl border border-cv-border/60 bg-cv-deep/30 p-4">
          <div className="cv-studio-guide-image-frame shrink-0 w-36 h-36 bg-transparent rounded-lg">
            <img
              src={RULES_EMPTY_STATE_IMAGE}
              alt=""
              className="cv-studio-guide-image w-full h-full object-contain motion-safe:animate-fade-in"
            />
          </div>
          <div className="min-w-0">
            <p className="font-medium text-cv-text text-sm">{title ?? t('emptyState.defaultTitle')}</p>
            <p className="text-cv-muted mt-1 text-xs leading-relaxed">{hint ?? t('emptyState.defaultHint')}</p>
          </div>
        </div>
        {action && <div className="mt-6 flex justify-center">{action}</div>}
      </div>
    );
  }

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
