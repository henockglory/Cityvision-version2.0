import type { ReactNode } from 'react';
import Card from '@/components/ui/Card';

/** @deprecated use ui/Card */
export default function CyberCard({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
  glow?: boolean;
}) {
  return <Card className={className}>{children}</Card>;
}
