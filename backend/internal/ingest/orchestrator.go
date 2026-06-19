package ingest

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
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
		httpClient: &http.Client{Timeout: 15 * time.Second},
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

type Orchestrator struct {
	pool     *pgxpool.Pool
	ai       *AIClient
	spatial  *spatial.Service
	cameras  *camera.Service
	log      *slog.Logger
	interval time.Duration
	active   map[uuid.UUID]bool
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
		active:   make(map[uuid.UUID]bool),
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

func (o *Orchestrator) sync(ctx context.Context) {
	if os.Getenv("DISABLE_AI_INGEST") == "1" || os.Getenv("VIDEO_ONLY_MODE") == "1" {
		for camID := range o.active {
			_ = o.ai.StopCamera(ctx, camID.String())
			delete(o.active, camID)
		}
		return
	}
	rows, err := o.pool.Query(ctx, `
		SELECT c.id, c.org_id
		FROM cameras c WHERE c.is_active = TRUE`)
	if err != nil {
		o.log.Error("orchestrator query failed", "error", err)
		return
	}
	defer rows.Close()

	seen := make(map[uuid.UUID]bool)
	for rows.Next() {
		var id, orgID uuid.UUID
		if err := rows.Scan(&id, &orgID); err != nil {
			continue
		}
		seen[id] = true
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
		}
		if videoFile != "" {
			req.VideoFile = videoFile
		} else {
			req.RTSPURL = rtspURL
		}
		if err := o.ai.StartCamera(ctx, id.String(), req); err != nil {
			o.log.Warn("failed to start camera", "camera_id", id, "error", err)
		} else {
			o.active[id] = true
		}
	}

	for camID := range o.active {
		if !seen[camID] {
			_ = o.ai.StopCamera(ctx, camID.String())
			delete(o.active, camID)
		}
	}
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
			return filepath.Join(root, "data", "videos", "benedicte_stream.mp4")
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
		var polygon []map[string]float64
		_ = json.Unmarshal(z.Polygon, &polygon)
		loiterSec := 30
		if strings.HasPrefix(z.Name, "e2e-") || os.Getenv("E2E_MODE") == "1" {
			loiterSec = 5
		}
		zoneList = append(zoneList, map[string]interface{}{
			"zone_id":          z.Name,
			"name":             z.Name,
			"zone_kind":        z.ZoneKind,
			"polygon":          polygon,
			"loiter_threshold": loiterSec,
		})
	}

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
		lineList = append(lineList, map[string]interface{}{
			"line_id":    l.Name,
			"name":       l.Name,
			"start":      start,
			"end":        end,
			"direction":  dir,
		})
	}

	return map[string]interface{}{
		"zones":          zoneList,
		"lines":          lineList,
		"presence_rules": o.buildPresenceRulesFromActiveRules(ctx, orgID, cameraID, zoneList),
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
