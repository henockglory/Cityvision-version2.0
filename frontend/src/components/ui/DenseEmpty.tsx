import type { LucideIcon } from 'lucide-react';

interface DenseEmptyProps {
  title: string;
  hint?: string;
  icon?: LucideIcon;
  iconSrc?: string;
  action?: React.ReactNode;
}

export default function DenseEmpty({ title, hint, icon: Icon, iconSrc, action }: DenseEmptyProps) {
  return (
    <div className="flex flex-col items-center justify-center py-5 px-4 text-center">
      {iconSrc ? (
        <img src={iconSrc} alt="" className="w-10 h-10 opacity-70 mb-2" />
      ) : Icon ? (
        <Icon className="w-8 h-8 text-cv-muted/60 mb-2" />
      ) : null}
      <p className="text-sm font-medium text-cv-text">{title}</p>
      {hint && <p className="text-xs text-cv-muted mt-1 max-w-sm">{hint}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
