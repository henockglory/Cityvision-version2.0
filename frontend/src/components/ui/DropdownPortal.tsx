import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

const VIEWPORT_MARGIN = 8;
const GAP = 4;

interface DropdownPortalProps {
  anchorRef: React.RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  minWidth?: number;
  zIndex?: number;
  align?: 'left' | 'right';
}

interface PortalPos {
  top: number;
  left: number;
  maxHeight: number;
  width: number;
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
  const [pos, setPos] = useState<PortalPos>({
    top: 0,
    left: 0,
    maxHeight: 288,
    width: minWidth,
  });

  const updatePosition = useCallback(() => {
    if (!anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    const panel = portalRef.current;
    const measuredW = Math.max(minWidth, panel?.offsetWidth || minWidth);
    const measuredH = panel?.scrollHeight || panel?.offsetHeight || 240;
    const width = Math.min(measuredW, vw - VIEWPORT_MARGIN * 2);

    const spaceBelow = vh - rect.bottom - VIEWPORT_MARGIN - GAP;
    const spaceAbove = rect.top - VIEWPORT_MARGIN - GAP;
    const preferBelow = spaceBelow >= Math.min(measuredH, 160) || spaceBelow >= spaceAbove;
    const available = Math.max(120, preferBelow ? spaceBelow : spaceAbove);
    const maxHeight = available;

    let top: number;
    if (preferBelow) {
      top = rect.bottom + GAP;
    } else {
      const h = Math.min(measuredH, maxHeight);
      top = Math.max(VIEWPORT_MARGIN, rect.top - GAP - h);
    }

    let left = align === 'left' ? rect.left : rect.right - width;
    left = Math.min(Math.max(VIEWPORT_MARGIN, left), vw - width - VIEWPORT_MARGIN);

    setPos({ top, left, maxHeight, width });
  }, [anchorRef, minWidth, align]);

  useLayoutEffect(() => {
    if (!open) return;
    updatePosition();
    const id = requestAnimationFrame(() => updatePosition());
    return () => cancelAnimationFrame(id);
  }, [open, updatePosition, children]);

  useEffect(() => {
    if (!open) return;
    const onScrollOrResize = () => updatePosition();
    window.addEventListener('scroll', onScrollOrResize, true);
    window.addEventListener('resize', onScrollOrResize);
    const el = portalRef.current;
    const ro = typeof ResizeObserver !== 'undefined' && el ? new ResizeObserver(() => updatePosition()) : null;
    if (el && ro) ro.observe(el);
    return () => {
      window.removeEventListener('scroll', onScrollOrResize, true);
      window.removeEventListener('resize', onScrollOrResize);
      ro?.disconnect();
    };
  }, [open, updatePosition]);

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
      className="fixed cv-dropdown-panel overflow-y-auto overscroll-contain"
      style={{
        top: pos.top,
        left: pos.left,
        minWidth: Math.max(minWidth, pos.width),
        width: pos.width > minWidth ? pos.width : undefined,
        maxHeight: pos.maxHeight,
        zIndex,
        ['--cv-dropdown-max-h' as string]: `${pos.maxHeight}px`,
      }}
    >
      {children}
    </div>,
    document.body,
  );
}
