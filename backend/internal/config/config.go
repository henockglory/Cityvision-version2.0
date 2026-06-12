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

	SeedAdminEmail    string
	SeedAdminPassword string
	SeedTenantName    string
	SeedTenantSlug    string

	PostgresURL string

	RedisURL      string
	RedisPassword string

	MQTTBroker   string
	MQTTClientID string
	MQTTUsername string
	MQTTPassword string

	AIEngineHost          string
	AIEnginePort          int
	AIModelPath           string
	AIConfidenceThreshold float64
	VideoEngineHost       string
	VideoEnginePort       int
	RecordingsPath        string
	CameraCredentialKey   string
	SMTPHost              string
	SMTPPort              int
	SMTPUser              string
	SMTPPassword          string
	SMTPFrom              string
	SMSWebhookURL         string
	MaxCameras            int
	NightModeStart        int
	NightModeEnd          int
	MinIOEndpoint         string
	MinIOAccessKey        string
	MinIOSecretKey        string
	MinIOBucket           string
	MinIOUseSSL           bool
}

func Load() (*Config, error) {
	cfg := &Config{
		AppEnv:   getEnv("APP_ENV", "development"),
		AppName:  getEnv("APP_NAME", "citevision"),
		LogLevel: getEnv("LOG_LEVEL", "info"),

		APIHost: getEnv("API_HOST", "0.0.0.0"),
		APIPort: getEnvInt("API_PORT", 8080),

		JWTAccessTTL:  getEnvDuration("JWT_ACCESS_TTL", 15*time.Minute),
		JWTRefreshTTL: getEnvDuration("JWT_REFRESH_TTL", 168*time.Hour),

		SeedAdminEmail:    getEnv("SEED_ADMIN_EMAIL", ""),
		SeedAdminPassword: getEnv("SEED_ADMIN_PASSWORD", ""),
		SeedTenantName:    getEnv("SEED_TENANT_NAME", "Citevision Demo"),
		SeedTenantSlug:    getEnv("SEED_TENANT_SLUG", "demo"),

		RedisURL:      getEnv("REDIS_URL", fmt.Sprintf("redis://localhost:%d", getEnvInt("REDIS_PORT", 6379))),
		RedisPassword: getEnv("REDIS_PASSWORD", ""),

		MQTTClientID: getEnv("MQTT_CLIENT_ID", "citevision-backend"),
		MQTTUsername: getEnv("MQTT_USERNAME", ""),
		MQTTPassword: getEnv("MQTT_PASSWORD", ""),

		AIEngineHost:          getEnv("AI_ENGINE_HOST", "localhost"),
		AIEnginePort:          getEnvInt("AI_ENGINE_PORT", 8000),
		AIModelPath:           getEnv("CITEVISION_MODEL_PATH", getEnv("AI_MODEL_PATH", "models/yolov8n.onnx")),
		AIConfidenceThreshold: getEnvFloat("AI_CONFIDENCE_THRESHOLD", 0.5),
		VideoEngineHost:       getEnv("VIDEO_ENGINE_HOST", "localhost"),
		VideoEnginePort:       getEnvInt("CITEVISION_HEALTH_PORT", getEnvInt("VIDEO_ENGINE_PORT", 9010)),
		RecordingsPath:        getEnv("RECORDINGS_PATH", "data/recordings"),
		SMTPHost:              getEnv("SMTP_HOST", ""),
		SMTPPort:              getEnvInt("SMTP_PORT", 587),
		SMTPUser:              getEnv("SMTP_USER", ""),
		SMTPPassword:          getEnv("SMTP_PASSWORD", ""),
		SMTPFrom:              getEnv("SMTP_FROM", "noreply@citevision.local"),
		SMSWebhookURL:         getEnv("SMS_WEBHOOK_URL", ""),
		MaxCameras:            getEnvInt("MAX_CAMERAS", 12),
		NightModeStart:        getEnvInt("NIGHT_MODE_START", 22),
		NightModeEnd:          getEnvInt("NIGHT_MODE_END", 6),
		MinIOBucket:           getEnv("MINIO_BUCKET", "citevision-evidence"),
		MinIOUseSSL:           getEnvBool("MINIO_USE_SSL", false),
	}

	cfg.PostgresURL = resolvePostgresURL()
	cfg.JWTSecret = os.Getenv("JWT_SECRET")
	cfg.AuditSignKey = os.Getenv("AUDIT_SIGNING_KEY")
	cfg.CameraCredentialKey = os.Getenv("CAMERA_CREDENTIAL_KEY")

	cfg.MinIOEndpoint = resolveMinIOEndpoint()
	cfg.MinIOAccessKey = getEnv("MINIO_ACCESS_KEY", getEnv("MINIO_ROOT_USER", "citevision"))
	cfg.MinIOSecretKey = getEnv("MINIO_SECRET_KEY", getEnv("MINIO_ROOT_PASSWORD", ""))

	cfg.MQTTBroker = resolveMQTTBroker()

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
	if len(missing) > 0 {
		return nil, fmt.Errorf("missing required environment variables: %s", strings.Join(missing, ", "))
	}

	if len(cfg.JWTSecret) < 16 {
		return nil, fmt.Errorf("JWT_SECRET must be at least 16 characters")
	}
	if len(cfg.CameraCredentialKey) < 32 {
		return nil, fmt.Errorf("CAMERA_CREDENTIAL_KEY must be at least 32 characters")
	}

	return cfg, nil
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
	return fmt.Sprintf("postgres://%s:%s@%s:%d/%s?sslmode=disable",
		url.PathEscape(user), url.PathEscape(pass), host, port, db)
}

func resolveMinIOEndpoint() string {
	if ep := os.Getenv("MINIO_ENDPOINT"); ep != "" {
		return ep
	}
	host := getEnv("MINIO_HOST", "localhost")
	port := getEnvInt("MINIO_API_PORT", 9000)
	return fmt.Sprintf("%s:%d", host, port)
}

func resolveMQTTBroker() string {
	if b := os.Getenv("MQTT_BROKER"); b != "" {
		return b
	}
	host := getEnv("CITEVISION_MQTT_HOST", "localhost")
	port := getEnvInt("CITEVISION_MQTT_PORT", getEnvInt("MQTT_PORT", 1883))
	return fmt.Sprintf("tcp://%s:%d", host, port)
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

func getEnvFloat(key string, fallback float64) float64 {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	f, err := strconv.ParseFloat(v, 64)
	if err != nil {
		return fallback
	}
	return f
}

func getEnvBool(key string, fallback bool) bool {
	v := strings.ToLower(os.Getenv(key))
	if v == "" {
		return fallback
	}
	return v == "1" || v == "true" || v == "yes"
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
