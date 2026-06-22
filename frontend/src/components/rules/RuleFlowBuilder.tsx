import { ArrowRight, Zap, Bell, Video } from 'lucide-react';
import type { Rule } from '@/types';
import { conditionNodesFromDefinition } from '@/lib/ruleExplainability';

const actionIcons: Record<string, typeof Bell> = {
  alert: Bell,
  record: Video,
  notify: Bell,
  relay: Zap,
};

interface RuleFlowBuilderProps {
  rule: Rule;
}

export default function RuleFlowBuilder({ rule }: RuleFlowBuilderProps) {
  const nodes = conditionNodesFromDefinition(rule.definition ?? {});
  const actions = rule.actions ?? [];

  if (nodes.length === 0 && actions.length === 0) return null;

  return (
    <div className="mt-4 p-4 rounded-lg bg-cv-deep/40 border border-cv-border/60 overflow-x-auto">
      <div className="flex items-center gap-2 min-w-max">
        <div className="flex flex-col gap-2">
          {nodes.map((node, i) => (
            <div
              key={`${node.field}-${i}`}
              className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cv-border bg-cv-surface text-sm"
            >
              <Zap className="w-3.5 h-3.5 text-cv-accent shrink-0" />
              <span className="whitespace-nowrap capitalize">
                {node.field} {String(node.op ?? '').toLowerCase()} {String(node.value ?? '')}
              </span>
            </div>
          ))}
        </div>
        {nodes.length > 0 && actions.length > 0 && (
          <ArrowRight className="w-5 h-5 text-cv-accent shrink-0" />
        )}
        <div className="flex flex-col gap-2">
          {actions.map((act, i) => {
            const Icon = actionIcons[act.type] ?? Bell;
            return (
              <div
                key={act.id ?? i}
                className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cv-accent/20 bg-cv-accent/5 text-sm"
              >
                <Icon className="w-3.5 h-3.5 text-cv-accent shrink-0" />
                <span className="capitalize whitespace-nowrap">{act.type}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
