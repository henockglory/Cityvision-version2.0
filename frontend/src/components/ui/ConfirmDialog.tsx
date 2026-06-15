import { useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle } from 'lucide-react';
import ModalPortal from '@/components/ui/ModalPortal';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirmer',
  cancelLabel = 'Annuler',
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <ModalPortal>
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="cv-card w-full max-w-md p-6 animate-fade-in" role="alertdialog" aria-labelledby="confirm-title">
        <div className="flex items-start gap-3 mb-4">
          <div className={`p-2 rounded-lg ${danger ? 'bg-red-500/15' : 'bg-cv-accent/10'}`}>
            <AlertTriangle className={`w-5 h-5 ${danger ? 'text-red-500' : 'text-cv-accent'}`} />
          </div>
          <div>
            <h2 id="confirm-title" className="font-display text-lg font-semibold text-cv-text">
              {title}
            </h2>
            <p className="text-sm text-cv-muted mt-1">{message}</p>
          </div>
        </div>
        <div className="flex gap-3 justify-end">
          <button type="button" onClick={onCancel} className="cv-btn-secondary">
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={danger ? 'cv-btn-danger' : 'cv-btn-primary'}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
    </ModalPortal>
  );
}

export function ToastStack({
  toasts,
}: {
  toasts: Array<{ id: string; message: string; action?: ReactNode }>;
}) {
  if (toasts.length === 0) return null;
  return createPortal(
    <div className="fixed bottom-6 right-6 z-[70] flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => (
        <div
          key={t.id}
          className="cv-card px-4 py-3 flex items-center justify-between gap-3 text-sm animate-slide-in"
        >
          <span className="text-cv-text">{t.message}</span>
          {t.action}
        </div>
      ))}
    </div>,
    document.body,
  );
}
