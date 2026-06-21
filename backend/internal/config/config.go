package config

import (
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	AppEnv   string
	AppName  string
	LogLevel string

	APIHost string
	APIPort int

	JWTSecret     string
	JWTAccessTTL  time.Duration
	JWTRefreshTTL time.Duration
	AuditSignKey  string

	PostgresURL string

	RedisURL      string
	RedisPassword string

	CameraCredentialKey string
	MinIOBucket         string

	AIEngineHost string
	AIEnginePort int

	InternalAPIKey string
	// CORSAllowedOrigins is the explicit allowlist of browser origins. Empty
	// means "dev defaults" (localhost). A single "*" entry allows any origin.
	CORSAllowedOrigins []string
	// WSAllowedOrigins restricts WebSocket upgrade origins. Empty reuses
	// CORSAllowedOrigins; "*" allows any.
	WSAllowedOrigins []string
}

func Load() (*Config, error) {
	cfg := &Config{
		AppEnv:   getEnv("APP_ENV", "development"),
		AppName:  getEnv("APP_NAME", "citevision-v2"),
		LogLevel: getEnv("LOG_LEVEL", "info"),

		APIHost: getEnv("API_HOST", "0.0.0.0"),
		APIPort: getEnvInt("API_PORT", 8081),

		JWTAccessTTL:  getEnvDuration("JWT_ACCESS_TTL", 15*time.Minute),
		JWTRefreshTTL: getEnvDuration("JWT_REFRESH_TTL", 168*time.Hour),

		RedisURL:      getEnv("REDIS_URL", fmt.Sprintf("redis://localhost:%d", getEnvInt("REDIS_PORT", 6379))),
		RedisPassword: getEnv("REDIS_PASSWORD", ""),

		MinIOBucket: getEnv("MINIO_BUCKET", "citevision-evidence"),

		AIEngineHost: getEnv("AI_ENGINE_HOST", "localhost"),
		AIEnginePort: getEnvInt("AI_ENGINE_PORT", 8001),
	}

	cfg.PostgresURL = resolvePostgresURL()
	cfg.JWTSecret = os.Getenv("JWT_SECRET")
	cfg.AuditSignKey = os.Getenv("AUDIT_SIGNING_KEY")
	cfg.CameraCredentialKey = os.Getenv("CAMERA_CREDENTIAL_KEY")
	cfg.InternalAPIKey = os.Getenv("INTERNAL_API_KEY")
	cfg.CORSAllowedOrigins = splitCSV(os.Getenv("CORS_ALLOWED_ORIGINS"))
	cfg.WSAllowedOrigins = splitCSV(os.Getenv("WS_ALLOWED_ORIGINS"))

	var missing []string
	if cfg.PostgresURL == "" {
		missing = append(missing, "POSTGRES_URL or (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB)")
	}
	if cfg.JWTSecret == "" {
		missing = append(missing, "JWT_SECRET")
	}
	if cfg.AuditSignKey == "" {
		missing = append(missing, "AUDIT_SIGNING_KEY")
	}
	if cfg.CameraCredentialKey == "" {
		missing = append(missing, "CAMERA_CREDENTIAL_KEY")
	}
	if cfg.InternalAPIKey == "" {
		missing = append(missing, "INTERNAL_API_KEY")
	}
	if len(missing) > 0 {
		return nil, fmt.Errorf("missing required environment variables: %s", strings.Join(missing, ", "))
	}

	if len(cfg.JWTSecret) < 16 {
		return nil, fmt.Errorf("JWT_SECRET must be at least 16 characters")
	}
	if len(cfg.CameraCredentialKey) < 32 {
		return nil, fmt.Errorf("CAMERA_CREDENTIAL_KEY must be at least 32 characters")
	}
	// Reject the shipped placeholder outside development so a real key is set.
	if cfg.AppEnv != "development" && cfg.InternalAPIKey == "changeme_internal_service_key" {
		return nil, fmt.Errorf("INTERNAL_API_KEY must be changed from the default placeholder in %s", cfg.AppEnv)
	}

	return cfg, nil
}

func splitCSV(v string) []string {
	if strings.TrimSpace(v) == "" {
		return nil
	}
	parts := strings.Split(v, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if s := strings.TrimSpace(p); s != "" {
			out = append(out, s)
		}
	}
	return out
}

func resolvePostgresURL() string {
	if u := os.Getenv("POSTGRES_URL"); u != "" {
		return u
	}
	user := os.Getenv("POSTGRES_USER")
	pass := os.Getenv("POSTGRES_PASSWORD")
	db := os.Getenv("POSTGRES_DB")
	if user == "" || pass == "" || db == "" {
		return ""
	}
	host := getEnv("POSTGRES_HOST", "localhost")
	port := getEnvInt("POSTGRES_PORT", 5432)
	sslmode := getEnv("POSTGRES_SSLMODE", "disable")
	return fmt.Sprintf("postgres://%s:%s@%s:%d/%s?sslmode=%s",
		url.PathEscape(user), url.PathEscape(pass), host, port, db, sslmode)
}

func (c *Config) Addr() string {
	return fmt.Sprintf("%s:%d", c.APIHost, c.APIPort)
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}

func getEnvDuration(key string, fallback time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return fallback
	}
	return d
}
