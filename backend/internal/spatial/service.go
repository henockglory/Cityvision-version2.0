package spatial

import (
	"context"
	"encoding/json"
	"errors"
	"time"

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

// zoneColumns is the canonical ordered column list scanned into models.Zone.
const zoneColumns = `id, org_id, site_id, camera_id, name, polygon, color, zone_kind, behavior_config, is_active, created_at, updated_at`

func scanZone(row pgx.Row, z *models.Zone) error {
	return row.Scan(&z.ID, &z.OrgID, &z.SiteID, &z.CameraID, &z.Name, &z.Polygon, &z.Color, &z.ZoneKind, &z.BehaviorConfig, &z.IsActive, &z.CreatedAt, &z.UpdatedAt)
}

// lineColumns is the canonical ordered column list scanned into models.Line.
const lineColumns = `id, org_id, site_id, camera_id, name, start_point, end_point, direction, behavior_config, is_active, created_at, updated_at`

func scanLine(row pgx.Row, l *models.Line) error {
	return row.Scan(&l.ID, &l.OrgID, &l.SiteID, &l.CameraID, &l.Name, &l.StartPoint, &l.EndPoint, &l.Direction, &l.BehaviorConfig, &l.IsActive, &l.CreatedAt, &l.UpdatedAt)
}

type ZoneRequest struct {
	OrgID          uuid.UUID       `json:"org_id"`
	SiteID         uuid.UUID       `json:"site_id"`
	CameraID       *uuid.UUID      `json:"camera_id,omitempty"`
	Name           string          `json:"name"`
	Polygon        json.RawMessage `json:"polygon"`
	Color          string          `json:"color"`
	ZoneKind       string          `json:"zone_kind,omitempty"`
	BehaviorConfig json.RawMessage `json:"behavior_config,omitempty"`
}

func (s *Service) CreateZone(ctx context.Context, req ZoneRequest) (*models.Zone, error) {
	color := req.Color
	if color == "" {
		color = "#FF5733"
	}
	behavior := req.BehaviorConfig
	if len(behavior) == 0 {
		behavior = json.RawMessage(`{}`)
	}
	var z models.Zone
	err := scanZone(s.pool.QueryRow(ctx, `
		INSERT INTO zones (org_id, site_id, camera_id, name, polygon, color, zone_kind, behavior_config)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
		RETURNING `+zoneColumns,
		req.OrgID, req.SiteID, req.CameraID, req.Name, req.Polygon, color, req.ZoneKind, behavior,
	), &z)
	return &z, err
}

func (s *Service) ListZones(ctx context.Context, orgID uuid.UUID, siteID *uuid.UUID) ([]models.Zone, error) {
	q := `SELECT ` + zoneColumns + ` FROM zones WHERE org_id = $1`
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
		if err := scanZone(rows, &z); err != nil {
			return nil, err
		}
		list = append(list, z)
	}
	return list, rows.Err()
}

type LineRequest struct {
	OrgID          uuid.UUID       `json:"org_id"`
	SiteID         uuid.UUID       `json:"site_id"`
	CameraID       *uuid.UUID      `json:"camera_id,omitempty"`
	Name           string          `json:"name"`
	StartPoint     json.RawMessage `json:"start_point"`
	EndPoint       json.RawMessage `json:"end_point"`
	Direction      *string         `json:"direction,omitempty"`
	BehaviorConfig json.RawMessage `json:"behavior_config,omitempty"`
}

func (s *Service) CreateLine(ctx context.Context, req LineRequest) (*models.Line, error) {
	behavior := req.BehaviorConfig
	if len(behavior) == 0 {
		behavior = json.RawMessage(`{}`)
	}
	var l models.Line
	err := scanLine(s.pool.QueryRow(ctx, `
		INSERT INTO lines (org_id, site_id, camera_id, name, start_point, end_point, direction, behavior_config)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
		RETURNING `+lineColumns,
		req.OrgID, req.SiteID, req.CameraID, req.Name, req.StartPoint, req.EndPoint, req.Direction, behavior,
	), &l)
	return &l, err
}

func (s *Service) ListLines(ctx context.Context, orgID uuid.UUID, siteID *uuid.UUID) ([]models.Line, error) {
	q := `SELECT ` + lineColumns + ` FROM lines WHERE org_id = $1`
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
		if err := scanLine(rows, &l); err != nil {
			return nil, err
		}
		list = append(list, l)
	}
	return list, rows.Err()
}

