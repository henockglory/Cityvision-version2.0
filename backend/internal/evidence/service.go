package evidence

import (
	"context"
	"fmt"
	"io"
	"net/url"
	"os"
	"path"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type Config struct {
	Endpoint  string
	AccessKey string
	SecretKey string
	Bucket    string
	UseSSL    bool
	APIBase   string // e.g. http://localhost:8081/api/v1
}

func ConfigFromEnv() Config {
	useSSL := strings.EqualFold(os.Getenv("MINIO_USE_SSL"), "true")
	rawEndpoint := strings.TrimSpace(os.Getenv("MINIO_ENDPOINT"))
	if strings.HasPrefix(strings.ToLower(rawEndpoint), "https://") {
		useSSL = true
	}
	endpoint := normalizeMinIOEndpoint(rawEndpoint)
	if endpoint == "" {
		host := os.Getenv("MINIO_HOST")
		if host == "" {
			host = "localhost"
		}
		port := os.Getenv("MINIO_PORT")
		if port == "" {
			port = "9000"
		}
		endpoint = host + ":" + port
	}
	apiBase := os.Getenv("PUBLIC_API_BASE")
	if apiBase == "" {
		port := os.Getenv("API_PORT")
		if port == "" {
			port = "8081"
		}
		apiBase = "http://localhost:" + port + "/api/v1"
	}
	return Config{
		Endpoint:  endpoint,
		AccessKey: os.Getenv("MINIO_ACCESS_KEY"),
		SecretKey: os.Getenv("MINIO_SECRET_KEY"),
		Bucket:    getenv("MINIO_BUCKET", "citevision-evidence"),
		UseSSL:    useSSL,
		APIBase:   strings.TrimRight(apiBase, "/"),
	}
}

type Service struct {
	client *minio.Client
	cfg    Config
}

func NewService(cfg Config) (*Service, error) {
	if cfg.AccessKey == "" || cfg.SecretKey == "" {
		return &Service{cfg: cfg}, nil
	}
	client, err := minio.New(cfg.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.AccessKey, cfg.SecretKey, ""),
		Secure: cfg.UseSSL,
	})
	if err != nil {
		return nil, err
	}
	return &Service{client: client, cfg: cfg}, nil
}

func (s *Service) Available() bool {
	return s != nil && s.client != nil
}

type UploadInput struct {
	OrgID     uuid.UUID
	CameraID  string
	EventID   string
	Clip      io.Reader
	ClipSize  int64
	Scene     io.Reader
	SceneSize int64
	Subject   io.Reader
	SubjectSz int64
	Metadata  map[string]interface{}
}

func objectPrefix(orgID uuid.UUID, cameraID, eventID string) string {
	day := time.Now().UTC().Format("2006-01-02")
	if eventID == "" {
		eventID = uuid.New().String()
	}
	return path.Join("orgs", orgID.String(), "cameras", cameraID, day, eventID)
}

func (s *Service) UploadPackage(ctx context.Context, in UploadInput) (*Package, error) {
	if !s.Available() {
		return nil, fmt.Errorf("minio not configured")
	}
	if in.CameraID == "" {
		return nil, fmt.Errorf("camera_id required")
	}
	prefix := objectPrefix(in.OrgID, in.CameraID, in.EventID)
	pkg := &Package{Version: 1, Metadata: in.Metadata}

	if in.Clip != nil && in.ClipSize > 0 {
		key := prefix + "/clip.mp4"
		if _, err := s.client.PutObject(ctx, s.cfg.Bucket, key, in.Clip, in.ClipSize, minio.PutObjectOptions{ContentType: "video/mp4"}); err != nil {
			return nil, fmt.Errorf("upload clip: %w", err)
		}
		pkg.Clip = &Clip{
			AssetID:     key,
			URL:         s.assetURL(in.OrgID, key),
			DurationSec: 6,
			Mime:        "video/mp4",
		}
	}
	if in.Scene != nil && in.SceneSize > 0 {
		key := prefix + "/scene.jpg"
		if _, err := s.client.PutObject(ctx, s.cfg.Bucket, key, in.Scene, in.SceneSize, minio.PutObjectOptions{ContentType: "image/jpeg"}); err != nil {
			return nil, fmt.Errorf("upload scene: %w", err)
		}
		pkg.Images = append(pkg.Images, Image{
			Role: "scene", AssetID: key, URL: s.assetURL(in.OrgID, key),
			Label: "Vue scène", Mime: "image/jpeg",
		})
	}
	if in.Subject != nil && in.SubjectSz > 0 {
		key := prefix + "/subject.jpg"
		if _, err := s.client.PutObject(ctx, s.cfg.Bucket, key, in.Subject, in.SubjectSz, minio.PutObjectOptions{ContentType: "image/jpeg"}); err != nil {
			return nil, fmt.Errorf("upload subject: %w", err)
		}
		img := Image{
			Role: "subject", AssetID: key, URL: s.assetURL(in.OrgID, key),
			Label: "Cible détectée", Mime: "image/jpeg",
		}
		if in.Metadata != nil {
			if bb, ok := in.Metadata["bbox"].(map[string]interface{}); ok {
				img.BBox = mapToBBox(bb)
			}
		}
		pkg.Images = append(pkg.Images, img)
	}
	return pkg, nil
}

func mapToBBox(m map[string]interface{}) *BBox {
	b := &BBox{}
	if v, ok := m["x"].(float64); ok {
		b.X = v
	}
	if v, ok := m["y"].(float64); ok {
		b.Y = v
	}
	if v, ok := m["width"].(float64); ok {
		b.Width = v
	}
	if v, ok := m["height"].(float64); ok {
		b.Height = v
	}
	return b
}

func (s *Service) assetURL(orgID uuid.UUID, objectKey string) string {
	return fmt.Sprintf("%s/orgs/%s/evidence/asset?key=%s", s.cfg.APIBase, orgID.String(), url.QueryEscape(objectKey))
}

func (s *Service) PresignedGet(ctx context.Context, objectKey string) (string, error) {
	if !s.Available() {
		return "", fmt.Errorf("minio not configured")
	}
	u, err := s.client.PresignedGetObject(ctx, s.cfg.Bucket, objectKey, time.Hour, nil)
	if err != nil {
		return "", err
	}
	return u.String(), nil
}

func (s *Service) GetObject(ctx context.Context, objectKey string) (*minio.Object, error) {
	if !s.Available() {
		return nil, fmt.Errorf("minio not configured")
	}
	return s.client.GetObject(ctx, s.cfg.Bucket, objectKey, minio.GetObjectOptions{})
}

func (s *Service) StatObject(ctx context.Context, objectKey string) (minio.ObjectInfo, error) {
	return s.client.StatObject(ctx, s.cfg.Bucket, objectKey, minio.StatObjectOptions{})
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

// normalizeMinIOEndpoint strips scheme/path from MINIO_ENDPOINT for minio-go (host:port only).
func normalizeMinIOEndpoint(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}
	if strings.Contains(raw, "://") {
		if u, err := url.Parse(raw); err == nil && u.Host != "" {
			return u.Host
		}
	}
	return strings.TrimPrefix(strings.TrimPrefix(raw, "https://"), "http://")
}
