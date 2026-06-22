import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { Shapes } from 'lucide-react';
import { iconForCategory } from '@/lib/iconMap';
import { iconTokens } from '@/lib/iconTokens';

interface IconBadgeProps {
  src?: string;
  alt?: string;
  size?: 'sm' | 'md' | 'lg';
  category?: string;
  children?: ReactNode;
  className?: string;
}

const SIZES = {
  sm: `shrink-0 rounded-lg bg-cv-surface/80 border border-cv-border/50 backdrop-blur-sm flex items-center justify-center p-1 ${iconTokens.item}`,
  md: `shrink-0 rounded-lg bg-cv-surface/80 border border-cv-border/50 backdrop-blur-sm flex items-center justify-center p-1 ${iconTokens.item}`,
  lg: `shrink-0 rounded-lg bg-cv-surface/80 border border-cv-border/50 backdrop-blur-sm flex items-center justify-center p-1.5 ${iconTokens.category}`,
};

/** Glass container for PNG/SVG icons used across the design system. */
export default function IconBadge({
  src,
  alt = '',
  size = 'md',
  category,
  children,
  className = '',
}: IconBadgeProps) {
  const [svgMarkup, setSvgMarkup] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const fallbackSrc = category ? iconForCategory(category) : '/icons/rule.svg';

  useEffect(() => {
    if (!src) return;
    let cancelled = false;
    setFailed(false);
    setSvgMarkup(null);

    async function run() {
      const iconSrc = src;
      if (!iconSrc) return;
      try {
        const res = await fetch(iconSrc);
        if (!res.ok) {
          if (!cancelled) setFailed(true);
          return;
        }
        let text = await res.text();

        text = text
          .replace(/fill="undefined"/g, 'fill="currentColor"')
          .replace(/stroke="undefined"/g, 'stroke="currentColor"')
          .replace(/<rect\s+width="64"\s+height="64"[^>]*\/?>/g, '');

        text = text.replace(/<svg([^>]*)>/, (_m, attrs: string) => {
          let a = attrs.replace(/\s(width|height)="[^"]*"/g, '');
          if (!/viewBox=/.test(a)) a += ' viewBox="0 0 64 64"';
          return `<svg${a} width="100%" height="100%">`;
        });

        if (!cancelled) setSvgMarkup(text);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, [src]);

  const showFallbackImg = failed && fallbackSrc;
  const isEmpty = src && !svgMarkup && !showFallbackImg && !children;

  return (
    <div
      className={`${SIZES[size]} ${className}`}
      style={{ color: 'rgb(var(--cv-accent))' }}
      data-icon-empty={isEmpty ? 'true' : 'false'}
    >
      {children}
      {!children && src && svgMarkup && (
        <div className="w-full h-full flex items-center justify-center" aria-label={alt} dangerouslySetInnerHTML={{ __html: svgMarkup }} />
      )}
      {!children && showFallbackImg && (
        <img src={fallbackSrc} alt={alt} className="w-full h-full object-contain" />
      )}
      {!children && isEmpty && <Shapes className="w-4 h-4 text-cv-muted/70" aria-hidden />}
    </div>
  );
}
