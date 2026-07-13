package ingest

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"hash/fnv"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"log/slog"

	"github.com/citevision/citevision-v2/backend/internal/camera"
	"github.com/citevision/citevision-v2/backend/internal/config"
	"github.com/citevision/citevision-v2/backend/internal/spatial"
)

type AIClient struct {
	baseURL    string
	httpClient *http.Client
}

func NewAIClient(cfg *config.Config) *AIClient {
	host := cfg.AIEngineHost
	if host == "" || host == "0.0.0.0" {
		host = "localhost"
	}
	return &AIClient{
		baseURL: fmt.Sprintf("http://%s:%d", host, cfg.AIEnginePort),
		httpClient: &http.Client{Timeout: 60 * time.Second},
	}
}

type AnalyticsThresholds struct {
	DurationSeconds    *float64 `json:"duration_seconds,omitempty"`
	SpeedKmh           *float64 `json:"speed_kmh,omitempty"`
	CrowdThreshold     *int     `json:"crowd_threshold,omitempty"`
	VehicleThreshold   *int     `json:"vehicle_threshold,omitempty"`
	DensityThreshold   *float64 `json:"density_threshold,omitempty"`
	FightOverlapRatio  *float64 `json:"fight_overlap_ratio,omitempty"`
}

type StartCameraRequest struct {
	RTSPURL              string                   `json:"rtsp_url,omitempty"`
	VideoFile            string                   `json:"video_file,omitempty"`
	AIFps                float64                  `json:"ai_fps,omitempty"`
	OrgID                string                   `json:"org_id,omitempty"`
	SpatialRules         map[string]interface{}   `json:"spatial_rules"`
	Calibration          map[string]interface{}   `json:"calibration"`
	Watchlist            []map[string]interface{} `json:"watchlist"`
	Plates               []map[string]interface{} `json:"plates"`
	AnalyticsThresholds  AnalyticsThresholds      `json:"analytics_thresholds,omitempty"`
	EvidenceCaptureRules []map[string]interface{} `json:"evidence_capture_rules,omitempty"`
	CapabilityProfiles   []map[string]interface{} `json:"capability_profiles,omitempty"`
	CapabilityManifest   *CapabilityManifest    `json:"capability_manifest,omitempty"`
}

func (c *AIClient) StartCamera(ctx context.Context, cameraID string, req StartCameraRequest) error {
	body, _ := json.Marshal(req)
	url := fmt.Sprintf("%s/cameras/%s/start", c.baseURL, cameraID)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("ai engine start failed: %s", string(b))
	}
	return nil
}

func (c *AIClient) RequestEvidenceCapture(ctx context.Context, cameraID string, payload map[string]interface{}) (map[string]interface{}, error) {
	body, _ := json.Marshal(payload)
	url := fmt.Sprintf("%s/cameras/%s/evidence/capture", c.baseURL, cameraID)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("ai evidence capture: %s", string(b))
	}
	var out map[string]interface{}
	_ = json.Unmarshal(b, &out)
	return out, nil
}

func (c *AIClient) StopCamera(ctx context.Context, cameraID string) error {
	url := fmt.Sprintf("%s/cameras/%s/stop", c.baseURL, cameraID)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, nil)
	if err != nil {
		return err
	}
	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return nil
}

type AICameraStatus struct {
	Running         bool
	FramesProcessed int
	LastError       string
}

func (c *AIClient) CameraStatus(ctx context.Context, cameraID string) (AICameraStatus, error) {
	var out AICameraStatus
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/cameras", nil)
	if err != nil {
		return out, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return out, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return out, fmt.Errorf("ai list cameras: %s", string(b))
	}
	var body struct {
		Cameras []struct {
			CameraID        string `json:"camera_id"`
			Running         bool   `json:"running"`
			FramesProcessed int    `json:"frames_processed"`
			LastError       string `json:"last_error"`
		} `json:"cameras"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return out, err
	}
	for _, cam := range body.Cameras {
		if cam.CameraID == cameraID {
			return AICameraStatus{
				Running:         cam.Running,
				FramesProcessed: cam.FramesProcessed,
				LastError:       cam.LastError,
			}, nil
		}
	}
	return out, fmt.Errorf("camera %s not registered", cameraID)
}

func (c *AIClient) ResetDemoActivate(ctx context.Context, cameraID, previousCameraID string) error {
	payload := map[string]string{"camera_id": cameraID}
	if previousCameraID != "" {
		payload["previous_camera_id"] = previousCameraID
	}
	body, _ := json.Marshal(payload)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/internal/demo/activate", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("ai demo activate: %s", string(b))
	}
	return nil
}

func (c *AIClient) PostEmpty(ctx context.Context, url string) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, nil)
	if err != nil {
		return err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return nil
}

func (c *AIClient) Healthy(ctx context.Context) bool {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/health", nil)
	if err != nil {
		return false
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode < 500
}

// FetchHealth returns AI /health as string map (all keys stringified).
func (c *AIClient) FetchHealth(ctx context.Context) (map[string]string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/health", nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("ai health: %s", string(b))
	}
	var raw map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		return nil, err
	}
	out := make(map[string]string, len(raw))
	for k, v := range raw {
		out[k] = fmt.Sprint(v)
	}
	return out, nil
}

// ReloadSecondaryModels asks the AI engine to reload secondary/org ONNX models.
func (c *AIClient) ReloadSecondaryModels(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/admin/reload-secondary-models", nil)
	if err != nil {
		return err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("ai reload: %s", string(b))
	}
	return nil
}

// ListRunningCameras returns camera IDs currently ingesting on the AI engine.
// Used to detect AI restarts: orchestrator may still think cameras are active
// while the remote worker manager was wiped.
func (c *AIClient) ListRunningCameras(ctx context.Context) (map[string]bool, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/cameras", nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("ai list cameras: %s", string(b))
	}
	var body struct {
		Cameras []struct {
			CameraID string `json:"camera_id"`
			Running  bool   `json:"running"`
		} `json:"cameras"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return nil, err
	}
	out := make(map[string]bool, len(body.Cameras))
	for _, cam := range body.Cameras {
		if cam.Running {
			out[cam.CameraID] = true
		}
	}
	return out, nil
}

