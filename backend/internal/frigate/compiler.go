package frigate

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"go.yaml.in/yaml/v3"

	"github.com/citevision/citevision-v2/backend/internal/camera"
	"github.com/citevision/citevision-v2/backend/internal/models"
)

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
	Coordinates string `yaml:"coordinates"`
	Filters     struct {
		MinArea float64 `yaml:"min_area,omitempty"`
	} `yaml:"filters,omitempty"`
}

// EvidenceAggregate drives record/snapshots/lpr per camera from active rules.
type EvidenceAggregate struct {
	RecordEnabled    bool
	SnapshotsEnabled bool
	LPREnabled       bool
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
	base["go2rtc"] = go2rtc
	// Frigate 0.17+ requires global lpr.enabled when any camera has lpr.enabled.
	for _, entry := range camMap {
		if entry.LPR.Enabled {
			base["lpr"] = map[string]interface{}{"enabled": true}
			break
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
	entry.Detect.Enabled = true
	entry.Detect.FPS = 10
	if stats != nil && stats.Width > 0 && stats.Height > 0 {
		entry.Detect.Width = stats.Width
		entry.Detect.Height = stats.Height
	} else {
		entry.Detect.Width = 1280
		entry.Detect.Height = 720
	}
	entry.Objects.Track = []string{"car", "truck", "motorcycle", "bus", "van"}
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
			entry.Zones[ZoneID(z.ID.String())] = ZoneEntry{Coordinates: coords}
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
