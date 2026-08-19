package frigate

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/camera"
	"github.com/citevision/citevision-v2/backend/internal/ingest"
	"github.com/citevision/citevision-v2/backend/internal/models"
)

// SyncService compiles DB → frigate.generated.yml and reloads Frigate (best-effort).
type SyncService struct {
	cfg      Config
	pool     *pgxpool.Pool
	cameras  *camera.Service
	compiler *Compiler
	client   *Client
	log      *slog.Logger

	mu        sync.Mutex
	lastSync  time.Time
	lastError string
}

func NewSyncService(pool *pgxpool.Pool, cameras *camera.Service, cfg Config, log *slog.Logger) *SyncService {
	if log == nil {
		log = slog.Default()
	}
	return &SyncService{
		cfg:      cfg,
		pool:     pool,
		cameras:  cameras,
		compiler: NewCompiler(cfg),
		client:   NewClient(cfg.URL),
		log:      log,
	}
}

func (s *SyncService) Enabled() bool {
	return s.cfg.SyncEnabled()
}

// RegisterWatchlistFace mirrors a CiteVision watchlist photo into Frigate Face Library.
func (s *SyncService) RegisterWatchlistFace(ctx context.Context, name string, jpeg []byte) error {
	if s == nil || s.client == nil {
		return fmt.Errorf("frigate client unavailable")
	}
	name = strings.TrimSpace(name)
	if name == "" {
		return fmt.Errorf("face name required")
	}
	// create is idempotent enough — ignore "already exists" style failures
	_ = s.client.CreateFace(ctx, name)
	return s.client.RegisterFace(ctx, name, jpeg)
}

// NeedsFaceRecognition is true when any active face watchlist has entries
// or any enabled rule emits face_watchlist_match.
func (s *SyncService) NeedsFaceRecognition(ctx context.Context) bool {
	if s == nil || s.pool == nil {
		return false
	}
	var n int
	_ = s.pool.QueryRow(ctx, `
		SELECT COALESCE(SUM(jsonb_array_length(entries)), 0)::int
		FROM surveillance_lists
		WHERE list_type = 'face_watchlist' AND is_active = TRUE`).Scan(&n)
	if n > 0 {
		return true
	}
	rows, err := s.pool.Query(ctx, `SELECT definition FROM rules WHERE is_enabled = TRUE`)
	if err != nil {
		return false
	}
	defer rows.Close()
	for rows.Next() {
		var defRaw []byte
		if err := rows.Scan(&defRaw); err != nil {
			continue
		}
		raw := strings.ToLower(string(defRaw))
		if strings.Contains(raw, "face_watchlist_match") {
			return true
		}
	}
	return false
}

// RebuildAll regenerates config for every active camera and reloads Frigate.
func (s *SyncService) RebuildAll(ctx context.Context) error {
	return s.rebuildAll(ctx, true)
}

// RebuildAllHot persists YAML; in demo mode it is a no-op.
// Demo YAML keeps detect.enabled true on go2rtc cameras; live focus is MQTT
// (FocusDetectForCamera / AlignCameraPower). Compiling all cameras on every
// rule/video switch exhausts the DB pool and makes /health/ready flap 503.
func (s *SyncService) RebuildAllHot(ctx context.Context) error {
	if s.cfg.DemoMode {
		s.log.Info("frigate rebuild hot skipped in demo (MQTT detect focus only)")
		return nil
	}
	return s.rebuildAll(ctx, true)
}

