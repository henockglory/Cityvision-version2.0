package demo

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/camera"
	"github.com/citevision/citevision-v2/backend/internal/evidence"
	"github.com/citevision/citevision-v2/backend/internal/models"
)

const (
	MaxVideosPerOrg   = 5
	RetentionMinutes   = 60
	MaxDemoEventsTotal = 2000
	DefaultNavLabel   = "Démo Kinshasa"
	DefaultContext    = "Ministère · Urbanisme & Transport · Kinshasa"
	DefaultTitle      = "Démonstration CitéVision"
	DefaultSubtitle   = "Vidéo, zonage, règles et alertes — prêt pour présentation client."
)

var (
	ErrVideoNotFound  = errors.New("demo video not found")
	ErrVideoLimit     = errors.New("demo video library full (max 5)")
	ErrInvalidVideo   = errors.New("only mp4 videos are supported")
)

type Video struct {
	ID              uuid.UUID `json:"id"`
	OrgID           uuid.UUID `json:"org_id"`
	Name            string    `json:"name"`
	Status          string    `json:"status"`
	Progress        int       `json:"progress"`
	Go2rtcSrc       string    `json:"go2rtc_src,omitempty"`
	SizeBytes       int64     `json:"size_bytes"`
	DurationSec     *float64  `json:"duration_sec,omitempty"`
	ErrorMessage    string    `json:"error_message,omitempty"`
	CreatedAt       time.Time `json:"created_at"`
}

type Settings struct {
	ContextLabel   string     `json:"context_label"`
	Title          string     `json:"title"`
	Subtitle       string     `json:"subtitle"`
	NavLabel       string     `json:"nav_label"`
	SourceMode     string     `json:"source_mode"`
	ActiveVideoID  *uuid.UUID `json:"active_video_id,omitempty"`
	ActiveCameraID *uuid.UUID `json:"active_camera_id,omitempty"`
	ActiveStream   string     `json:"active_go2rtc_src,omitempty"`
	Videos         []Video    `json:"videos"`
}

type PatchSettingsRequest struct {
	ContextLabel   *string    `json:"context_label"`
	Title          *string    `json:"title"`
	Subtitle       *string    `json:"subtitle"`
	NavLabel       *string    `json:"nav_label"`
	SourceMode     *string    `json:"source_mode"`
	ActiveVideoID  *uuid.UUID `json:"active_video_id"`
	ActiveCameraID *uuid.UUID `json:"active_camera_id"`
}

type Service struct {
	pool         *pgxpool.Pool
	cameras      *camera.Service
	evidence     *evidence.Service
	go2rtc       *camera.Go2RTCClient
	minio        *MinioStore
	log          *slog.Logger
	// transcodeSem serialises ffmpeg invocations so that concurrent uploads do
	// not start two heavy encode processes at the same time on the same host.
	transcodeSem chan struct{}
}

func NewService(pool *pgxpool.Pool, cameras *camera.Service, log *slog.Logger) *Service {
	return NewServiceWithEvidence(pool, cameras, nil, log)
}

func NewServiceWithEvidence(pool *pgxpool.Pool, cameras *camera.Service, ev *evidence.Service, log *slog.Logger) *Service {
	ms, _ := NewMinioStore()
	if log == nil {
		log = slog.Default()
	}
	return &Service{
		pool:         pool,
		cameras:      cameras,
		evidence:     ev,
		go2rtc:       camera.NewGo2RTCClient(),
		minio:        ms,
		log:          log,
		transcodeSem: make(chan struct{}, 1),
	}
}

