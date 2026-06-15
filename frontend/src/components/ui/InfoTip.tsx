import type { ReactNode } from 'react';
import { HelpCircle } from 'lucide-react';
import Tooltip from '@/components/ui/Tooltip';
import { useUiStore } from '@/stores/uiStore';

interface InfoTipProps {
  content: string;
  children?: ReactNode;
}

export default function InfoTip({ content, children }: InfoTipProps) {
  const enabled = useUiStore((s) => s.tooltipsEnabled);
  if (!enabled) return <>{children ?? null}</>;

  return (
    <Tooltip content={content}>
      {children ?? (
        <button type="button" className="text-cv-muted hover:text-cv-accent p-0.5" aria-label="Aide">
          <HelpCircle className="w-3.5 h-3.5" />
        </button>
      )}
    </Tooltip>
  );
}
