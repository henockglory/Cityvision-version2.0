import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { GitBranch, Plus, Trash2, Pencil } from 'lucide-react';

import {

  type ConditionNode,

  createGroup,

  createLeaf,

  isGroupNode,

  opsForField,

} from '@/lib/conditionTree';

import { narrateConditionSummary, technicalLeafLine } from '@/lib/conditionNarrative';

import type { NarrativeContext } from '@/lib/conditionNarrative';

import type { SpatialContext } from '@/components/rules/ConditionValueField';

import ConditionValueField from '@/components/rules/ConditionValueField';

import ExplanatorySelect from '@/components/ui/ExplanatorySelect';

import InfoTip from '@/components/ui/InfoTip';

import {
  buildConditionFieldOptions,
  buildConditionOpOptions,
  buildGroupOpOptions,
} from '@/lib/conditionValueOptions';



interface ConditionTreeVisualEditorProps {

  value: ConditionNode;

  onChange: (node: ConditionNode) => void;

  narrativeContext?: NarrativeContext;

  spatialContext?: SpatialContext;

  templateEventHint?: string;

}



export default function ConditionTreeVisualEditor({

  value,

  onChange,

  narrativeContext = {},

  spatialContext,

  templateEventHint,

}: ConditionTreeVisualEditorProps) {

  const { t, i18n } = useTranslation();

  const lang = i18n.language.startsWith('en') ? 'en' : 'fr';

  const fieldOptions = useMemo(
    () => buildConditionFieldOptions(lang, (key, fb) => t(`rules.narrative.fields.${key}`, fb)),
    [lang, t],
  );

  const groupOpOptions = useMemo(
    () =>
      buildGroupOpOptions(lang, {
        and: t('rules.studio.opAnd'),
        or: t('rules.studio.opOr'),
        sequence: t('rules.studio.opSequence', { defaultValue: 'Séquence temporelle' }),
      }),
    [lang, t],
  );



  const updateAt = (path: number[], updater: (node: ConditionNode) => ConditionNode) => {

    const clone = JSON.parse(JSON.stringify(value)) as ConditionNode;

    if (path.length === 0) {

      onChange(updater(clone));

      return;

    }

    let cur: ConditionNode = clone;

    for (let i = 0; i < path.length - 1; i++) {

      cur = (cur.children ?? [])[path[i]];

    }

    const last = path[path.length - 1];

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



  const groupBadgeClass = (op: string) => {

    const u = op.toUpperCase();

    if (u === 'OU' || u === 'OR') return 'bg-amber-500/15 text-amber-400 border-amber-500/35';

    if (u === 'SEQUENCE') return 'bg-violet-500/15 text-violet-400 border-violet-500/35';

    return 'bg-cv-accent/15 text-cv-accent border-cv-accent/35';

  };



  const renderNode = (node: ConditionNode, path: number[], depth = 0) => {

    if (isGroupNode(node)) {

      const op = String(node.op ?? 'AND').toUpperCase();

      const groupLabel =

        op === 'OU' || op === 'OR'

          ? t('rules.studio.opOr')

          : op === 'SEQUENCE'

            ? t('rules.studio.opSequence', { defaultValue: 'Séquence temporelle' })

            : t('rules.studio.opAnd');



      return (

        <div key={path.join('-') || 'root'} className="relative pl-4 border-l-2 border-cv-accent/25 ml-2">

          <div

            className={`rounded-xl border p-3 space-y-3 bg-cv-deep/40 ${depth === 0 ? 'border-cv-accent/30' : 'border-cv-border/60'}`}

          >

            <div className="flex items-center justify-between gap-3 min-w-0">

              <div className="flex items-center gap-2 min-w-0 shrink">

                <GitBranch className="w-4 h-4 text-cv-accent shrink-0" />

                <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border shrink-0 ${groupBadgeClass(op)}`}>

                  {groupLabel}

                </span>

                {op === 'SEQUENCE' && (

                  <InfoTip helpKey="sequenceCondition" content={t('rules.studio.sequenceHint')} />

                )}

              </div>

              <div className="flex items-center gap-1.5 shrink-0 flex-nowrap">

                <ExplanatorySelect
                  className="w-[8.5rem]"
                  compact
                  searchable={false}
                  value={op === 'OU' || op === 'OR' ? 'OR' : op === 'SEQUENCE' ? 'SEQUENCE' : 'AND'}
                  onChange={(v) => updateAt(path, (n) => ({ ...n, op: v }))}
                  options={groupOpOptions}
                />

                <button

                  type="button"

                  className="cv-btn-ghost text-xs py-1.5 px-2 whitespace-nowrap shrink-0"

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

                  className="cv-btn-ghost text-xs py-1.5 px-2 whitespace-nowrap shrink-0"

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

                  <button
                    type="button"
                    className="cv-btn-ghost text-red-500 p-1.5 shrink-0 inline-flex items-center justify-center"
                    onClick={() => removeAt(path)}
                    title={t('common.delete', { defaultValue: 'Supprimer' })}
                  >

                    <Trash2 className="w-3.5 h-3.5" />

                  </button>

                )}

              </div>

            </div>

            <p className="text-xs text-cv-muted leading-relaxed shrink-0 pb-1">

              {op === 'OU' || op === 'OR'

                ? t('rules.studio.visual.orExplain')

                : op === 'SEQUENCE'

                  ? t('rules.studio.visual.sequenceExplain')

                  : t('rules.studio.visual.andExplain')}

            </p>

            <div className="space-y-2">

              {(node.children ?? []).map((child, i) => renderNode(child, [...path, i], depth + 1))}

            </div>

          </div>

        </div>

      );

    }



    const field = String(node.field ?? 'event_type');

    const fieldOps = opsForField(field);
    const opOptions = buildConditionOpOptions(fieldOps, lang);

    const sentence = narrateConditionSummary(node, t, narrativeContext);

    const tech = technicalLeafLine(node);

    return (

      <div

        key={path.join('-')}

        className="rounded-lg border border-cv-border/70 bg-cv-surface/40 p-3 space-y-2"

      >

        <div className="flex items-start gap-2">

          <span className="mt-1 w-2 h-2 rounded-full bg-cv-accent shrink-0" />

          <p className="text-sm text-cv-text leading-relaxed flex-1">{sentence}</p>

          <button

            type="button"

            className="cv-btn-ghost p-1.5 shrink-0"

            title={t('rules.studio.visual.editCondition')}

            onClick={() => {

              /* inline edit below */

            }}

          >

            <Pencil className="w-3.5 h-3.5" />

          </button>

          {path.length > 0 && (

            <button type="button" className="cv-btn-ghost text-red-500 p-1.5 shrink-0" onClick={() => removeAt(path)}>

              <Trash2 className="w-3.5 h-3.5" />

            </button>

          )}

        </div>

        <div className="grid grid-cols-1 md:grid-cols-[minmax(130px,1.1fr)_minmax(88px,0.45fr)_minmax(150px,1.2fr)] gap-2 items-center pl-4 border-l border-cv-border/40 min-w-0">

          <ExplanatorySelect
            className="flex-1 min-w-[120px]"
            compact
            searchable={false}
            value={field}
            onChange={(nextField) => {
              const allowed = opsForField(nextField);
              const nextOp = allowed.some((o) => o.value === node.op) ? node.op : allowed[0]?.value ?? 'eq';
              updateAt(path, (n) => ({ ...n, field: nextField, op: nextOp, value: '' }));
            }}
            options={fieldOptions}
          />

          <ExplanatorySelect
            className="w-32 min-w-[100px]"
            compact
            searchable={false}
            value={String(node.op ?? fieldOps[0]?.value ?? 'eq')}
            onChange={(v) => updateAt(path, (n) => ({ ...n, op: v }))}
            options={opOptions}
          />

          <ConditionValueField

            field={field}

            value={node.value}

            onChange={(v) => updateAt(path, (n) => ({ ...n, value: v }))}

            spatial={spatialContext}

            templateEventHint={templateEventHint}

          />

        </div>

        <p className="text-[10px] font-mono text-cv-muted/80 pl-4">{tech}</p>

      </div>

    );

  };



  const root = isGroupNode(value) ? value : createGroup('AND', [value]);



  return (

    <div className="space-y-3">

      <div>

        <p className="text-sm font-medium text-cv-text">{t('rules.studio.conditionsTitle')}</p>

        <p className="text-xs text-cv-muted mt-1">{t('rules.studio.visual.subtitle')}</p>

      </div>

      {renderNode(root, [])}

    </div>

  );

}