func (s *Service) GetSettings(ctx context.Context, orgID uuid.UUID) (*Settings, error) {
	if err := s.ensureSettingsRow(ctx, orgID); err != nil {
		return nil, err
	}
	var st Settings
	var activeVideo, activeCam *uuid.UUID
	err := s.pool.QueryRow(ctx, `
		SELECT context_label, title, subtitle, COALESCE(nav_label, $2), source_mode, active_video_id, active_camera_id
		FROM org_demo_settings WHERE org_id = $1`, orgID, DefaultNavLabel,
	).Scan(&st.ContextLabel, &st.Title, &st.Subtitle, &st.NavLabel, &st.SourceMode, &activeVideo, &activeCam)
	if err != nil {
		return nil, err
	}
	st.ActiveVideoID = activeVideo
	st.ActiveCameraID = activeCam
	if st.SourceMode == "" {
		st.SourceMode = "video"
	}
	if st.SourceMode == "camera" && st.ActiveCameraID != nil && s.IsDemoCamera(ctx, *st.ActiveCameraID) {
		_, _ = s.pool.Exec(ctx, `
			UPDATE org_demo_settings SET active_camera_id = NULL, source_mode = 'video', updated_at = NOW()
			WHERE org_id = $1`, orgID)
		st.ActiveCameraID = nil
		st.SourceMode = "video"
	}
	st.ActiveStream = s.resolveActiveStream(ctx, orgID, &st)
	videos, err := s.listVideos(ctx, orgID)
	if err != nil {
		return nil, err
	}
	st.Videos = videos
	return &st, nil
}

func (s *Service) PatchSettings(ctx context.Context, orgID uuid.UUID, req PatchSettingsRequest) (*Settings, error) {
	if err := s.ensureSettingsRow(ctx, orgID); err != nil {
		return nil, err
	}
	if req.ActiveVideoID != nil {
		v, err := s.getVideo(ctx, orgID, *req.ActiveVideoID)
		if err != nil {
			return nil, err
		}
		if v.Status != "ready" || v.Go2rtcSrc == "" {
			return nil, fmt.Errorf("video not ready")
		}
		mode := "video"
		req.SourceMode = &mode
		req.ActiveCameraID = nil
	}
	if req.ActiveCameraID != nil {
		cam, err := s.cameras.Get(ctx, orgID, *req.ActiveCameraID)
		if err != nil {
			return nil, err
		}
		var meta map[string]interface{}
		_ = json.Unmarshal(cam.Metadata, &meta)
		if meta["demo"] == true || meta["virtual"] == true {
			return nil, fmt.Errorf("select a real RTSP camera, not the demo virtual camera")
		}
		mode := "camera"
		req.SourceMode = &mode
		req.ActiveVideoID = nil
	}
	_, err := s.pool.Exec(ctx, `
		UPDATE org_demo_settings SET
			context_label = COALESCE($2, context_label),
			title = COALESCE($3, title),
			subtitle = COALESCE($4, subtitle),
			nav_label = COALESCE($5, nav_label),
			source_mode = COALESCE($6, source_mode),
			active_video_id = CASE WHEN $7::uuid IS NOT NULL THEN $7::uuid WHEN $8::uuid IS NOT NULL THEN NULL ELSE active_video_id END,
			active_camera_id = CASE WHEN $8::uuid IS NOT NULL THEN $8::uuid WHEN $7::uuid IS NOT NULL THEN NULL ELSE active_camera_id END,
			updated_at = NOW()
		WHERE org_id = $1`,
		orgID, req.ContextLabel, req.Title, req.Subtitle, req.NavLabel, req.SourceMode, req.ActiveVideoID, req.ActiveCameraID,
	)
	if err != nil {
		return nil, err
	}
	if req.ActiveVideoID != nil {
		if err := s.activateVideo(ctx, orgID, *req.ActiveVideoID); err != nil {
			return nil, err
		}
	}
	return s.GetSettings(ctx, orgID)
}

