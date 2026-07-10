import { useMemo, useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Download, Film, Radio, RefreshCw, AlertCircle } from 'lucide-react';
import {
  evidenceMediaSlots,
  evidenceQuality,
  evidenceThumbnailUrl,
  isValidEvidenceBBox,
  parseEvidenceSnapshot,
  type EvidenceSnapshot,
} from '@/lib/evidence';
import { getAuthCredentials } from '@/lib/authSession';
import { useEvidenceMediaUrl } from '@/hooks/useEvidenceMediaUrl';
import EvidenceLightbox, { EvidenceImageTile, useLightbox } from './EvidenceLightbox';
import { EvidenceVideo } from './EvidenceMedia';

function formatValue(val: unknown): string {
  if (val == null) return '';
  return String(val);
}

interface EvidenceViewerProps {
  evidence: EvidenceSnapshot | Record<string, unknown> | undefined;
  cameraId?: string;
  ruleId?: string;
  compact?: boolean;
}

export default function EvidenceViewer({ evidence: raw, cameraId, ruleId, compact = false }: EvidenceViewerProps) {
  const { t } = useTranslation();
  const { lightbox, openLightbox, closeLightbox } = useLightbox();
  const { orgId } = getAuthCredentials();
  const ev = useMemo(() => parseEvidenceSnapshot(raw), [raw]);
  const pkg = ev.package;
  const mediaSlots = useMemo(() => evidenceMediaSlots(ev, orgId), [ev, orgId]);
  const { clip: clipUrl, scene: sceneUrl, subject: subjectUrl, plate: plateUrl } = mediaSlots.urls;

  const scene = pkg?.images?.find((i) => i.role === 'scene');
  const subject = pkg?.images?.find((i) => i.role === 'subject');
  const plateImg = pkg?.images?.find((i) => i.role === 'plate');

  const [clipRetry, setClipRetry] = useState(0);
  const clipMedia = useEvidenceMediaUrl(clipUrl, { mimeFallback: 'video/mp4', retryKey: clipRetry });
  const sceneMedia = useEvidenceMediaUrl(sceneUrl, { mimeFallback: 'image/jpeg' });
  const subjectMedia = useEvidenceMediaUrl(subjectUrl, { mimeFallback: 'image/jpeg' });
  const plateMedia = useEvidenceMediaUrl(plateUrl, { mimeFallback: 'image/jpeg' });
  const [clipDuration, setClipDuration] = useState(0);

  useEffect(() => {
    setClipDuration(0);
  }, [clipUrl, clipRetry]);

  const quality = useMemo(
    () => evidenceQuality(ev, orgId, {
      clip: { loading: clipMedia.loading, error: Boolean(clipMedia.error), blobUrl: clipMedia.blobUrl, duration: clipDuration },
      scene: { loading: sceneMedia.loading, error: Boolean(sceneMedia.error), blobUrl: sceneMedia.blobUrl },
      subject: { loading: subjectMedia.loading, error: Boolean(subjectMedia.error), blobUrl: subjectMedia.blobUrl },
      plate: { loading: plateMedia.loading, error: Boolean(plateMedia.error), blobUrl: plateMedia.blobUrl },
    }),
    [ev, orgId, clipMedia, sceneMedia, subjectMedia, plateMedia, clipDuration],
  );

  const badgeClass = quality.state === 'complete'
    ? 'bg-metric-rules/20 text-metric-rules'
    : quality.state === 'loading'
      ? 'bg-cv-accent/15 text-cv-accent'
      : quality.state === 'metadata_only'
        ? 'bg-cv-muted/20 text-cv-muted'
        : 'bg-metric-alerts/15 text-metric-alerts';

  const badgeLabel = {
    complete: t('evidence.complete'),
    loading: t('evidence.loadingMedia'),
    partial: t('evidence.partial', { have: quality.loaded, total: quality.expected || mediaSlots.total }),
    failed: t('evidence.loadFailed'),
    metadata_only: t('evidence.metadataOnly'),
  }[quality.state];

  // Preuves historiques du mode segments (abandonné) ou capture avec bbox
  // sans contenu détecté : contenu visuel potentiellement non fiable.
  const captureSource = pkg?.metadata?.capture_source as string | undefined;
  const bboxQualityOk = pkg?.metadata?.bbox_quality_ok as boolean | undefined;
  const isLegacyEvidence = captureSource === 'segment';
  const isLowQualityEvidence = bboxQualityOk === false;

  const plateValue = formatValue(ev.plate_number);
  const metaFields = [
    {
      label: t('evidence.plate'),
      value: plateValue || (plateUrl ? t('evidence.plateUnread') : ''),
    },
    { label: t('evidence.face'), value: formatValue(ev.face_label) },
    { label: t('evidence.eventType'), value: formatValue(ev.event_type) },
    { label: t('evidence.class'), value: formatValue(ev.class_name) },
    { label: t('evidence.speed'), value: ev.speed_kmh != null ? `${ev.speed_kmh} km/h` : '' },
    { label: t('evidence.zone'), value: formatValue(ev.zone_id) },
    { label: t('evidence.track'), value: formatValue(ev.track_id) },
  ].filter((f) => f.value !== '');

  const hasMediaUrls = Boolean(clipUrl || sceneUrl || subjectUrl || plateUrl);
  const thumbApiUrl = evidenceThumbnailUrl(ev, orgId);
  const thumbMedia = useEvidenceMediaUrl(thumbApiUrl);
  const displayClipSec = clipDuration > 0 ? Math.round(clipDuration) : (pkg?.clip?.duration_sec ?? 6);

  const retryClip = useCallback(() => setClipRetry((n) => n + 1), []);

  if (!hasMediaUrls && !ev.bbox && ev.confidence == null && metaFields.length === 0) {
    return <p className="text-xs text-cv-muted py-2">{t('evidence.none')}</p>;
  }

  return (
    <div id="evidence-viewer" className={`space-y-3 ${compact ? '' : 'mt-2'}`}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="font-medium text-sm text-cv-text flex items-center gap-2">
          <Film className="w-4 h-4 text-cv-accent" />
          {t('evidence.title')}
        </p>
        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${badgeClass}`}>
          {badgeLabel}
        </span>
      </div>

      {(isLegacyEvidence || isLowQualityEvidence) && (
        <p className="text-xs text-amber-500 flex items-center gap-1">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          {isLegacyEvidence
            ? t('evidence.legacySegment', { defaultValue: 'Preuve issue de l\u2019ancien mode segments — contenu visuel potentiellement décalé.' })
            : t('evidence.lowQualityBBox', { defaultValue: 'Cible non confirmée dans le cadre — preuve à vérifier manuellement.' })}
        </p>
      )}

      {clipUrl && (
        <div id="evidence-viewer-clip">
        <EvidenceVideo
          apiUrl={clipUrl}
          durationSec={displayClipSec}
          onDuration={setClipDuration}
        />
        </div>
      )}

      {(sceneUrl || subjectUrl || plateUrl) && (
        <div id="evidence-viewer-images" className={`grid gap-2 ${plateUrl ? 'grid-cols-3' : 'grid-cols-2'}`}>
          {sceneUrl && (
            <EvidenceImageTile
              apiUrl={sceneUrl}
              label={scene?.label ?? t('evidence.scene')}
              bbox={isValidEvidenceBBox(scene?.bbox ?? ev.bbox) ? (scene?.bbox ?? ev.bbox) : undefined}
              onOpen={() => openLightbox(
                sceneUrl,
                scene?.label ?? t('evidence.scene'),
                isValidEvidenceBBox(scene?.bbox ?? ev.bbox) ? (scene?.bbox ?? ev.bbox) : undefined,
              )}
            />
          )}
          {subjectUrl && (
            <EvidenceImageTile
              apiUrl={subjectUrl}
              label={subject?.label ?? t('evidence.subject')}
              onOpen={() => openLightbox(
                subjectUrl,
                subject?.label ?? t('evidence.subject'),
              )}
            />
          )}
          {plateUrl && (
            <EvidenceImageTile
              apiUrl={plateUrl}
              label={plateImg?.label ?? t('evidence.plateCrop')}
              onOpen={() => openLightbox(plateUrl, plateImg?.label ?? t('evidence.plateCrop'))}
            />
          )}
        </div>
      )}

      {!plateUrl && Array.isArray(pkg?.metadata?.missing_roles) && (pkg.metadata.missing_roles as string[]).includes('plate') && (
        <p className="text-xs text-cv-muted flex items-center gap-1">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          {t('evidence.plateUnavailable', { defaultValue: 'Plaque non disponible (crop impossible sur cette capture).' })}
        </p>
      )}

      {quality.state === 'failed' && hasMediaUrls && (
        <div className="flex items-center gap-2 p-3 rounded-lg border border-metric-alerts/30 bg-metric-alerts/10 text-xs text-cv-muted">
          <AlertCircle className="w-4 h-4 text-metric-alerts shrink-0" />
          <span className="flex-1">{t('evidence.loadFailed')}</span>
          {clipUrl && (
            <button type="button" className="cv-btn-secondary text-xs py-1 px-2" onClick={retryClip}>
              <RefreshCw className="w-3 h-3 inline mr-1" />
              {t('common.retry', { defaultValue: 'Réessayer' })}
            </button>
          )}
        </div>
      )}

      {quality.state === 'metadata_only' && ev.bbox && (
        <p className="text-xs text-cv-muted flex items-center gap-1">
          <AlertCircle className="w-3.5 h-3.5" />
          {t('evidence.metadataOnly')}
        </p>
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
        {ruleId && (
          <Link
            to="/rules"
            state={{ editRuleId: ruleId, editStep: 3 }}
            className="cv-btn-secondary text-xs py-1 px-2 inline-flex items-center gap-1"
          >
            Personnaliser les preuves de cette règle
          </Link>
        )}
        {cameraId && (
          <Link to={`/live?camera=${cameraId}`} className="cv-btn-secondary text-xs py-1 px-2 inline-flex items-center gap-1">
            <Radio className="w-3 h-3" />
            {t('evidence.openLive')}
          </Link>
        )}
        {thumbMedia.blobUrl && (
          <a href={thumbMedia.blobUrl} download="evidence-scene.jpg" className="cv-btn-secondary text-xs py-1 px-2 inline-flex items-center gap-1">
            <Download className="w-3 h-3" />
            {t('evidence.download')}
          </a>
        )}
      </div>

      {lightbox && (
        <EvidenceLightbox apiUrl={lightbox.apiUrl} alt={lightbox.alt} bbox={lightbox.bbox} onClose={closeLightbox} />
      )}
    </div>
  );
}
