package camera

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/models"
)

var ErrNotFound = errors.New("camera not found")

type CreateRequest struct {
	OrgID         uuid.UUID           `json:"org_id"`
	SiteID        uuid.UUID           `json:"site_id"`
	Name          string              `json:"name"`
	Vendor        models.CameraVendor `json:"vendor"`
	Host          string              `json:"host"`
	Port          int                 `json:"port"`
	Channel       int                 `json:"channel"`
	Username      string              `json:"username"`
	Password      string              `json:"password"`
	RTSPPath      string              `json:"rtsp_path"`
	StreamProfile string              `json:"stream_profile"`
	Metadata      json.RawMessage     `json:"metadata"`
}

type UpdateRequest struct {
	Name          *string              `json:"name,omitempty"`
	Vendor        *models.CameraVendor `json:"vendor,omitempty"`
	Host          *string              `json:"host,omitempty"`
	Port          *int                 `json:"port,omitempty"`
	Channel       *int                 `json:"channel,omitempty"`
	Username      *string              `json:"username,omitempty"`
	Password      *string              `json:"password,omitempty"`
	RTSPPath      *string              `json:"rtsp_path,omitempty"`
	StreamProfile *string              `json:"stream_profile,omitempty"`
	IsActive      *bool                `json:"is_active,omitempty"`
	Metadata      json.RawMessage      `json:"metadata,omitempty"`
}

type Service struct {
	pool   *pgxpool.Pool
	cipher *CredentialCipher
}

func NewService(pool *pgxpool.Pool, cipher *CredentialCipher) *Service {
	return &Service{pool: pool, cipher: cipher}
}

func (s *Service) Create(ctx context.Context, req CreateRequest) (*models.Camera, error) {
	if req.Port == 0 {
		req.Port = 554
	}
	if req.Channel == 0 {
		req.Channel = 1
	}
	if req.StreamProfile == "" {
		req.StreamProfile = "main"
	}
	if req.Vendor == "" {
		req.Vendor = models.VendorGeneric
	}
	req.Host = NormalizeHost(req.Host)
	meta := req.Metadata
	if meta == nil {
		meta = json.RawMessage(`{}`)
	}

	var enc []byte
	var err error
	if req.Password != "" {
		enc, err = s.cipher.Encrypt(req.Password)
		if err != nil {
			return nil, err
		}
	}

	var username, rtspPath *string
	if req.Username != "" {
		username = &req.Username
	}
	if req.RTSPPath != "" {
		rtspPath = &req.RTSPPath
	}

	var cam models.Camera
	err = s.pool.QueryRow(ctx, `
		INSERT INTO cameras (org_id, site_id, name, vendor, host, port, channel, username, password_encrypted, rtsp_path, stream_profile, metadata)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
		RETURNING id, org_id, site_id, name, vendor, host(host), port, channel, username, rtsp_path, stream_profile, status, metadata, is_active, created_at, updated_at`,
		req.OrgID, req.SiteID, req.Name, req.Vendor, req.Host, req.Port, req.Channel,
		username, enc, rtspPath, req.StreamProfile, meta,
	).Scan(&cam.ID, &cam.OrgID, &cam.SiteID, &cam.Name, &cam.Vendor, &cam.Host, &cam.Port,
		&cam.Channel, &cam.Username, &cam.RTSPPath, &cam.StreamProfile, &cam.Status,
		&cam.Metadata, &cam.IsActive, &cam.CreatedAt, &cam.UpdatedAt)
	if err != nil {
		return nil, err
	}
	cam.Host = NormalizeHost(cam.Host)
	if err := s.onboardAfterSave(ctx, &cam); err != nil {
		_ = s.persistMetadata(ctx, cam.ID, cam.Metadata)
	}
	return &cam, nil
}

func (s *Service) Get(ctx context.Context, orgID, id uuid.UUID) (*models.Camera, error) {
	cam, err := s.scanOne(ctx, `SELECT id, org_id, site_id, name, vendor, host(host), port, channel, username, rtsp_path, stream_profile, status, metadata, is_active, created_at, updated_at
		FROM cameras WHERE id = $1 AND org_id = $2`, id, orgID)
	if err != nil {
		return nil, err
	}
	cam.Host = NormalizeHost(cam.Host)
	return cam, nil
}