func (s *Service) UploadVideo(ctx context.Context, orgID uuid.UUID, name string, r io.Reader, size int64, contentType string) (*Video, error) {
	lowerCT := strings.ToLower(contentType)
	lowerName := strings.ToLower(name)
	// Accept if content-type contains "mp4" or "video", OR if name ends with ".mp4".
	if !strings.Contains(lowerCT, "mp4") && !strings.Contains(lowerCT, "video") &&
		!strings.HasSuffix(lowerName, ".mp4") {
		return nil, ErrInvalidVideo
	}
	count, err := s.countVideos(ctx, orgID)
	if err != nil {
		return nil, err
	}
	if count >= MaxVideosPerOrg {
		return nil, ErrVideoLimit
	}
	if name == "" {
		name = "Vidéo de test"
	}
	vid := uuid.New()
	rawKey := fmt.Sprintf("raw/%s/%s.mp4", orgID, vid)
	localRaw := filepath.Join(TempDir(), orgID.String(), vid.String()+"_raw.mp4")
	if err := os.MkdirAll(filepath.Dir(localRaw), 0o755); err != nil {
		return nil, err
	}
	rawFile, err := os.Create(localRaw)
	if err != nil {
		return nil, err
	}
	if _, err := io.Copy(rawFile, r); err != nil {
		rawFile.Close()
		return nil, err
	}
	rawFile.Close()
	var v Video
	err = s.pool.QueryRow(ctx, `
		INSERT INTO org_demo_videos (id, org_id, name, status, progress, minio_raw_key, size_bytes)
		VALUES ($1,$2,$3,'uploading',5,$4,$5)
		RETURNING id, org_id, name, status, progress, size_bytes, created_at`,
		vid, orgID, name, localRaw, size,
	).Scan(&v.ID, &v.OrgID, &v.Name, &v.Status, &v.Progress, &v.SizeBytes, &v.CreatedAt)
	if err != nil {
		return nil, err
	}
	if s.minio != nil && s.minio.Available() {
		lf, err := os.Open(localRaw)
		if err == nil {
			st, _ := lf.Stat()
			if putErr := s.minio.Put(ctx, rawKey, lf, st.Size(), "video/mp4"); putErr != nil {
				s.log.Warn("demo minio upload failed, using local file", "error", putErr)
			}
			lf.Close()
		}
	}
	_, _ = s.pool.Exec(ctx, `UPDATE org_demo_videos SET status = 'processing', progress = 20 WHERE id = $1`, vid)
	go s.processVideoAsync(vid, orgID, localRaw)
	v.Status = "processing"
	v.Progress = 20
	return &v, nil
}

func (s *Service) GetVideo(ctx context.Context, orgID, videoID uuid.UUID) (*Video, error) {
	row, err := s.getVideo(ctx, orgID, videoID)
	if err != nil {
		return nil, err
	}
	return &row.Video, nil
}

func (s *Service) RenameVideo(ctx context.Context, orgID, videoID uuid.UUID, name string) (*Video, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return nil, fmt.Errorf("name required")
	}
	tag, err := s.pool.Exec(ctx, `
		UPDATE org_demo_videos SET name = $3, updated_at = NOW()
		WHERE id = $1 AND org_id = $2`, videoID, orgID, name)
	if err != nil {
		return nil, err
	}
	if tag.RowsAffected() == 0 {
		return nil, ErrVideoNotFound
	}
	return s.GetVideo(ctx, orgID, videoID)
}

func (s *Service) RetryVideo(ctx context.Context, orgID, videoID uuid.UUID) (*Video, error) {
	v, err := s.getVideo(ctx, orgID, videoID)
	if err != nil {
		return nil, err
	}
	raw := strings.TrimSpace(v.minioRawKey)
	if raw == "" {
		return nil, fmt.Errorf("source file missing")
	}
	if strings.HasPrefix(raw, "raw/") {
		// Legacy rows can still reference MinIO keys.
		if s.minio == nil || !s.minio.Available() {
			return nil, fmt.Errorf("source file unavailable (minio)")
		}
	} else if _, err := os.Stat(raw); err != nil {
		// Retry old rows that point to a local path by falling back to canonical MinIO key.
		fallbackRawKey := fmt.Sprintf("raw/%s/%s.mp4", orgID, videoID)
		if s.minio != nil && s.minio.Available() {
			raw = fallbackRawKey
		} else {
			return nil, fmt.Errorf("source file not found on disk")
		}
	}
	if v.Go2rtcSrc != "" {
		_ = s.go2rtc.UnregisterStream(ctx, v.Go2rtcSrc)
	}
	_, err = s.pool.Exec(ctx, `
		UPDATE org_demo_videos SET status = 'processing', progress = 20, error_message = '', updated_at = NOW()
		WHERE id = $1 AND org_id = $2`, videoID, orgID)
	if err != nil {
		return nil, err
	}
	go s.processVideoAsync(videoID, orgID, raw)
	return s.GetVideo(ctx, orgID, videoID)
}

