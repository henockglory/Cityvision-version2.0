package alerts

import (
	"context"
	"encoding/json"
	"errors"
	"strconv"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/models"
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

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) CreateAlert(ctx context.Context, req CreateAlertRequest) (*models.Alert, error) {
	if req.Severity == "" {
		req.Severity = "medium"
	}
	meta := EnrichCreateMetadata(req.Metadata)
	var metaMap map[string]interface{}
	_ = json.Unmarshal(meta, &metaMap)
	evidence := BuildEvidenceSnapshot(metaMap)
	var msg *string
	if req.Message != "" {
		msg = &req.Message
	}
	var a models.Alert
	err := s.pool.QueryRow(ctx, `
		INSERT INTO alerts (org_id, site_id, rule_id, event_id, title, message, severity, metadata, evidence_snapshot)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
		RETURNING id, org_id, site_id, rule_id, event_id, title, message, severity, status, metadata, created_at, updated_at`,
		req.OrgID, req.SiteID, req.RuleID, req.EventID, req.Title, msg, req.Severity, meta, evidence,
	).Scan(&a.ID, &a.OrgID, &a.SiteID, &a.RuleID, &a.EventID, &a.Title, &a.Message, &a.Severity, &a.Status, &a.Metadata, &a.CreatedAt, &a.UpdatedAt)
	return &a, err
}

type EnrichedAlert struct {
	models.Alert
	CameraName        string          `json:"camera_name,omitempty"`
	RuleName          *string         `json:"rule_name,omitempty"`
	CameraID          string          `json:"camera_id,omitempty"`
	ArchivedAt        *time.Time      `json:"archived_at,omitempty"`
	ArchiveComment    *string         `json:"archive_comment,omitempty"`
	EvidenceSnapshot  json.RawMessage `json:"evidence_snapshot,omitempty"`
}

type ListFilter struct {
	Status   string
	Severity string
	RuleID   *uuid.UUID
	CameraID string
	From     *time.Time
	To       *time.Time
	Limit    int
	Offset   int
}

