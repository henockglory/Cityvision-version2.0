import type { ReactNode } from 'react';

interface SplitLayoutProps {
  list: ReactNode;
  detail: ReactNode;
  listCols?: string;
  className?: string;
}

export default function SplitLayout({
  list,
  detail,
  listCols = 'lg:col-span-2',
  className = '',
}: SplitLayoutProps) {
  return (
    <div className={`grid grid-cols-1 lg:grid-cols-5 gap-4 min-h-[420px] ${className}`}>
      <div className={`${listCols} max-h-[70vh] overflow-y-auto`}>{list}</div>
      <div className="lg:col-span-3 cv-card p-5 min-h-[280px]">{detail}</div>
    </div>
  );
}