func (s *Service) DeleteVideo(ctx context.Context, orgID, videoID uuid.UUID) error {
	v, err := s.getVideo(ctx, orgID, videoID)
	if err != nil {
		return err
	}
	// Remove go2rtc stream (persists in yaml via PUT; DELETE removes it).
	if v.Go2rtcSrc != "" {
		_ = s.go2rtc.DeleteStream(ctx, v.Go2rtcSrc)
	}
	if s.minio != nil {
		_ = s.minio.Remove(ctx, v.minioKeys()...)
	}
	if v.LocalPath != "" {
		_ = os.Remove(v.LocalPath)
	}
	if v.minioRawKey != "" && !strings.HasPrefix(v.minioRawKey, "raw/") {
		_ = os.Remove(v.minioRawKey)
	}
	// Delete from DB.
	_, err = s.pool.Exec(ctx, `DELETE FROM org_demo_videos WHERE id = $1 AND org_id = $2`, videoID, orgID)
	if err != nil {
		return err
	}
	_, _ = s.pool.Exec(ctx, `
		UPDATE org_demo_settings SET active_video_id = NULL, active_camera_id = NULL
		WHERE org_id = $1 AND active_video_id = $2`, orgID, videoID)
	// Delete associated virtual camera (cascades zones/rules via FK).
	virtualCamID := s.findVirtualCameraByVideoID(ctx, orgID, videoID)
	if virtualCamID != uuid.Nil {
		if err := s.cameras.Delete(ctx, orgID, virtualCamID); err != nil {
			s.log.Warn("demo: failed to delete virtual camera", "cam_id", virtualCamID, "video_id", videoID, "error", err)
		} else {
			s.log.Info("demo: deleted virtual camera for video", "cam_id", virtualCamID, "video_id", videoID)
		}
	}
	return nil
}

