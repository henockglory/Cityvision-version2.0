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
			Path  string   `yaml:"path"`
			Roles []string `yaml:"roles"`
		} `yaml:"inputs"`
	} `yaml:"ffmpeg"`
	Detect struct {
		Enabled bool `yaml:"enabled"`
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
	for _, cam := range cameras {
		camMap[cam.FrigateID] = cam.Entry
	}
	base["cameras"] = camMap
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
	FrigateID string
	CameraID  string
	OrgID     string
	Entry     CameraEntry
}

// UpsertCamera builds a Frigate camera entry from CitéVision camera + RTSP URL.
func UpsertCamera(cam *models.Camera, rtspURL string, stats *camera.StreamStats, agg EvidenceAggregate, zones []models.Zone) CompiledCamera {
	fid := CameraID(cam.ID.String())
	entry := CameraEntry{}
	entry.Detect.Enabled = true
	entry.Record.Enabled = agg.RecordEnabled
	entry.Snapshots.Enabled = agg.SnapshotsEnabled
	entry.LPR.Enabled = agg.LPREnabled
	src := rtspURL
	if stats != nil {
		src = camera.Go2RTCSourceForRTSP(rtspURL, stats)
	}
	roles := []string{"detect"}
	if agg.RecordEnabled {
		roles = append(roles, "record")
	}
	entry.FFmpeg.Inputs = []struct {
		Path  string   `yaml:"path"`
		Roles []string `yaml:"roles"`
	}{
		{Path: src, Roles: roles},
	}
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
		FrigateID: fid,
		CameraID:  cam.ID.String(),
		OrgID:     cam.OrgID.String(),
		Entry:     entry,
	}
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
