import { useTranslation } from 'react-i18next';
import { GitBranch, Plus, Trash2 } from 'lucide-react';
import {
  type ConditionNode,
  CONDITION_FIELDS,
  CONDITION_OPS,
  createGroup,
  createLeaf,
  isGroupNode,
} from '@/lib/conditionTree';
import PremiumSelect from '@/components/ui/PremiumSelect';

interface ConditionTreeEditorProps {
  value: ConditionNode;
  onChange: (node: ConditionNode) => void;
}

export default function ConditionTreeEditor({ value, onChange }: ConditionTreeEditorProps) {
  const { t } = useTranslation();

  const updateAt = (path: number[], updater: (node: ConditionNode) => ConditionNode) => {
    const clone = JSON.parse(JSON.stringify(value)) as ConditionNode;
    let cur: ConditionNode = clone;
    for (let i = 0; i < path.length - 1; i++) {
      cur = (cur.children ?? [])[path[i]];
    }
    const last = path[path.length - 1];
    if (path.length === 0) {
      onChange(updater(clone));
      return;
    }
    if (!cur.children) cur.children = [];
    cur.children[last] = updater(cur.children[last]);
    onChange(clone);
  };

  const removeAt = (path: number[]) => {
    if (path.length === 0) return;
    const clone = JSON.parse(JSON.stringify(value)) as ConditionNode;
    if (path.length === 1) {
      const root = clone;
      root.children = (root.children ?? []).filter((_, i) => i !== path[0]);
      onChange(root.children?.length === 1 ? root.children[0] : root);
      return;
    }
    let cur: ConditionNode = clone;
    for (let i = 0; i < path.length - 1; i++) {
      cur = (cur.children ?? [])[path[i]];
    }
    cur.children = (cur.children ?? []).filter((_, i) => i !== path[path.length - 1]);
    onChange(clone);
  };

  const renderNode = (node: ConditionNode, path: number[], depth = 0) => {
    if (isGroupNode(node)) {
      return (
        <div
          key={path.join('-')}
          className="rounded-lg border border-cv-border/80 bg-cv-deep/40 p-3 space-y-2"
          style={{ marginLeft: depth * 12 }}
        >
          <div className="flex items-center gap-2 flex-wrap">
            <GitBranch className="w-4 h-4 text-cv-accent shrink-0" />
            <PremiumSelect
              className="w-auto min-w-[140px]"
              minWidth={160}
              triggerClassName="text-xs py-1"
              value={String(node.op ?? 'AND')}
              onChange={(v) => updateAt(path, (n) => ({ ...n, op: v }))}
              options={[
                { value: 'AND', label: t('rules.studio.opAnd') },
                { value: 'OR', label: t('rules.studio.opOr') },
                { value: 'SEQUENCE', label: t('rules.studio.opSequence', 'Séquence temporelle') },
              ]}
            />
            <button
              type="button"
              className="cv-btn-ghost text-xs py-1 px-2"
              onClick={() =>
                updateAt(path, (n) => ({
                  ...n,
                  children: [...(n.children ?? []), createLeaf()],
                }))
              }
            >
              <Plus className="w-3 h-3" />
              {t('rules.studio.addCondition')}
            </button>
            <button
              type="button"
              className="cv-btn-ghost text-xs py-1 px-2"
              onClick={() =>
                updateAt(path, (n) => ({
                  ...n,
                  children: [...(n.children ?? []), createGroup('AND', [createLeaf()])],
                }))
              }
            >
              {t('rules.studio.addGroup')}
            </button>
            {path.length > 0 && (
              <button type="button" className="cv-btn-ghost text-xs text-red-500 p-1" onClick={() => removeAt(path)}>
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <div className="space-y-2">
            {(node.children ?? []).map((child, i) => renderNode(child, [...path, i], depth + 1))}
          </div>
        </div>
      );
    }

    return (
      <div
        key={path.join('-')}
        className="flex flex-wrap items-center gap-2 p-2 rounded-lg border border-cv-border/60 bg-cv-surface/30"
        style={{ marginLeft: depth * 12 }}
      >
        <PremiumSelect
          className="flex-1 min-w-[120px]"
          minWidth={160}
          triggerClassName="text-xs py-1"
          value={String(node.field ?? '')}
          onChange={(v) => updateAt(path, (n) => ({ ...n, field: v }))}
          options={CONDITION_FIELDS.map((f) => ({ value: f.value, label: f.label }))}
        />
        <PremiumSelect
          className="w-28"
          minWidth={110}
          triggerClassName="text-xs py-1"
          value={String(node.op ?? 'eq')}
          onChange={(v) => updateAt(path, (n) => ({ ...n, op: v }))}
          options={CONDITION_OPS.map((o) => ({ value: o.value, label: o.label }))}
        />
        <input
          className="cv-input text-xs py-1 flex-1 min-w-[80px]"
          value={node.value != null ? String(node.value) : ''}
          onChange={(e) => {
            const raw = e.target.value;
            const num = Number(raw);
            updateAt(path, (n) => ({
              ...n,
              value: raw !== '' && !Number.isNaN(num) && String(num) === raw ? num : raw,
            }));
          }}
          placeholder={t('rules.studio.valuePlaceholder')}
        />
        {path.length > 0 && (
          <button type="button" className="cv-btn-ghost text-red-500 p-1" onClick={() => removeAt(path)}>
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    );
  };

  const root = isGroupNode(value) ? value : createGroup('AND', [value]);

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-cv-text">{t('rules.studio.conditionsTitle')}</p>
      <p className="text-xs text-cv-muted">{t('rules.studio.conditionsHint')}</p>
      {renderNode(root, [])}
    </div>
  );
}
