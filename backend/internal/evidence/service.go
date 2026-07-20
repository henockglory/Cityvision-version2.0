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
	return Config{
		Endpoint:  endpoint,
		AccessKey: os.Getenv("MINIO_ACCESS_KEY"),
		SecretKey: os.Getenv("MINIO_SECRET_KEY"),
		Bucket:    getenv("MINIO_BUCKET", "citevision-evidence"),
		UseSSL:    useSSL,
		APIBase:   normalizeAPIBase(os.Getenv("PUBLIC_API_BASE")),
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
	Plate     io.Reader
	PlateSz   int64
	ExtraFrames []FrameUpload
	Metadata  map[string]interface{}
}

type FrameUpload struct {
	Role string
	Data io.Reader
	Size int64
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
		dur := 6.0
		if in.Metadata != nil {
			if v, ok := in.Metadata["clip_duration_sec"].(float64); ok && v > 0 {
				dur = v
			}
		}
		pkg.Clip = &Clip{
			AssetID:     key,
			URL:         s.assetURL(in.OrgID, key),
			DurationSec: dur,
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
			Label: labelFromMeta(in.Metadata, "scene", "Vue d'ensemble"), Mime: "image/jpeg",
		})
	}
	if in.Subject != nil && in.SubjectSz > 0 {
		key := prefix + "/subject.jpg"
		if _, err := s.client.PutObject(ctx, s.cfg.Bucket, key, in.Subject, in.SubjectSz, minio.PutObjectOptions{ContentType: "image/jpeg"}); err != nil {
			return nil, fmt.Errorf("upload subject: %w", err)
		}
		img := Image{
			Role: "subject", AssetID: key, URL: s.assetURL(in.OrgID, key),
			Label: labelFromMeta(in.Metadata, "subject", "Cible détectée"), Mime: "image/jpeg",
		}
		if in.Metadata != nil {
			if bb, ok := in.Metadata["bbox"].(map[string]interface{}); ok {
				img.BBox = mapToBBox(bb)
			}
		}
		pkg.Images = append(pkg.Images, img)
	}
	if in.Plate != nil && in.PlateSz > 0 {
		key := prefix + "/plate.jpg"
		if _, err := s.client.PutObject(ctx, s.cfg.Bucket, key, in.Plate, in.PlateSz, minio.PutObjectOptions{ContentType: "image/jpeg"}); err != nil {
			return nil, fmt.Errorf("upload plate: %w", err)
		}
		pkg.Images = append(pkg.Images, Image{
			Role: "plate", AssetID: key, URL: s.assetURL(in.OrgID, key),
			Label: labelFromMeta(in.Metadata, "plate", "Plaque"), Mime: "image/jpeg",
		})
	}
	for _, fr := range in.ExtraFrames {
		if fr.Data == nil || fr.Size <= 0 || fr.Role == "" {
			continue
		}
		key := prefix + "/" + fr.Role + ".jpg"
		if _, err := s.client.PutObject(ctx, s.cfg.Bucket, key, fr.Data, fr.Size, minio.PutObjectOptions{ContentType: "image/jpeg"}); err != nil {
			return nil, fmt.Errorf("upload %s: %w", fr.Role, err)
		}
		pkg.Images = append(pkg.Images, Image{
			Role: fr.Role, AssetID: key, URL: s.assetURL(in.OrgID, key),
			Label: labelFromMeta(in.Metadata, fr.Role, fr.Role), Mime: "image/jpeg",
		})
	}
	return pkg, nil
}

func mapToBBox(m map[string]interface{}) *BBox {
	if m == nil {
		return nil
	}
	b := &BBox{}
	if v, ok := toFloat64(m["x"]); ok {
		b.X = v
	}
	if v, ok := toFloat64(m["y"]); ok {
		b.Y = v
	}
	if v, ok := toFloat64(m["width"]); ok {
		b.Width = v
	}
	if v, ok := toFloat64(m["height"]); ok {
		b.Height = v
	}
	if b.Width <= 0 || b.Height <= 0 {
		return nil
	}
	return b
}

