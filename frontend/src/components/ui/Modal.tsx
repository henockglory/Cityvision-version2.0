import { useEffect, type ReactNode } from 'react';
import ModalPortal from '@/components/ui/ModalPortal';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  footerLeft?: ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl' | '4xl' | '5xl' | '6xl' | 'studio';
  className?: string;
  id?: string;
}

const widthClass = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '3xl': 'max-w-3xl',
  '4xl': 'max-w-4xl',
  '5xl': 'max-w-5xl',
  '6xl': 'max-w-6xl',
  studio: 'max-w-[min(98vw,1320px)]',
};

export default function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  footerLeft,
  maxWidth = 'lg',
  className = '',
  id,
}: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <ModalPortal>
      <div
        className="cv-modal-overlay fixed inset-0 z-[110] flex items-center justify-center p-4"
        onClick={(e) => {
          if (e.target === e.currentTarget) onClose();
        }}
        role="presentation"
      >
        <div
          id={id}
          className={`cv-card w-full ${widthClass[maxWidth]} p-6 animate-fade-in flex flex-col ${className}`}
          role="dialog"
          aria-modal="true"
          onClick={(e) => e.stopPropagation()}
        >
          {title && (
            <h2 className="font-display text-lg font-semibold text-cv-text mb-4 shrink-0">{title}</h2>
          )}
          <div className="flex flex-col flex-1 min-h-0 overflow-hidden">{children}</div>
          {(footer || footerLeft) && (
            <div className="flex items-center justify-between gap-3 mt-6 pt-4 border-t border-cv-border/50 shrink-0">
              <div>{footerLeft}</div>
              <div className="flex gap-3 justify-end flex-1">{footer}</div>
            </div>
          )}
        </div>
      </div>
    </ModalPortal>
  );
}
