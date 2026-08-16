package frigate

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"go.yaml.in/yaml/v3"

	"github.com/citevision/citevision-v2/backend/internal/camera"
	"github.com/citevision/citevision-v2/backend/internal/models"
)

// errConfigUnchanged means the generated YAML matches disk — skip Frigate reload.
var errConfigUnchanged = errors.New("frigate config unchanged")

// CameraEntry is the Frigate camera config block for one CitéVision camera.
type CameraEntry struct {
	FFmpeg struct {
		Inputs []struct {
			Path      string   `yaml:"path"`
			InputArgs string   `yaml:"input_args,omitempty"`
			Roles     []string `yaml:"roles"`
		} `yaml:"inputs"`
	} `yaml:"ffmpeg"`
	Detect struct {
		Enabled bool `yaml:"enabled"`
		Width   int  `yaml:"width,omitempty"`
		Height  int  `yaml:"height,omitempty"`
		FPS     int  `yaml:"fps,omitempty"`
	} `yaml:"detect"`
	Record struct {
		Enabled bool `yaml:"enabled"`
	} `yaml:"record"`
	Snapshots struct {
		Enabled bool `yaml:"enabled"`
	} `yaml:"snapshots"`
	LPR struct {
		Enabled bool `yaml:"enabled"`
	} `yaml:"lpr"`
	Objects struct {
		Track []string `yaml:"track,omitempty"`
	} `yaml:"objects,omitempty"`
	Live struct {
		Streams map[string]string `yaml:"streams,omitempty"`
	} `yaml:"live,omitempty"`
	Zones map[string]ZoneEntry `yaml:"zones,omitempty"`
}

type ZoneEntry struct {
	Coordinates    string  `yaml:"coordinates"`
	Distances      string  `yaml:"distances,omitempty"`
	SpeedThreshold float64 `yaml:"speed_threshold,omitempty"`
	Filters        struct {
		MinArea float64 `yaml:"min_area,omitempty"`
	} `yaml:"filters,omitempty"`
}

// ObjectSurveillanceLabels are additive Frigate objects.track labels for abandoned /
// removed / disappeared object rules (bags + a few useful classes). Never replaces vehicles.
var ObjectSurveillanceLabels = []string{
	"backpack", "handbag", "suitcase", "umbrella", "bicycle", "dog",
}

// EvidenceAggregate drives record/snapshots/lpr per camera from active rules.
type EvidenceAggregate struct {
	RecordEnabled    bool
	SnapshotsEnabled bool
	LPREnabled       bool
	// DetectEnabled is true when ≥1 enabled rule applies to this camera (incl. observation_mode).
	// Frigate detect is OFF for cameras without enabled rules so the detector focuses on active work.
	DetectEnabled bool
	// TrackPerson forces Frigate objects.track to include person (face watchlist / face rules).
	TrackPerson bool
	// TrackObjects merges extra Frigate objects.track labels (object surveillance).
	TrackObjects []string
}

// Compiler builds frigate.generated.yml from DB state.
type Compiler struct {
	cfg Config
}

func NewCompiler(cfg Config) *Compiler {
	return &Compiler{cfg: cfg}
}

func (c *Compiler) BuildConfig(
	cameras []CompiledCamera,
	faceRecognition bool,
) ([]byte, error) {
	base, err := c.loadBase()
	if err != nil {
		return nil, err
	}
	camMap := map[string]CameraEntry{}
	go2rtcStreams := map[string][]string{}
	for _, cam := range cameras {
		camMap[cam.FrigateID] = cam.Entry
		go2rtcStreams[cam.FrigateID] = []string{
			cam.UpstreamURL,
			fmt.Sprintf("ffmpeg:%s#audio=opus", cam.FrigateID),
		}
	}
	base["cameras"] = camMap
	go2rtc, _ := base["go2rtc"].(map[string]interface{})
	if go2rtc == nil {
		go2rtc = map[string]interface{}{}
	}
	go2rtc["streams"] = go2rtcStreams
	// Host-network Frigate must not steal demo go2rtc ports (1984/8554/8555).
	// Keep dedicated Frigate-embedded ports aligned with infra/frigate.base.yaml.
	go2rtc["api"] = map[string]interface{}{"listen": ":1985"}
	go2rtc["rtsp"] = map[string]interface{}{"listen": ":8557"}
	go2rtc["webrtc"] = map[string]interface{}{"listen": ":8556"}
	base["go2rtc"] = go2rtc
	// Frigate 0.17+ requires global lpr.enabled when any camera has lpr.enabled.
	for _, entry := range camMap {
		if entry.LPR.Enabled {
			base["lpr"] = map[string]interface{}{"enabled": true}
			break
		}
	}
	// Global face_recognition when CiteVision has face watchlist / face rules.
	// model_size=large prefers GPU/NPU (A.5); Frigate falls back internally if needed.
	if faceRecognition {
		modelSize := "large"
		if strings.EqualFold(os.Getenv("FRIGATE_FACE_MODEL_SIZE"), "small") {
			modelSize = "small"
		}
		base["face_recognition"] = map[string]interface{}{
			"enabled":    true,
			"model_size": modelSize,
		}
	}
	return yaml.Marshal(base)
}