type Orchestrator struct {
	pool     *pgxpool.Pool
	ai       *AIClient
	spatial  *spatial.Service
	cameras  *camera.Service
	log      *slog.Logger
	interval time.Duration
	mu       sync.Mutex
	active   map[uuid.UUID]bool
	// configHash tracks the last spatial/rules/watchlist config pushed per camera so
	// the orchestrator can hot-reload (re-push) when zones/lines/rules change, without
	// a manual restart.
	configHash map[uuid.UUID]string
	// Backoff after failed AI start attempts (avoids hammering backend/AI every 10s).
	failNext    map[uuid.UUID]time.Time
	failBackoff map[uuid.UUID]time.Duration
	aiDownUntil time.Time
	frigateHooks FrigateHooks
}

// FrigateHooks avoids import cycle with frigate package.
type FrigateHooks struct {
	Rebuild   func(ctx context.Context) error
	WaitFresh func(ctx context.Context, cameraID string, maxAgeSec float64) error
}

func (o *Orchestrator) SetFrigateHooks(h FrigateHooks) {
	if o == nil {
		return
	}
	o.frigateHooks = h
}

func NewOrchestrator(
	pool *pgxpool.Pool,
	ai *AIClient,
	spatialSvc *spatial.Service,
	cameraSvc *camera.Service,
	log *slog.Logger,
) *Orchestrator {
	return &Orchestrator{
		pool:     pool,
		ai:       ai,
		spatial:  spatialSvc,
		cameras:  cameraSvc,
		log:      log,
		interval: 10 * time.Second,
		active:      make(map[uuid.UUID]bool),
		configHash:  make(map[uuid.UUID]string),
		failNext:    make(map[uuid.UUID]time.Time),
		failBackoff: make(map[uuid.UUID]time.Duration),
	}
}

func (o *Orchestrator) Run(ctx context.Context) {
	ticker := time.NewTicker(o.interval)
	defer ticker.Stop()
	o.sync(ctx)
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			o.sync(ctx)
		}
	}
}

func (o *Orchestrator) clearActiveIngest() {
	o.mu.Lock()
	defer o.mu.Unlock()
	for camID := range o.active {
		delete(o.active, camID)
		delete(o.configHash, camID)
	}
}

// DropCamera stops AI ingest for one camera and clears local orchestrator state (best-effort).
func (o *Orchestrator) DropCamera(ctx context.Context, cameraID uuid.UUID) {
	o.mu.Lock()
	wasActive := o.active[cameraID]
	delete(o.active, cameraID)
	delete(o.configHash, cameraID)
	delete(o.failNext, cameraID)
	o.mu.Unlock()
	if !wasActive {
		return
	}
	stopCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	_ = o.ai.StopCamera(stopCtx, cameraID.String())
}

// InvalidateConfigHashes forces the next sync tick to re-push spatial/rules to the AI
// engine for every active camera (hot-reload), without stopping ingest workers.
func (o *Orchestrator) InvalidateConfigHashes() {
	o.mu.Lock()
	defer o.mu.Unlock()
	for id := range o.configHash {
		delete(o.configHash, id)
	}
}

// SyncNow runs one orchestrator sync immediately (e.g. after spatial seed).
// It also clears the aiDownUntil backoff so a manual resync-spatial always
// reaches the AI even if it was recently detected as unreachable.
func (o *Orchestrator) SyncNow(ctx context.Context) {
	o.mu.Lock()
	o.aiDownUntil = time.Time{}
	o.mu.Unlock()
	o.sync(ctx)
}

