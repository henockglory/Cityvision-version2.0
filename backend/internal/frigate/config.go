package frigate

import (
	"os"
	"strconv"
)

// Config holds Frigate integration feature flags (all off by default).
type Config struct {
	Enabled      bool
	ConfigSync   bool
	Live         bool
	Evidence     bool
	Events       bool
	DemoMode     bool
	URL          string
	ConfigPath   string
	BaseYAML     string
	GeneratedDir string
	InputViaGo2RTC bool
	Go2RTCHost   string
	Go2RTCPort   int
}

func ConfigFromEnv() Config {
	return Config{
		Enabled:        envBool("FRIGATE_ENABLED", false),
		ConfigSync:     envBool("FRIGATE_CONFIG_SYNC", false),
		Live:           envBool("FRIGATE_LIVE", false),
		Evidence:       envBool("FRIGATE_EVIDENCE", false),
		Events:         envBool("FRIGATE_EVENTS", false),
		DemoMode:       envBool("FRIGATE_DEMO_MODE", true),
		URL:            envStr("FRIGATE_URL", "http://127.0.0.1:5000"),
		ConfigPath:     envStr("FRIGATE_CONFIG_PATH", "infra/frigate-config/config.yml"),
		BaseYAML:       envStr("FRIGATE_BASE_YAML", "infra/frigate.base.yaml"),
		GeneratedDir:   envStr("FRIGATE_GENERATED_DIR", "infra/frigate-config"),
		InputViaGo2RTC: envBool("FRIGATE_INPUT_VIA_GO2RTC", false),
		// Frigate runs with network_mode: host — Docker DNS names are unreachable; use loopback.
		Go2RTCHost:     envStr("FRIGATE_GO2RTC_HOST", "127.0.0.1"),
		Go2RTCPort:     envInt("FRIGATE_GO2RTC_PORT", 8554),
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

func envInt(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}
