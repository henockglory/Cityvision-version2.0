import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import {
  Camera, Loader2, Trash2, Check, AlertTriangle, Upload, Pencil, Film, XCircle, RotateCcw, Shapes,
} from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import Go2RtcPlayer from '@/components/camera/Go2RtcPlayer';
import LiveStreamPlayer from '@/components/live/LiveStreamPlayer';
import SegmentedTabs from '@/components/ui/SegmentedTabs';
import { demoApi, type DemoSettings, type DemoVideo } from '@/api/client';
import { queryKeys } from '@/hooks/api/queries';
import { useAuthStore } from '@/stores/authStore';
import { useCameras } from '@/hooks/api/queries';
import { go2rtcStreamSrc, shouldUseFrigateLive } from '@/config/streams';

interface DemoVideoPanelProps {
  settings?: DemoSettings | null;
  isLoading?: boolean;
  onExplicitSourceSelect?: (sourceKey: string) => void;
  onEditZones?: (videoId: string) => void;
}

const MAX_VIDEOS = 5;
const LARGE_FILE_BYTES = 500 * 1024 * 1024;

function formatBytes(n: number): string {
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} Ko`;
  return `${(n / (1024 * 1024)).toFixed(1)} Mo`;
}

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  if (m === 0) return `${s}s`;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function formatImportDate(iso: string, t: (k: string) => string): string {
  const d = new Date(iso);
  const now = Date.now();
  const diffMs = now - d.getTime();
  const diffH = diffMs / 3_600_000;
  if (diffH < 1) return t('demoCenter.importedJustNow');
  if (diffH < 24) return t('demoCenter.importedToday');
  const diffD = Math.floor(diffH / 24);
  if (diffD === 1) return t('demoCenter.importedYesterday');
  if (diffD < 7) return t('demoCenter.importedDaysAgo').replace('{{n}}', String(diffD));
  return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short' });
}

function progressStep(progress: number, t: (k: string) => string): string {
  if (progress < 20) return t('demoCenter.encodingStep1');
  if (progress < 30) return t('demoCenter.encodingQueued');
  if (progress < 45) return t('demoCenter.encodingStep2');
  if (progress < 85) return t('demoCenter.encodingStep3');
  if (progress < 100) return t('demoCenter.encodingStep4');
  return t('demoCenter.statusReady');
}

function statusLabel(status: string, t: (k: string) => string): string {
  switch (status) {
    case 'ready': return t('demoCenter.statusReady');
    case 'processing': return t('demoCenter.statusProcessing');
    case 'uploading': return t('demoCenter.statusUploading');
    case 'failed': return t('demoCenter.statusFailed');
    default: return status;
  }
}

export default function DemoVideoPanel({ settings, isLoading = false, onExplicitSourceSelect, onEditZones }: DemoVideoPanelProps) {
  const { t } = useTranslation();
  const orgId = useAuthStore((s) => s.orgId);
  const qc = useQueryClient();
  const { data: cameras = [] } = useCameras();
  const fileRef = useRef<HTMLInputElement>(null);
  const [sourceTab, setSourceTab] = useState<'video' | 'camera'>(
    settings?.source_mode === 'camera' ? 'camera' : 'video',
  );
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState('');
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const videos = settings?.videos ?? [];
  const processingVideo = videos.find((v) => v.status === 'uploading' || v.status === 'processing');

  const streamSrc = settings?.active_go2rtc_src ?? '';
  const hasStream = Boolean(streamSrc);
  const readyCount = videos.filter((v) => v.status === 'ready').length;
  const activeCamera =
    settings?.source_mode === 'camera' && settings.active_camera_id
      ? cameras.find((c) => c.id === settings.active_camera_id) ?? null
      : null;
  const useFrigateLive = Boolean(activeCamera && shouldUseFrigateLive(activeCamera));

  const realCameras = cameras.filter((c) => {
    const meta = c.metadata as Record<string, unknown> | undefined;
    return meta?.demo !== true && meta?.virtual !== true;
  });

  useEffect(() => {
    if (settings?.source_mode) {
      setSourceTab(settings.source_mode === 'camera' ? 'camera' : 'video');
    }
  }, [settings?.source_mode]);

  // Clear a stale upload error once server-side processing is visible.
  useEffect(() => {
    if (processingVideo && uploadError) {
      setUploadError('');
    }
  }, [processingVideo?.id, uploadError]);

  // Poll individual video status every 2s while processing.
  useEffect(() => {
    if (!processingVideo || !orgId) return;
    const id = setInterval(() => {
      void qc.invalidateQueries({ queryKey: queryKeys.demoSettings });
    }, 2000);
    return () => clearInterval(id);
  }, [processingVideo?.id, orgId, qc]);

  const patchSettings = useCallback(async (body: Parameters<typeof demoApi.patchSettings>[1]) => {
    if (!orgId) return;
    await demoApi.patchSettings(orgId, body);
    void qc.invalidateQueries({ queryKey: queryKeys.demoSettings });
  }, [orgId, qc]);

  const handleUpload = async (file: File) => {
    if (!orgId) return;
    if (videos.length >= MAX_VIDEOS) {
      setUploadError(t('demoCenter.videoLimit'));
      return;
    }
    setUploadError('');
    setUploadPct(5);
    const displayName = file.name.replace(/\.mp4$/i, '');
    try {
      const { data: uploaded } = await demoApi.uploadVideo(orgId, file, displayName, setUploadPct);
      setUploadPct(null);
      // Immediately insert the returned video into the cached settings so the
      // in-card progress bar appears without waiting for the next poll cycle.
      qc.setQueryData<DemoSettings>(queryKeys.demoSettings, (old) => {
        if (!old) return old;
        const deduped = old.videos.filter((v) => v.id !== uploaded.id);
        return { ...old, videos: [uploaded, ...deduped] };
      });
      // Fire-and-forget: don't await so a slow/failed refetch never triggers
      // the catch block and displays a spurious "upload failed" banner.
      void qc.invalidateQueries({ queryKey: queryKeys.demoSettings });
    } catch (err) {
      setUploadPct(null);
      // Vite proxy or network may drop before the HTTP response while the backend
      // already ingested the file and started ffmpeg — recover silently if so.
      try {
        const { data: fresh } = await demoApi.getSettings(orgId);
        qc.setQueryData(queryKeys.demoSettings, fresh);
        const recovered = fresh.videos.some(
          (v) =>
            (v.status === 'processing' || v.status === 'uploading') &&
            v.name === displayName &&
            v.size_bytes > 0 &&
            Math.abs(v.size_bytes - file.size) <= Math.max(4096, file.size * 0.02),
        );
        if (recovered) {
          setUploadError('');
          return;
        }
      } catch {
        // fall through to error banner
      }
      let msg = t('demoCenter.uploadFailed');
      if (axios.isAxiosError(err)) {
        const apiMsg = (err.response?.data as { error?: string })?.error;
        if (apiMsg) msg = apiMsg;
      }
      setUploadError(msg);
    }
  };

  const activateVideo = async (video: DemoVideo) => {
    if (video.status !== 'ready') return;
    try {
      await patchSettings({ active_video_id: video.id, active_camera_id: null, source_mode: 'video' });
      onExplicitSourceSelect?.(`video:${video.id}`);
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 404) {
        // Stale video, refresh silently.
        void qc.invalidateQueries({ queryKey: queryKeys.demoSettings });
        return;
      }
      setUploadError(t('demoCenter.sourceSelectFailed'));
    }
  };

  const activateCamera = async (cameraId: string) => {
    try {
      await patchSettings({ active_camera_id: cameraId, active_video_id: null, source_mode: 'camera' });
      onExplicitSourceSelect?.(`camera:${cameraId}`);
    } catch {
      setUploadError(t('demoCenter.sourceSelectFailed'));
    }
  };

  const retryVideo = async (video: DemoVideo) => {
    if (!orgId) return;
    setUploadError('');
    try {
      await demoApi.retryVideo(orgId, video.id);
      void qc.invalidateQueries({ queryKey: queryKeys.demoSettings });
    } catch (err) {
      let msg = t('demoCenter.uploadFailed');
      if (axios.isAxiosError(err)) {
        const apiMsg = (err.response?.data as { error?: string })?.error;
        if (apiMsg) msg = apiMsg;
      }
      setUploadError(msg);
    }
  };

  const deleteVideo = async (video: DemoVideo) => {
    if (!orgId) return;
    setUploadError('');
    setDeletingId(video.id);
    // Optimistically remove the card immediately so the user gets instant feedback.
    qc.setQueryData<DemoSettings>(queryKeys.demoSettings, (old) => {
      if (!old) return old;
      return { ...old, videos: old.videos.filter((v) => v.id !== video.id) };
    });
    try {
      await demoApi.deleteVideo(orgId, video.id);
      // Confirm with server state; also refresh camera list.
      void qc.invalidateQueries({ queryKey: queryKeys.demoSettings });
      void qc.invalidateQueries({ queryKey: queryKeys.cameras });
    } catch (err) {
      // On any error, restore real server state.
      void qc.invalidateQueries({ queryKey: queryKeys.demoSettings });
      void qc.invalidateQueries({ queryKey: queryKeys.cameras });
      if (axios.isAxiosError(err)) {
        const status = err.response?.status;
        // 404 = already deleted — silent success.
        if (status === 404) {
          setDeletingId(null);
          return;
        }
        const apiMsg = (err.response?.data as { error?: string })?.error;
        if (apiMsg) { setUploadError(apiMsg); } else { setUploadError(t('demoCenter.deleteFailed')); }
      } else {
        setUploadError(t('demoCenter.deleteFailed'));
      }
    } finally {
      setDeletingId(null);
    }
  };

  const startRename = (video: DemoVideo, e: MouseEvent) => {
    e.stopPropagation();
    setRenamingId(video.id);
    setRenameDraft(video.name);
  };

  const saveRename = async (videoId: string) => {
    if (!orgId || !renameDraft.trim()) {
      setRenamingId(null);
      return;
    }
    await demoApi.renameVideo(orgId, videoId, renameDraft.trim());
    setRenamingId(null);
    void qc.invalidateQueries({ queryKey: queryKeys.demoSettings });
  };

  return (
    <div id="demo-video" className="space-y-4">
      {/* Main player area */}
      <div className="cv-card overflow-hidden p-0 relative cv-demo-player-shell">
        {hasStream ? (
          useFrigateLive && activeCamera ? (
            <LiveStreamPlayer
              className="aspect-video w-full min-h-[280px]"
              src={go2rtcStreamSrc(activeCamera) ?? streamSrc}
              label={activeCamera.name ?? t('demoCenter.tabRealCameras')}
              cameraId={activeCamera.id}
              camera={activeCamera}
              showOverlay
            />
          ) : (
            <Go2RtcPlayer
              className="aspect-video w-full min-h-[280px]"
              src={streamSrc}
              friendlyErrors
              label={settings?.source_mode === 'camera' ? t('demoCenter.tabRealCameras') : t('demoCenter.tabTestVideos')}
            />
          )
        ) : (
          <div className="cv-demo-empty-stream aspect-video w-full min-h-[280px]">
            <div className="cv-demo-empty-stream-inner">
              <div className="cv-demo-empty-icon">
                <Upload className="w-8 h-8" />
              </div>
              <p className="text-base font-semibold text-cv-text">{t('demoCenter.emptyStreamTitle')}</p>
              <p className="text-sm text-cv-muted max-w-sm text-center">{t('demoCenter.emptyStreamBody')}</p>
              <button type="button" className="cv-btn-primary text-sm mt-2" onClick={() => fileRef.current?.click()}>
                <Camera className="w-4 h-4" />
                {t('demoCenter.uploadVideo')}
              </button>
            </div>
          </div>
        )}

        {/* Upload button (floating top-right, always visible when stream exists) */}
        {hasStream && (
          <button
            type="button"
            className="cv-demo-upload-btn"
            onClick={() => fileRef.current?.click()}
            title={t('demoCenter.uploadVideo')}
          >
            <Camera className="w-5 h-5" />
          </button>
        )}

        {/* Upload progress — light banner at bottom of player (non-blocking) */}
        {uploadPct !== null && (
          <div className="cv-demo-upload-banner">
            <div className="flex items-center gap-2 min-w-0">
              <Loader2 className="w-4 h-4 animate-spin shrink-0 text-cv-accent" />
              <span className="text-xs font-medium truncate">{t('demoCenter.uploading')}</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <div className="w-24 h-1.5 rounded-full bg-white/20 overflow-hidden">
                <div
                  className="h-full bg-cv-accent transition-all duration-300 rounded-full"
                  style={{ width: `${Math.min(100, uploadPct)}%` }}
                />
              </div>
              <span className="text-[11px] font-mono text-white/70 w-8 text-right">{uploadPct}%</span>
            </div>
          </div>
        )}

        <input
          ref={fileRef}
          type="file"
          accept="video/mp4"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) {
              if (f.size > LARGE_FILE_BYTES) {
                setUploadError(t('demoCenter.largeFileWarning'));
              }
              void handleUpload(f);
            }
            e.target.value = '';
          }}
        />
      </div>

      {uploadError && (
        <div className="cv-demo-alert flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <p className="text-sm">{uploadError}</p>
        </div>
      )}

      {/* Source selector + video library */}
      <div className="cv-demo-source-section">
        <div className="flex items-center justify-between gap-3 mb-3">
          <SegmentedTabs
            value={sourceTab}
            onChange={(v) => setSourceTab(v as 'video' | 'camera')}
            tabs={[
              { id: 'video', label: t('demoCenter.tabTestVideos') },
              { id: 'camera', label: t('demoCenter.tabRealCameras') },
            ]}
          />
          {sourceTab === 'video' && (
            <span className="text-xs text-cv-muted shrink-0">
              {t('demoCenter.libraryCount', { count: videos.length, max: MAX_VIDEOS, ready: readyCount })}
            </span>
          )}
        </div>

        {sourceTab === 'video' ? (
          <div className="cv-demo-video-grid">
            {isLoading && videos.length === 0 && (
              <>
                {[0, 1].map((i) => (
                  <div key={i} className="cv-demo-video-card animate-pulse" style={{ minHeight: '4.5rem', opacity: 0.5 }}>
                    <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgb(var(--cv-surface-2))' }} />
                    <div className="cv-demo-video-card-body" style={{ gap: 6, display: 'flex', flexDirection: 'column' }}>
                      <div style={{ height: 12, width: '55%', borderRadius: 4, background: 'rgb(var(--cv-surface-2))' }} />
                      <div style={{ height: 10, width: '30%', borderRadius: 4, background: 'rgb(var(--cv-surface-2))' }} />
                    </div>
                  </div>
                ))}
              </>
            )}
            {!isLoading && videos.length === 0 && (
              <p className="text-sm text-cv-muted col-span-full py-6 text-center">{t('demoCenter.noVideos')}</p>
            )}
            {videos.map((v) => {
              const isActive = settings?.active_video_id === v.id;
              const isFailed = v.status === 'failed';
              const isBusy = v.status === 'processing' || v.status === 'uploading';
              const isReady = v.status === 'ready';
              const isDeleting = deletingId === v.id;

              return (
                <div
                  key={v.id}
                  role={isReady ? 'button' : undefined}
                  tabIndex={isReady ? 0 : undefined}
                  className={[
                    'cv-demo-video-card',
                    isReady ? 'cv-demo-video-card--clickable' : '',
                    isActive ? 'cv-demo-video-card--active' : '',
                    isFailed ? 'cv-demo-video-card--failed' : '',
                  ].join(' ')}
                  onClick={() => { if (isReady) void activateVideo(v); }}
                  onKeyDown={(e) => { if (isReady && (e.key === 'Enter' || e.key === ' ')) void activateVideo(v); }}
                >
                  {/* Icon */}
                  <div className="cv-demo-video-card-icon">
                    {isBusy
                      ? <Loader2 className="w-5 h-5 text-cv-accent animate-spin" />
                      : isFailed
                      ? <XCircle className="w-5 h-5 text-red-400" />
                      : <Film className="w-5 h-5 text-cv-accent" />}
                  </div>

                  {/* Body */}
                  <div className="cv-demo-video-card-body">
                    {/* Name row */}
                    <div className="flex items-start gap-2 min-w-0">
                      {renamingId === v.id ? (
                        <input
                          autoFocus
                          className="cv-demo-edit-inline text-sm flex-1 min-w-0"
                          value={renameDraft}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => setRenameDraft(e.target.value)}
                          onBlur={() => void saveRename(v.id)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') void saveRename(v.id);
                            if (e.key === 'Escape') setRenamingId(null);
                          }}
                        />
                      ) : (
                        <span className="font-semibold text-sm leading-snug text-cv-text break-words min-w-0">
                          {v.name}
                        </span>
                      )}
                      {isActive && (
                        <span className="cv-demo-status-pill cv-demo-status-pill--active shrink-0 ml-auto">
                          <Check className="w-3 h-3" /> {t('demoCenter.active')}
                        </span>
                      )}
                    </div>

                    {/* Meta row: status · size · duration · date */}
                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                      <span className={`cv-demo-status-pill cv-demo-status-pill--${v.status}`}>
                        {statusLabel(v.status, t)}
                      </span>
                      {v.size_bytes > 0 && (
                        <span className="text-[10px] text-cv-muted">{formatBytes(v.size_bytes)}</span>
                      )}
                      {(v.duration_sec ?? 0) > 0 && (
                        <>
                          <span className="text-[10px] text-cv-muted/40">·</span>
                          <span className="text-[10px] text-cv-muted">{formatDuration(v.duration_sec!)}</span>
                        </>
                      )}
                      {v.created_at && (
                        <>
                          <span className="text-[10px] text-cv-muted/40">·</span>
                          <span className="text-[10px] text-cv-muted/70">{formatImportDate(v.created_at, t)}</span>
                        </>
                      )}
                    </div>

                    {/* Multi-step progress bar for processing videos */}
                    {isBusy && (
                      <div className="mt-2 space-y-1">
                        <p className="text-[11px] text-cv-muted">{progressStep(v.progress, t)}</p>
                        <div className="w-full h-1.5 rounded-full bg-cv-border overflow-hidden">
                          <div
                            className="h-full bg-cv-accent transition-all duration-500 rounded-full"
                            style={{ width: `${Math.min(100, v.progress)}%` }}
                          />
                        </div>
                        <p className="text-[10px] text-cv-muted/70">{t('demoCenter.transcodeHint')}</p>
                      </div>
                    )}

                    {/* Error detail */}
                    {isFailed && v.error_message && (
                      <p className="text-[11px] text-red-400/90 mt-1.5 line-clamp-2" title={v.error_message}>
                        {v.error_message}
                      </p>
                    )}
                  </div>

                  {/* Action row — always visible, stopPropagation so card click isn't triggered */}
                  <div className="cv-demo-action-row">
                    {isReady && onEditZones && (
                      <button
                        type="button"
                        className="cv-demo-zone-btn"
                        onClick={(e) => { e.stopPropagation(); void onEditZones(v.id); }}
                        title={t('demoCenter.editZones')}
                      >
                        <Shapes className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {!isBusy && (
                      <button
                        type="button"
                        className="cv-demo-video-rename-btn"
                        onClick={(e) => { e.stopPropagation(); startRename(v, e); }}
                        title={t('demoCenter.renameVideo')}
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {isFailed && (
                      <button
                        type="button"
                        className="cv-demo-video-rename-btn"
                        onClick={(e) => { e.stopPropagation(); void retryVideo(v); }}
                        title={t('demoCenter.retryVideo')}
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <button
                      type="button"
                      className="cv-demo-video-delete-btn"
                      onClick={(e) => { e.stopPropagation(); void deleteVideo(v); }}
                      disabled={isDeleting}
                      title={t('common.delete')}
                    >
                      {isDeleting
                        ? <Loader2 className="w-4 h-4 animate-spin" />
                        : <Trash2 className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="cv-demo-video-grid">
            {realCameras.length === 0 && (
              <p className="text-sm text-cv-muted col-span-full py-6 text-center">{t('demoCenter.noRealCameras')}</p>
            )}
            {realCameras.map((c) => {
              const isActive = settings?.active_camera_id === c.id;
              return (
                <button
                  key={c.id}
                  type="button"
                  className={`cv-demo-video-card cv-demo-video-card--clickable text-left ${isActive ? 'cv-demo-video-card--active' : ''}`}
                  onClick={() => void activateCamera(c.id)}
                >
                  <div className="cv-demo-video-card-icon">
                    <Camera className="w-5 h-5 text-cv-accent" />
                  </div>
                  <div className="cv-demo-video-card-body min-w-0">
                    <p className="font-medium text-sm truncate">{c.name}</p>
                    <p className="text-[10px] text-cv-muted mt-1">RTSP · {go2rtcStreamSrc(c)}</p>
                    {isActive && (
                      <span className="cv-demo-status-pill cv-demo-status-pill--active mt-1.5 inline-flex">
                        <Check className="w-3 h-3" /> {t('demoCenter.active')}
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
