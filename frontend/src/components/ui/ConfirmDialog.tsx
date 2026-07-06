import { type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, Trash2 } from 'lucide-react';
import Modal from '@/components/ui/Modal';
import DialogTourHelpButton from '@/components/ui/DialogTourHelpButton';
import { useDialogTour } from '@/hooks/useDialogTour';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  detail?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  loading?: boolean;
  loadingLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  /** Désactive le tutoriel contextuel pour ce dialogue. */
  tourDisabled?: boolean;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  detail,
  confirmLabel = 'Confirmer',
  cancelLabel = 'Annuler',
  danger = false,
  loading = false,
  loadingLabel = '…',
  onConfirm,
  onCancel,
  tourDisabled = false,
}: ConfirmDialogProps) {
  const Icon = danger ? Trash2 : AlertTriangle;
  const startTour = useDialogTour('confirmDialog', open && !tourDisabled);

  return (
    <Modal
      open={open}
      onClose={onCancel}
      id="confirm-dialog"
      maxWidth="sm"
      className={danger ? 'border-red-500/25 shadow-xl shadow-red-950/20' : ''}
      footerLeft={!tourDisabled ? <DialogTourHelpButton onClick={() => startTour()} /> : undefined}
      footer={
        <div id="confirm-dialog-actions" className="flex w-full gap-3 justify-end">
          <button type="button" onClick={onCancel} disabled={loading} className="cv-btn-secondary min-w-[5.5rem]">
            {cancelLabel}
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={(e) => {
              e.stopPropagation();
              onConfirm();
            }}
            className={danger ? 'cv-btn-danger min-w-[5.5rem]' : 'cv-btn-primary min-w-[5.5rem]'}
          >
            {danger && <Trash2 className="w-4 h-4" />}
            {loading ? loadingLabel : confirmLabel}
          </button>
        </div>
      }
    >
      <div
        id="confirm-dialog-body"
        className="flex flex-col sm:flex-row items-center sm:items-start gap-4 text-center sm:text-left"
        role="alertdialog"
        aria-labelledby="confirm-title"
      >
        <div
          className={`shrink-0 w-14 h-14 rounded-2xl flex items-center justify-center ${
            danger
              ? 'bg-gradient-to-br from-red-500/25 to-red-600/5 border border-red-500/30 ring-4 ring-red-500/10'
              : 'bg-cv-accent/10 border border-cv-accent/25 ring-4 ring-cv-accent/10'
          }`}
        >
          <Icon className={`w-6 h-6 ${danger ? 'text-red-400' : 'text-cv-accent'}`} />
        </div>
        <div className="flex-1 min-w-0">
          <h2 id="confirm-title" className="font-display text-xl font-semibold text-cv-text tracking-tight">
            {title}
          </h2>
          <p className="text-sm text-cv-muted mt-2 leading-relaxed">{message}</p>
          {detail && (
            <p className="mt-3 text-xs font-mono text-cv-muted/90 bg-cv-deep/50 border border-cv-border/50 rounded-lg px-3 py-2 truncate">
              {detail}
            </p>
          )}
        </div>
      </div>
    </Modal>
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
