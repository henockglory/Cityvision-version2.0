import { useEffect, type ReactNode } from 'react';
import ModalPortal from '@/components/ui/ModalPortal';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  footerLeft?: ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  className?: string;
}

const widthClass = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
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
        className="cv-modal-overlay fixed inset-0 z-[60] flex items-center justify-center p-4"
        onClick={onClose}
        role="presentation"
      >
        <div
          className={`cv-card w-full ${widthClass[maxWidth]} p-6 animate-fade-in ${className}`}
          role="dialog"
          aria-modal="true"
          onClick={(e) => e.stopPropagation()}
        >
          {title && (
            <h2 className="font-display text-lg font-semibold text-cv-text mb-4">{title}</h2>
          )}
          <div>{children}</div>
          {(footer || footerLeft) && (
            <div className="flex items-center justify-between gap-3 mt-6 pt-4 border-t border-cv-border/50">
              <div>{footerLeft}</div>
              <div className="flex gap-3 justify-end flex-1">{footer}</div>
            </div>
          )}
        </div>
      </div>
    </ModalPortal>
  );
}
