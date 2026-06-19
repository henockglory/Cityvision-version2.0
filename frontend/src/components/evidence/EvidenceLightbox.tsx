import { useState } from 'react';
import { Download, ZoomIn } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import Modal from '@/components/ui/Modal';
import type { EvidenceBBox } from '@/lib/evidence';
import { useEvidenceMediaUrl } from '@/hooks/useEvidenceMediaUrl';
import { EvidenceImage } from './EvidenceMedia';

interface EvidenceLightboxProps {
  apiUrl: string;
  alt: string;
  bbox?: EvidenceBBox | null;
  onClose: () => void;
}

function BboxOverlay({ bbox }: { bbox: EvidenceBBox }) {
  return (
    <div
      className="absolute border-2 border-cv-accent bg-cv-accent/10 pointer-events-none rounded-sm"
      style={{
        left: `${Math.min(100, Math.max(0, (bbox.x ?? 0) * 100))}%`,
        top: `${Math.min(100, Math.max(0, (bbox.y ?? 0) * 100))}%`,
        width: `${Math.min(100, Math.max(2, (bbox.width ?? 0.1) * 100))}%`,
        height: `${Math.min(100, Math.max(2, (bbox.height ?? 0.1) * 100))}%`,
      }}
    />
  );
}

export default function EvidenceLightbox({ apiUrl, alt, bbox, onClose }: EvidenceLightboxProps) {
  const { t } = useTranslation();
  const { blobUrl } = useEvidenceMediaUrl(apiUrl, { mimeFallback: 'image/jpeg' });

  return (
    <Modal
      open
      onClose={onClose}
      title={alt}
      maxWidth="2xl"
      className="!max-w-3xl !p-4 sm:!p-5"
      footerLeft={
        bbox ? (
          <span className="text-xs text-cv-muted">
            {t('evidence.bboxHint', { defaultValue: 'Cadre bleu = zone détectée' })}
          </span>
        ) : undefined
      }
      footer={
        <>
          {blobUrl && (
            <a
              href={blobUrl}
              download={`evidence-${alt.replace(/\s+/g, '-').toLowerCase()}.jpg`}
              className="cv-btn-secondary text-sm"
            >
              <Download className="w-4 h-4" />
              {t('evidence.download')}
            </a>
          )}
          <button type="button" className="cv-btn-primary text-sm" onClick={onClose}>
            {t('common.close', { defaultValue: 'Fermer' })}
          </button>
        </>
      }
    >
      <div className="flex justify-center rounded-lg bg-black/80 border border-cv-border/60 overflow-hidden">
        <div className="relative inline-block max-w-full">
          <EvidenceImage
            apiUrl={apiUrl}
            alt={alt}
            className="block max-h-[min(70vh,520px)] max-w-full w-auto h-auto object-contain mx-auto"
          />
          {bbox && <BboxOverlay bbox={bbox} />}
        </div>
      </div>
    </Modal>
  );
}

interface EvidenceImageTileProps {
  apiUrl: string;
  label: string;
  bbox?: EvidenceBBox | null;
  onOpen: () => void;
}

export function EvidenceImageTile({ apiUrl, label, bbox, onOpen }: EvidenceImageTileProps) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group relative aspect-video rounded-lg overflow-hidden border border-cv-border/70 bg-black/40 text-left transition-colors hover:border-cv-accent/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-cv-accent/50"
      aria-label={t('evidence.openPreview', { label, defaultValue: `Aperçu : ${label}` })}
    >
      <EvidenceImage apiUrl={apiUrl} alt={label} />
      {bbox && <BboxOverlay bbox={bbox} />}
      <span className="absolute bottom-0 inset-x-0 bg-black/75 px-2 py-1.5 text-[11px] text-white flex items-center justify-between gap-2">
        <span className="truncate">{label}</span>
        <ZoomIn className="w-3.5 h-3.5 shrink-0 opacity-70 group-hover:opacity-100" />
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