// DebugSpatialConfig returns the spatial payload that would be sent to the AI engine.
func (o *Orchestrator) DebugSpatialConfig(ctx context.Context, orgID, cameraID uuid.UUID) map[string]interface{} {
	return o.buildSpatialConfig(ctx, orgID, cameraID)
}

func (o *Orchestrator) reconcileWithAI(ctx context.Context) {
	listCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	running, err := o.ai.ListRunningCameras(listCtx)
	cancel()
	if err != nil {
		o.log.Debug("ai camera list unavailable", "error", err)
		return
	}
	o.mu.Lock()
	defer o.mu.Unlock()
	for camID := range o.active {
		if !running[camID.String()] {
			delete(o.active, camID)
			delete(o.configHash, camID)
			o.log.Info("camera ingest stale after ai restart, will re-push", "camera_id", camID)
		}
	}
}

func (o *Orchestrator) sync(ctx context.Context) {
	if os.Getenv("DISABLE_AI_INGEST") == "1" || os.Getenv("VIDEO_ONLY_MODE") == "1" {
		o.mu.Lock()
		active := make([]uuid.UUID, 0, len(o.active))
		for camID := range o.active {
			active = append(active, camID)
		}
		o.mu.Unlock()
		for _, camID := range active {
			_ = o.ai.StopCamera(ctx, camID.String())
		}
		o.mu.Lock()
		for _, camID := range active {
			delete(o.active, camID)
		}
		o.mu.Unlock()
		return
	}
	if time.Now().Before(o.aiDownUntil) {
		return
	}
	probeCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
	aiUp := o.ai.Healthy(probeCtx)
	cancel()
	if !aiUp {
		o.aiDownUntil = time.Now().Add(2 * time.Minute)
		o.mu.Lock()
		hadActive := len(o.active) > 0
		o.mu.Unlock()
		if hadActive {
			o.clearActiveIngest()
			o.log.Warn("ai engine unreachable — cleared local ingest state for re-sync")
		}
		return
	}
	o.aiDownUntil = time.Time{}
	o.reconcileWithAI(ctx)
	rows, err := o.pool.Query(ctx, `
		SELECT c.id, c.org_id, c.metadata
		FROM cameras c WHERE c.is_active = TRUE`)
	if err != nil {
		o.log.Error("orchestrator query failed", "error", err)
		return
	}
	defer rows.Close()

	seen := make(map[uuid.UUID]bool)
	for rows.Next() {
		var id, orgID uuid.UUID
		var meta json.RawMessage
		if err := rows.Scan(&id, &orgID, &meta); err != nil {
			continue
		}
		if o.skipInactiveDemoCamera(ctx, orgID, id, meta) {
			o.mu.Lock()
			wasActive := o.active[id]
			if wasActive {
				o.mu.Unlock()
				_ = o.ai.StopCamera(ctx, id.String())
				o.mu.Lock()
				delete(o.active, id)
				delete(o.configHash, id)
			}
			o.mu.Unlock()
			continue
		}
		seen[id] = true
		o.mu.Lock()
		camActive := o.active[id]
		if !camActive {
			if next, ok := o.failNext[id]; ok && time.Now().Before(next) {
				o.mu.Unlock()
				continue
			}
		}
		o.mu.Unlock()
		rtspURL, err := o.cameras.BuildRTSP(ctx, orgID, id)
		if err != nil || rtspURL == "" {
			o.log.Warn("failed to build RTSP URL", "camera_id", id, "error", err)
			continue
		}
		spatialCfg := o.buildSpatialConfig(ctx, orgID, id)
		calib := o.extractCalibrationFromCamera(ctx, orgID, id)
		videoFile := o.extractVideoFileFromCamera(ctx, orgID, id)
		thresholds := o.mergeAnalyticsThresholds(ctx, orgID, id)
		evidenceRules := o.buildEvidenceCaptureRulesForCamera(ctx, orgID, id)
		capProfiles := o.buildCapabilityProfiles(ctx, orgID, id)
		manifest := o.buildCapabilityManifest(ctx, orgID, id, spatialCfg, capProfiles, evidenceRules)
		req := StartCameraRequest{
			OrgID:                orgID.String(),
			SpatialRules:         spatialCfg,
			Calibration:          calib,
			Watchlist:            o.buildWatchlist(ctx, orgID),
			Plates:               o.buildPlates(ctx, orgID),
			AIFps:                8,
			AnalyticsThresholds:  thresholds,
			EvidenceCaptureRules: evidenceRules,
			CapabilityProfiles:   capProfiles,
			CapabilityManifest:   &manifest,
		}
		if frigateEvidenceIngestViaGo2RTC() && isDemoCameraMetadata(meta) {
			if demoRTSP := demoGo2rtcRTSPURL(meta); demoRTSP != "" {
				req.RTSPURL = demoRTSP
				o.log.Info("demo ingest via go2rtc RTSP (Frigate timeline)", "camera_id", id, "stream", demoGo2rtcStreamFromMetadata(meta))
			} else if videoFile != "" {
				req.VideoFile = videoFile
			} else {
				req.RTSPURL = rtspURL
			}
		} else if videoFile != "" {
			req.VideoFile = videoFile
		} else {
			req.RTSPURL = rtspURL
		}

		// Hot-reload: skip if already active AND the config fingerprint is unchanged.
		newHash := configFingerprint(req)
		o.mu.Lock()
		prevHash := o.configHash[id]
		reload := o.active[id]
		if reload && prevHash == newHash {
			o.mu.Unlock()
			continue
		}
		o.mu.Unlock()
		if err := o.ai.StartCamera(ctx, id.String(), req); err != nil {
			o.log.Warn("failed to start camera", "camera_id", id, "error", err, "reload", reload)
			if !reload {
				o.scheduleRetry(id)
			}
		} else {
			o.mu.Lock()
			o.active[id] = true
			o.configHash[id] = newHash
			delete(o.failNext, id)
			delete(o.failBackoff, id)
			o.mu.Unlock()
			if reload {
				o.log.Info("camera config hot-reloaded", "camera_id", id, "behaviors", zoneBehaviorNames(spatialCfg))
			}
		}
	}

	o.mu.Lock()
	stale := make([]uuid.UUID, 0)
	for camID := range o.active {
		if !seen[camID] {
			stale = append(stale, camID)
		}
	}
	o.mu.Unlock()
	for _, camID := range stale {
		_ = o.ai.StopCamera(ctx, camID.String())
		o.mu.Lock()
		delete(o.active, camID)
		delete(o.configHash, camID)
		delete(o.failNext, camID)
		delete(o.failBackoff, camID)
		o.mu.Unlock()
	}
}