func toFloat64(v interface{}) (float64, bool) {
	switch n := v.(type) {
	case float64:
		return n, true
	case float32:
		return float64(n), true
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	default:
		return 0, false
	}
}

func labelFromMeta(meta map[string]interface{}, role, fallback string) string {
	if meta == nil {
		return fallback
	}
	if labels, ok := meta["image_labels"].(map[string]interface{}); ok {
		if lbl, ok := labels[role].(string); ok && lbl != "" {
			return lbl
		}
	}
	return fallback
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

// GetObjectBytes downloads a full object into memory along with its content type.
// Intended for small assets (e.g. JPEG proof images embedded inline in emails).
func (s *Service) GetObjectBytes(ctx context.Context, objectKey string) ([]byte, string, error) {
	if !s.Available() {
		return nil, "", fmt.Errorf("minio not configured")
	}
	stat, err := s.StatObject(ctx, objectKey)
	if err != nil {
		return nil, "", err
	}
	obj, err := s.GetObject(ctx, objectKey)
	if err != nil {
		return nil, "", err
	}
	defer obj.Close()
	data, err := io.ReadAll(obj)
	if err != nil {
		return nil, "", err
	}
	ct := stat.ContentType
	if ct == "" || ct == "application/octet-stream" {
		ct = contentTypeForKeyEv(objectKey)
	}
	return data, ct, nil
}

func contentTypeForKeyEv(key string) string {
	lower := strings.ToLower(key)
	switch {
	case strings.HasSuffix(lower, ".jpg"), strings.HasSuffix(lower, ".jpeg"):
		return "image/jpeg"
	case strings.HasSuffix(lower, ".png"):
		return "image/png"
	case strings.HasSuffix(lower, ".mp4"):
		return "video/mp4"
	default:
		return "application/octet-stream"
	}
}

// PurgeOrg deletes all evidence objects for an organization from object storage.
func (s *Service) PurgeOrg(ctx context.Context, orgID uuid.UUID) (int, error) {
	if !s.Available() {
		return 0, nil
	}
	prefix := path.Join("orgs", orgID.String()) + "/"
	listCh := s.client.ListObjects(ctx, s.cfg.Bucket, minio.ListObjectsOptions{
		Prefix:    prefix,
		Recursive: true,
	})
	objectsCh := make(chan minio.ObjectInfo)
	go func() {
		defer close(objectsCh)
		for obj := range listCh {
			if obj.Err != nil {
				objectsCh <- minio.ObjectInfo{Err: obj.Err}
				return
			}
			if obj.Key != "" {
				objectsCh <- obj
			}
		}
	}()

	removed := 0
	for rmErr := range s.client.RemoveObjects(ctx, s.cfg.Bucket, objectsCh, minio.RemoveObjectsOptions{}) {
		if rmErr.Err != nil {
			return removed, rmErr.Err
		}
		removed++
	}
	return removed, nil
}

// PurgeDemoPrefix deletes demo-tagged evidence objects for an organization.
func (s *Service) PurgeDemoPrefix(ctx context.Context, orgID uuid.UUID) (int, error) {
	if !s.Available() {
		return 0, nil
	}
	prefix := path.Join("orgs", orgID.String(), "demo") + "/"
	listCh := s.client.ListObjects(ctx, s.cfg.Bucket, minio.ListObjectsOptions{
		Prefix:    prefix,
		Recursive: true,
	})
	removed := 0
	for obj := range listCh {
		if obj.Err != nil {
			return removed, obj.Err
		}
		if obj.Key != "" {
			_ = s.client.RemoveObject(ctx, s.cfg.Bucket, obj.Key, minio.RemoveObjectOptions{})
			removed++
		}
	}
	return removed, nil
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func normalizeAPIBase(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		port := os.Getenv("API_PORT")
		if port == "" {
			port = "8081"
		}
		raw = "http://localhost:" + port
	}
	raw = strings.TrimRight(raw, "/")
	if !strings.HasSuffix(raw, "/api/v1") {
		raw += "/api/v1"
	}
	return raw
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
