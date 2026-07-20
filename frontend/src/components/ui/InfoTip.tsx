import { useCallback, useId, useRef, type ReactNode } from 'react';
import { HelpCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import Tooltip from '@/components/ui/Tooltip';
import { runFieldTour } from '@/lib/contextualTour';
import { useUiStore } from '@/stores/uiStore';

interface InfoTipProps {
  /** Texte court (infobulle survol ou repli si pas de clé enrichie). */
  content: string;
  /** Clé sous tours.fields.* pour titre, description, astuce et procédure. */
  helpKey?: string;
  children?: ReactNode;
}

function HelpButton({
  onOpen,
  btnRef,
  id,
}: {
  onOpen: () => void;
  btnRef: React.RefObject<HTMLButtonElement>;
  id: string;
}) {
  const { t } = useTranslation();
  return (
    <button
      ref={btnRef}
      id={id}
      type="button"
      className="text-cv-muted hover:text-cv-accent p-0.5 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-cv-accent/50"
      aria-label={t('tours.common.fieldAria', 'Ouvrir l\'aide détaillée')}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onOpen();
      }}
    >
      <HelpCircle className="w-3.5 h-3.5" />
    </button>
  );
}

export default function InfoTip({ content, helpKey, children }: InfoTipProps) {
  const { t } = useTranslation();
  const tooltipsEnabled = useUiStore((s) => s.tooltipsEnabled);
  const toursEnabled = useUiStore((s) => s.toursEnabled);
  const anchorId = useId().replace(/:/g, '');
  const btnRef = useRef<HTMLButtonElement>(null);

  const openRichHelp = useCallback(() => {
    if (!toursEnabled) return;
    const anchor = btnRef.current;
    if (!anchor) return;
    runFieldTour(anchor, t, { helpKey, content });
  }, [t, helpKey, content, toursEnabled]);

  if (!tooltipsEnabled) return <>{children ?? null}</>;

  const helpBtn = (
    <HelpButton
      btnRef={btnRef}
      id={`cv-field-tip-${anchorId}`}
      onOpen={openRichHelp}
    />
  );

  if (children) {
    if (!toursEnabled) {
      return <Tooltip content={content}>{children}</Tooltip>;
    }
    return (
      <span className="inline-flex items-center gap-0.5">
        {children}
        {helpBtn}
      </span>
    );
  }

  if (!toursEnabled) {
    return (
      <Tooltip content={content}>
        {helpBtn}
      </Tooltip>
    );
  }

  return helpBtn;
}