// configFingerprint produces a stable hash of the camera's effective AI config so
// the orchestrator can detect zone/line/rule/watchlist changes and re-push them.
func configFingerprint(req StartCameraRequest) string {
	b, err := json.Marshal(req)
	if err != nil {
		return ""
	}
	h := fnv.New64a()
	_, _ = h.Write(b)
	return strconv.FormatUint(h.Sum64(), 16)
}

func zoneBehaviorNames(spatial map[string]interface{}) []string {
	zones, _ := spatial["zones"].([]map[string]interface{})
	if zones == nil {
		raw, ok := spatial["zones"].([]interface{})
		if !ok {
			return nil
		}
		out := make([]string, 0, len(raw))
		for _, item := range raw {
			z, ok := item.(map[string]interface{})
			if !ok {
				continue
			}
			if b, ok := z["behavior"].(string); ok && b != "" {
				out = append(out, b)
			}
		}
		return out
	}
	out := make([]string, 0, len(zones))
	for _, z := range zones {
		if b, ok := z["behavior"].(string); ok && b != "" {
			out = append(out, b)
		}
	}
	return out
}

func (o *Orchestrator) scheduleRetry(cameraID uuid.UUID) {
	const maxBackoff = 5 * time.Minute
	o.mu.Lock()
	defer o.mu.Unlock()
	wait := o.failBackoff[cameraID]
	if wait == 0 {
		wait = 30 * time.Second
	} else {
		wait *= 2
		if wait > maxBackoff {
			wait = maxBackoff
		}
	}
	o.failBackoff[cameraID] = wait
	o.failNext[cameraID] = time.Now().Add(wait)
}

func (o *Orchestrator) extractVideoFileFromCamera(ctx context.Context, orgID, cameraID uuid.UUID) string {
	cam, err := o.cameras.Get(ctx, orgID, cameraID)
	if err != nil {
		return ""
	}
	var meta map[string]interface{}
	if err := json.Unmarshal(cam.Metadata, &meta); err != nil {
		return ""
	}
	if vf, ok := meta["video_file"].(string); ok && vf != "" {
		return vf
	}
	if meta["virtual"] == true {
		if p := os.Getenv("DEMO_VIDEO_PATH"); p != "" {
			return p
		}
		if src, ok := meta["source"].(string); ok && src != "" {
			root := os.Getenv("PROJECT_ROOT")
			if root == "" {
				root = "."
			}
			candidate := filepath.Join(root, "data", "videos", src)
			if _, err := os.Stat(candidate); err == nil {
				return candidate
			}
		}
	}
	return ""
}

func (o *Orchestrator) extractCalibrationFromCamera(ctx context.Context, orgID, cameraID uuid.UUID) map[string]interface{} {
	cam, err := o.cameras.Get(ctx, orgID, cameraID)
	if err != nil {
		return map[string]interface{}{}
	}
	return o.extractCalibration(cam.Metadata)
}

