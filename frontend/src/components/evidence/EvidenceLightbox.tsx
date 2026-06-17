import { useState } from 'react';
import { X, ZoomIn } from 'lucide-react';
import type { EvidenceBBox } from '@/lib/evidence';
import { EvidenceImage } from './EvidenceMedia';

interface EvidenceLightboxProps {
  apiUrl: string;
  alt: string;
  bbox?: EvidenceBBox | null;
  onClose: () => void;
}

export default function EvidenceLightbox({ apiUrl, alt, bbox, onClose }: EvidenceLightboxProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
    >
      <button
        type="button"
        className="absolute top-4 right-4 p-2 rounded-lg bg-black/50 text-white hover:bg-black/70"
        onClick={onClose}
        aria-label="Fermer"
      >
        <X className="w-5 h-5" />
      </button>
      <div className="relative max-w-5xl w-full max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
        <EvidenceImage apiUrl={apiUrl} alt={alt} className="w-full h-auto max-h-[85vh] object-contain rounded-lg" />
        {bbox && (
          <div
            className="absolute border-2 border-cv-accent pointer-events-none"
            style={{
              left: `${Math.min(100, Math.max(0, (bbox.x ?? 0) * 100))}%`,
              top: `${Math.min(100, Math.max(0, (bbox.y ?? 0) * 100))}%`,
              width: `${Math.min(100, Math.max(2, (bbox.width ?? 0.1) * 100))}%`,
              height: `${Math.min(100, Math.max(2, (bbox.height ?? 0.1) * 100))}%`,
            }}
          />
        )}
      </div>
    </div>
  );
}

interface EvidenceImageTileProps {
  apiUrl: string;
  label: string;
  bbox?: EvidenceBBox | null;
  onOpen: () => void;
}

export function EvidenceImageTile({ apiUrl, label, bbox, onOpen }: EvidenceImageTileProps) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group relative aspect-video rounded-lg overflow-hidden border border-cv-border bg-black/40 text-left"
    >
      <EvidenceImage apiUrl={apiUrl} alt={label} />
      {bbox && (
        <div
          className="absolute border border-cv-accent/90 bg-cv-accent/10 pointer-events-none"
          style={{
            left: `${Math.min(100, Math.max(0, (bbox.x ?? 0) * 100))}%`,
            top: `${Math.min(100, Math.max(0, (bbox.y ?? 0) * 100))}%`,
            width: `${Math.min(100, Math.max(2, (bbox.width ?? 0.1) * 100))}%`,
            height: `${Math.min(100, Math.max(2, (bbox.height ?? 0.1) * 100))}%`,
          }}
        />
      )}
      <span className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 to-transparent px-2 py-1.5 text-[10px] text-white flex items-center justify-between">
        {label}
        <ZoomIn className="w-3 h-3 opacity-70 group-hover:opacity-100" />
      </span>
    </button>
  );
}

export function useLightbox() {
  const [lightbox, setLightbox] = useState<{ apiUrl: string; alt: string; bbox?: EvidenceBBox | null } | null>(null);
  return {
    lightbox,
    openLightbox: (apiUrl: string, alt: string, bbox?: EvidenceBBox | null) => setLightbox({ apiUrl, alt, bbox }),
    closeLightbox: () => setLightbox(null),
  };
}
