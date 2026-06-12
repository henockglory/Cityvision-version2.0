package alerts

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision/backend/internal/models"
)

var ErrNotFound = errors.New("resource not found")

type CreateAlertRequest struct {
	OrgID    uuid.UUID       `json:"org_id"`
	SiteID   *uuid.UUID      `json:"site_id,omitempty"`
	RuleID   *uuid.UUID      `json:"rule_id,omitempty"`
	EventID  *uuid.UUID      `json:"event_id,omitempty"`
	Title    string          `json:"title"`
	Message  string          `json:"message"`
	Severity string          `json:"severity"`
	Metadata json.RawMessage `json:"metadata"`
}

type CreateIncidentRequest struct {
	OrgID       uuid.UUID       `json:"org_id"`
	SiteID      *uuid.UUID      `json:"site_id,omitempty"`
	Title       string          `json:"title"`
	Description string          `json:"description"`
	Severity    string          `json:"severity"`
	Metadata    json.RawMessage `json:"metadata"`
}

type EvidenceRequest struct {
	MinIOBucket string          `json:"minio_bucket"`
	MinIOObject string          `json:"minio_object"`
	ContentType string          `json:"content_type"`
	SizeBytes   int64           `json:"size_bytes"`
	Metadata    json.RawMessage `json:"metadata"`
}

type Service struct {
	pool          *pgxpool.Pool
	defaultBucket string
}

func NewService(pool *pgxpool.Pool, defaultBucket string) *Service {
	return &Service{pool: pool, defaultBucket: defaultBucket}
}

func (s *Service) CreateAlert(ctx context.Context, req CreateAlertRequest) (*models.Alert, error) {
	if req.Severity == "" {
		req.Severity = "medium"
	}
	meta := req.Metadata
	if meta == nil {
		meta = json.RawMessage(`{}`)
	}
	var msg *string
	if req.Message != "" {
		msg = &req.Message
	}
	var a models.Alert
	err := s.pool.QueryRow(ctx, `
		INSERT INTO alerts (org_id, site_id, rule_id, event_id, title, message, severity, metadata)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
		RETURNING id, org_id, site_id, rule_id, event_id, title, message, severity, status, metadata, created_at, updated_at`,
		req.OrgID, req.SiteID, req.RuleID, req.EventID, req.Title, msg, req.Severity, meta,
	).Scan(&a.ID, &a.OrgID, &a.SiteID, &a.RuleID, &a.EventID, &a.Title, &a.Message, &a.Severity, &a.Status, &a.Metadata, &a.CreatedAt, &a.UpdatedAt)
	return &a, err
}

func (s *Service) ListAlerts(ctx context.Context, orgID uuid.UUID, status string) ([]models.Alert, error) {
	q := `SELECT id, org_id, site_id, rule_id, event_id, title, message, severity, status, metadata, created_at, updated_at FROM alerts WHERE org_id = $1`
	args := []interface{}{orgID}
	if status != "" {
		q += ` AND status = $2`
		args = append(args, status)
	}
	q += ` ORDER BY created_at DESC LIMIT 100`
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []models.Alert
	for rows.Next() {
		var a models.Alert
		if err := rows.Scan(&a.ID, &a.OrgID, &a.SiteID, &a.RuleID, &a.EventID, &a.Title, &a.Message, &a.Severity, &a.Status, &a.Metadata, &a.CreatedAt, &a.UpdatedAt); err != nil {
			return nil, err
		}
		list = append(list, a)
	}
	return list, rows.Err()
}

