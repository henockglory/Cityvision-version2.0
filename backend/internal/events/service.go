package events

import (
	"context"
	"encoding/json"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision/backend/internal/models"
)

type IngestRequest struct {
	OrgID      uuid.UUID       `json:"org_id"`
	SiteID     *uuid.UUID      `json:"site_id,omitempty"`
	CameraID   *uuid.UUID      `json:"camera_id,omitempty"`
	EventType  string          `json:"event_type"`
	Severity   string          `json:"severity"`
	Payload    json.RawMessage `json:"payload"`
	OccurredAt *time.Time      `json:"occurred_at,omitempty"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) Ingest(ctx context.Context, req IngestRequest) (*models.Event, error) {
	if req.Severity == "" {
		req.Severity = "info"
	}
	payload := req.Payload
	if payload == nil {
		payload = json.RawMessage(`{}`)
	}
	occurred := time.Now()
	if req.OccurredAt != nil {
		occurred = *req.OccurredAt
	}

	var e models.Event
	err := s.pool.QueryRow(ctx, `
		INSERT INTO events (org_id, site_id, camera_id, event_type, severity, payload, occurred_at)
		VALUES ($1,$2,$3,$4,$5,$6,$7)
		RETURNING id, org_id, site_id, camera_id, event_type, severity, payload, occurred_at, ingested_at`,
		req.OrgID, req.SiteID, req.CameraID, req.EventType, req.Severity, payload, occurred,
	).Scan(&e.ID, &e.OrgID, &e.SiteID, &e.CameraID, &e.EventType, &e.Severity, &e.Payload, &e.OccurredAt, &e.IngestedAt)
	return &e, err
}

func (s *Service) List(ctx context.Context, orgID uuid.UUID, limit int) ([]models.Event, error) {
	if limit <= 0 {
		limit = 50
	}
	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, site_id, camera_id, event_type, severity, payload, occurred_at, ingested_at
		FROM events WHERE org_id = $1 ORDER BY occurred_at DESC LIMIT $2`, orgID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []models.Event
	for rows.Next() {
		var e models.Event
		if err := rows.Scan(&e.ID, &e.OrgID, &e.SiteID, &e.CameraID, &e.EventType, &e.Severity, &e.Payload, &e.OccurredAt, &e.IngestedAt); err != nil {
			return nil, err
		}
		list = append(list, e)
	}
	return list, rows.Err()
}

func (s *Service) CountSince(ctx context.Context, orgID uuid.UUID, since time.Time) (int, error) {
	var n int
	err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM events WHERE org_id = $1 AND occurred_at >= $2`, orgID, since).Scan(&n)
	return n, err
}