func (s *Service) processVideoAsync(videoID, orgID uuid.UUID, rawKey string) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()

	s.log.Info("demo: processing video", "video_id", videoID, "org_id", orgID, "raw_key", rawKey)
	_ = s.setProgress(ctx, videoID, 30)

	tmpDir := filepath.Join(TempDir(), orgID.String())
	_ = os.MkdirAll(tmpDir, 0o755)
	rawLocal := filepath.Join(tmpDir, videoID.String()+"_raw.mp4")

	// Step 1: resolve raw file
	if strings.HasPrefix(rawKey, "raw/") {
		s.log.Info("demo: fetching raw from minio", "key", rawKey)
		if err := s.minio.Get(ctx, rawKey, rawLocal); err != nil {
			fallback := filepath.Join(TempDir(), orgID.String(), videoID.String()+"_raw.mp4")
			if _, statErr := os.Stat(fallback); statErr == nil {
				s.log.Info("demo: using local fallback for raw", "path", fallback)
				rawLocal = fallback
			} else {
				s.log.Error("demo: raw file unavailable", "minio_error", err, "fallback", fallback)
				_ = s.setVideoFailed(ctx, videoID, humanizeDemoError(err.Error()))
				return
			}
		}
	} else {
		rawLocal = rawKey
		if _, err := os.Stat(rawLocal); err != nil {
			s.log.Error("demo: raw local file missing", "path", rawLocal, "error", err)
			_ = s.setVideoFailed(ctx, videoID, "fichier source introuvable: "+rawLocal)
			return
		}
	}
	s.log.Info("demo: raw file resolved", "path", rawLocal)

	// Step 2: transcode — serialised via semaphore to avoid parallel ffmpeg overload.
	// Mark video as "queued" while waiting for the encoder slot.
	_ = s.setProgress(ctx, videoID, 25)
	s.log.Info("demo: waiting for transcode slot", "video_id", videoID)
	select {
	case s.transcodeSem <- struct{}{}:
	case <-ctx.Done():
		_ = s.setVideoFailed(ctx, videoID, "transcode annulé (délai dépassé)")
		return
	}
	defer func() { <-s.transcodeSem }()
	_ = s.setProgress(ctx, videoID, 45)
	streamLocal := FastTempStreamPath(videoID.String())
	s.log.Info("demo: starting ffmpeg transcode", "input", rawLocal, "output", streamLocal)

	// Heartbeat: advance progress 45→68 while ffmpeg runs so the UI bar visibly moves.
	stopHeartbeat := make(chan struct{})
	go func() {
		p := 48
		ticker := time.NewTicker(20 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				if p < 66 {
					_ = s.setProgress(ctx, videoID, p)
					p += 2
				}
			case <-stopHeartbeat:
				return
			case <-ctx.Done():
				return
			}
		}
	}()

	transcodeErr := TranscodeForStream(ctx, rawLocal, streamLocal)
	close(stopHeartbeat) // stop the heartbeat goroutine

	if transcodeErr != nil {
		s.log.Error("demo: transcode failed", "error", transcodeErr)
		_ = s.setVideoFailed(ctx, videoID, humanizeDemoError(transcodeErr.Error()))
		return
	}
	s.log.Info("demo: transcode complete, copying to videos dir")

	// Step 3: copy to final location
	_ = s.setProgress(ctx, videoID, 70)
	rel := LocalStreamRelPath(orgID.String(), videoID.String())
	dest := filepath.Join(VideosBasePath(), rel)
	s.log.Info("demo: copying stream file", "src", streamLocal, "dst", dest, "videos_base", VideosBasePath())
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		s.log.Error("demo: mkdir failed", "path", filepath.Dir(dest), "error", err)
		_ = s.setVideoFailed(ctx, videoID, err.Error())
		return
	}
	if err := copyFile(streamLocal, dest); err != nil {
		s.log.Error("demo: copy stream file failed", "error", err)
		_ = s.setVideoFailed(ctx, videoID, err.Error())
		return
	}
	_ = os.Remove(streamLocal)
	if err := validateOutput(dest); err != nil {
		s.log.Error("demo: output validation failed", "path", dest, "error", err)
		_ = s.setVideoFailed(ctx, videoID, humanizeDemoError(err.Error()))
		return
	}

	// Step 4: upload to minio (optional)
	streamKey := fmt.Sprintf("ready/%s/%s_stream.mp4", orgID, videoID)
	if s.minio != nil && s.minio.Available() {
		f, err := os.Open(dest)
		if err == nil {
			st, _ := f.Stat()
			if putErr := s.minio.Put(ctx, streamKey, f, st.Size(), "video/mp4"); putErr != nil {
				s.log.Warn("demo: minio stream upload failed (non-fatal)", "error", putErr)
			}
			f.Close()
		}
	}

	// Step 5: register go2rtc stream
	_ = s.setProgress(ctx, videoID, 85)
	go2rtcName := fmt.Sprintf("demo-%s-%s", orgID.String()[:8], videoID.String()[:8])
	src := Go2rtcStreamSource(rel)
	s.log.Info("demo: registering go2rtc stream", "name", go2rtcName, "src", src)
	if _, err := s.go2rtc.RegisterStream(ctx, go2rtcName, src); err != nil {
		s.log.Error("demo: go2rtc registration failed", "name", go2rtcName, "error", err)
		_ = s.setVideoFailed(ctx, videoID, humanizeDemoError("go2rtc: "+err.Error()))
		return
	}
	s.log.Info("demo: go2rtc stream registered", "name", go2rtcName)

	_, err := s.pool.Exec(ctx, `
		UPDATE org_demo_videos SET status = 'ready', progress = 100,
			minio_stream_key = $2, go2rtc_src = $3, local_stream_path = $4, updated_at = NOW()
		WHERE id = $1`, videoID, streamKey, go2rtcName, dest)
	if err != nil {
		s.log.Error("demo: DB update to ready failed", "error", err)
		_ = s.setVideoFailed(ctx, videoID, err.Error())
		return
	}
	s.log.Info("demo: video ready", "video_id", videoID, "go2rtc", go2rtcName, "path", dest)

	vrow, _ := s.getVideo(ctx, orgID, videoID)
	if vrow != nil {
		if _, err := s.syncDemoVirtualCamera(ctx, orgID, vrow); err != nil {
			s.log.Warn("demo: virtual camera sync failed", "error", err)
		}
	}
	// Auto-activate first ready video if none active.
	var active *uuid.UUID
	_ = s.pool.QueryRow(ctx, `SELECT active_video_id FROM org_demo_settings WHERE org_id = $1`, orgID).Scan(&active)
	if active == nil {
		_ = s.activateVideo(ctx, orgID, videoID)
	}
}