func (o *Orchestrator) buildSpatialConfig(ctx context.Context, orgID, cameraID uuid.UUID) map[string]interface{} {
	zones, _ := o.spatial.ListZones(ctx, orgID, nil)
	lines, _ := o.spatial.ListLines(ctx, orgID, nil)

	zoneList := make([]map[string]interface{}, 0)
	for _, z := range zones {
		if z.CameraID != nil && *z.CameraID != cameraID {
			continue
		}
		var polygon []map[string]interface{}
		_ = json.Unmarshal(z.Polygon, &polygon)
		loiterSec := 30
		if strings.HasPrefix(z.Name, "e2e-") || os.Getenv("E2E_MODE") == "1" {
			loiterSec = 5
		}
		// Parse the rich behavior config; fall back to legacy zone_kind.
		behavior, behaviorConfig := parseZoneBehavior(z.BehaviorConfig, z.ZoneKind)
		zoneList = append(zoneList, map[string]interface{}{
			"zone_id":          z.Name,
			"name":             z.Name,
			"zone_kind":        z.ZoneKind,
			"behavior":         behavior,
			"behavior_config":  behaviorConfig,
			"polygon":          polygon,
			"loiter_threshold": loiterSec,
		})
	}
	o.applyRuleSpeedLimitsToZones(ctx, orgID, cameraID, zoneList)

	lineList := make([]map[string]interface{}, 0)
	for _, l := range lines {
		if l.CameraID != nil && *l.CameraID != cameraID {
			continue
		}
		var start, end map[string]float64
		_ = json.Unmarshal(l.StartPoint, &start)
		_ = json.Unmarshal(l.EndPoint, &end)
		dir := "unknown"
		if l.Direction != nil {
			dir = *l.Direction
		}
		// Parse the rich behavior config (mirrors zones). class_filter on the line
		// is the single source of truth for what the counter counts ([C.27]/[C.30]).
		lineBehavior, lineBehaviorConfig := parseZoneBehavior(l.BehaviorConfig, "line_cross")
		classFilter := "any"
		if cf, ok := lineBehaviorConfig["class_filter"].(string); ok && cf != "" {
			classFilter = cf
		}
		if bdir, ok := lineBehaviorConfig["direction"].(string); ok && bdir != "" && dir == "unknown" {
			dir = bdir
		}
		lineList = append(lineList, map[string]interface{}{
			"line_id":         l.Name,
			"name":            l.Name,
			"start":           start,
			"end":             end,
			"direction":       dir,
			"behavior":        lineBehavior,
			"behavior_config": lineBehaviorConfig,
			"class_filter":    classFilter,
		})
	}

	return map[string]interface{}{
		"zones":          zoneList,
		"lines":          lineList,
		"presence_rules": o.buildPresenceRulesFromActiveRules(ctx, orgID, cameraID, zoneList),
	}
}

// parseZoneBehavior extracts {behavior, config} from a zone's behavior_config JSON.
// It falls back to the legacy zone_kind when no behavior is configured so existing
// zones keep working unchanged.
func parseZoneBehavior(raw json.RawMessage, zoneKind string) (string, map[string]interface{}) {
	cfg := map[string]interface{}{}
	behavior := ""
	if len(raw) > 0 {
		var parsed map[string]interface{}
		if err := json.Unmarshal(raw, &parsed); err == nil {
			if b, ok := parsed["behavior"].(string); ok {
				behavior = b
			}
			if c, ok := parsed["config"].(map[string]interface{}); ok {
				cfg = c
			}
		}
	}
	if behavior == "" {
		behavior = zoneKind
	}
	return behavior, cfg
}

// extractZoneNameFromCondition recursively searches a rule's condition tree for an
// `eq` clause on `zone_id` (used by rules that bind the zone via their condition rather
// than an explicit `bindings.zone_name`, e.g. rules built/edited through the Studio
// with a compound AND condition).
func extractZoneNameFromCondition(cond map[string]interface{}) string {
	if cond == nil {
		return ""
	}
	if field, _ := cond["field"].(string); field == "zone_id" {
		if op, _ := cond["op"].(string); op == "eq" || op == "" {
			if v, ok := cond["value"].(string); ok && v != "" {
				return v
			}
		}
	}
	if children, ok := cond["children"].([]interface{}); ok {
		for _, c := range children {
			if cm, ok := c.(map[string]interface{}); ok {
				if v := extractZoneNameFromCondition(cm); v != "" {
					return v
				}
			}
		}
	}
	return ""
}

