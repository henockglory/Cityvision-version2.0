import type { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}

export default function Card({ children, className = '', hover = false }: CardProps) {
  return (
    <div className={`${hover ? 'cv-card-hover' : 'cv-card'} ${className}`}>{children}</div>
  );
}