// rebuildAll writes frigate.generated.yml. When reload is false, MQTT detect focus
// remains authoritative (demo hyper-reactive path) — Frigate reload mid-SLO stalls
// the detector for tens of seconds.
func (s *SyncService) rebuildAll(ctx context.Context, reload bool) error {
	if !s.Enabled() {
		return nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, site_id, name, vendor, host(host), port, channel, username, rtsp_path,
		       stream_profile, status, metadata, is_active, created_at, updated_at
		FROM cameras WHERE is_active = true`)
	if err != nil {
		s.lastError = err.Error()
		return err
	}
	defer rows.Close()

	var compiled []CompiledCamera
	var compileFails int
	for rows.Next() {
		var cam models.Camera
		if err := rows.Scan(&cam.ID, &cam.OrgID, &cam.SiteID, &cam.Name, &cam.Vendor, &cam.Host, &cam.Port,
			&cam.Channel, &cam.Username, &cam.RTSPPath, &cam.StreamProfile, &cam.Status,
			&cam.Metadata, &cam.IsActive, &cam.CreatedAt, &cam.UpdatedAt); err != nil {
			s.log.Error("frigate scan camera row failed", "error", err)
			continue
		}
		cc, err := s.compileCamera(ctx, &cam)
		if err != nil {
			compileFails++
			s.log.Error("frigate compile camera failed (technical; not a policy exclude)",
				"camera", cam.ID, "host", cam.Host, "error", err)
			_ = s.setCameraFrigateError(ctx, cam.ID, err.Error())
			continue
		}
		compiled = append(compiled, cc)
		_ = s.setCameraFrigateOK(ctx, cam.ID, cc.FrigateID)
	}

	data, err := s.compiler.BuildConfig(compiled, s.NeedsFaceRecognition(ctx))
	if err != nil {
		s.lastError = err.Error()
		return err
	}
	if err := s.compiler.WriteGenerated(data); err != nil {
		if errors.Is(err, errConfigUnchanged) {
			s.lastError = ""
			s.log.Info("frigate config unchanged — skip reload", "cameras", len(compiled))
			s.alignDemoPower(ctx, compiled)
			return nil
		}
		s.lastError = err.Error()
		return err
	}
	if !reload {
		s.lastSync = time.Now().UTC()
		s.lastError = ""
		s.log.Info("frigate config written (reload skipped)", "cameras", len(compiled), "compile_fails", compileFails)
		s.alignDemoPower(ctx, compiled)
		return nil
	}
	if err := s.client.Reload(ctx); err != nil {
		s.lastError = err.Error()
		s.log.Warn("frigate reload failed", "error", err)
		return err
	}
	s.lastSync = time.Now().UTC()
	s.lastError = ""
	s.log.Info("frigate config rebuilt", "cameras", len(compiled), "compile_fails", compileFails)
	s.scheduleDemoPowerAlign(compiled)
	return nil
}

// scheduleDemoPowerAlign MQTT-focuses enabled-rule cameras after a reload.
// Frigate resets MQTT to YAML on reload, so a delayed second pass is required.
func (s *SyncService) scheduleDemoPowerAlign(compiled []CompiledCamera) {
	s.alignDemoPower(context.Background(), compiled)
	copied := append([]CompiledCamera(nil), compiled...)
	go func() {
		time.Sleep(8 * time.Second)
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		s.alignDemoPower(ctx, copied)
	}()
}

// alignDemoPower MQTT-wakes cameras that serve an enabled rule and stops the rest.
// Demo YAML keeps detect.enabled true so MQTT detect/set ON actually starts a detector;
// without this align, a reload would decode every looping demo stream at once.
func (s *SyncService) alignDemoPower(ctx context.Context, compiled []CompiledCamera) {
	if s == nil || !s.cfg.DemoMode {
		return
	}
	seen := map[uuid.UUID]struct{}{}
	for _, cc := range compiled {
		orgID, err := uuid.Parse(cc.OrgID)
		if err != nil {
			continue
		}
		if _, ok := seen[orgID]; ok {
			continue
		}
		seen[orgID] = struct{}{}
		s.AlignCameraPower(ctx, orgID)
	}
}

func (s *SyncService) compileCamera(ctx context.Context, cam *models.Camera) (CompiledCamera, error) {
	rtsp, err := s.cameras.BuildRTSP(ctx, cam.OrgID, cam.ID)
	if err != nil {
		return CompiledCamera{}, err
	}
	var stats *camera.StreamStats
	if !isDemoGo2rtcCamera(cam.Metadata) {
		stats = probeStreamStats(ctx, rtsp)
	}
	agg := s.evidenceAggregateForCamera(ctx, cam.OrgID, cam.ID)
	zones, _ := s.listZonesForCamera(ctx, cam.OrgID, cam.ID)
	return UpsertCamera(cam, rtsp, stats, agg, zones), nil
}

func (s *SyncService) SyncCamera(ctx context.Context, orgID, cameraID uuid.UUID) {
	if !s.Enabled() {
		return
	}
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
		defer cancel()
		if err := s.RebuildAllHot(ctx); err != nil {
			s.log.Warn("frigate sync after camera change", "camera", cameraID, "error", err)
		}
	}()
}

func (s *SyncService) SyncAfterSpatialChange(ctx context.Context, orgID uuid.UUID, cameraID *uuid.UUID) {
	if !s.Enabled() {
		return
	}
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
		defer cancel()
		_ = s.RebuildAllHot(ctx)
	}()
}

func (s *SyncService) SyncAfterRuleChange(ctx context.Context, orgID uuid.UUID) {
	if !s.Enabled() {
		return
	}
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
		defer cancel()
		if err := s.RebuildAllHot(ctx); err != nil {
			s.log.Warn("frigate sync after rule change", "error", err)
		}
		// Demo focus: power cameras strictly from enabled rules — a disabled
		// rule must free its camera's ffmpeg decode for the active one.
		s.AlignCameraPower(ctx, orgID)
	}()
}

// AlignCameraPower publishes MQTT enabled+detect per camera from enabled rules:
// cameras serving ≥1 enabled rule are woken, all others fully stopped. Decoding
// every demo stream at once pinned Frigate at ~676% CPU and starved detection.
func (s *SyncService) AlignCameraPower(ctx context.Context, orgID uuid.UUID) {
	if s == nil || s.pool == nil {
		return
	}
	rows, err := s.pool.Query(ctx, `SELECT definition FROM rules WHERE org_id = $1 AND is_enabled = TRUE`, orgID)
	if err != nil {
		return
	}
	active := map[string]bool{}
	for rows.Next() {
		var defRaw []byte
		if rows.Scan(&defRaw) != nil {
			continue
		}
		if camID, ok := CameraIDFromRuleDefinition(defRaw); ok {
			active[camID.String()] = true
		}
	}
	rows.Close()
	var on, off []string
	for _, id := range s.listActiveCameraIDs(ctx, orgID) {
		if active[id.String()] {
			on = append(on, id.String())
		} else {
			off = append(off, id.String())
		}
	}
	gate := NewDetectGate(s.log)
	if err := gate.AlignPower(on, off); err != nil {
		s.log.Warn("frigate camera power align failed", "error", err)
	}
}

// FocusDetectForCamera MQTT-boosts detect on keepCamera (others OFF, retain=false).
// YAML detect/record sync is left to SyncAfterRuleChange — doing RebuildAll here
// (especially with an 8s delay) saturates the Frigate mutex and makes /health/ready
// flap during demo 1-hit validation.
func (s *SyncService) FocusDetectForCamera(ctx context.Context, orgID, keepCameraID uuid.UUID) {
	if s == nil {
		return
	}
	go func() {
		bg, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		others := s.listActiveCameraIDs(bg, orgID)
		gate := NewDetectGate(s.log)
		ids := make([]string, 0, len(others))
		for _, id := range others {
			ids = append(ids, id.String())
		}
		if err := gate.BoostKeepCamera(keepCameraID.String(), ids); err != nil {
			s.log.Warn("frigate detect boost failed", "camera", keepCameraID, "error", err)
		}
	}()
}

// ClearRetainedDetectGhosts clears sticky MQTT detect/set retained OFF from older runs.
func (s *SyncService) ClearRetainedDetectGhosts(ctx context.Context) {
	if s == nil || s.pool == nil {
		return
	}
	rows, err := s.pool.Query(ctx, `SELECT id FROM cameras WHERE is_active = true`)
	if err != nil {
		return
	}
	defer rows.Close()
	var ids []string
	for rows.Next() {
		var id uuid.UUID
		if rows.Scan(&id) == nil {
			ids = append(ids, id.String())
		}
	}
	if len(ids) == 0 {
		return
	}
	gate := NewDetectGate(s.log)
	if err := gate.ClearRetainedDetect(ids); err != nil {
		s.log.Warn("clear retained detect failed", "error", err)
	}
}

func (s *SyncService) listActiveCameraIDs(ctx context.Context, orgID uuid.UUID) []uuid.UUID {
	rows, err := s.pool.Query(ctx, `SELECT id FROM cameras WHERE org_id = $1 AND is_active = true`, orgID)
	if err != nil {
		return nil
	}
	defer rows.Close()
	var out []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if rows.Scan(&id) == nil {
			out = append(out, id)
		}
	}
	return out
}

// CameraIDFromRuleDefinition extracts bindings.camera_id / camera_id from a rule definition.
func CameraIDFromRuleDefinition(def json.RawMessage) (uuid.UUID, bool) {
	if len(def) == 0 {
		return uuid.Nil, false
	}
	var m map[string]interface{}
	if err := json.Unmarshal(def, &m); err != nil || m == nil {
		return uuid.Nil, false
	}
	raw := ""
	if bindings, ok := m["bindings"].(map[string]interface{}); ok {
		raw, _ = bindings["camera_id"].(string)
	}
	if raw == "" {
		raw, _ = m["camera_id"].(string)
	}
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return uuid.Nil, false
	}
	id, err := uuid.Parse(raw)
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}

func (s *SyncService) Status(ctx context.Context) map[string]interface{} {
	out := map[string]interface{}{
		"enabled":      s.cfg.Enabled,
		"config_sync":  s.cfg.ConfigSync,
		"live":         s.cfg.Live,
		"evidence":     s.cfg.Evidence,
		"events":       s.cfg.Events,
		"url":          s.cfg.URL,
	}
	if !s.lastSync.IsZero() {
		out["last_sync_at"] = s.lastSync.Format(time.RFC3339)
	}
	if s.lastError != "" {
		out["last_error"] = s.lastError
	}
	if s.cfg.Enabled {
		if err := s.client.Ping(ctx); err != nil {
			out["reachable"] = false
			out["ping_error"] = err.Error()
		} else {
			out["reachable"] = true
		}
	}
	return out
}

func (s *SyncService) setCameraFrigateOK(ctx context.Context, cameraID uuid.UUID, frigateID string) error {
	_, err := s.pool.Exec(ctx, `
		UPDATE cameras SET metadata = COALESCE(metadata, '{}'::jsonb) ||
			jsonb_build_object(
				'frigate_camera_id', $2::text,
				'frigate_synced_at', to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
				'frigate_error', null
			),
			updated_at = NOW()
		WHERE id = $1`, cameraID, frigateID)
	return err
}

func (s *SyncService) setCameraFrigateError(ctx context.Context, cameraID uuid.UUID, msg string) error {
	_, err := s.pool.Exec(ctx, `
		UPDATE cameras SET metadata = COALESCE(metadata, '{}'::jsonb) ||
			jsonb_build_object('frigate_error', $2::text),
			updated_at = NOW()
		WHERE id = $1`, cameraID, msg)
	return err
}

func (s *SyncService) listZonesForCamera(ctx context.Context, orgID, cameraID uuid.UUID) ([]models.Zone, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, site_id, camera_id, name, polygon, color, zone_kind, behavior_config, is_active, created_at, updated_at
		FROM zones WHERE org_id = $1 AND camera_id = $2 AND is_active = true`, orgID, cameraID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []models.Zone
	for rows.Next() {
		var z models.Zone
		if err := rows.Scan(&z.ID, &z.OrgID, &z.SiteID, &z.CameraID, &z.Name, &z.Polygon, &z.Color, &z.ZoneKind, &z.BehaviorConfig, &z.IsActive, &z.CreatedAt, &z.UpdatedAt); err != nil {
			continue
		}
		list = append(list, z)
	}
	return list, rows.Err()
}

func (s *SyncService) evidenceAggregateForCamera(ctx context.Context, orgID, cameraID uuid.UUID) EvidenceAggregate {
	return CompileEvidenceAggregate(ctx, s.pool, orgID, cameraID)
}

func isVirtualCamera(meta json.RawMessage) bool {
	var m map[string]interface{}
	_ = json.Unmarshal(meta, &m)
	if m == nil {
		return false
	}
	if v, _ := m["virtual"].(bool); v {
		return true
	}
	if src, _ := m["go2rtc_src"].(string); src == "benedicte" {
		return true
	}
	return false
}

func isDemoGo2rtcCamera(meta json.RawMessage) bool {
	var m map[string]interface{}
	_ = json.Unmarshal(meta, &m)
	if m == nil {
		return false
	}
	demo, _ := m["demo"].(bool)
	if !demo {
		return false
	}
	if src, _ := m["go2rtc_src"].(string); strings.TrimSpace(src) != "" {
		return true
	}
	// Virtual demo cameras are backed by org_demo_videos even when onboard stripped go2rtc_src.
	if vid, _ := m["demo_video_id"].(string); strings.TrimSpace(vid) != "" {
		return true
	}
	return false
}

func probeStreamStats(ctx context.Context, rtspURL string) *camera.StreamStats {
	// Independent short timeout: parent rebuild ctx must not block on one offline RTSP.
	probeCtx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	stats, err := camera.ProbeStreamStats(probeCtx, rtspURL)
	if err != nil {
		return nil
	}
	return stats
}

// CompileEvidenceAggregate derives Frigate record/snapshots/lpr from alert rules.
// DetectEnabled follows currently enabled rules only.
// In FRIGATE_DEMO_MODE, LPR/record/snapshots/track capabilities also come from
// disabled rules on the camera so a later enable can hot-path via MQTT detect
// without requiring a Frigate reload to turn LPR/zones on.
func CompileEvidenceAggregate(ctx context.Context, pool *pgxpool.Pool, orgID, cameraID uuid.UUID) EvidenceAggregate {
	var agg EvidenceAggregate
	camStr := cameraID.String()
	demoCaps := ConfigFromEnv().DemoMode
	q := `SELECT definition, is_enabled FROM rules WHERE org_id = $1`
	if !demoCaps {
		q = `SELECT definition, TRUE FROM rules WHERE org_id = $1 AND is_enabled = TRUE`
	}
	rows, err := pool.Query(ctx, q, orgID)
	if err != nil {
		return agg
	}
	defer rows.Close()
	for rows.Next() {
		var defRaw []byte
		var enabled bool
		if err := rows.Scan(&defRaw, &enabled); err != nil {
			continue
		}
		var def map[string]interface{}
		if err := json.Unmarshal(defRaw, &def); err != nil {
			continue
		}
		if !ingest.RuleAppliesToCamera(def, camStr) {
			continue
		}
		// Any enabled rule on this camera needs Frigate detect (incl. observation/count).
		if enabled {
			agg.DetectEnabled = true
		}
		if bindings, ok := def["bindings"].(map[string]interface{}); ok {
			if v, ok := bindings["observation_mode"].(bool); ok && v {
				continue
			}
		}
		// Face watchlist / face identity rules require Frigate person tracking.
		rawLower := strings.ToLower(string(defRaw))
		if strings.Contains(rawLower, "face_watchlist") || strings.Contains(rawLower, "tpl-face-watchlist") ||
			strings.Contains(rawLower, "face_detected") || strings.Contains(rawLower, "tpl-face-") {
			agg.TrackPerson = true
		}
		if ruleNeedsObjectSurveillance(def, rawLower) {
			agg.TrackObjects = mergeTrackObjectLabels(agg.TrackObjects, ObjectSurveillanceLabels)
		}
		if ruleNeedsWrongWayVehicles(def, rawLower) {
			agg.TrackObjects = mergeTrackObjectLabels(agg.TrackObjects, []string{"car", "truck", "bus", "motorcycle", "van"})
		}
		// Rule personalization: class_filter / track_objects → Frigate objects.track.
		person, extras := trackLabelsFromRuleDefinition(def)
		if person {
			agg.TrackPerson = true
		}
		if len(extras) > 0 {
			agg.TrackObjects = mergeTrackObjectLabels(agg.TrackObjects, extras)
		}
		if !ruleHasAlertAction(def) {
			continue
		}
		ev := mergeEvidencePolicy(def)
		if en, _ := ev["enabled"].(bool); !en {
			continue
		}
		clipSec := 0.0
		switch v := ev["clip_seconds"].(type) {
		case float64:
			clipSec = v
		case int:
			clipSec = float64(v)
		}
		if clipSec > 0 {
			agg.RecordEnabled = true
		}
		if imgs, ok := ev["images"].([]interface{}); ok {
			for _, im := range imgs {
				m, ok := im.(map[string]interface{})
				if !ok {
					continue
				}
				role, _ := m["role"].(string)
				if role == "scene" || role == "subject" {
					agg.SnapshotsEnabled = true
				}
				if role == "plate" {
					agg.LPREnabled = true
				}
			}
		}
	}
	return agg
}

func ruleNeedsWrongWayVehicles(def map[string]interface{}, rawLower string) bool {
	markers := []string{"wrong_way", "tpl-wrong-way"}
	for _, m := range markers {
		if strings.Contains(rawLower, m) {
			return true
		}
	}
	if bindings, ok := def["bindings"].(map[string]interface{}); ok {
		tid := strings.ToLower(strings.TrimSpace(fmt.Sprint(bindings["template_id"])))
		if tid == "tpl-wrong-way" {
			return true
		}
	}
	return false
}

func ruleNeedsObjectSurveillance(def map[string]interface{}, rawLower string) bool {
	markers := []string{
		"object_abandoned", "abandoned_object", "object_removed", "object_disappeared",
		"tpl-abandoned-object", "tpl-object-removed", "tpl-object-disappeared",
	}
	for _, m := range markers {
		if strings.Contains(rawLower, m) {
			return true
		}
	}
	if bindings, ok := def["bindings"].(map[string]interface{}); ok {
		tid := strings.ToLower(strings.TrimSpace(fmt.Sprint(bindings["template_id"])))
		switch tid {
		case "tpl-abandoned-object", "tpl-object-removed", "tpl-object-disappeared":
			return true
		}
	}
	return false
}

// trackLabelsFromRuleDefinition extracts Frigate track labels from bindings.class_filter
// and bindings.track_objects (and nested condition matches_class leaves).
func trackLabelsFromRuleDefinition(def map[string]interface{}) (trackPerson bool, labels []string) {
	var raw []string
	if bindings, ok := def["bindings"].(map[string]interface{}); ok {
		raw = append(raw, stringLabelsFromAny(bindings["class_filter"])...)
		raw = append(raw, stringLabelsFromAny(bindings["track_objects"])...)
		raw = append(raw, stringLabelsFromAny(bindings["class_name"])...)
	}
	collectMatchesClassLabels(def["condition"], &raw)
	for _, et := range collectMemberEventTypes(def["condition"]) {
		raw = append(raw, trackHintsFromEventType(et)...)
	}
	for _, lab := range raw {
		lab = strings.ToLower(strings.TrimSpace(lab))
		if lab == "" || lab == "any" || lab == "*" {
			continue
		}
		if lab == "motorbike" {
			lab = "motorcycle"
		}
		switch lab {
		case "person", "people", "pedestrian":
			trackPerson = true
		case "vehicle", "vehicles":
			labels = mergeTrackObjectLabels(labels, []string{"car", "truck", "bus", "motorcycle", "van"})
		case "bag", "bags", "package":
			labels = mergeTrackObjectLabels(labels, []string{"backpack", "handbag", "suitcase"})
		default:
			labels = mergeTrackObjectLabels(labels, []string{lab})
		}
	}
	return trackPerson, labels
}

func collectMemberEventTypes(node interface{}) []string {
	m, ok := node.(map[string]interface{})
	if !ok {
		return nil
	}
	var out []string
	seen := map[string]struct{}{}
	add := func(s string) {
		s = strings.ToLower(strings.TrimSpace(s))
		if s == "" {
			return
		}
		if _, ok := seen[s]; ok {
			return
		}
		seen[s] = struct{}{}
		out = append(out, s)
	}
	for _, s := range stringLabelsFromAny(m["member_event_types"]) {
		add(s)
	}
	if field, _ := m["field"].(string); field == "event_type" {
		add(fmt.Sprint(m["value"]))
	}
	for _, key := range []string{"and", "or", "args", "children", "conditions"} {
		if arr, ok := m[key].([]interface{}); ok {
			for _, child := range arr {
				for _, s := range collectMemberEventTypes(child) {
					add(s)
				}
			}
		}
	}
	if inner, ok := m["condition"]; ok {
		for _, s := range collectMemberEventTypes(inner) {
			add(s)
		}
	}
	return out
}

func trackHintsFromEventType(et string) []string {
	et = strings.ToLower(strings.TrimSpace(et))
	switch {
	case strings.Contains(et, "face"), strings.Contains(et, "person"), strings.Contains(et, "loiter"),
		strings.Contains(et, "crowd"), et == "zone_enter", et == "zone_exit", et == "zone_presence",
		et == "perimeter_breach", et == "unauthorized_exit":
		return []string{"person"}
	case strings.Contains(et, "plate"), strings.Contains(et, "speed"), strings.Contains(et, "vehicle"),
		et == "wrong_way", et == "red_light_violation", et == "line_cross", et == "congestion",
		et == "vehicle_stopped", et == "vehicle_count_threshold":
		return []string{"car", "truck", "bus", "motorcycle", "van"}
	case strings.Contains(et, "abandon"), strings.Contains(et, "object_"):
		return []string{"backpack", "handbag", "suitcase"}
	default:
		return nil
	}
}

func stringLabelsFromAny(v interface{}) []string {
	switch t := v.(type) {
	case string:
		parts := strings.Split(t, ",")
		out := make([]string, 0, len(parts))
		for _, p := range parts {
			p = strings.TrimSpace(p)
			if p != "" {
				out = append(out, p)
			}
		}
		return out
	case []interface{}:
		out := make([]string, 0, len(t))
		for _, item := range t {
			s := strings.TrimSpace(fmt.Sprint(item))
			if s != "" && s != "<nil>" {
				out = append(out, s)
			}
		}
		return out
	case []string:
		return t
	default:
		return nil
	}
}

func collectMatchesClassLabels(node interface{}, out *[]string) {
	m, ok := node.(map[string]interface{})
	if !ok {
		return
	}
	if op, _ := m["op"].(string); strings.EqualFold(op, "matches_class") {
		*out = append(*out, stringLabelsFromAny(m["value"])...)
		*out = append(*out, stringLabelsFromAny(m["class"])...)
	}
	if field, _ := m["field"].(string); field == "class_name" || field == "class_filter" {
		*out = append(*out, stringLabelsFromAny(m["value"])...)
	}
	for _, key := range []string{"and", "or", "args", "children", "conditions"} {
		if arr, ok := m[key].([]interface{}); ok {
			for _, child := range arr {
				collectMatchesClassLabels(child, out)
			}
		}
	}
	if inner, ok := m["condition"]; ok {
		collectMatchesClassLabels(inner, out)
	}
}

func mergeTrackObjectLabels(dst, add []string) []string {
	seen := map[string]struct{}{}
	var out []string
	for _, lab := range dst {
		lab = strings.ToLower(strings.TrimSpace(lab))
		if lab == "" {
			continue
		}
		if _, ok := seen[lab]; ok {
			continue
		}
		seen[lab] = struct{}{}
		out = append(out, lab)
	}
	for _, lab := range add {
		lab = strings.ToLower(strings.TrimSpace(lab))
		if lab == "" {
			continue
		}
		if lab == "motorbike" {
			lab = "motorcycle"
		}
		if _, ok := seen[lab]; ok {
			continue
		}
		seen[lab] = struct{}{}
		out = append(out, lab)
	}
	return out
}

func ruleHasAlertAction(def map[string]interface{}) bool {
	actions, ok := def["actions"].([]interface{})
	if !ok {
		return false
	}
	for _, a := range actions {
		m, ok := a.(map[string]interface{})
		if !ok {
			continue
		}
		if t, _ := m["type"].(string); t == "alert" {
			return true
		}
	}
	return false
}

func mergeEvidencePolicy(def map[string]interface{}) map[string]interface{} {
	out := map[string]interface{}{
		"enabled":      true,
		"clip_seconds": 6,
	}
	raw, ok := def["evidence"].(map[string]interface{})
	if !ok {
		return out
	}
	for k, v := range raw {
		out[k] = v
	}
	return out
}

// YoungestEventAgeSec returns age in seconds of the newest Frigate event across active cameras.
func (s *SyncService) YoungestEventAgeSec(ctx context.Context) (float64, bool) {
	if s == nil || !s.cfg.Enabled {
		return 0, false
	}
	rows, err := s.pool.Query(ctx, `SELECT id FROM cameras WHERE is_active = true LIMIT 20`)
	if err != nil {
		return 0, false
	}
	defer rows.Close()
	bestAge := -1.0
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			continue
		}
		age, ok := s.youngestForCamera(ctx, CameraID(id.String()))
		if !ok {
			continue
		}
		if bestAge < 0 || age < bestAge {
			bestAge = age
		}
	}
	if bestAge < 0 {
		return 0, false
	}
	return bestAge, true
}

