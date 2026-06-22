import { useCallback, useState, type ReactNode } from 'react';
import { ToastStack } from '@/components/ui/ConfirmDialog';

interface ToastItem {
  id: string;
  message: string;
  action?: ReactNode;
}

export function useUndoToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showUndo = useCallback(
    (message: string, onUndo: () => void | Promise<void>, durationMs = 10000) => {
      const id = crypto.randomUUID();
      const action = (
        <button
          type="button"
          className="cv-btn-ghost text-xs py-1 px-2"
          onClick={() => {
            void onUndo();
            dismiss(id);
          }}
        >
          Annuler
        </button>
      );
      setToasts((prev) => [...prev, { id, message, action }]);
      window.setTimeout(() => dismiss(id), durationMs);
    },
    [dismiss],
  );

  const ToastContainer = useCallback(() => <ToastStack toasts={toasts} />, [toasts]);

  return { showUndo, ToastContainer };
}
