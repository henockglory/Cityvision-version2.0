package frigate

import (
	"context"
	"encoding/json"
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

// RebuildAll regenerates config for every active camera eligible for Frigate
// (real RTSP cameras + demo virtual cameras fed by go2rtc).
func (s *SyncService) RebuildAll(ctx context.Context) error {
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
	for rows.Next() {
		var cam models.Camera
		if err := rows.Scan(&cam.ID, &cam.OrgID, &cam.SiteID, &cam.Name, &cam.Vendor, &cam.Host, &cam.Port,
			&cam.Channel, &cam.Username, &cam.RTSPPath, &cam.StreamProfile, &cam.Status,
			&cam.Metadata, &cam.IsActive, &cam.CreatedAt, &cam.UpdatedAt); err != nil {
			continue
		}
		if skipFrigateCamera(cam.Metadata) {
			continue
		}
		cc, err := s.compileCamera(ctx, &cam)
		if err != nil {
			s.log.Warn("frigate compile camera failed", "camera", cam.ID, "error", err)
			_ = s.setCameraFrigateError(ctx, cam.ID, err.Error())
			continue
		}
		compiled = append(compiled, cc)
		_ = s.setCameraFrigateOK(ctx, cam.ID, cc.FrigateID)
	}

	data, err := s.compiler.BuildConfig(compiled)
	if err != nil {
		s.lastError = err.Error()
		return err
	}
	if err := s.compiler.WriteGenerated(data); err != nil {
		s.lastError = err.Error()
		return err
	}
	if err := s.client.Reload(ctx); err != nil {
		s.lastError = err.Error()
		s.log.Warn("frigate reload failed", "error", err)
		return err
	}
	s.lastSync = time.Now().UTC()
	s.lastError = ""
	s.log.Info("frigate config rebuilt", "cameras", len(compiled))
	return nil
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
		if err := s.RebuildAll(ctx); err != nil {
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
		_ = s.RebuildAll(ctx)
	}()
}

func (s *SyncService) SyncAfterRuleChange(ctx context.Context, orgID uuid.UUID) {
	if !s.Enabled() {
		return
	}
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
		defer cancel()
		_ = s.RebuildAll(ctx)
	}()
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

// skipFrigateCamera excludes virtual cameras unless they are demo feeds on go2rtc.
func skipFrigateCamera(meta json.RawMessage) bool {
	if !isVirtualCamera(meta) {
		return false
	}
	return !isDemoGo2rtcCamera(meta)
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

// CompileEvidenceAggregate derives Frigate record/snapshots/lpr from active alert rules.
func CompileEvidenceAggregate(ctx context.Context, pool *pgxpool.Pool, orgID, cameraID uuid.UUID) EvidenceAggregate {
	var agg EvidenceAggregate
	camStr := cameraID.String()
	rows, err := pool.Query(ctx, `
		SELECT definition FROM rules WHERE org_id = $1 AND is_enabled = TRUE`, orgID)
	if err != nil {
		return agg
	}
	defer rows.Close()
	for rows.Next() {
		var defRaw []byte
		if err := rows.Scan(&defRaw); err != nil {
			continue
		}
		var def map[string]interface{}
		if err := json.Unmarshal(defRaw, &def); err != nil {
			continue
		}
		if bindings, ok := def["bindings"].(map[string]interface{}); ok {
			if v, ok := bindings["observation_mode"].(bool); ok && v {
				continue
			}
		}
		if !ingest.RuleAppliesToCamera(def, camStr) {
			continue
		}
		if !ruleHasAlertAction(def) {
			continue
		}
		ev := mergeEvidencePolicy(def)
		if enabled, _ := ev["enabled"].(bool); !enabled {
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