func (s *Service) PurgeForOrg(ctx context.Context, orgID uuid.UUID) (int64, error) {
	tag, err := s.pool.Exec(ctx, `DELETE FROM alerts WHERE org_id = $1`, orgID)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

func (s *Service) ListEnriched(ctx context.Context, orgID uuid.UUID, f ListFilter) ([]EnrichedAlert, error) {
	if f.Limit <= 0 || f.Limit > 500 {
		f.Limit = 100
	}
	q := `
		SELECT a.id, a.org_id, a.site_id, a.rule_id, a.event_id, a.title, a.message, a.severity, a.status, a.metadata, a.created_at, a.updated_at,
			a.archived_at, a.archive_comment, COALESCE(a.evidence_snapshot, '{}'::jsonb),
			COALESCE(c.name, a.metadata->>'camera_name', ''),
			r.name
		FROM alerts a
		LEFT JOIN rules r ON r.id = a.rule_id
		LEFT JOIN cameras c ON c.id::text = COALESCE(a.metadata->>'camera_id', '')
		WHERE a.org_id = $1`
	args := []interface{}{orgID}
	n := 2
	if f.Status != "" {
		q += ` AND a.status = $` + itoa(n)
		args = append(args, f.Status)
		n++
	}
	if f.Severity != "" {
		q += ` AND a.severity = $` + itoa(n)
		args = append(args, f.Severity)
		n++
	}
	if f.RuleID != nil {
		q += ` AND a.rule_id = $` + itoa(n)
		args = append(args, *f.RuleID)
		n++
	}
	if f.CameraID != "" {
		q += ` AND a.metadata->>'camera_id' = $` + itoa(n)
		args = append(args, f.CameraID)
		n++
	}
	if f.From != nil {
		q += ` AND a.created_at >= $` + itoa(n)
		args = append(args, *f.From)
		n++
	}
	if f.To != nil {
		q += ` AND a.created_at <= $` + itoa(n)
		args = append(args, *f.To)
		n++
	}
	q += ` ORDER BY a.created_at DESC LIMIT $` + itoa(n) + ` OFFSET $` + itoa(n+1)
	args = append(args, f.Limit, f.Offset)
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []EnrichedAlert
	for rows.Next() {
		var ea EnrichedAlert
		var ruleName *string
		if err := rows.Scan(
			&ea.ID, &ea.OrgID, &ea.SiteID, &ea.RuleID, &ea.EventID, &ea.Title, &ea.Message, &ea.Severity, &ea.Status, &ea.Metadata, &ea.CreatedAt, &ea.UpdatedAt,
			&ea.ArchivedAt, &ea.ArchiveComment, &ea.EvidenceSnapshot,
			&ea.CameraName, &ruleName,
		); err != nil {
			return nil, err
		}
		ea.RuleName = ruleName
		var meta map[string]interface{}
		_ = json.Unmarshal(ea.Metadata, &meta)
		if cid, ok := meta["camera_id"].(string); ok {
			ea.CameraID = cid
		}
		if ea.CameraName == "" {
			ea.CameraName = "—"
		}
		list = append(list, ea)
	}
	return list, rows.Err()
}

func itoa(n int) string {
	return strconv.Itoa(n)
}

func (s *Service) ListEnrichedLegacy(ctx context.Context, orgID uuid.UUID, status string) ([]EnrichedAlert, error) {
	return s.ListEnriched(ctx, orgID, ListFilter{Status: status, Limit: 100})
}

func (s *Service) ListAlerts(ctx context.Context, orgID uuid.UUID, status string) ([]models.Alert, error) {
	enriched, err := s.ListEnrichedLegacy(ctx, orgID, status)
	if err != nil {
		return nil, err
	}
	out := make([]models.Alert, len(enriched))
	for i, ea := range enriched {
		out[i] = ea.Alert
	}
	return out, nil
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

type ArchiveRequest struct {
	Comment          string
	EvidenceSnapshot json.RawMessage
	ArchivedBy       *uuid.UUID
}

func (s *Service) ArchiveAlert(ctx context.Context, orgID, id uuid.UUID, req ArchiveRequest) (*models.Alert, error) {
	evidence := req.EvidenceSnapshot
	if evidence == nil {
		evidence = json.RawMessage(`{}`)
	}
	var a models.Alert
	err := s.pool.QueryRow(ctx, `
		UPDATE alerts SET status = 'archived', archived_at = NOW(), archived_by = $1,
			archive_comment = $2, evidence_snapshot = $3, updated_at = NOW()
		WHERE id = $4 AND org_id = $5
		RETURNING id, org_id, site_id, rule_id, event_id, title, message, severity, status, metadata, created_at, updated_at`,
		req.ArchivedBy, req.Comment, evidence, id, orgID,
	).Scan(&a.ID, &a.OrgID, &a.SiteID, &a.RuleID, &a.EventID, &a.Title, &a.Message, &a.Severity, &a.Status, &a.Metadata, &a.CreatedAt, &a.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &a, err
}

func (s *Service) IncrementRuleCounter(ctx context.Context, orgID, ruleID uuid.UUID, delta int) error {
	if delta == 0 {
		delta = 1
	}
	_, err := s.pool.Exec(ctx, `
		INSERT INTO rule_counters (org_id, rule_id, count, updated_at)
		VALUES ($1, $2, $3, NOW())
		ON CONFLICT (org_id, rule_id) DO UPDATE SET count = rule_counters.count + $3, updated_at = NOW()`,
		orgID, ruleID, delta)
	return err
}

func (s *Service) ArchiveStaleByRule(ctx context.Context, orgID, ruleID uuid.UUID, olderThanMin int, comment string, evidence json.RawMessage) (int64, error) {
	if olderThanMin <= 0 {
		olderThanMin = 5
	}
	if evidence == nil {
		evidence = json.RawMessage(`{}`)
	}
	tag, err := s.pool.Exec(ctx, `
		UPDATE alerts SET status = 'archived', archived_at = NOW(),
			archive_comment = $1, evidence_snapshot = $2, updated_at = NOW()
		WHERE org_id = $3 AND rule_id = $4 AND status = 'open'
			AND created_at < NOW() - ($5 || ' minutes')::interval`,
		comment, evidence, orgID, ruleID, strconv.Itoa(olderThanMin))
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}
