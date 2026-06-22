import type { LucideIcon } from 'lucide-react';
import { Check } from 'lucide-react';

export interface WizardStep {
  n: number;
  label: string;
  icon: LucideIcon;
}

interface WizardStepsProps {
  steps: WizardStep[];
  current: number;
  className?: string;
}

export default function WizardSteps({ steps, current, className = '' }: WizardStepsProps) {
  return (
    <div className={`flex items-center justify-center gap-2 flex-wrap ${className}`}>
      {steps.map((s, idx) => {
        const done = current > s.n;
        const active = current === s.n;
        const Icon = s.icon;
        return (
          <div key={s.n} className="flex items-center gap-2">
            <div
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                active
                  ? 'border-cv-accent bg-cv-accent/15 text-cv-accent'
                  : done
                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-500'
                    : 'border-cv-border/60 text-cv-muted'
              }`}
            >
              <span
                className={`w-6 h-6 rounded-full flex items-center justify-center ${
                  active ? 'bg-cv-accent text-white' : done ? 'bg-emerald-500 text-white' : 'bg-cv-deep'
                }`}
              >
                {done ? <Check className="w-3.5 h-3.5" /> : <Icon className="w-3.5 h-3.5" />}
              </span>
              <span className="hidden sm:inline">{s.label}</span>
            </div>
            {idx < steps.length - 1 && (
              <div className={`w-6 h-px ${done ? 'bg-emerald-500/50' : 'bg-cv-border/60'}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
