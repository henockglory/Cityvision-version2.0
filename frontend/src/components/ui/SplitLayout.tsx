import type { ReactNode } from 'react';

interface SplitLayoutProps {
  list: ReactNode;
  detail: ReactNode;
  listCols?: string;
  className?: string;
  /** Viewport-bound split: each column scrolls independently under the pointer. */
  fillHeight?: boolean;
  listClassName?: string;
}

const paneScroll = 'min-h-0 h-full overflow-y-auto overscroll-y-contain';

/** Two-column layout: independent scroll per side when fillHeight is set. */
export default function SplitLayout({
  list,
  detail,
  listCols = 'lg:col-span-2',
  className = '',
  fillHeight = false,
  listClassName = '',
}: SplitLayoutProps) {
  if (fillHeight) {
    return (
      <div className={`flex flex-col lg:flex-row gap-4 h-full min-h-0 overflow-hidden ${className}`}>
        <div className={`lg:flex-[2] flex-1 ${paneScroll} cv-panel p-2 ${listClassName}`}>
          <div className="space-y-2">{list}</div>
        </div>
        <div className={`lg:flex-[3] flex-1 ${paneScroll} cv-card p-5`}>{detail}</div>
      </div>
    );
  }

  return (
    <div className={`grid grid-cols-1 lg:grid-cols-5 gap-4 items-start ${className}`}>
      <div className={`${listCols} cv-panel p-2 ${listClassName}`}>
        <div className="space-y-2">{list}</div>
      </div>
      <div className="lg:col-span-3 cv-card p-5 min-h-[min(480px,70vh)]">{detail}</div>
    </div>
  );
}
