package demo

import (
	"context"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

const DemoVideosBucket = "demo-videos"

type MinioStore struct {
	client *minio.Client
}

func NewMinioStore() (*MinioStore, error) {
	accessKey := os.Getenv("MINIO_ACCESS_KEY")
	secretKey := os.Getenv("MINIO_SECRET_KEY")
	if accessKey == "" || secretKey == "" {
		return &MinioStore{}, nil
	}
	endpoint := normalizeEndpoint(os.Getenv("MINIO_ENDPOINT"))
	if endpoint == "" {
		host := getenv("MINIO_HOST", "localhost")
		port := getenv("MINIO_PORT", "9000")
		endpoint = host + ":" + port
	}
	useSSL := strings.EqualFold(os.Getenv("MINIO_USE_SSL"), "true")
	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(accessKey, secretKey, ""),
		Secure: useSSL,
	})
	if err != nil {
		return nil, err
	}
	return &MinioStore{client: client}, nil
}

func (m *MinioStore) Available() bool {
	return m != nil && m.client != nil
}

func (m *MinioStore) EnsureBucket(ctx context.Context) error {
	if !m.Available() {
		return fmt.Errorf("minio unavailable")
	}
	exists, err := m.client.BucketExists(ctx, DemoVideosBucket)
	if err != nil {
		return err
	}
	if !exists {
		return m.client.MakeBucket(ctx, DemoVideosBucket, minio.MakeBucketOptions{})
	}
	return nil
}

func (m *MinioStore) Put(ctx context.Context, key string, r io.Reader, size int64, contentType string) error {
	if !m.Available() {
		return fmt.Errorf("minio unavailable")
	}
	if err := m.EnsureBucket(ctx); err != nil {
		return err
	}
	_, err := m.client.PutObject(ctx, DemoVideosBucket, key, r, size, minio.PutObjectOptions{ContentType: contentType})
	return err
}

func (m *MinioStore) Get(ctx context.Context, key, destPath string) error {
	if !m.Available() {
		return fmt.Errorf("minio unavailable")
	}
	obj, err := m.client.GetObject(ctx, DemoVideosBucket, key, minio.GetObjectOptions{})
	if err != nil {
		return err
	}
	defer obj.Close()
	f, err := os.Create(destPath)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = io.Copy(f, obj)
	return err
}

func (m *MinioStore) Remove(ctx context.Context, keys ...string) error {
	if !m.Available() {
		return nil
	}
	for _, key := range keys {
		if key == "" {
			continue
		}
		_ = m.client.RemoveObject(ctx, DemoVideosBucket, key, minio.RemoveObjectOptions{})
	}
	return nil
}

func (m *MinioStore) RemovePrefix(ctx context.Context, prefix string) (int, error) {
	if !m.Available() {
		return 0, nil
	}
	ch := m.client.ListObjects(ctx, DemoVideosBucket, minio.ListObjectsOptions{Prefix: prefix, Recursive: true})
	n := 0
	for obj := range ch {
		if obj.Err != nil {
			continue
		}
		_ = m.client.RemoveObject(ctx, DemoVideosBucket, obj.Key, minio.RemoveObjectOptions{})
		n++
	}
	return n, nil
}

func normalizeEndpoint(raw string) string {
	raw = strings.TrimSpace(raw)
	raw = strings.TrimPrefix(raw, "https://")
	raw = strings.TrimPrefix(raw, "http://")
	if i := strings.Index(raw, "/"); i >= 0 {
		raw = raw[:i]
	}
	return raw
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