func (s *Service) List(ctx context.Context, orgID uuid.UUID, siteID *uuid.UUID) ([]models.Camera, error) {
	query := `SELECT id, org_id, site_id, name, vendor, host(host), port, channel, username, rtsp_path, stream_profile, status, metadata, is_active, created_at, updated_at
		FROM cameras WHERE org_id = $1`
	args := []interface{}{orgID}
	if siteID != nil {
		query += ` AND site_id = $2`
		args = append(args, *siteID)
	}
	query += ` ORDER BY name`

	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var list []models.Camera
	for rows.Next() {
		cam, err := scanCamera(rows)
		if err != nil {
			return nil, err
		}
		cam.Host = NormalizeHost(cam.Host)
		list = append(list, *cam)
	}
	return list, rows.Err()
}

func (s *Service) Update(ctx context.Context, orgID, id uuid.UUID, req UpdateRequest) (*models.Camera, error) {
	cam, err := s.Get(ctx, orgID, id)
	if err != nil {
		return nil, err
	}
	reOnboard := req.Host != nil || req.Password != nil || req.RTSPPath != nil ||
		req.Username != nil || req.Port != nil || req.Channel != nil || req.Vendor != nil || req.StreamProfile != nil
	if req.Name != nil {
		cam.Name = *req.Name
	}
	if req.Vendor != nil {
		cam.Vendor = *req.Vendor
	}
	if req.Host != nil {
		cam.Host = NormalizeHost(*req.Host)
	}
	if req.Port != nil {
		cam.Port = *req.Port
	}
	if req.Channel != nil {
		cam.Channel = *req.Channel
	}
	if req.Username != nil {
		cam.Username = req.Username
	}
	if req.RTSPPath != nil {
		cam.RTSPPath = req.RTSPPath
	}
	if req.StreamProfile != nil {
		cam.StreamProfile = *req.StreamProfile
	}
	if req.IsActive != nil {
		cam.IsActive = *req.IsActive
	}
	if req.Metadata != nil {
		cam.Metadata = req.Metadata
	}

	var enc []byte
	if req.Password != nil && *req.Password != "" {
		enc, err = s.cipher.Encrypt(*req.Password)
		if err != nil {
			return nil, err
		}
	}

	_, err = s.pool.Exec(ctx, `
		UPDATE cameras SET name=$1, vendor=$2, host=$3, port=$4, channel=$5, username=$6,
		password_encrypted=COALESCE($7, password_encrypted), rtsp_path=$8, stream_profile=$9,
		is_active=$10, metadata=$11, updated_at=NOW()
		WHERE id=$12 AND org_id=$13`,
		cam.Name, cam.Vendor, cam.Host, cam.Port, cam.Channel, cam.Username,
		enc, cam.RTSPPath, cam.StreamProfile, cam.IsActive, cam.Metadata, id, orgID,
	)
	if err != nil {
		return nil, err
	}
	if reOnboard {
		updated, err := s.Get(ctx, orgID, id)
		if err != nil {
			return nil, err
		}
		if err := s.onboardAfterSave(ctx, updated); err != nil {
			_ = s.persistMetadata(ctx, updated.ID, updated.Metadata)
		}
		return updated, nil
	}
	return s.Get(ctx, orgID, id)
}

func (s *Service) Delete(ctx context.Context, orgID, id uuid.UUID) error {
	streamName := "cam-" + id.String()
	go2rtcCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	_ = NewGo2RTCClient().UnregisterStream(go2rtcCtx, streamName)
	cancel()

	tag, err := s.pool.Exec(ctx, `DELETE FROM cameras WHERE id = $1 AND org_id = $2`, id, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *Service) BuildRTSP(ctx context.Context, orgID, id uuid.UUID) (string, error) {
	var vendor, host, profile string
	var port, channel int
	var username, rtspPath *string
	var enc []byte
	var metadata json.RawMessage
	err := s.pool.QueryRow(ctx, `
		SELECT vendor, host(host), port, channel, username, password_encrypted, rtsp_path, stream_profile, metadata
		FROM cameras WHERE id = $1 AND org_id = $2`, id, orgID,
	).Scan(&vendor, &host, &port, &channel, &username, &enc, &rtspPath, &profile, &metadata)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", ErrNotFound
		}
		return "", err
	}
	host = NormalizeHost(host)

	var meta map[string]interface{}
	_ = json.Unmarshal(metadata, &meta)
	if url, ok := meta["rtsp_url"].(string); ok && url != "" {
		return url, nil
	}

	user, pass := "", ""
	if username != nil {
		user = *username
	}
	if len(enc) > 0 {
		pass, err = s.cipher.Decrypt(enc)
		if err != nil {
			return "", err
		}
	}
	path := ""
	if rtspPath != nil {
		path = *rtspPath
		if len(path) > 4 && path[:4] == "rtsp" {
			return path, nil
		}
	}
	return BuildRTSPURL(vendor, host, port, channel, user, pass, path, profile), nil
}