// resolveRuleZoneName finds the zone a speed rule targets: explicit `bindings.zone_name`
// first, then a `zone_id` equality inside the rule condition tree, then — for speed
// rules scoped to a single camera with exactly one speed_measurement zone — that zone.
// This keeps rules created/edited via the Studio (which may omit `zone_name`) in sync
// with the AI zone engine instead of silently skipping the live-traffic/limit overlay.
func resolveRuleZoneName(def map[string]interface{}, bindings map[string]interface{}, isSpeed bool, zones []map[string]interface{}) string {
	if zoneName, _ := bindings["zone_name"].(string); zoneName != "" {
		return zoneName
	}
	if cond, ok := def["condition"].(map[string]interface{}); ok {
		if v := extractZoneNameFromCondition(cond); v != "" {
			return v
		}
	}
	if !isSpeed {
		return ""
	}
	speedZone := ""
	count := 0
	for _, z := range zones {
		if behavior, _ := z["behavior"].(string); behavior == "speed_measurement" {
			count++
			name, _ := z["name"].(string)
			speedZone = name
		}
	}
	if count == 1 {
		return speedZone
	}
	return ""
}

// applyRuleSpeedLimitsToZones overlays speed_limit_kmh and live-traffic tuning from enabled
// speeding rules (bindings + zone_name, or a zone_id condition fallback) so the AI zone
// engine matches the UI rule.
func (o *Orchestrator) applyRuleSpeedLimitsToZones(
	ctx context.Context,
	orgID, cameraID uuid.UUID,
	zones []map[string]interface{},
) {
	rows, err := o.pool.Query(ctx, `
		SELECT definition FROM rules
		WHERE org_id = $1 AND is_enabled = TRUE`, orgID)
	if err != nil {
		return
	}
	defer rows.Close()

	camStr := cameraID.String()
	type zoneOverlay struct {
		limit       float64
		hasLimit    bool
		cooldown    float64
		hasCooldown bool
		spatialSec  float64
		hasSpatial  bool
		liveTraffic bool
	}
	overlays := map[string]zoneOverlay{}
	for rows.Next() {
		var defRaw []byte
		if err := rows.Scan(&defRaw); err != nil {
			continue
		}
		var def map[string]interface{}
		if err := json.Unmarshal(defRaw, &def); err != nil {
			continue
		}
		if !ruleAppliesToCamera(def, camStr) {
			continue
		}
		bindings, _ := def["bindings"].(map[string]interface{})
		if bindings == nil {
			continue
		}
		tplID, _ := bindings["template_id"].(string)
		isSpeed := tplID == "tpl-speeding-premium" || tplID == "tpl-speed-threshold"
		zoneName := resolveRuleZoneName(def, bindings, isSpeed, zones)
		if zoneName == "" {
			continue
		}
		limit, hasLimit := toFloat64(bindings["speed_kmh"])
		if !hasLimit || limit <= 0 {
			if !isSpeed {
				continue
			}
		}
		ov := overlays[zoneName]
		if hasLimit && limit > 0 {
			if !ov.hasLimit || limit < ov.limit {
				ov.limit = limit
			}
			ov.hasLimit = true
		}
		if v, ok := toFloat64(bindings["cooldown_sec"]); ok && v > 0 {
			if !ov.hasCooldown || v < ov.cooldown {
				ov.cooldown = v
			}
			ov.hasCooldown = true
		}
		if v, ok := toFloat64(bindings["spatial_dedup_sec"]); ok && v > 0 {
			if !ov.hasSpatial || v < ov.spatialSec {
				ov.spatialSec = v
			}
			ov.hasSpatial = true
		}
		if bindings["live_traffic"] == true {
			ov.liveTraffic = true
		}
		if s, ok := bindings["traffic_profile"].(string); ok && strings.EqualFold(strings.TrimSpace(s), "live_traffic") {
			ov.liveTraffic = true
		}
		if isSpeed && !ov.liveTraffic {
			ov.liveTraffic = true
		}
		overlays[zoneName] = ov
	}
	if len(overlays) == 0 {
		return
	}
	for _, z := range zones {
		name, _ := z["name"].(string)
		if name == "" {
			name, _ = z["zone_id"].(string)
		}
		ov, ok := overlays[name]
		if !ok {
			continue
		}
		cfg, _ := z["behavior_config"].(map[string]interface{})
		if cfg == nil {
			cfg = map[string]interface{}{}
		}
		if ov.hasLimit {
			cfg["speed_limit_kmh"] = ov.limit
		}
		if ov.hasCooldown {
			cfg["cooldown_sec"] = ov.cooldown
		}
		if ov.hasSpatial {
			cfg["spatial_dedup_sec"] = ov.spatialSec
		}
		if ov.liveTraffic {
			cfg["live_traffic"] = true
			if !ov.hasCooldown {
				cfg["cooldown_sec"] = 2.0
			}
			if !ov.hasSpatial {
				cfg["spatial_dedup_sec"] = 4.0
			}
			cfg["spatial_dedup_dist"] = 0.04
		}
		z["behavior_config"] = cfg
	}
}

var presenceRuleTemplates = map[string]bool{
	"tpl-zone-presence": true,
}

