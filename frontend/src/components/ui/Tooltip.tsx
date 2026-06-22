import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { useUiStore } from '@/stores/uiStore';

interface TooltipContextValue {
  enabled: boolean;
}

const TooltipCtx = createContext<TooltipContextValue>({ enabled: true });

export function TooltipProvider({ children }: { children: ReactNode }) {
  const enabled = useUiStore((s) => s.tooltipsEnabled);
  return <TooltipCtx.Provider value={{ enabled }}>{children}</TooltipCtx.Provider>;
}

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  side?: 'top' | 'bottom' | 'right';
  delay?: number;
  className?: string;
}

export default function Tooltip({
  content,
  children,
  side = 'top',
  delay = 300,
  className = '',
}: TooltipProps) {
  const { enabled } = useContext(TooltipCtx);
  const id = useId();
  const triggerRef = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const updatePos = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    if (side === 'right') {
      setPos({ top: r.top + r.height / 2, left: r.right + 8 });
    } else {
      setPos({
        top: side === 'top' ? r.top - 8 : r.bottom + 8,
        left: r.left + r.width / 2,
      });
    }
  }, [side]);

  const show = () => {
    if (!enabled) return;
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      updatePos();
      setOpen(true);
    }, delay);
  };

  const hide = () => {
    clearTimeout(timerRef.current);
    setOpen(false);
  };

  useEffect(() => () => clearTimeout(timerRef.current), []);

  return (
    <>
      <span
        ref={triggerRef}
        className={`inline-flex ${className}`}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        aria-describedby={open ? id : undefined}
      >
        {children}
      </span>
      {open && enabled && createPortal(
        <div
          id={id}
          role="tooltip"
          className="fixed z-[200] max-w-xs px-3 py-2 text-xs leading-relaxed rounded-lg
            bg-cv-deep border border-cv-border text-cv-text shadow-soft pointer-events-none
            animate-fade-in -translate-x-1/2"
          style={{
            top: pos.top,
            left: pos.left,
            transform:
              side === 'right'
                ? 'translate(0, -50%)'
                : `translate(-50%, ${side === 'top' ? '-100%' : '0'})`,
          }}
        >
          {content}
        </div>,
        document.body,
      )}
    </>
  );
}
