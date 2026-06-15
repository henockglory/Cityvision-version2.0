import type { ReactNode } from 'react';

interface IconBadgeProps {
  src?: string;
  alt?: string;
  size?: 'sm' | 'md' | 'lg';
  children?: ReactNode;
  className?: string;
}

const SIZES = {
  sm: 'w-8 h-8 p-1',
  md: 'w-12 h-12 p-1.5',
  lg: 'w-16 h-16 p-2',
};

/** Glass container for PNG/SVG icons used across the design system. */
export default function IconBadge({ src, alt = '', size = 'md', children, className = '' }: IconBadgeProps) {
  return (
    <div
      className={`shrink-0 rounded-lg bg-cv-surface/80 border border-cv-border/50 backdrop-blur-sm flex items-center justify-center ${SIZES[size]} ${className}`}
    >
      {src ? <img src={src} alt={alt} className="w-full h-full object-contain" /> : children}
    </div>
  );
}
