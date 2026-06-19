import { useState } from 'react';
import { Film, Loader2, AlertCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useEvidenceMediaUrl } from '@/hooks/useEvidenceMediaUrl';

interface EvidenceVideoProps {
  apiUrl: string;
  durationSec?: number;
  onCanPlay?: (ok: boolean) => void;
  onDuration?: (sec: number) => void;
}

export function EvidenceVideo({ apiUrl, durationSec = 6, onCanPlay, onDuration }: EvidenceVideoProps) {
  const { t } = useTranslation();
  const { blobUrl, loading, error } = useEvidenceMediaUrl(apiUrl, { mimeFallback: 'video/mp4' });
  const [decodeError, setDecodeError] = useState(false);

  const failed = error || decodeError;

  return (
    <div className="relative w-full aspect-video bg-black rounded-xl overflow-hidden border border-cv-border/60">
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/60 z-10">
          <Loader2 className="w-8 h-8 text-cv-accent animate-spin" />
        </div>
      )}
      {failed && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-cv-muted text-xs p-4 z-10">
          <AlertCircle className="w-6 h-6 text-metric-alerts" />
          {t('evidence.loadFailed')}
        </div>
      )}
      {blobUrl && !failed && (
        <video
          src={blobUrl}
          controls
          playsInline
          preload="metadata"
          className="w-full h-full object-contain"
          onLoadedData={() => {
            setDecodeError(false);
          }}
          onLoadedMetadata={(e) => {
            const dur = e.currentTarget.duration;
            if (Number.isFinite(dur) && dur > 0) {
              onDuration?.(dur);
              onCanPlay?.(dur >= 0.5);
            }
          }}
          onError={() => {
            setDecodeError(true);
            onCanPlay?.(false);
          }}
        />
      )}
      <span className="absolute top-2 left-2 text-[10px] bg-black/60 text-white px-2 py-0.5 rounded z-20">
        {t('evidence.clipLabel', { sec: durationSec })}
      </span>
    </div>
  );
}

interface EvidenceImageProps {
  apiUrl: string;
  alt: string;
  className?: string;
}

export function EvidenceImage({ apiUrl, alt, className = 'w-full h-full object-cover' }: EvidenceImageProps) {
  const { t } = useTranslation();
  const { blobUrl, loading, error } = useEvidenceMediaUrl(apiUrl, { mimeFallback: 'image/jpeg' });

  if (loading) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-black/40">
        <Loader2 className="w-5 h-5 text-cv-accent animate-spin" />
      </div>
    );
  }
  if (error || !blobUrl) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center gap-1 bg-black/40 text-[10px] text-cv-muted p-2">
        <AlertCircle className="w-4 h-4 text-metric-alerts" />
        {t('evidence.loadFailed')}
      </div>
    );
  }
  return <img src={blobUrl} alt={alt} className={className} draggable={false} />;
}

interface EvidenceThumbnailProps {
  apiUrl: string;
  className?: string;
}

export function EvidenceThumbnail({ apiUrl, className }: EvidenceThumbnailProps) {
  const { blobUrl, loading, error } = useEvidenceMediaUrl(apiUrl, { mimeFallback: 'image/jpeg' });
  if (loading) {
    return <span className={`animate-pulse bg-cv-surface ${className ?? ''}`} />;
  }
  if (error || !blobUrl) {
    return (
      <span className={`flex items-center justify-center bg-cv-deep/60 border border-cv-border/40 ${className ?? ''}`}>
        <Film className="w-4 h-4 text-cv-muted" />
      </span>
    );
  }
  return <img src={blobUrl} alt="" className={className} />;
}