// WaitFresh blocks until a Frigate event younger than maxAgeSec appears or timeout.
func (s *SyncService) WaitFresh(ctx context.Context, cameraID string, maxAgeSec float64) error {
	if s == nil || !s.cfg.Enabled {
		return nil
	}
	fid := CameraID(cameraID)
	deadline := time.Now().Add(35 * time.Second)
	for time.Now().Before(deadline) {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}
		age, ok := s.youngestForCamera(ctx, fid)
		if ok && age <= maxAgeSec {
			return nil
		}
		time.Sleep(2 * time.Second)
	}
	return fmt.Errorf("frigate not fresh for %s", fid)
}

func (s *SyncService) youngestForCamera(ctx context.Context, frigateID string) (float64, bool) {
	events, err := s.client.ListEvents(ctx, frigateID, 3)
	if err != nil || len(events) == 0 {
		return 0, false
	}
	now := float64(time.Now().Unix())
	ts := eventStartTime(events[0])
	if ts <= 0 {
		return 0, false
	}
	age := now - ts
	if age < 0 {
		age = 0
	}
	return age, true
}

func eventStartTime(ev map[string]interface{}) float64 {
	for _, key := range []string{"start_time", "startTime"} {
		if v, ok := ev[key]; ok {
			switch t := v.(type) {
			case float64:
				return t
			case int:
				return float64(t)
			}
		}
	}
	return 0
}
