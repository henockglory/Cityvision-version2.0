import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pencil, RefreshCw } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { demoApi, type DemoSettings } from '@/api/client';
import { queryKeys } from '@/hooks/api/queries';
import { useAuthStore } from '@/stores/authStore';

type Field = 'context_label' | 'title' | 'subtitle' | 'nav_label';

interface DemoEditableHeaderProps {
  settings?: DemoSettings | null;
  onRefresh?: () => void;
}

export default function DemoEditableHeader({ settings, onRefresh }: DemoEditableHeaderProps) {
  const { t } = useTranslation();
  const orgId = useAuthStore((s) => s.orgId);
  const qc = useQueryClient();
  const [editing, setEditing] = useState<Field | null>(null);
  const [draft, setDraft] = useState('');

  const context = settings?.context_label || t('demoCenter.context');
  const title = settings?.title || t('demoCenter.title');
  const subtitle = settings?.subtitle || t('demoCenter.subtitle');
  const navLabel = settings?.nav_label || t('nav.demo');

  const startEdit = (field: Field, value: string) => {
    setEditing(field);
    setDraft(value);
  };

  const save = useCallback(async (field: Field) => {
    setEditing(null);
    if (!orgId || draft.trim() === '') return;
    const current = settings?.[field] ?? '';
    if (draft.trim() === current) return;
    try {
      await demoApi.patchSettings(orgId, { [field]: draft.trim() });
      void qc.invalidateQueries({ queryKey: queryKeys.demoSettings });
    } catch {
      /* fallback i18n values remain visible */
    }
  }, [orgId, draft, settings, qc]);

  const EditableLine = ({
    field,
    value,
    className,
    as = 'p',
  }: {
    field: Field;
    value: string;
    className: string;
    as?: 'p' | 'h1';
  }) => {
    const Tag = as;
    if (editing === field) {
      return (
        <input
          autoFocus
          className={`${className} bg-transparent border-b border-cv-accent outline-none w-full`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => void save(field)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void save(field);
            if (e.key === 'Escape') setEditing(null);
          }}
        />
      );
    }
    return (
      <div className="group flex items-start gap-2">
        <Tag className={className}>{value}</Tag>
        <button
          type="button"
          className="cv-demo-edit-trigger opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-0.5"
          onClick={() => startEdit(field, value)}
          aria-label={t('demoCenter.editLabel')}
        >
          <Pencil className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  };

  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 flex-1">
        <EditableLine
          field="context_label"
          value={context}
          className="text-xs font-semibold uppercase tracking-widest text-cv-accent mb-1"
        />
        <EditableLine
          field="title"
          value={title}
          as="h1"
          className="text-2xl md:text-3xl font-display font-semibold tracking-tight"
        />
        <EditableLine
          field="subtitle"
          value={subtitle}
          className="text-sm text-cv-muted mt-1 max-w-xl"
        />
        <div className="mt-3 pt-3 border-t border-cv-border/50">
          <p className="text-[10px] text-cv-muted mb-1">{t('demoCenter.navLabelHint')}</p>
          <EditableLine
            field="nav_label"
            value={navLabel}
            className="text-xs font-medium text-cv-accent"
          />
        </div>
      </div>
      {onRefresh && (
        <button type="button" onClick={onRefresh} className="cv-btn-secondary text-sm">
          <RefreshCw className="w-4 h-4" />
          {t('demoCenter.refresh')}
        </button>
      )}
    </header>
  );
}
