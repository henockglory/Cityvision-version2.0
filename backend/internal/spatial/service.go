package spatial

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/models"
)

var ErrNotFound = errors.New("resource not found")

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

type ZoneRequest struct {
	OrgID    uuid.UUID       `json:"org_id"`
	SiteID   uuid.UUID       `json:"site_id"`
	CameraID *uuid.UUID      `json:"camera_id,omitempty"`
	Name     string          `json:"name"`
	Polygon  json.RawMessage `json:"polygon"`
	Color    string          `json:"color"`
}

func (s *Service) CreateZone(ctx context.Context, req ZoneRequest) (*models.Zone, error) {
	color := req.Color
	if color == "" {
		color = "#FF5733"
	}
	var z models.Zone
	err := s.pool.QueryRow(ctx, `
		INSERT INTO zones (org_id, site_id, camera_id, name, polygon, color)
		VALUES ($1,$2,$3,$4,$5,$6)
		RETURNING id, org_id, site_id, camera_id, name, polygon, color, is_active, created_at, updated_at`,
		req.OrgID, req.SiteID, req.CameraID, req.Name, req.Polygon, color,
	).Scan(&z.ID, &z.OrgID, &z.SiteID, &z.CameraID, &z.Name, &z.Polygon, &z.Color, &z.IsActive, &z.CreatedAt, &z.UpdatedAt)
	return &z, err
}

func (s *Service) ListZones(ctx context.Context, orgID uuid.UUID, siteID *uuid.UUID) ([]models.Zone, error) {
	q := `SELECT id, org_id, site_id, camera_id, name, polygon, color, is_active, created_at, updated_at FROM zones WHERE org_id = $1`
	args := []interface{}{orgID}
	if siteID != nil {
		q += ` AND site_id = $2`
		args = append(args, *siteID)
	}
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []models.Zone
	for rows.Next() {
		var z models.Zone
		if err := rows.Scan(&z.ID, &z.OrgID, &z.SiteID, &z.CameraID, &z.Name, &z.Polygon, &z.Color, &z.IsActive, &z.CreatedAt, &z.UpdatedAt); err != nil {
			return nil, err
		}
		list = append(list, z)
	}
	return list, rows.Err()
}

type LineRequest struct {
	OrgID      uuid.UUID       `json:"org_id"`
	SiteID     uuid.UUID       `json:"site_id"`
	CameraID   *uuid.UUID      `json:"camera_id,omitempty"`
	Name       string          `json:"name"`
	StartPoint json.RawMessage `json:"start_point"`
	EndPoint   json.RawMessage `json:"end_point"`
	Direction  *string         `json:"direction,omitempty"`
}

func (s *Service) CreateLine(ctx context.Context, req LineRequest) (*models.Line, error) {
	var l models.Line
	err := s.pool.QueryRow(ctx, `
		INSERT INTO lines (org_id, site_id, camera_id, name, start_point, end_point, direction)
		VALUES ($1,$2,$3,$4,$5,$6,$7)
		RETURNING id, org_id, site_id, camera_id, name, start_point, end_point, direction, is_active, created_at, updated_at`,
		req.OrgID, req.SiteID, req.CameraID, req.Name, req.StartPoint, req.EndPoint, req.Direction,
	).Scan(&l.ID, &l.OrgID, &l.SiteID, &l.CameraID, &l.Name, &l.StartPoint, &l.EndPoint, &l.Direction, &l.IsActive, &l.CreatedAt, &l.UpdatedAt)
	return &l, err
}

func (s *Service) ListLines(ctx context.Context, orgID uuid.UUID, siteID *uuid.UUID) ([]models.Line, error) {
	q := `SELECT id, org_id, site_id, camera_id, name, start_point, end_point, direction, is_active, created_at, updated_at FROM lines WHERE org_id = $1`
	args := []interface{}{orgID}
	if siteID != nil {
		q += ` AND site_id = $2`
		args = append(args, *siteID)
	}
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []models.Line
	for rows.Next() {
		var l models.Line
		if err := rows.Scan(&l.ID, &l.OrgID, &l.SiteID, &l.CameraID, &l.Name, &l.StartPoint, &l.EndPoint, &l.Direction, &l.IsActive, &l.CreatedAt, &l.UpdatedAt); err != nil {
			return nil, err
		}
		list = append(list, l)
	}
	return list, rows.Err()
}

func (s *Service) GetZone(ctx context.Context, orgID, id uuid.UUID) (*models.Zone, error) {
	var z models.Zone
	err := s.pool.QueryRow(ctx, `
		SELECT id, org_id, site_id, camera_id, name, polygon, color, is_active, created_at, updated_at
		FROM zones WHERE id = $1 AND org_id = $2`, id, orgID,
	).Scan(&z.ID, &z.OrgID, &z.SiteID, &z.CameraID, &z.Name, &z.Polygon, &z.Color, &z.IsActive, &z.CreatedAt, &z.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &z, err
}