func (o *Orchestrator) buildPresenceRulesFromActiveRules(
	ctx context.Context,
	orgID, cameraID uuid.UUID,
	zones []map[string]interface{},
) []map[string]interface{} {
	rows, err := o.pool.Query(ctx, `
		SELECT definition FROM rules
		WHERE org_id = $1 AND is_enabled = TRUE`, orgID)
	if err != nil {
		return nil
	}
	defer rows.Close()

	zoneByName := make(map[string]map[string]interface{})
	for _, z := range zones {
		name, _ := z["name"].(string)
		if name == "" {
			name, _ = z["zone_id"].(string)
		}
		if name != "" {
			zoneByName[name] = z
		}
	}

	camStr := cameraID.String()
	var out []map[string]interface{}
	for rows.Next() {
		var defRaw []byte
		if err := rows.Scan(&defRaw); err != nil {
			continue
		}
		var def map[string]interface{}
		if err := json.Unmarshal(defRaw, &def); err != nil {
			continue
		}
		if !ruleAppliesToCamera(def, camStr) {
			continue
		}
		bindings, _ := def["bindings"].(map[string]interface{})
		if bindings == nil {
			continue
		}
		tpl, _ := bindings["template_id"].(string)
		if !presenceRuleTemplates[tpl] {
			continue
		}
		zoneName, _ := bindings["zone_name"].(string)
		if zoneName == "" {
			continue
		}
		z, ok := zoneByName[zoneName]
		if !ok {
			continue
		}
		presenceSec := 5.0
		if ds, ok := toFloat64(bindings["duration_seconds"]); ok && ds > 0 {
			presenceSec = ds
		}
		classFilter := "person"
		if cf, ok := bindings["class_filter"].(string); ok && cf != "" {
			classFilter = cf
		}
		out = append(out, map[string]interface{}{
			"zone_id":          zoneName,
			"polygon":          z["polygon"],
			"presence_seconds": presenceSec,
			"class_filter":     classFilter,
		})
	}
	return out
}

func (o *Orchestrator) extractCalibration(metadata json.RawMessage) map[string]interface{} {
	var meta map[string]interface{}
	_ = json.Unmarshal(metadata, &meta)
	if cal, ok := meta["calibration"].(map[string]interface{}); ok {
		return cal
	}
	if pts, ok := meta["calibration_points"]; ok {
		return map[string]interface{}{
			"calibration_points": pts,
			"world_scale":        meta["world_scale"],
			"speed_limit_kmh":    meta["speed_limit_kmh"],
		}
	}
	return map[string]interface{}{}
}

func (o *Orchestrator) buildWatchlist(ctx context.Context, orgID uuid.UUID) []map[string]interface{} {
	rows, err := o.pool.Query(ctx, `
		SELECT id, name, entries FROM surveillance_lists
		WHERE org_id = $1 AND list_type = 'face_watchlist' AND is_active = TRUE`, orgID)
	if err != nil {
		return nil
	}
	defer rows.Close()
	var out []map[string]interface{}
	for rows.Next() {
		var id uuid.UUID
		var name string
		var entries json.RawMessage
		if err := rows.Scan(&id, &name, &entries); err != nil {
			continue
		}
		var ents []map[string]interface{}
		_ = json.Unmarshal(entries, &ents)
		for _, e := range ents {
			entry := map[string]interface{}{
				"identifier": e["identifier"],
				"label":      e["label"],
				"metadata":   e["metadata"],
			}
			if entry["identifier"] == nil {
				entry["identifier"] = e["id"]
			}
			out = append(out, entry)
		}
	}
	if out == nil {
		out = []map[string]interface{}{}
	}
	return out
}

func (o *Orchestrator) buildPlates(ctx context.Context, orgID uuid.UUID) []map[string]interface{} {
	rows, err := o.pool.Query(ctx, `
		SELECT id, name, list_type, entries FROM surveillance_lists
		WHERE org_id = $1 AND list_type IN ('plate_block', 'plate_allow') AND is_active = TRUE`, orgID)
	if err != nil {
		return nil
	}
	defer rows.Close()
	var out []map[string]interface{}
	for rows.Next() {
		var id uuid.UUID
		var name, listType string
		var entries json.RawMessage
		if err := rows.Scan(&id, &name, &listType, &entries); err != nil {
			continue
		}
		var ents []map[string]interface{}
		_ = json.Unmarshal(entries, &ents)
		status := "blocked"
		if listType == "plate_allow" {
			status = "allowed"
		}
		for _, e := range ents {
			plate := e["plate_number"]
			if plate == nil {
				plate = e["identifier"]
			}
			if plate == nil {
				plate = e["plate"]
			}
			out = append(out, map[string]interface{}{
				"identifier": plate,
				"metadata": map[string]interface{}{
					"status": status,
					"list":   name,
				},
			})
		}
	}
	if out == nil {
		out = []map[string]interface{}{}
	}
	return out
}

