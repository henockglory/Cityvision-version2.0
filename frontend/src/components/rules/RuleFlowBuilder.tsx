import { ArrowRight, GitBranch, Zap, Bell, Video } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { Rule } from '@/types';
import type { ConditionNode } from '@/lib/conditionTree';
import { isGroupNode } from '@/lib/conditionTree';
import { narrateConditionSummary } from '@/lib/conditionNarrative';

const actionIcons: Record<string, typeof Bell> = {
  alert: Bell,
  record: Video,
  notify: Bell,
  relay: Zap,
};

function FlowGroup({
  node,
  depth,
  t,
}: {
  node: ConditionNode;
  depth: number;
  t: TFunction;
}) {
  const op = String(node.op ?? 'AND').toUpperCase();
  const label =
    op === 'OU' || op === 'OR'
      ? t('rules.studio.opOr')
      : op === 'SEQUENCE'
        ? t('rules.studio.opSequence', { defaultValue: 'Séquence' })
        : t('rules.studio.opAnd');

  return (
    <div
      className="space-y-2 pl-3 border-l-2 border-cv-accent/30"
      style={{ marginLeft: depth * 8 }}
    >
      <div className="flex items-center gap-2 text-xs font-semibold text-cv-accent">
        <GitBranch className="w-3.5 h-3.5" />
        {label}
      </div>
      {(node.children ?? []).map((child, i) => (
        <FlowNode key={i} node={child} depth={depth + 1} t={t} />
      ))}
    </div>
  );
}

function FlowNode({
  node,
  depth,
  t,
}: {
  node: ConditionNode;
  depth: number;
  t: TFunction;
}) {
  if (isGroupNode(node)) {
    return <FlowGroup node={node} depth={depth} t={t} />;
  }
  const sentence = narrateConditionSummary(node, t);
  return (
    <div className="flex items-start gap-2 px-3 py-2 rounded-lg border border-cv-border bg-cv-surface text-sm">
      <Zap className="w-3.5 h-3.5 text-cv-accent shrink-0 mt-0.5" />
      <div className="min-w-0">
        <p className="text-cv-text leading-relaxed">{sentence}</p>
        <p className="text-[10px] font-mono text-cv-muted mt-1">
          {node.field} {String(node.op ?? 'eq')} {JSON.stringify(node.value ?? '')}
        </p>
      </div>
    </div>
  );
}

interface RuleFlowBuilderProps {
  rule: Rule;
}

export default function RuleFlowBuilder({ rule }: RuleFlowBuilderProps) {
  const { t } = useTranslation();
  const condition = (rule.definition?.condition ?? rule.definition?.conditions) as ConditionNode | undefined;
  const actions = rule.actions ?? [];

  if (!condition && actions.length === 0) return null;

  return (
    <div className="mt-4 p-4 rounded-lg bg-cv-deep/40 border border-cv-border/60">
      <p className="text-xs font-medium text-cv-muted mb-3">{t('rules.studio.visual.flowTitle')}</p>
      <div className="flex flex-col lg:flex-row items-stretch gap-3 min-w-0">
        <div className="flex-1 min-w-0 space-y-2">
          {condition ? (
            isGroupNode(condition) ? (
              <FlowGroup node={condition} depth={0} t={t} />
            ) : (
              <FlowNode node={condition} depth={0} t={t} />
            )
          ) : null}
        </div>
        {condition && actions.length > 0 && (
          <div className="flex items-center justify-center shrink-0 py-2 lg:py-0">
            <ArrowRight className="w-5 h-5 text-cv-accent rotate-90 lg:rotate-0" />
          </div>
        )}
        <div className="flex flex-col gap-2 flex-1 min-w-0">
          {actions.map((act, i) => {
            const Icon = actionIcons[act.type] ?? Bell;
            return (
              <div
                key={act.id ?? i}
                className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cv-accent/20 bg-cv-accent/5 text-sm"
              >
                <Icon className="w-3.5 h-3.5 text-cv-accent shrink-0" />
                <span className="capitalize">{act.type}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
