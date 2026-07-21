package handler

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/camera"
	"github.com/citevision/citevision-v2/backend/internal/demo"
	"github.com/citevision/citevision-v2/backend/internal/health"
	"github.com/citevision/citevision-v2/backend/internal/middleware"
)

func (a *API) GetDemoSettings(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	st, err := a.Demo.GetSettings(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to load demo settings")
		return
	}
	if a.Orchestrator != nil {
		snap := a.Orchestrator.DemoPipelineStatus(r.Context(), orgID, st.ActiveCameraID)
		if snap.PipelineStatus != "" && snap.PipelineStatus != "unknown" {
			st.PipelineStatus = snap.PipelineStatus
		}
		st.IngestReady = snap.IngestReady
	}
	writeJSON(w, http.StatusOK, st)
}

func (a *API) PatchDemoSettings(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	var req demo.PatchSettingsRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid json")
		return
	}
	var prevCamID *uuid.UUID
	if req.ActiveVideoID != nil || req.ActiveCameraID != nil {
		if before, err := a.Demo.GetSettings(r.Context(), orgID); err == nil {
			prevCamID = before.ActiveCameraID
		}
	}
	st, err := a.Demo.PatchSettings(r.Context(), orgID, req)
	if err != nil {
		if errors.Is(err, demo.ErrVideoNotFound) {
			writeError(w, http.StatusNotFound, err.Error())
			return
		}
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if a.Orchestrator != nil && (req.ActiveVideoID != nil || req.ActiveCameraID != nil) {
		st.PipelineStatus = "healing"
		st.IngestReady = false
		a.Orchestrator.StartDemoSwitchHealAsync(
			a.Demo, orgID, prevCamID, st.ActiveCameraID, st.ActiveVideoID,
		)
		if a.Frigate != nil && a.Frigate.Enabled() {
			go a.triggerFrigateSync(context.Background(), orgID, st.ActiveCameraID)
		}
	}
	writeJSON(w, http.StatusOK, st)
}

func (a *API) UploadDemoVideo(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	if err := r.ParseMultipartForm(2 << 30); err != nil {
		writeError(w, http.StatusBadRequest, "invalid multipart form")
		return
	}
	file, hdr, err := r.FormFile("video")
	if err != nil {
		writeError(w, http.StatusBadRequest, "video file required")
		return
	}
	defer file.Close()

	name := strings.TrimSpace(r.FormValue("name"))
	if name == "" && hdr.Filename != "" {
		// filepath.Base strips Windows full paths (e.g. C:\Users\...\benedicte.mp4 → benedicte.mp4).
		// We also replace any stray backslashes that slip through on some clients.
		baseName := filepath.Base(strings.ReplaceAll(hdr.Filename, "\\", "/"))
		name = strings.TrimSuffix(baseName, filepath.Ext(baseName))
		name = strings.TrimSpace(name)
	}
	contentType := hdr.Header.Get("Content-Type")
	// If the browser/curl didn't set a proper content-type, detect from filename.
	if contentType == "" || contentType == "application/octet-stream" {
		if strings.HasSuffix(strings.ToLower(hdr.Filename), ".mp4") {
			contentType = "video/mp4"
		} else {
			contentType = "video/mp4" // default — service validates extension anyway
		}
	}

	v, err := a.Demo.UploadVideo(r.Context(), orgID, name, file, hdr.Size, contentType)
	if err != nil {
		switch {
		case errors.Is(err, demo.ErrVideoLimit):
			writeError(w, http.StatusConflict, err.Error())
		case errors.Is(err, demo.ErrInvalidVideo):
			writeError(w, http.StatusBadRequest, err.Error())
		default:
			writeError(w, http.StatusInternalServerError, err.Error())
		}
		return
	}
	writeJSON(w, http.StatusAccepted, v)
}

