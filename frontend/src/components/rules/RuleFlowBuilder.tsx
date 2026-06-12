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

        <div className="flex flex-col items-center px-2">
          <div className="h-px w-8 bg-gradient-to-r from-cv-border to-cv-accent" />
          <ArrowRight className="w-5 h-5 text-cv-accent my-1" />
          <div className="h-px w-8 bg-gradient-to-r from-cv-accent to-cv-border" />
        </div>

        <div className="px-4 py-3 rounded-xl border-2 border-dashed border-cv-accent/40 bg-cv-accent/5">
          <p className="text-[10px] uppercase tracking-widest text-cv-accent text-center">Trigger</p>
        </div>

        <div className="flex flex-col items-center px-2">
          <div className="h-px w-8 bg-gradient-to-r from-cv-border to-cv-accent" />
          <ArrowRight className="w-5 h-5 text-cv-accent my-1" />
          <div className="h-px w-8 bg-gradient-to-r from-cv-accent to-cv-border" />
        </div>

        <div className="flex flex-col gap-2">
          {rule.actions.map((action, i) => {
            const Icon = actionIcons[action.type] ?? Bell;
            return (
              <div
                key={action.id}
                className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cv-accent/30 bg-cv-accent/10"
              >
                <Icon className="w-3.5 h-3.5 text-cv-accent shrink-0" />
                <span className="text-sm capitalize text-cv-accent whitespace-nowrap">{action.type}</span>
                <span className="text-[10px] text-cv-muted font-mono">{i + 1}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