func (c *Compiler) WriteGenerated(data []byte) error {
	dir := c.cfg.GeneratedDir
	if dir == "" {
		dir = filepath.Dir(c.cfg.ConfigPath)
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	target := c.cfg.ConfigPath
	if target == "" {
		target = filepath.Join(dir, "frigate.generated.yml")
	}
	if prev, err := os.ReadFile(target); err == nil && bytes.Equal(prev, data) {
		return errConfigUnchanged
	}
	tmp := target + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, target)
}

func (c *Compiler) loadBase() (map[string]interface{}, error) {
	path := c.cfg.BaseYAML
	if path == "" {
		path = "infra/frigate.base.yaml"
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read base yaml: %w", err)
	}
	var base map[string]interface{}
	if err := yaml.Unmarshal(raw, &base); err != nil {
		return nil, fmt.Errorf("parse base yaml: %w", err)
	}
	if base == nil {
		base = map[string]interface{}{}
	}
	return base, nil
}

// CompiledCamera pairs a Frigate camera id with its config entry.
type CompiledCamera struct {
	FrigateID   string
	CameraID    string
	OrgID       string
	UpstreamURL string
	Entry       CameraEntry
}

// UpsertCamera builds a Frigate camera entry from CitéVision camera + RTSP URL.
func UpsertCamera(cam *models.Camera, rtspURL string, stats *camera.StreamStats, agg EvidenceAggregate, zones []models.Zone) CompiledCamera {
	fid := CameraID(cam.ID.String())
	entry := CameraEntry{}
	// Focus Frigate detector on cameras that have enabled rules.
	entry.Detect.Enabled = agg.DetectEnabled
	entry.Detect.FPS = 10
	if stats != nil && stats.Width > 0 && stats.Height > 0 {
		entry.Detect.Width = stats.Width
		entry.Detect.Height = stats.Height
	} else {
		entry.Detect.Width = 1280
		entry.Detect.Height = 720
	}
	entry.Objects.Track = []string{"car", "truck", "motorcycle", "bus", "van"}
	needPerson := agg.TrackPerson
	trackExtra := map[string]struct{}{}
	entry.Record.Enabled = agg.RecordEnabled
	entry.Snapshots.Enabled = agg.SnapshotsEnabled
	entry.LPR.Enabled = agg.LPREnabled
	cfg := ConfigFromEnv()
	if cfg.Evidence && !cfg.DemoMode {
		entry.Snapshots.Enabled = true
		entry.Record.Enabled = true
	} else if cfg.Evidence && cfg.DemoMode {
		// Demo: snapshots on events only; record follows rule aggregate (event clips).
		entry.Snapshots.Enabled = agg.SnapshotsEnabled || agg.RecordEnabled
	}
	// Demo go2rtc: always keep snapshots; record ONLY when this camera has an
	// enabled rule (DetectEnabled). Recording all demo cams at once saturates
	// Frigate's record maintainer → discarded segments → clip.mp4 HTTP 400
	// ("No recordings found") even when has_clip=true. Clips fall back to go2rtc.
	if isDemoGo2rtcCamera(cam.Metadata) {
		entry.Snapshots.Enabled = true
		if agg.DetectEnabled {
			entry.Record.Enabled = true
		} else if strings.EqualFold(strings.TrimSpace(os.Getenv("DEMO_EVIDENCE_STRICT")), "1") ||
			strings.EqualFold(strings.TrimSpace(os.Getenv("DEMO_EVIDENCE_BACKEND")), "strict_frigate") {
			entry.Record.Enabled = false
		}
		// NOTE: do NOT set enabled:false in config — Frigate refuses MQTT
		// enabled/set ON for config-disabled cameras ("Camera must be enabled
		// in the config"). Idle cameras are stopped via MQTT enabled/set OFF
		// (detect gate), which frees the ffmpeg decode while staying wakeable.
	}
	upstream := frigateUpstreamPath(cam.ID.String(), rtspURL, cam.Metadata)
	roles := []string{"detect"}
	if entry.Record.Enabled {
		roles = append(roles, "record")
	}
	ffmpegPath := upstream
	inputArgs := ""
	if cfg.InputViaGo2RTC {
		ffmpegPath = frigateRestreamPath(fid)
		inputArgs = "preset-rtsp-restream"
	}
	entry.FFmpeg.Inputs = []struct {
		Path      string   `yaml:"path"`
		InputArgs string   `yaml:"input_args,omitempty"`
		Roles     []string `yaml:"roles"`
	}{
		{
			Path:      ffmpegPath,
			InputArgs: inputArgs,
			Roles:     roles,
		},
	}
	entry.Live.Streams = map[string]string{"Live": fid}
	if len(zones) > 0 {
		entry.Zones = map[string]ZoneEntry{}
		for _, z := range zones {
			if z.CameraID == nil || *z.CameraID != cam.ID {
				continue
			}
			coords := polygonToFrigateCoords(z.Polygon)
			if coords == "" {
				continue
			}
			ze := ZoneEntry{Coordinates: coords}
			behavior, cfgMap := parseZoneBehaviorConfig(z.BehaviorConfig, z.ZoneKind)
			if behaviorNeedsPerson(behavior) {
				needPerson = true
			}
			if behavior == "abandoned_object" {
				for _, lab := range ObjectSurveillanceLabels {
					trackExtra[lab] = struct{}{}
				}
			}
			for _, lab := range trackObjectsFromCfg(cfgMap) {
				trackExtra[lab] = struct{}{}
				if lab == "person" {
					needPerson = true
				}
			}
			if behavior == "speed_measurement" || behavior == "wrong_way" {
				if behavior == "speed_measurement" {
					if dists, ok := speedDistancesCSV(z.Polygon, cfgMap); ok {
						ze.Distances = dists
						ze.SpeedThreshold = 1
						if st := floatFromCfg(cfgMap, "frigate_speed_threshold"); st > 0 {
							ze.SpeedThreshold = st
						}
					}
				}
			}
			entry.Zones[ZoneID(z.ID.String())] = ze
		}
	}
	if needPerson {
		trackExtra["person"] = struct{}{}
	}
	for _, lab := range agg.TrackObjects {
		lab = strings.ToLower(strings.TrimSpace(lab))
		if lab == "" {
			continue
		}
		if lab == "motorbike" {
			lab = "motorcycle"
		}
		trackExtra[lab] = struct{}{}
	}
	if len(trackExtra) > 0 {
		seen := map[string]struct{}{}
		for _, lab := range entry.Objects.Track {
			seen[lab] = struct{}{}
		}
		for lab := range trackExtra {
			if _, ok := seen[lab]; ok {
				continue
			}
			entry.Objects.Track = append(entry.Objects.Track, lab)
			seen[lab] = struct{}{}
		}
	}
	return CompiledCamera{
		FrigateID:   fid,
		CameraID:    cam.ID.String(),
		OrgID:       cam.OrgID.String(),
		UpstreamURL: upstream,
		Entry:       entry,
	}
}