func (a *API) GetDemoVideoStatus(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	videoID, err := uuid.Parse(chi.URLParam(r, "videoID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid video id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	v, err := a.Demo.GetVideo(r.Context(), orgID, videoID)
	if err != nil {
		if errors.Is(err, demo.ErrVideoNotFound) {
			writeError(w, http.StatusNotFound, err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, v)
}

func (a *API) DeleteDemoVideo(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	videoID, err := uuid.Parse(chi.URLParam(r, "videoID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid video id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	if err := a.Demo.DeleteVideo(r.Context(), orgID, videoID); err != nil {
		if errors.Is(err, demo.ErrVideoNotFound) {
			writeError(w, http.StatusNotFound, err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}

func (a *API) PatchDemoVideo(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	videoID, err := uuid.Parse(chi.URLParam(r, "videoID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid video id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	var body struct {
		Name string `json:"name"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid json")
		return
	}
	v, err := a.Demo.RenameVideo(r.Context(), orgID, videoID, body.Name)
	if err != nil {
		if errors.Is(err, demo.ErrVideoNotFound) {
			writeError(w, http.StatusNotFound, err.Error())
			return
		}
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, v)
}

func (a *API) RetryDemoVideo(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	videoID, err := uuid.Parse(chi.URLParam(r, "videoID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid video id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	v, err := a.Demo.RetryVideo(r.Context(), orgID, videoID)
	if err != nil {
		if errors.Is(err, demo.ErrVideoNotFound) {
			writeError(w, http.StatusNotFound, err.Error())
			return
		}
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusAccepted, v)
}

func (a *API) ResetDemoWorkspace(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	if a.Demo == nil {
		a.ResetDemo(w, r)
		return
	}
	result, err := a.Demo.ResetWorkspace(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (a *API) InternalRepairDemoStreams(w http.ResponseWriter, r *http.Request) {
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	res := a.Demo.RepairAllDemoStreams(r.Context())
	writeJSON(w, http.StatusOK, res)
}

// InternalHealLivePreviews re-onboards real cameras and heals unsafe go2rtc preview sources.
// Called from start-full-stack so live HEVC cameras (e.g. 108) work after restart.
func (a *API) InternalHealLivePreviews(w http.ResponseWriter, r *http.Request) {
	if a.Cameras == nil {
		writeError(w, http.StatusServiceUnavailable, "camera service unavailable")
		return
	}
	ok, failed := a.Cameras.ReOnboardAllRealCameras(r.Context())
	healed, healFailed := a.Cameras.HealUnsafeLivePreviews(r.Context())
	writeJSON(w, http.StatusOK, map[string]int{
		"reonboard_ok":     ok,
		"reonboard_failed": failed,
		"healed":           healed,
		"heal_failed":      healFailed,
	})
}

func (a *API) DemoPreflight(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	waitSec := 0
	if raw := strings.TrimSpace(r.URL.Query().Get("wait_sec")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			waitSec = n
		}
	}
	if waitSec > 120 {
		waitSec = 120
	}
	minFrames := 10
	if raw := strings.TrimSpace(r.URL.Query().Get("min_frames")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			minFrames = n
		}
	}
	mode := strings.TrimSpace(r.URL.Query().Get("mode"))
	cameraOverride := strings.TrimSpace(r.URL.Query().Get("camera_id"))

	result := a.runDemoPreflightWait(r.Context(), orgID, waitSec, minFrames, mode, cameraOverride)
	writeJSON(w, http.StatusOK, result)
}

func (a *API) runDemoPreflightWait(
	parent context.Context,
	orgID uuid.UUID,
	waitSec int,
	minFrames int,
	mode string,
	cameraOverride string,
) map[string]interface{} {
	deadline := time.Now()
	if waitSec > 0 {
		deadline = deadline.Add(time.Duration(waitSec) * time.Second)
	}

	var lastFailed []string
	var lastReport health.PlatformHealth
	var ingestReady bool
	var pipelineStatus string

	for {
		ctx, cancel := context.WithTimeout(parent, 15*time.Second)
		report := health.CollectPlatformHealth(ctx, a.platformHealthDeps())
		failed := demoPreflightFailures(
			ctx, a, orgID, report, mode, cameraOverride, minFrames,
			&ingestReady, &pipelineStatus,
		)
		cancel()
		lastFailed = failed
		lastReport = report

		if len(failed) == 0 || time.Now().After(deadline) {
			break
		}
		if waitSec <= 0 {
			break
		}
		select {
		case <-parent.Done():
			goto done
		case <-time.After(2 * time.Second):
		}
	}
done:
	blocked := len(lastFailed) > 0
	reason := ""
	if blocked {
		reason = strings.Join(lastFailed, ", ")
	}
	return map[string]interface{}{
		"org_id":             orgID.String(),
		"ready":              !blocked,
		"blocked":            blocked,
		"suppression_reason": reason,
		"ingest_ready":       ingestReady,
		"pipeline_status":    pipelineStatus,
		"failed":             lastFailed,
		"platform":           lastReport,
	}
}

func demoPreflightFailures(
	ctx context.Context,
	a *API,
	orgID uuid.UUID,
	report health.PlatformHealth,
	mode string,
	cameraOverride string,
	minFrames int,
	ingestReady *bool,
	pipelineStatus *string,
) []string {
	failed := make([]string, 0)
	if report.Status == "down" {
		failed = append(failed, "platform_down")
	}

	if ok, errText := demoPreflightMQTT(); !ok {
		failed = append(failed, "mqtt_unreachable:"+errText)
	}

	// Rules-engine must be reachable (active_rules=0 is OK before first activation).
	if re, ok := report.Components["rules_engine"]; ok && re.Status == "down" {
		failed = append(failed, "rules_engine_down")
	}

	targetCamID := cameraOverride
	if targetCamID == "" && mode != "live" && a.Demo != nil {
		if st, err := a.Demo.GetSettings(ctx, orgID); err == nil && st.ActiveCameraID != nil {
			targetCamID = st.ActiveCameraID.String()
		}
	}

	if a.AI != nil && targetCamID != "" {
		aiSt, aiErr := a.AI.CameraStatus(ctx, targetCamID)
		if aiErr != nil {
			failed = append(failed, "ai_camera_status:"+aiErr.Error())
		} else {
			*ingestReady = aiSt.Running && aiSt.FramesProcessed >= minFrames
			if aiSt.Running && aiSt.FramesProcessed >= minFrames {
				*pipelineStatus = "ready"
			} else if aiSt.Running {
				*pipelineStatus = "healing"
				failed = append(
					failed,
					fmt.Sprintf("ai_ingest_not_ready:running=%t,frames=%d", aiSt.Running, aiSt.FramesProcessed),
				)
			} else {
				*pipelineStatus = "degraded"
				failed = append(failed, "ai_ingest_not_running")
			}
		}
	} else if mode != "live" && a.Demo != nil {
		if st, err := a.Demo.GetSettings(ctx, orgID); err == nil && st.ActiveCameraID == nil {
			failed = append(failed, "demo_no_active_camera")
		}
	}

	if mode != "live" && a.Demo != nil {
		if st, err := a.Demo.GetSettings(ctx, orgID); err == nil {
			stream := strings.TrimSpace(st.ActiveStream)
			if stream == "" && st.ActiveVideoID != nil {
				if v, vErr := a.Demo.GetVideo(ctx, orgID, *st.ActiveVideoID); vErr == nil {
					stream = strings.TrimSpace(v.Go2rtcSrc)
				}
			}
			if stream != "" {
				g2 := camera.NewGo2RTCClient()
				if !g2.StreamExists(ctx, stream) {
					failed = append(failed, "go2rtc_stream_missing:"+stream)
				}
			} else if st.ActiveCameraID != nil {
				failed = append(failed, "go2rtc_stream_unconfigured")
			}
		}
	}

	if a.Frigate != nil && a.Frigate.Enabled() {
		if fr, ok := report.Components["frigate"]; ok {
			// Only block on Frigate down/unreachable — "degraded" (e.g. youngest
			// event age > 25s) is normal between demo detections and must not
			// prevent rule enable after a successful script preflight.
			if fr.Status == "down" {
				failed = append(failed, "frigate_not_ready")
			}
		} else {
			fs := a.Frigate.Status(ctx)
			if reach, _ := fs["reachable"].(bool); !reach {
				failed = append(failed, "frigate_unreachable")
			}
		}
	}

	return failed
}

func demoPreflightMQTT() (bool, string) {
	host := os.Getenv("MQTT_HOST")
	if strings.TrimSpace(host) == "" {
		host = "127.0.0.1"
	}
	port := 1884
	if raw := strings.TrimSpace(os.Getenv("MQTT_PORT")); raw != "" {
		if p, err := strconv.Atoi(raw); err == nil && p > 0 {
			port = p
		}
	}
	conn, err := net.DialTimeout("tcp", fmt.Sprintf("%s:%d", host, port), 2*time.Second)
	if err != nil {
		return false, err.Error()
	}
	_ = conn.Close()
	return true, ""
}