func (s *Service) TestStream(ctx context.Context, orgID, id uuid.UUID, timeout time.Duration) StreamTestResult {
	url, err := s.BuildRTSP(ctx, orgID, id)
	if err != nil {
		return StreamTestResult{Error: err.Error()}
	}
	if timeout == 0 {
		timeout = 5 * time.Second
	}
	return TestStream(ctx, url, timeout)
}

func (s *Service) scanOne(ctx context.Context, query string, args ...interface{}) (*models.Camera, error) {
	row := s.pool.QueryRow(ctx, query, args...)
	cam, err := scanCameraRow(row)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	return cam, nil
}

type scannable interface {
	Scan(dest ...interface{}) error
}

func scanCamera(rows pgx.Rows) (*models.Camera, error) {
	var cam models.Camera
	err := rows.Scan(&cam.ID, &cam.OrgID, &cam.SiteID, &cam.Name, &cam.Vendor, &cam.Host, &cam.Port,
		&cam.Channel, &cam.Username, &cam.RTSPPath, &cam.StreamProfile, &cam.Status,
		&cam.Metadata, &cam.IsActive, &cam.CreatedAt, &cam.UpdatedAt)
	return &cam, err
}

func scanCameraRow(row scannable) (*models.Camera, error) {
	var cam models.Camera
	err := row.Scan(&cam.ID, &cam.OrgID, &cam.SiteID, &cam.Name, &cam.Vendor, &cam.Host, &cam.Port,
		&cam.Channel, &cam.Username, &cam.RTSPPath, &cam.StreamProfile, &cam.Status,
		&cam.Metadata, &cam.IsActive, &cam.CreatedAt, &cam.UpdatedAt)
	return &cam, err
}

func ValidateCreate(req CreateRequest) error {
	if req.Name == "" || req.Host == "" || req.SiteID == uuid.Nil || req.OrgID == uuid.Nil {
		return fmt.Errorf("name, host, org_id and site_id are required")
	}
	return nil
}

func (s *Service) onboardAfterSave(ctx context.Context, cam *models.Camera) error {
	rtsp, err := s.BuildRTSP(ctx, cam.OrgID, cam.ID)
	if err != nil || rtsp == "" {
		return err
	}
	if err := OnboardCamera(ctx, cam, rtsp); err != nil {
		return err
	}
	return s.persistMetadata(ctx, cam.ID, cam.Metadata)
}

func (s *Service) persistMetadata(ctx context.Context, id uuid.UUID, meta json.RawMessage) error {
	if len(meta) == 0 {
		return nil
	}
	_, err := s.pool.Exec(ctx, `UPDATE cameras SET metadata = $1, updated_at = NOW() WHERE id = $2`, meta, id)
	return err
}

// ReOnboardAllRealCameras registers go2rtc streams for all active non-virtual cameras (startup/repair).
func (s *Service) ReOnboardAllRealCameras(ctx context.Context) (ok, failed int) {
	rows, err := s.pool.Query(ctx, `SELECT org_id, id FROM cameras WHERE is_active = true`)
	if err != nil {
		return 0, 0
	}
	defer rows.Close()
	for rows.Next() {
		var orgID, id uuid.UUID
		if err := rows.Scan(&orgID, &id); err != nil {
			continue
		}
		cam, err := s.Get(ctx, orgID, id)
		if err != nil {
			failed++
			continue
		}
		var meta map[string]interface{}
		_ = json.Unmarshal(cam.Metadata, &meta)
		if meta != nil {
			if v, _ := meta["virtual"].(bool); v {
				continue
			}
			if src, _ := meta["go2rtc_src"].(string); src == "benedicte" {
				continue
			}
		}
		if err := s.onboardAfterSave(ctx, cam); err != nil {
			_ = s.persistMetadata(ctx, cam.ID, cam.Metadata)
			failed++
		} else {
			ok++
		}
	}
	return ok, failed
}

// ReOnboardCamera rebuilds go2rtc registration for an existing camera.
func (s *Service) ReOnboardCamera(ctx context.Context, orgID, id uuid.UUID) (*models.Camera, error) {
	cam, err := s.Get(ctx, orgID, id)
	if err != nil {
		return nil, err
	}
	if err := s.onboardAfterSave(ctx, cam); err != nil {
		_ = s.persistMetadata(ctx, cam.ID, cam.Metadata)
		return cam, err
	}
	return s.Get(ctx, orgID, id)
}