func frigateRestreamPath(frigateID string) string {
	return fmt.Sprintf("rtsp://127.0.0.1:8554/%s", frigateID)
}

// frigateUpstreamPath is the external source registered in go2rtc.streams (Docker-safe relay by default).
func frigateUpstreamPath(cameraUUID, rtspURL string, meta json.RawMessage) string {
	cfg := ConfigFromEnv()
	if demo := demoGo2rtcStreamName(meta, rtspURL); demo != "" {
		return fmt.Sprintf("rtsp://%s:%d/%s", cfg.Go2RTCHost, cfg.Go2RTCPort, demo)
	}
	if cfg.InputViaGo2RTC {
		return fmt.Sprintf("rtsp://%s:%d/cam-%s", cfg.Go2RTCHost, cfg.Go2RTCPort, cameraUUID)
	}
	return rtspURL
}

// demoGo2rtcStreamName resolves the looped demo file stream (demo-{org}-{video}) for Frigate/go2rtc.
func demoGo2rtcStreamName(meta json.RawMessage, rtspURL string) string {
	var m map[string]interface{}
	_ = json.Unmarshal(meta, &m)
	if m != nil {
		if src, _ := m["go2rtc_src"].(string); strings.TrimSpace(src) != "" {
			return strings.TrimSpace(src)
		}
	}
	path := rtspURL
	if i := strings.Index(path, "://"); i >= 0 {
		if j := strings.Index(path[i+3:], "/"); j >= 0 {
			path = path[i+3+j:]
		}
	}
	name := strings.TrimPrefix(path, "/")
	if strings.HasPrefix(name, "demo-") {
		return name
	}
	return ""
}