func (s *Service) DeleteZone(ctx context.Context, orgID, id uuid.UUID) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM zones WHERE id = $1 AND org_id = $2`, id, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

type ZonePatchRequest struct {
	Name           *string         `json:"name,omitempty"`
	ZoneKind       *string         `json:"zone_kind,omitempty"`
	BehaviorConfig json.RawMessage `json:"behavior_config,omitempty"`
	Polygon        json.RawMessage `json:"polygon,omitempty"`
}

func (s *Service) UpdateZone(ctx context.Context, orgID, id uuid.UUID, patch ZonePatchRequest) (*models.Zone, error) {
	if patch.Name == nil && patch.ZoneKind == nil && len(patch.BehaviorConfig) == 0 && len(patch.Polygon) == 0 {
		return s.GetZone(ctx, orgID, id)
	}
	// behaviorArg is nil when not provided so COALESCE keeps the existing value.
	var behaviorArg interface{}
	if len(patch.BehaviorConfig) > 0 {
		behaviorArg = patch.BehaviorConfig
	}
	var polygonArg interface{}
	if len(patch.Polygon) > 0 {
		polygonArg = patch.Polygon
	}
	var z models.Zone
	err := scanZone(s.pool.QueryRow(ctx, `
		UPDATE zones SET
			name = COALESCE($3, name),
			zone_kind = COALESCE($4, zone_kind),
			behavior_config = COALESCE($5, behavior_config),
			polygon = COALESCE($6, polygon),
			updated_at = NOW()
		WHERE id = $1 AND org_id = $2
		RETURNING `+zoneColumns,
		id, orgID, patch.Name, patch.ZoneKind, behaviorArg, polygonArg,
	), &z)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &z, err
}

type LinePatchRequest struct {
	Name           *string         `json:"name,omitempty"`
	BehaviorConfig json.RawMessage `json:"behavior_config,omitempty"`
}

func (s *Service) UpdateLine(ctx context.Context, orgID, id uuid.UUID, patch LinePatchRequest) (*models.Line, error) {
	if patch.Name == nil && len(patch.BehaviorConfig) == 0 {
		var l models.Line
		err := scanLine(s.pool.QueryRow(ctx, `
			SELECT `+lineColumns+`
			FROM lines WHERE id = $1 AND org_id = $2`, id, orgID,
		), &l)
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNotFound
		}
		return &l, err
	}
	var behaviorArg interface{}
	if len(patch.BehaviorConfig) > 0 {
		behaviorArg = patch.BehaviorConfig
	}
	var l models.Line
	err := scanLine(s.pool.QueryRow(ctx, `
		UPDATE lines SET
			name = COALESCE($3, name),
			behavior_config = COALESCE($4, behavior_config),
			updated_at = NOW()
		WHERE id = $1 AND org_id = $2
		RETURNING `+lineColumns,
		id, orgID, patch.Name, behaviorArg,
	), &l)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &l, err
}

func (s *Service) DeleteLine(ctx context.Context, orgID, id uuid.UUID) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM lines WHERE id = $1 AND org_id = $2`, id, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// LineCounter is a persistent per-line crossing tally.
type LineCounter struct {
	LineID       string     `json:"line_id"`
	ClassFilter  string     `json:"class_filter,omitempty"`
	CameraID     *uuid.UUID `json:"camera_id,omitempty"`
	CountIn      int64      `json:"count_in"`
	CountOut     int64      `json:"count_out"`
	CountTotal   int64      `json:"count_total"`
	LastClass    string     `json:"last_class"`
	UpdatedAt    time.Time  `json:"updated_at"`
}

// ListLineCounters returns the crossing counters for an org, optionally scoped to a camera.
func (s *Service) ListLineCounters(ctx context.Context, orgID uuid.UUID, cameraID *uuid.UUID) ([]LineCounter, error) {
	q := `SELECT line_id, class_filter, camera_id, count_in, count_out, count_total, last_class, updated_at
		FROM line_counters WHERE org_id = $1`
	args := []interface{}{orgID}
	if cameraID != nil {
		q += ` AND camera_id = $2`
		args = append(args, *cameraID)
	}
	q += ` ORDER BY line_id, class_filter`
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]LineCounter, 0)
	for rows.Next() {
		var c LineCounter
		if err := rows.Scan(&c.LineID, &c.ClassFilter, &c.CameraID, &c.CountIn, &c.CountOut, &c.CountTotal, &c.LastClass, &c.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	return out, rows.Err()
}

// ResetLineCounters clears crossing counters for an org, optionally scoped to a camera.
func (s *Service) ResetLineCounters(ctx context.Context, orgID uuid.UUID, cameraID *uuid.UUID) error {
	if cameraID != nil {
		_, err := s.pool.Exec(ctx, `DELETE FROM line_counters WHERE org_id = $1 AND camera_id = $2`, orgID, *cameraID)
		return err
	}
	_, err := s.pool.Exec(ctx, `DELETE FROM line_counters WHERE org_id = $1`, orgID)
	return err
}

func (s *Service) GetZone(ctx context.Context, orgID, id uuid.UUID) (*models.Zone, error) {
	var z models.Zone
	err := scanZone(s.pool.QueryRow(ctx, `
		SELECT `+zoneColumns+`
		FROM zones WHERE id = $1 AND org_id = $2`, id, orgID,
	), &z)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &z, err
}
