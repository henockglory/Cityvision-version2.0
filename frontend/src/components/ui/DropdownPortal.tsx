import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

interface DropdownPortalProps {
  anchorRef: React.RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  minWidth?: number;
  zIndex?: number;
  align?: 'left' | 'right';
}

export default function DropdownPortal({
  anchorRef,
  open,
  onClose,
  children,
  minWidth = 160,
  zIndex = 100,
  align = 'right',
}: DropdownPortalProps) {
  const portalRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  const updatePosition = () => {
    if (!anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    const left =
      align === 'left'
        ? Math.max(8, rect.left)
        : Math.max(8, rect.right - minWidth);
    setPos({
      top: rect.bottom + 4,
      left,
    });
  };

  useEffect(() => {
    if (!open) return;
    updatePosition();
    window.addEventListener('scroll', updatePosition, true);
    window.addEventListener('resize', updatePosition);
    return () => {
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [open, anchorRef, minWidth, align]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const target = e.target as Node;
      if (anchorRef.current?.contains(target)) return;
      if (portalRef.current?.contains(target)) return;
      onClose();
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  return createPortal(
    <div
      ref={portalRef}
      className="fixed cv-dropdown-panel"
      style={{ top: pos.top, left: pos.left, minWidth, zIndex }}
    >
      {children}
    </div>,
    document.body,
  );
}