func (o *Orchestrator) mergeAnalyticsThresholds(ctx context.Context, orgID, cameraID uuid.UUID) AnalyticsThresholds {
	rows, err := o.pool.Query(ctx, `
		SELECT definition FROM rules
		WHERE org_id = $1 AND is_enabled = TRUE`, orgID)
	if err != nil {
		return AnalyticsThresholds{}
	}
	defer rows.Close()

	camStr := cameraID.String()
	var merged AnalyticsThresholds
	for rows.Next() {
		var defRaw []byte
		if err := rows.Scan(&defRaw); err != nil {
			continue
		}
		var def map[string]interface{}
		if err := json.Unmarshal(defRaw, &def); err != nil {
			continue
		}
		if !ruleAppliesToCamera(def, camStr) {
			continue
		}
		mergeThresholdsFromDefinition(&merged, def)
	}
	if os.Getenv("E2E_MODE") == "1" {
		v := 1
		if merged.VehicleThreshold == nil || *merged.VehicleThreshold > v {
			merged.VehicleThreshold = &v
		}
		f := 0.08
		if merged.FightOverlapRatio == nil {
			merged.FightOverlapRatio = &f
		}
		d := 3.0
		if merged.DurationSeconds == nil {
			merged.DurationSeconds = &d
		}
	}
	return merged
}

func RuleAppliesToCamera(def map[string]interface{}, cameraID string) bool {
	return ruleAppliesToCamera(def, cameraID)
}

func ruleAppliesToCamera(def map[string]interface{}, cameraID string) bool {
	if cam, ok := def["camera_id"].(string); ok && cam != "" && cam != cameraID {
		return false
	}
	if bindings, ok := def["bindings"].(map[string]interface{}); ok {
		if cam, ok := bindings["camera_id"].(string); ok && cam != "" && cam != cameraID {
			return false
		}
	}
	return true
}

func mergeThresholdsFromDefinition(merged *AnalyticsThresholds, def map[string]interface{}) {
	if bindings, ok := def["bindings"].(map[string]interface{}); ok {
		mergeFloatMin(&merged.DurationSeconds, bindings["duration_seconds"])
		mergeFloatMax(&merged.SpeedKmh, bindings["speed_kmh"])
		mergeIntMin(&merged.CrowdThreshold, bindings["crowd_threshold"])
		mergeIntMin(&merged.CrowdThreshold, bindings["person_count"])
		mergeIntMin(&merged.VehicleThreshold, bindings["vehicle_threshold"])
		mergeFloatMin(&merged.DensityThreshold, bindings["density_threshold"])
	}
	if cond, ok := def["condition"].(map[string]interface{}); ok {
		walkConditionThresholds(merged, cond)
	}
}

func walkConditionThresholds(merged *AnalyticsThresholds, node map[string]interface{}) {
	field, _ := node["field"].(string)
	op, _ := node["op"].(string)
	opUpper := strings.ToUpper(op)
	if (opUpper == "GT" || opUpper == "GTE") && field != "" {
		switch field {
		case "duration_seconds":
			mergeFloatMin(&merged.DurationSeconds, node["value"])
		case "speed_kmh":
			mergeFloatMax(&merged.SpeedKmh, node["value"])
		case "person_count", "face_count":
			mergeIntMin(&merged.CrowdThreshold, node["value"])
		case "vehicle_count":
			mergeIntMin(&merged.VehicleThreshold, node["value"])
		case "density_per_m2":
			mergeFloatMin(&merged.DensityThreshold, node["value"])
		}
	}
	if children, ok := node["children"].([]interface{}); ok {
		for _, c := range children {
			if child, ok := c.(map[string]interface{}); ok {
				walkConditionThresholds(merged, child)
			}
		}
	}
}

func mergeFloatMin(dst **float64, raw interface{}) {
	v, ok := toFloat64(raw)
	if !ok || v <= 0 {
		return
	}
	if *dst == nil || v < **dst {
		copy := v
		*dst = &copy
	}
}

func mergeFloatMax(dst **float64, raw interface{}) {
	v, ok := toFloat64(raw)
	if !ok || v <= 0 {
		return
	}
	if *dst == nil || v > **dst {
		copy := v
		*dst = &copy
	}
}

func mergeIntMin(dst **int, raw interface{}) {
	v, ok := toFloat64(raw)
	if !ok || v <= 0 {
		return
	}
	iv := int(v)
	if *dst == nil || iv < **dst {
		copy := iv
		*dst = &copy
	}
}

func toFloat64(raw interface{}) (float64, bool) {
	switch n := raw.(type) {
	case float64:
		return n, true
	case float32:
		return float64(n), true
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	case json.Number:
		f, err := n.Float64()
		return f, err == nil
	default:
		return 0, false
	}
}
