import { ArrowRight, Zap, Bell, Video, Workflow } from 'lucide-react';
import type { Rule } from '@/types';

const conditionIcons: Record<string, typeof Zap> = {
  motion: Zap,
  zone: Workflow,
  line: Workflow,
  schedule: Workflow,
  object: Zap,
};

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
  return (
    <div className="mt-4 p-4 rounded-lg bg-cv-deep/60 border border-cv-border overflow-x-auto">
      <div className="flex items-center gap-2 min-w-max">
        <div className="flex flex-col gap-2">
          {rule.conditions.map((cond, i) => {
            const Icon = conditionIcons[cond.type] ?? Zap;
            return (
              <div
                key={cond.id}
                className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cv-border bg-cv-surface"
              >
                <span className="text-[10px] text-cv-muted font-mono w-4">{i + 1}</span>
                <Icon className="w-3.5 h-3.5 text-cv-accent shrink-0" />
                <span className="text-sm capitalize whitespace-nowrap">{cond.type}</span>
              </div>
            );
          })}
        </div>
        <ArrowRight className="w-5 h-5 text-cv-accent shrink-0" />
        <div className="flex flex-col gap-2">
          {rule.actions.map((act, i) => {
            const Icon = actionIcons[act.type] ?? Bell;
            return (
              <div
                key={act.id}
                className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cv-accent/20 bg-cv-accent/5"
              >
                <span className="text-[10px] text-cv-muted font-mono w-4">{i + 1}</span>
                <Icon className="w-3.5 h-3.5 text-cv-accent shrink-0" />
                <span className="text-sm capitalize whitespace-nowrap">{act.type}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