func polygonToFrigateCoords(polygon json.RawMessage) string {
	if len(polygon) == 0 {
		return ""
	}
	var pts []map[string]float64
	if err := json.Unmarshal(polygon, &pts); err != nil {
		var alt [][]float64
		if err2 := json.Unmarshal(polygon, &alt); err2 != nil {
			return ""
		}
		var parts []string
		for _, p := range alt {
			if len(p) >= 2 {
				parts = append(parts, fmt.Sprintf("%.4f,%.4f", p[0], p[1]))
			}
		}
		return strings.Join(parts, ",")
	}
	var parts []string
	for _, p := range pts {
		x, okX := p["x"]
		y, okY := p["y"]
		if okX && okY {
			parts = append(parts, fmt.Sprintf("%.4f,%.4f", x, y))
		}
	}
	return strings.Join(parts, ",")
}

func polygonPointCount(polygon json.RawMessage) int {
	if len(polygon) == 0 {
		return 0
	}
	var pts []map[string]float64
	if err := json.Unmarshal(polygon, &pts); err == nil {
		return len(pts)
	}
	var alt [][]float64
	if err := json.Unmarshal(polygon, &alt); err == nil {
		return len(alt)
	}
	return 0
}

// parseZoneBehaviorConfig mirrors ingest parseZoneBehavior for Frigate compile.
func parseZoneBehaviorConfig(raw json.RawMessage, zoneKind string) (string, map[string]interface{}) {
	cfg := map[string]interface{}{}
	behavior := ""
	if len(raw) > 0 {
		var parsed map[string]interface{}
		if err := json.Unmarshal(raw, &parsed); err == nil {
			if b, _ := parsed["behavior"].(string); b != "" {
				behavior = b
			}
			if c, ok := parsed["config"].(map[string]interface{}); ok {
				cfg = c
			}
		}
	}
	if behavior == "" {
		behavior = strings.TrimSpace(zoneKind)
	}
	return behavior, cfg
}

func behaviorNeedsPerson(behavior string) bool {
	switch behavior {
	case "seatbelt", "phone_use", "driver_cabin", "presence", "perimeter",
		"loitering", "controlled_exit", "parking":
		return true
	default:
		return false
	}
}

func floatFromCfg(cfg map[string]interface{}, key string) float64 {
	if cfg == nil {
		return 0
	}
	raw, ok := cfg[key]
	if !ok || raw == nil {
		return 0
	}
	switch v := raw.(type) {
	case float64:
		return v
	case json.Number:
		f, err := v.Float64()
		if err != nil {
			return 0
		}
		return f
	case int:
		return float64(v)
	case int64:
		return float64(v)
	case string:
		f, err := strconv.ParseFloat(strings.TrimSpace(v), 64)
		if err != nil {
			return 0
		}
		return f
	default:
		return 0
	}
}

// trackObjectsFromCfg reads optional behavior_config.config.track_objects
// (e.g. ["car","motorcycle","bus","person"]) for Frigate objects.track union.
func trackObjectsFromCfg(cfg map[string]interface{}) []string {
	if cfg == nil {
		return nil
	}
	raw, ok := cfg["track_objects"]
	if !ok || raw == nil {
		return nil
	}
	var out []string
	seen := map[string]struct{}{}
	add := func(s string) {
		lab := strings.ToLower(strings.TrimSpace(s))
		if lab == "" {
			return
		}
		if lab == "motorbike" {
			lab = "motorcycle"
		}
		if _, ok := seen[lab]; ok {
			return
		}
		seen[lab] = struct{}{}
		out = append(out, lab)
	}
	switch v := raw.(type) {
	case []interface{}:
		for _, item := range v {
			if s, ok := item.(string); ok {
				add(s)
			}
		}
	case []string:
		for _, s := range v {
			add(s)
		}
	case string:
		for _, part := range strings.Split(v, ",") {
			add(part)
		}
	}
	return out
}

// speedDistancesCSV returns Frigate distances CSV when polygon has exactly 4 points
// and edge_distances_m has 4 positive metres. Otherwise ok=false (no false speed sync).
func speedDistancesCSV(polygon json.RawMessage, cfg map[string]interface{}) (string, bool) {
	if polygonPointCount(polygon) != 4 {
		return "", false
	}
	raw, ok := cfg["edge_distances_m"]
	if !ok {
		return "", false
	}
	var nums []float64
	switch v := raw.(type) {
	case []interface{}:
		for _, item := range v {
			switch n := item.(type) {
			case float64:
				if n > 0 {
					nums = append(nums, n)
				}
			case json.Number:
				f, err := n.Float64()
				if err == nil && f > 0 {
					nums = append(nums, f)
				}
			}
		}
	}
	if len(nums) != 4 {
		return "", false
	}
	parts := make([]string, 4)
	for i, n := range nums {
		parts[i] = fmt.Sprintf("%.3f", n)
	}
	return strings.Join(parts, ","), true
}