func (s *Service) UpdateAlertStatus(ctx context.Context, orgID, id uuid.UUID, status string) (*models.Alert, error) {
	var a models.Alert
	err := s.pool.QueryRow(ctx, `
		UPDATE alerts SET status = $1, updated_at = NOW()
		WHERE id = $2 AND org_id = $3
		RETURNING id, org_id, site_id, rule_id, event_id, title, message, severity, status, metadata, created_at, updated_at`,
		status, id, orgID,
	).Scan(&a.ID, &a.OrgID, &a.SiteID, &a.RuleID, &a.EventID, &a.Title, &a.Message, &a.Severity, &a.Status, &a.Metadata, &a.CreatedAt, &a.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &a, err
}

func (s *Service) CreateIncident(ctx context.Context, req CreateIncidentRequest) (*models.Incident, error) {
	if req.Severity == "" {
		req.Severity = "high"
	}
	meta := req.Metadata
	if meta == nil {
		meta = json.RawMessage(`{}`)
	}
	var desc *string
	if req.Description != "" {
		desc = &req.Description
	}
	var inc models.Incident
	err := s.pool.QueryRow(ctx, `
		INSERT INTO incidents (org_id, site_id, title, description, severity, metadata)
		VALUES ($1,$2,$3,$4,$5,$6)
		RETURNING id, org_id, site_id, title, description, status, severity, assigned_to, metadata, created_at, updated_at, resolved_at`,
		req.OrgID, req.SiteID, req.Title, desc, req.Severity, meta,
	).Scan(&inc.ID, &inc.OrgID, &inc.SiteID, &inc.Title, &inc.Description, &inc.Status, &inc.Severity, &inc.AssignedTo, &inc.Metadata, &inc.CreatedAt, &inc.UpdatedAt, &inc.ResolvedAt)
	return &inc, err
}

func (s *Service) ListIncidents(ctx context.Context, orgID uuid.UUID) ([]models.Incident, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, site_id, title, description, status, severity, assigned_to, metadata, created_at, updated_at, resolved_at
		FROM incidents WHERE org_id = $1 ORDER BY created_at DESC LIMIT 100`, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []models.Incident
	for rows.Next() {
		var inc models.Incident
		if err := rows.Scan(&inc.ID, &inc.OrgID, &inc.SiteID, &inc.Title, &inc.Description, &inc.Status, &inc.Severity, &inc.AssignedTo, &inc.Metadata, &inc.CreatedAt, &inc.UpdatedAt, &inc.ResolvedAt); err != nil {
			return nil, err
		}
		list = append(list, inc)
	}
	return list, rows.Err()
}

func (s *Service) AddEvidence(ctx context.Context, incidentID uuid.UUID, req EvidenceRequest) (*models.IncidentEvidence, error) {
	bucket := req.MinIOBucket
	if bucket == "" {
		bucket = s.defaultBucket
	}
	meta := req.Metadata
	if meta == nil {
		meta = json.RawMessage(`{}`)
	}
	var ct *string
	if req.ContentType != "" {
		ct = &req.ContentType
	}
	var size *int64
	if req.SizeBytes > 0 {
		size = &req.SizeBytes
	}
	var ev models.IncidentEvidence
	err := s.pool.QueryRow(ctx, `
		INSERT INTO incident_evidence (incident_id, minio_bucket, minio_object, content_type, size_bytes, metadata)
		VALUES ($1,$2,$3,$4,$5,$6)
		RETURNING id, incident_id, minio_bucket, minio_object, content_type, size_bytes, metadata, created_at`,
		incidentID, bucket, req.MinIOObject, ct, size, meta,
	).Scan(&ev.ID, &ev.IncidentID, &ev.MinIOBucket, &ev.MinIOObject, &ev.ContentType, &ev.SizeBytes, &ev.Metadata, &ev.CreatedAt)
	return &ev, err
}

func (s *Service) CountOpenAlerts(ctx context.Context, orgID uuid.UUID) (int, error) {
	var n int
	err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM alerts WHERE org_id = $1 AND status = 'open'`, orgID).Scan(&n)
	return n, err
}

func (s *Service) CountOpenIncidents(ctx context.Context, orgID uuid.UUID) (int, error) {
	var n int
	err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM incidents WHERE org_id = $1 AND status IN ('open','investigating')`, orgID).Scan(&n)
	return n, err
}

func (s *Service) ResolveIncident(ctx context.Context, orgID, id uuid.UUID) (*models.Incident, error) {
	now := time.Now()
	var inc models.Incident
	err := s.pool.QueryRow(ctx, `
		UPDATE incidents SET status = 'resolved', resolved_at = $1, updated_at = NOW()
		WHERE id = $2 AND org_id = $3
		RETURNING id, org_id, site_id, title, description, status, severity, assigned_to, metadata, created_at, updated_at, resolved_at`,
		now, id, orgID,
	).Scan(&inc.ID, &inc.OrgID, &inc.SiteID, &inc.Title, &inc.Description, &inc.Status, &inc.Severity, &inc.AssignedTo, &inc.Metadata, &inc.CreatedAt, &inc.UpdatedAt, &inc.ResolvedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &inc, err
}
