import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Download, Film, Radio } from 'lucide-react';
import {
  evidenceCompleteness,
  evidenceThumbnailUrl,
  parseEvidenceSnapshot,
  type EvidenceSnapshot,
} from '@/lib/evidence';
import EvidenceLightbox, { EvidenceImageTile, useLightbox } from './EvidenceLightbox';

function formatValue(val: unknown): string {
  if (val == null) return '';
  return String(val);
}

interface EvidenceViewerProps {
  evidence: EvidenceSnapshot | Record<string, unknown> | undefined;
  cameraId?: string;
  compact?: boolean;
}

export default function EvidenceViewer({ evidence: raw, cameraId, compact = false }: EvidenceViewerProps) {
  const { t } = useTranslation();
  const { lightbox, openLightbox, closeLightbox } = useLightbox();
  const ev = useMemo(() => parseEvidenceSnapshot(raw), [raw]);
  const pkg = ev.package;
  const completeness = evidenceCompleteness(ev);

  const scene = pkg?.images?.find((i) => i.role === 'scene');
  const subject = pkg?.images?.find((i) => i.role === 'subject');
  const clipUrl = pkg?.clip?.url;

  const metaFields = [
    { label: t('evidence.plate'), value: formatValue(ev.plate_number) },
    { label: t('evidence.face'), value: formatValue(ev.face_label) },
    { label: t('evidence.eventType'), value: formatValue(ev.event_type) },
    { label: t('evidence.class'), value: formatValue(ev.class_name) },
    { label: t('evidence.speed'), value: ev.speed_kmh != null ? `${ev.speed_kmh} km/h` : '' },
    { label: t('evidence.zone'), value: formatValue(ev.zone_id) },
    { label: t('evidence.track'), value: formatValue(ev.track_id) },
  ].filter((f) => f.value !== '');

  const hasMedia = Boolean(clipUrl || scene?.url || subject?.url);
  const thumb = evidenceThumbnailUrl(ev);

  if (!hasMedia && !ev.bbox && ev.confidence == null && metaFields.length === 0) {
    return (
      <p className="text-xs text-cv-muted py-2">{t('evidence.none')}</p>
    );
  }

  return (
    <div className={`space-y-3 ${compact ? '' : 'mt-2'}`}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="font-medium text-sm text-cv-text flex items-center gap-2">
          <Film className="w-4 h-4 text-cv-accent" />
          {t('evidence.title')}
        </p>
        <span
          className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
            completeness.complete ? 'bg-metric-rules/20 text-metric-rules' : 'bg-metric-alerts/15 text-metric-alerts'
          }`}
        >
          {completeness.complete ? t('evidence.complete') : t('evidence.partial', { have: completeness.have, total: completeness.total })}
        </span>
      </div>

      {clipUrl && (
        <div className="relative w-full aspect-video bg-black rounded-xl overflow-hidden border border-cv-border/60">
          <video
            src={clipUrl}
            controls
            playsInline
            preload="metadata"
            className="w-full h-full object-contain"
          />
          <span className="absolute top-2 left-2 text-[10px] bg-black/60 text-white px-2 py-0.5 rounded">
            {t('evidence.clipLabel', { sec: pkg?.clip?.duration_sec ?? 6 })}
          </span>
        </div>
      )}

      {(scene?.url || subject?.url) && (
        <div className="grid grid-cols-2 gap-2">
          {scene?.url && (
            <EvidenceImageTile
              src={scene.url}
              label={scene.label ?? t('evidence.scene')}
              onOpen={() => openLightbox(scene.url!, scene.label ?? t('evidence.scene'))}
            />
          )}
          {subject?.url && (
            <EvidenceImageTile
              src={subject.url}
              label={subject.label ?? t('evidence.subject')}
              bbox={subject.bbox ?? ev.bbox}
              onOpen={() => openLightbox(subject.url!, subject.label ?? t('evidence.subject'), subject.bbox ?? ev.bbox)}
            />
          )}
        </div>
      )}

      {!hasMedia && ev.bbox && (
        <div className="relative w-full max-w-xs aspect-video bg-black/40 rounded-lg border border-cv-border/50 overflow-hidden">
          <div
            className="absolute border-2 border-cv-accent/80 bg-cv-accent/10"
            style={{
              left: `${Math.min(100, Math.max(0, (ev.bbox.x ?? 0) * 100))}%`,
              top: `${Math.min(100, Math.max(0, (ev.bbox.y ?? 0) * 100))}%`,
              width: `${Math.min(100, Math.max(2, (ev.bbox.width ?? 0.1) * 100))}%`,
              height: `${Math.min(100, Math.max(2, (ev.bbox.height ?? 0.1) * 100))}%`,
            }}
          />
          <span className="absolute bottom-1 right-1 text-[10px] text-cv-muted">{t('evidence.bboxOnly')}</span>
        </div>
      )}

      {ev.confidence != null && (
        <p className="text-xs text-cv-muted">
          {t('evidence.confidence')}{' '}
          <span className="text-cv-text">
            {Math.round(Number(ev.confidence) * (Number(ev.confidence) <= 1 ? 100 : 1))}%
          </span>
        </p>
      )}

      {metaFields.length > 0 && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          {metaFields.map((f) => (
            <p key={f.label} className="text-cv-muted">
              {f.label}: <span className="text-cv-text">{f.value}</span>
            </p>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        {cameraId && (
          <Link to={`/live?camera=${cameraId}`} className="cv-btn-secondary text-xs py-1 px-2 inline-flex items-center gap-1">
            <Radio className="w-3 h-3" />
            {t('evidence.openLive')}
          </Link>
        )}
        {thumb && (
          <a href={thumb} download target="_blank" rel="noreferrer" className="cv-btn-secondary text-xs py-1 px-2 inline-flex items-center gap-1">
            <Download className="w-3 h-3" />
            {t('evidence.download')}
          </a>
        )}
      </div>

      {lightbox && (
        <EvidenceLightbox src={lightbox.src} alt={lightbox.alt} bbox={lightbox.bbox} onClose={closeLightbox} />
      )}
    </div>
  );
}
