package frigate

import (
	"os"
	"strconv"
)

// Config holds Frigate integration feature flags (all off by default).
type Config struct {
	Enabled     bool
	ConfigSync  bool
	Live        bool
	Evidence    bool
	Events      bool
	URL         string
	ConfigPath  string
	BaseYAML    string
	GeneratedDir string
}

func ConfigFromEnv() Config {
	return Config{
		Enabled:      envBool("FRIGATE_ENABLED", false),
		ConfigSync:   envBool("FRIGATE_CONFIG_SYNC", false),
		Live:         envBool("FRIGATE_LIVE", false),
		Evidence:     envBool("FRIGATE_EVIDENCE", false),
		Events:       envBool("FRIGATE_EVENTS", false),
		URL:          envStr("FRIGATE_URL", "http://127.0.0.1:5000"),
		ConfigPath:   envStr("FRIGATE_CONFIG_PATH", "infra/frigate-config/config.yml"),
		BaseYAML:     envStr("FRIGATE_BASE_YAML", "infra/frigate.base.yaml"),
		GeneratedDir: envStr("FRIGATE_GENERATED_DIR", "infra/frigate-config"),
	}
}

func (c Config) SyncEnabled() bool {
	return c.Enabled && c.ConfigSync
}

func CameraID(cameraUUID string) string {
	return "cv_" + cameraUUID
}

func ZoneID(zoneUUID string) string {
	return "cv_zone_" + zoneUUID
}

func envBool(key string, def bool) bool {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	b, err := strconv.ParseBool(v)
	if err != nil {
		return def
	}
	return b
}

func envStr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
