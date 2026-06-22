import { useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

interface ModalPortalProps {
  children: ReactNode;
  lockScroll?: boolean;
}

export default function ModalPortal({ children, lockScroll = true }: ModalPortalProps) {
  useEffect(() => {
    if (!lockScroll) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [lockScroll]);

  return createPortal(children, document.body);
}
