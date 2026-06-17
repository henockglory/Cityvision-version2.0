package events

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/evidence"
	"github.com/citevision/citevision-v2/backend/internal/models"
)

type IngestRequest struct {
	OrgID            uuid.UUID       `json:"org_id"`
	SiteID           *uuid.UUID      `json:"site_id,omitempty"`
	CameraID         *uuid.UUID      `json:"camera_id,omitempty"`
	EventType        string          `json:"event_type"`
	Severity         string          `json:"severity"`
	Payload          json.RawMessage `json:"payload"`
	EvidenceSnapshot json.RawMessage `json:"evidence_snapshot,omitempty"`
	OccurredAt       *time.Time      `json:"occurred_at,omitempty"`
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
	evSnap := req.EvidenceSnapshot
	if evSnap == nil || string(evSnap) == "{}" || string(evSnap) == "null" {
		var pm map[string]interface{}
		_ = json.Unmarshal(payload, &pm)
		evSnap = evidence.SnapshotFromPayload(pm)
	}
	occurred := time.Now()
	if req.OccurredAt != nil {
		occurred = *req.OccurredAt
	}

	var e models.Event
	err := s.pool.QueryRow(ctx, `
		INSERT INTO events (org_id, site_id, camera_id, event_type, severity, payload, evidence_snapshot, occurred_at)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
		RETURNING id, org_id, site_id, camera_id, event_type, severity, payload, evidence_snapshot, occurred_at, ingested_at`,
		req.OrgID, req.SiteID, req.CameraID, req.EventType, req.Severity, payload, evSnap, occurred,
	).Scan(&e.ID, &e.OrgID, &e.SiteID, &e.CameraID, &e.EventType, &e.Severity, &e.Payload, &e.EvidenceSnapshot, &e.OccurredAt, &e.IngestedAt)
	return &e, err
}

func (s *Service) List(ctx context.Context, orgID uuid.UUID, limit int, eventType, cameraID string) ([]models.Event, error) {
	if limit <= 0 {
		limit = 50
	}
	q := `
		SELECT id, org_id, site_id, camera_id, event_type, severity, payload, occurred_at, ingested_at
		FROM events WHERE org_id = $1`
	args := []interface{}{orgID}
	n := 2
	if eventType != "" {
		q += fmt.Sprintf(` AND event_type = $%d`, n)
		args = append(args, eventType)
		n++
	}
	if cameraID != "" {
		if id, err := uuid.Parse(cameraID); err == nil {
			q += fmt.Sprintf(` AND camera_id = $%d`, n)
			args = append(args, id)
			n++
		}
	}
	q += fmt.Sprintf(` ORDER BY occurred_at DESC LIMIT $%d`, n)
	args = append(args, limit)

	rows, err := s.pool.Query(ctx, q, args...)
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

type EnrichedEvent struct {
	models.Event
	CameraName string   `json:"camera_name,omitempty"`
	RuleName   *string  `json:"rule_name,omitempty"`
	Confidence *float64 `json:"confidence,omitempty"`
	LabelFR    string   `json:"label_fr,omitempty"`
}

func (s *Service) ListEnriched(ctx context.Context, orgID uuid.UUID, limit int, eventType, cameraID string, ruleLinkedOnly bool, includeIncomplete bool) ([]EnrichedEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	q := `
		SELECT e.id, e.org_id, e.site_id, e.camera_id, e.event_type, e.severity, e.payload,
			COALESCE(e.evidence_snapshot, '{}'::jsonb), e.occurred_at, e.ingested_at,
			COALESCE(c.name, ''),
			r.name, COALESCE(r.definition, '{}'::jsonb)
		FROM events e
		LEFT JOIN cameras c ON c.id = e.camera_id
		LEFT JOIN rules r ON r.id = (e.payload->>'matched_rule_id')::uuid
		WHERE e.org_id = $1`
	args := []interface{}{orgID}
	n := 2
	if eventType != "" {
		q += fmt.Sprintf(` AND e.event_type = $%d`, n)
		args = append(args, eventType)
		n++
	}
	if cameraID != "" {
		if id, err := uuid.Parse(cameraID); err == nil {
			q += fmt.Sprintf(` AND e.camera_id = $%d`, n)
			args = append(args, id)
			n++
		}
	}
	if ruleLinkedOnly {
		q += ` AND (e.payload->>'matched_rule_id') IS NOT NULL`
	}
	q += fmt.Sprintf(` ORDER BY e.occurred_at DESC LIMIT $%d`, n)
	args = append(args, limit)

	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []EnrichedEvent
	for rows.Next() {
		var ee EnrichedEvent
		var ruleName *string
		var ruleDef json.RawMessage
		if err := rows.Scan(
			&ee.ID, &ee.OrgID, &ee.SiteID, &ee.CameraID, &ee.EventType, &ee.Severity, &ee.Payload,
			&ee.EvidenceSnapshot, &ee.OccurredAt, &ee.IngestedAt,
			&ee.CameraName, &ruleName, &ruleDef,
		); err != nil {
			return nil, err
		}
		ee.RuleName = ruleName
		if !includeIncomplete && ruleLinkedOnly {
			policy := evidence.PolicyFromDefinition(ruleDef)
			if evidence.PolicyRequiresProof(policy) && !evidence.IsComplete(ee.EvidenceSnapshot, policy) {
				continue
			}
		}
		var payload map[string]interface{}
		_ = json.Unmarshal(ee.Payload, &payload)
		if meta, ok := payload["metadata"].(map[string]interface{}); ok {
			if conf, ok := meta["confidence"].(float64); ok {
				ee.Confidence = &conf
			}
		}
		if ee.CameraName == "" {
			ee.CameraName = "—"
		}
		list = append(list, ee)
	}
	return list, rows.Err()
}

func (s *Service) PurgeForOrg(ctx context.Context, orgID uuid.UUID) (int64, error) {
	tag, err := s.pool.Exec(ctx, `DELETE FROM events WHERE org_id = $1`, orgID)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}
