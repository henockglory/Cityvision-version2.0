import { useState, type ReactNode } from 'react';

interface AnimatedHintProps {
  children: ReactNode;
  hint: string;
  className?: string;
}

/** Short explanatory text that fades in below the label on hover/focus. */
export default function AnimatedHint({ children, hint, className = '' }: AnimatedHintProps) {
  const [visible, setVisible] = useState(false);

  return (
    <span
      className={`inline-flex flex-col ${className}`}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      {children}
      <span
        className={`text-[10px] text-cv-muted leading-tight mt-0.5 transition-all duration-200 motion-reduce:transition-none ${
          visible ? 'opacity-100 translate-y-0 max-h-8' : 'opacity-0 -translate-y-1 max-h-0 overflow-hidden'
        }`}
        aria-hidden={!visible}
      >
        {hint}
      </span>
    </span>
  );
}