func humanizeDemoError(msg string) string {
	lower := strings.ToLower(msg)
	switch {
	case strings.Contains(lower, "executable file not found") && strings.Contains(lower, "ffmpeg"):
		return "ffmpeg non installé — installez ffmpeg sur le serveur"
	case strings.Contains(lower, "no such file") && strings.Contains(lower, "ffmpeg"):
		return "ffmpeg introuvable dans le PATH"
	case strings.Contains(lower, "go2rtc unreachable"):
		return "go2rtc inaccessible — vérifiez que le service tourne sur le port 1984"
	case strings.Contains(lower, "permission denied"):
		return "permission refusée sur le dossier vidéos"
	default:
		if len(msg) > 180 {
			return msg[:180] + "…"
		}
		return msg
	}
}

func (s *Service) activateVideo(ctx context.Context, orgID, videoID uuid.UUID) error {
	v, err := s.getVideo(ctx, orgID, videoID)
	if err != nil || v.Status != "ready" || v.Go2rtcSrc == "" {
		return fmt.Errorf("video not ready")
	}
	camID, err := s.syncDemoVirtualCamera(ctx, orgID, v)
	if err != nil {
		return err
	}
	_, err = s.pool.Exec(ctx, `
		UPDATE org_demo_settings SET active_video_id = $2, active_camera_id = $3, source_mode = 'video', updated_at = NOW()
		WHERE org_id = $1`, orgID, videoID, camID)
	if err != nil {
		return err
	}
	return nil
}

func (s *Service) syncDemoVirtualCamera(ctx context.Context, orgID uuid.UUID, v *videoRow) (uuid.UUID, error) {
	siteID, err := s.defaultSiteID(ctx, orgID)
	if err != nil {
		return uuid.Nil, err
	}
	meta := map[string]interface{}{
		"virtual":     true,
		"demo":        true,
		"go2rtc_src":  v.Go2rtcSrc,
		"video_file":  v.LocalPath,
		"demo_video_id": v.ID.String(),
		"ai_ingest":   "file",
		"source":      "demo-upload",
	}
	metaJSON, _ := json.Marshal(meta)
	// One virtual camera per uploaded video to isolate zones/lines by source.
	var camID uuid.UUID
	err = s.pool.QueryRow(ctx, `
		SELECT id FROM cameras
		WHERE org_id = $1 AND metadata->>'demo' = 'true' AND metadata->>'demo_video_id' = $2
		LIMIT 1`, orgID, v.ID.String()).Scan(&camID)
	if errors.Is(err, pgx.ErrNoRows) {
		req := camera.CreateRequest{
			OrgID:    orgID,
			SiteID:   siteID,
			Name:     "Démo — " + v.Name,
			Vendor:   models.VendorGeneric,
			Host:     "127.0.0.1",
			Port:     8554,
			RTSPPath: "/" + v.Go2rtcSrc,
			Metadata: metaJSON,
		}
		cam, err := s.cameras.Create(ctx, req)
		if err != nil {
			return uuid.Nil, err
		}
		camID = cam.ID
	} else if err != nil {
		return uuid.Nil, err
	} else {
		rtspPath := strPtr("/" + v.Go2rtcSrc)
		_, err = s.cameras.Update(ctx, orgID, camID, camera.UpdateRequest{
			Metadata: metaJSON,
			Name:     strPtr("Démo — " + v.Name),
			RTSPPath: rtspPath,
		})
		if err != nil {
			return uuid.Nil, err
		}
	}
	return camID, nil
}

func (s *Service) resolveActiveStream(ctx context.Context, orgID uuid.UUID, st *Settings) string {
	if st.SourceMode == "camera" && st.ActiveCameraID != nil {
		cam, err := s.cameras.Get(ctx, orgID, *st.ActiveCameraID)
		if err != nil {
			return ""
		}
		var meta map[string]interface{}
		_ = json.Unmarshal(cam.Metadata, &meta)
		if src, ok := meta["go2rtc_src"].(string); ok && src != "" {
			return src
		}
		return "cam-" + cam.ID.String()
	}
	if st.ActiveVideoID != nil {
		v, err := s.getVideo(ctx, orgID, *st.ActiveVideoID)
		if err == nil && v.Go2rtcSrc != "" && v.Status == "ready" {
			// Auto-repair: re-register go2rtc stream if it disappeared (e.g. after restart).
			if !s.go2rtc.StreamExists(ctx, v.Go2rtcSrc) {
				s.ensureStreamRegistered(ctx, orgID, v)
			}
			return v.Go2rtcSrc
		}
	}
	return ""
}

