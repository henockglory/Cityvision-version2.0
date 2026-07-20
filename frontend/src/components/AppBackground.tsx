import { useEffect, useRef } from 'react';
import { useUiStore } from '@/stores/uiStore';

/** Theme-aware premium background with subtle parallax. */
export default function AppBackground() {
  const theme = useUiStore((s) => s.theme);
  const layerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    let raf = 0;
    const onMove = (e: MouseEvent) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const x = (e.clientX / window.innerWidth - 0.5) * 12;
        const y = (e.clientY / window.innerHeight - 0.5) * 8;
        layer.style.transform = `translate(${x}px, ${y}px) scale(1.05)`;
      });
    };
    window.addEventListener('mousemove', onMove, { passive: true });
    return () => {
      window.removeEventListener('mousemove', onMove);
      cancelAnimationFrame(raf);
    };
  }, []);

  const isLight = theme === 'light';

  return (
    <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none" aria-hidden>
      <div
        ref={layerRef}
        className="absolute inset-0 bg-no-repeat transition-[filter,background-image] duration-500"
        style={{
          backgroundImage: isLight ? 'url(/bg-premium-light.png)' : 'url(/bg-premium-globe.png)',
          backgroundSize: 'cover',
          backgroundPosition: isLight ? 'center' : 'left center',
          filter: isLight ? 'brightness(1.02) saturate(1.05)' : 'brightness(0.65) saturate(1.05)',
        }}
      />
      <div
        className="absolute inset-0 transition-opacity duration-500"
        style={{
          background: isLight
            ? 'linear-gradient(135deg, rgba(241,245,249,0.55) 0%, rgba(224,231,255,0.75) 50%, rgba(241,245,249,0.92) 100%)'
            : 'linear-gradient(90deg, rgba(12,20,36,0.2) 0%, rgba(12,20,36,0.75) 42%, rgba(12,20,36,0.95) 100%)',
        }}
      />
    </div>
  );
}
