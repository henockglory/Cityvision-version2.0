import { useMemo, useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Download, Film, Radio, RefreshCw, AlertCircle } from 'lucide-react';
import {
  evidenceMediaSlots,
  evidenceQuality,
  evidenceThumbnailUrl,
  aiEvidenceStatus,
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
  const aiStatus = useMemo(() => aiEvidenceStatus(ev), [ev]);
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

  const badgeClass = (aiStatus === 'complete' || quality.state === 'complete')
    ? 'bg-metric-rules/20 text-metric-rules'
    : aiStatus === 'pending' || quality.state === 'loading'
      ? 'bg-cv-accent/15 text-cv-accent'
      : quality.state === 'metadata_only'
        ? 'bg-cv-muted/20 text-cv-muted'
        : 'bg-metric-alerts/15 text-metric-alerts';

  const badgeLabel = aiStatus
    ? {
        complete: t('evidence.complete'),
        partial: t('evidence.partialAi', { defaultValue: 'Preuve partielle (IA)' }),
        failed: t('evidence.loadFailed'),
        pending: t('evidence.loadingMedia'),
      }[aiStatus]
    : {
        complete: t('evidence.complete'),
        loading: t('evidence.loadingMedia'),
        partial: t('evidence.partial', { have: quality.loaded, total: quality.expected || mediaSlots.total }),
        failed: t('evidence.loadFailed'),
        metadata_only: t('evidence.metadataOnly'),
      }[quality.state];

  // Preuves historiques du mode segments (abandonné) ou capture avec bbox
  // sans contenu détecté : contenu visuel potentiellement non fiable.
  const captureSource = pkg?.metadata?.capture_source as string | undefined;
  const frigateBboxEmbedded = pkg?.metadata?.frigate_bbox_embedded === true;
  const bboxQualityOk = pkg?.metadata?.bbox_quality_ok as boolean | undefined;
  const evidenceStatus = String(pkg?.metadata?.evidence_status ?? aiStatus ?? '');
  const loopPos = pkg?.metadata?.demo_loop_position_sec;
  const loopDur = pkg?.metadata?.demo_loop_duration_sec;
  const missingRoles = Array.isArray(pkg?.metadata?.missing_roles)
    ? (pkg.metadata.missing_roles as string[])
    : [];
  const frigateFailReason = formatValue(
    pkg?.metadata?.frigate_error
      ?? pkg?.metadata?.frigate_fail_reason
      ?? pkg?.metadata?.evidence_error,
  );
  const isLegacyEvidence = captureSource === 'segment';
  const isLowQualityEvidence = bboxQualityOk === false;
  const isIncompleteEvidence = evidenceStatus === 'partial' || evidenceStatus === 'failed';
  // Frigate scene JPEG already includes native bbox — never overlay ai-engine coords on top.
  const metaBBox = pkg?.metadata?.bbox as typeof ev.bbox | undefined;
  const displayBBox =
    captureSource === 'frigate_track' && isValidEvidenceBBox(metaBBox)
      ? metaBBox
      : isValidEvidenceBBox(ev.bbox)
        ? ev.bbox
        : undefined;
  const sceneBboxOverlay =
    !frigateBboxEmbedded && isValidEvidenceBBox(scene?.bbox ?? displayBBox)
      ? (scene?.bbox ?? displayBBox)
      : undefined;

  const plateValue = formatValue(ev.plate_number ?? pkg?.metadata?.plate_number);
  const plateConf = pkg?.metadata?.plate_confidence;
  const identificationRaw = String(
    (pkg?.metadata?.identification as string | undefined)
      ?? (pkg?.metadata?.plate_status as string | undefined)
      ?? (ev as { identification?: string }).identification
      ?? (ev as { plate_status?: string }).plate_status
      ?? '',
  ).toLowerCase();
  const identificationBadge = (() => {
    if (!identificationRaw || identificationRaw === 'not_required') return null;
    if (identificationRaw === 'verified') {
      return {
        label: t('evidence.identificationVerified', { defaultValue: 'identification: verified' }),
        className: 'bg-metric-rules/20 text-metric-rules',
      };
    }
    if (identificationRaw === 'unreadable') {
      return {
        label: t('evidence.identificationUnreadable', { defaultValue: 'identification: unreadable' }),
        className: 'bg-amber-500/15 text-amber-600',
      };
    }
    if (identificationRaw === 'missing') {
      return {
        label: t('evidence.identificationMissing', { defaultValue: 'identification: missing' }),
        className: 'bg-cv-muted/20 text-cv-muted',
      };
    }
    return {
      label: `identification: ${identificationRaw}`,
      className: 'bg-cv-muted/20 text-cv-muted',
    };
  })();
  const frigateEventId = formatValue(pkg?.metadata?.frigate_event_id);
  const metaFields = [
    {
      label: t('evidence.plate'),
      value: plateValue
        ? (plateConf != null ? `${plateValue} (${Math.round(Number(plateConf) * (Number(plateConf) <= 1 ? 100 : 1))}%)` : plateValue)
        : (plateUrl ? t('evidence.plateUnread') : ''),
    },
    { label: t('evidence.face'), value: formatValue(ev.face_label) },
    { label: t('evidence.eventType'), value: formatValue(ev.event_type) },
    { label: t('evidence.class'), value: formatValue(ev.class_name) },
    { label: t('evidence.speed'), value: ev.speed_kmh != null ? `${ev.speed_kmh} km/h` : '' },
    { label: t('evidence.zone'), value: formatValue(ev.zone_id) },
    { label: t('evidence.track'), value: formatValue(ev.track_id) },
    { label: 'Frigate event', value: frigateEventId },
  ].filter((f) => f.value !== '');

  const hasMediaUrls = Boolean(clipUrl || sceneUrl || subjectUrl || plateUrl);
  const thumbApiUrl = evidenceThumbnailUrl(ev, orgId);
  const thumbMedia = useEvidenceMediaUrl(thumbApiUrl);
  const configuredClipSec = Number(pkg?.metadata?.clip_duration_sec ?? pkg?.clip?.duration_sec ?? 6);
  const displayClipSec = Math.round(configuredClipSec) || 6;

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
        <div className="flex items-center gap-1.5 flex-wrap justify-end">
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${badgeClass}`}>
            {badgeLabel}
          </span>
          {identificationBadge && (
            <span
              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${identificationBadge.className}`}
              title={t('evidence.identificationHint', {
                defaultValue: 'Statut d’identification plaque — distinct de la preuve de violation',
              })}
            >
              {identificationBadge.label}
            </span>
          )}
          {captureSource === 'demo_ring_buffer' && (
            <span
              className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-sky-500/15 text-sky-700"
              title={
                loopPos != null && loopDur != null
                  ? `loop ${Number(loopPos).toFixed(1)}s / ${Number(loopDur).toFixed(1)}s`
                  : 'Preuve ring-buffer démo (pas frigate_track)'
              }
            >
              {t('evidence.captureDemoRing', { defaultValue: 'capture_source: demo_ring_buffer' })}
            </span>
          )}
        </div>
      </div>

      {(isLegacyEvidence || isLowQualityEvidence) && (
        <p className="text-xs text-amber-500 flex items-center gap-1">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          {isLegacyEvidence
            ? t('evidence.legacySegment', { defaultValue: 'Preuve issue de l\u2019ancien mode segments — contenu visuel potentiellement décalé.' })
            : t('evidence.lowQualityBBox', { defaultValue: 'Cible non confirmée dans le cadre — preuve à vérifier manuellement.' })}
        </p>
      )}

      {isIncompleteEvidence && (
        <p className="text-xs text-amber-300 bg-amber-400/10 border border-amber-400/30 rounded-lg p-2 flex items-start gap-1.5">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span>
            {evidenceStatus === 'failed'
              ? t('evidence.captureFailed', { defaultValue: 'Capture preuve échouée (timeout Frigate ou backend indisponible).' })
              : t('evidence.incompleteProof', { defaultValue: 'Preuve incomplète — clip ou images manquants.' })}
            {missingRoles.length > 0 ? ` Rôles manquants: ${missingRoles.join(', ')}.` : ''}
            {frigateFailReason ? ` ${frigateFailReason}` : ''}
          </span>
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
              bbox={sceneBboxOverlay}
              onOpen={() => openLightbox(
                sceneUrl,
                scene?.label ?? t('evidence.scene'),
                sceneBboxOverlay,
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