// ensureStreamRegistered re-registers a go2rtc stream for a ready video if the stream
// was lost (e.g. go2rtc restarted and cleared its YAML state).
func (s *Service) ensureStreamRegistered(ctx context.Context, orgID uuid.UUID, v *videoRow) {
	if v.Go2rtcSrc == "" || v.LocalPath == "" {
		return
	}
	if _, err := os.Stat(v.LocalPath); err != nil {
		s.log.Warn("demo: stream file missing, cannot re-register", "stream", v.Go2rtcSrc, "path", v.LocalPath)
		return
	}
	rel := LocalStreamRelPath(orgID.String(), v.ID.String())
	src := Go2rtcStreamSource(rel)
	if _, err := s.go2rtc.RegisterStream(ctx, v.Go2rtcSrc, src); err != nil {
		s.log.Warn("demo: failed to re-register go2rtc stream after restart", "stream", v.Go2rtcSrc, "error", err)
		return
	}
	s.log.Info("demo: re-registered go2rtc stream after restart", "stream", v.Go2rtcSrc, "video_id", v.ID)
}

// EnsureAllOrgsStreamsRegistered iterates all orgs with ready demo videos and
// re-registers any stream that disappeared from go2rtc (e.g. after a restart).
// Should be called once at startup.
func (s *Service) EnsureAllOrgsStreamsRegistered(ctx context.Context) {
	rows, err := s.pool.Query(ctx, `SELECT DISTINCT org_id FROM org_demo_videos WHERE status = 'ready'`)
	if err != nil {
		s.log.Warn("demo: EnsureAllOrgsStreamsRegistered query failed", "error", err)
		return
	}
	defer rows.Close()
	var orgIDs []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err == nil {
			orgIDs = append(orgIDs, id)
		}
	}
	_ = rows.Err()
	for _, orgID := range orgIDs {
		s.EnsureAllStreamsRegistered(ctx, orgID)
	}
	if len(orgIDs) > 0 {
		s.log.Info("demo: startup stream repair complete", "orgs", len(orgIDs))
	}
}

// EnsureAllStreamsRegistered is called at startup to repair the DB/go2rtc desync
// that occurs when go2rtc restarts and loses its YAML state.
func (s *Service) EnsureAllStreamsRegistered(ctx context.Context, orgID uuid.UUID) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, name, status, progress, COALESCE(go2rtc_src,''), size_bytes, duration_sec,
			COALESCE(error_message,''), created_at, COALESCE(local_stream_path,''),
			COALESCE(minio_raw_key,''), COALESCE(minio_stream_key,'')
		FROM org_demo_videos WHERE org_id = $1 AND status = 'ready'`, orgID)
	if err != nil {
		s.log.Warn("demo: EnsureAllStreamsRegistered query failed", "error", err)
		return
	}
	defer rows.Close()
	for rows.Next() {
		var v videoRow
		if err := rows.Scan(&v.ID, &v.OrgID, &v.Name, &v.Status, &v.Progress, &v.Go2rtcSrc, &v.SizeBytes, &v.DurationSec,
			&v.ErrorMessage, &v.CreatedAt, &v.LocalPath, &v.minioRawKey, &v.minioStreamKey); err != nil {
			continue
		}
		if v.Go2rtcSrc != "" && !s.go2rtc.StreamExists(ctx, v.Go2rtcSrc) {
			s.ensureStreamRegistered(ctx, orgID, &v)
		}
	}
}

// findVirtualCameraByVideoID finds the virtual camera linked to a demo video.
func (s *Service) findVirtualCameraByVideoID(ctx context.Context, orgID, videoID uuid.UUID) uuid.UUID {
	var camID uuid.UUID
	err := s.pool.QueryRow(ctx, `
		SELECT id FROM cameras
		WHERE org_id = $1 AND metadata->>'demo' = 'true' AND metadata->>'demo_video_id' = $2
		LIMIT 1`, orgID, videoID.String()).Scan(&camID)
	if err != nil {
		return uuid.Nil
	}
	return camID
}

func (s *Service) IsDemoCamera(ctx context.Context, cameraID uuid.UUID) bool {
	var demo bool
	err := s.pool.QueryRow(ctx, `
		SELECT COALESCE((metadata->>'demo')::boolean, false) FROM cameras WHERE id = $1`, cameraID).Scan(&demo)
	return err == nil && demo
}

func (s *Service) ensureSettingsRow(ctx context.Context, orgID uuid.UUID) error {
	_, err := s.pool.Exec(ctx, `
		INSERT INTO org_demo_settings (org_id, context_label, title, subtitle, nav_label, source_mode)
		VALUES ($1, $2, $3, $4, $5, 'video')
		ON CONFLICT (org_id) DO NOTHING`,
		orgID, DefaultContext, DefaultTitle, DefaultSubtitle, DefaultNavLabel)
	return err
}

func (s *Service) listVideos(ctx context.Context, orgID uuid.UUID) ([]Video, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, name, status, progress, COALESCE(go2rtc_src,''), size_bytes, duration_sec, COALESCE(error_message,''), created_at
		FROM org_demo_videos WHERE org_id = $1 ORDER BY created_at DESC`, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []Video
	for rows.Next() {
		var v Video
		if err := rows.Scan(&v.ID, &v.OrgID, &v.Name, &v.Status, &v.Progress, &v.Go2rtcSrc, &v.SizeBytes, &v.DurationSec, &v.ErrorMessage, &v.CreatedAt); err != nil {
			return nil, err
		}
		list = append(list, v)
	}
	return list, rows.Err()
}

