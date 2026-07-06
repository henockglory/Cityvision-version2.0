import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronUp, Code2 } from 'lucide-react';
import type { ConditionNode } from '@/lib/conditionTree';

export default function ConditionTreeTechnicalMirror({ value }: { value: ConditionNode }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const json = JSON.stringify({ condition: value }, null, 2);

  return (
    <div className="rounded-lg border border-cv-border/50 bg-cv-deep/30">
      <button
        type="button"
        className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-xs text-cv-muted hover:text-cv-text"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="flex items-center gap-2">
          <Code2 className="w-3.5 h-3.5" />
          {t('rules.studio.visual.technicalJson')}
        </span>
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>
      {open && (
        <pre className="text-[10px] font-mono text-cv-muted/90 px-3 pb-3 overflow-x-auto max-h-48">{json}</pre>
      )}
    </div>
  );
}