type videoRow struct {
	Video
	LocalPath      string
	minioRawKey    string
	minioStreamKey string
}

func (v *videoRow) minioKeys() []string {
	return []string{v.minioRawKey, v.minioStreamKey}
}

func (s *Service) getVideo(ctx context.Context, orgID, id uuid.UUID) (*videoRow, error) {
	var v videoRow
	err := s.pool.QueryRow(ctx, `
		SELECT id, org_id, name, status, progress, COALESCE(go2rtc_src,''), size_bytes, duration_sec,
			COALESCE(error_message,''), created_at, COALESCE(local_stream_path,''),
			COALESCE(minio_raw_key,''), COALESCE(minio_stream_key,'')
		FROM org_demo_videos WHERE id = $1 AND org_id = $2`, id, orgID,
	).Scan(&v.ID, &v.OrgID, &v.Name, &v.Status, &v.Progress, &v.Go2rtcSrc, &v.SizeBytes, &v.DurationSec,
		&v.ErrorMessage, &v.CreatedAt, &v.LocalPath, &v.minioRawKey, &v.minioStreamKey)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrVideoNotFound
	}
	if err != nil {
		return nil, err
	}
	return &v, nil
}

func (s *Service) countVideos(ctx context.Context, orgID uuid.UUID) (int, error) {
	var n int
	err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM org_demo_videos WHERE org_id = $1`, orgID).Scan(&n)
	return n, err
}

func (s *Service) setProgress(ctx context.Context, id uuid.UUID, p int) error {
	_, err := s.pool.Exec(ctx, `UPDATE org_demo_videos SET progress = $2, updated_at = NOW() WHERE id = $1`, id, p)
	return err
}

func (s *Service) setVideoFailed(ctx context.Context, id uuid.UUID, msg string) error {
	_, err := s.pool.Exec(ctx, `
		UPDATE org_demo_videos SET status = 'failed', error_message = $2, updated_at = NOW() WHERE id = $1`, id, msg)
	if err != nil {
		return err
	}
	_, _ = s.pool.Exec(ctx, `
		UPDATE org_demo_settings
		SET active_video_id = NULL,
			active_camera_id = CASE
				WHEN active_camera_id IS NOT NULL AND active_camera_id IN (
					SELECT id FROM cameras WHERE metadata->>'demo_video_id' = $1::text
				) THEN NULL
				ELSE active_camera_id
			END,
			updated_at = NOW()
		WHERE active_video_id = $1
		   OR active_camera_id IN (
				SELECT id FROM cameras WHERE metadata->>'demo_video_id' = $1::text
		   )`, id)
	return nil
}

func (s *Service) defaultSiteID(ctx context.Context, orgID uuid.UUID) (uuid.UUID, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx, `SELECT id FROM sites WHERE org_id = $1 ORDER BY created_at LIMIT 1`, orgID).Scan(&id)
	return id, err
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()
	_, err = io.Copy(out, in)
	return err
}

func strPtr(s string) *string { return &s }

func (s *Service) MinioStore() *MinioStore { return s.minio }
