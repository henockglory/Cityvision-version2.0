package events

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
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
	// ExternalID: if set and a valid UUID, used as the event primary key so
	// the AI engine's event_id and the DB id stay in sync for evidence patching.
	ExternalID string `json:"external_id,omitempty"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) Ingest(ctx context.Context, req IngestRequest) (*models.Event, error) {
	req.Severity = normalizeEventSeverity(req.Severity)
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

	// Use the AI engine's own event_id as PK when provided — keeps DB id and
	// the upstream event_id aligned so PatchEvidenceSnapshot can find the row.
	var externalID *uuid.UUID
	if req.ExternalID != "" {
		if parsed, err := uuid.Parse(req.ExternalID); err == nil {
			externalID = &parsed
		}
	}

	var e models.Event
	var err error
	if externalID != nil {
		err = s.pool.QueryRow(ctx, `
			INSERT INTO events (id, org_id, site_id, camera_id, event_type, severity, payload, evidence_snapshot, occurred_at)
			VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
			ON CONFLICT (id) DO UPDATE SET evidence_snapshot = EXCLUDED.evidence_snapshot
			RETURNING id, org_id, site_id, camera_id, event_type, severity, payload, evidence_snapshot, occurred_at, ingested_at`,
			*externalID, req.OrgID, req.SiteID, req.CameraID, req.EventType, req.Severity, payload, evSnap, occurred,
		).Scan(&e.ID, &e.OrgID, &e.SiteID, &e.CameraID, &e.EventType, &e.Severity, &e.Payload, &e.EvidenceSnapshot, &e.OccurredAt, &e.IngestedAt)
	} else {
		err = s.pool.QueryRow(ctx, `
			INSERT INTO events (org_id, site_id, camera_id, event_type, severity, payload, evidence_snapshot, occurred_at)
			VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
			RETURNING id, org_id, site_id, camera_id, event_type, severity, payload, evidence_snapshot, occurred_at, ingested_at`,
			req.OrgID, req.SiteID, req.CameraID, req.EventType, req.Severity, payload, evSnap, occurred,
		).Scan(&e.ID, &e.OrgID, &e.SiteID, &e.CameraID, &e.EventType, &e.Severity, &e.Payload, &e.EvidenceSnapshot, &e.OccurredAt, &e.IngestedAt)
	}
	return &e, err
}

// PatchEvidenceSnapshot updates an event's evidence_snapshot in-place after async upload.
// It reads the existing snapshot first so bbox, speed_kmh and other ingest-time fields are preserved.
func (s *Service) PatchEvidenceSnapshot(ctx context.Context, orgID uuid.UUID, eventID string, pkg *evidence.Package) error {
	evID, err := uuid.Parse(eventID)
	if err != nil {
		return nil // invalid id — skip silently
	}
	// Read existing snapshot to preserve bbox, speed_kmh, plate_number, etc.
	var existingRaw []byte
	_ = s.pool.QueryRow(ctx,
		`SELECT evidence_snapshot FROM events WHERE id = $1 AND org_id = $2`,
		evID, orgID,
	).Scan(&existingRaw)
	var existing map[string]interface{}
	if len(existingRaw) > 0 {
		_ = json.Unmarshal(existingRaw, &existing)
	}
	snap := evidence.MergeIntoSnapshot(existing, pkg, nil)
	_, err = s.pool.Exec(ctx,
		`UPDATE events SET evidence_snapshot = $1 WHERE id = $2 AND org_id = $3`,
		snap, evID, orgID,
	)
	return err
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

// normalizeEventSeverity maps AI-engine labels to DB enum event_severity [D.44].
func normalizeEventSeverity(s string) string {
	s = strings.ToLower(strings.TrimSpace(s))
	switch s {
	case "warning", "warn":
		return "medium"
	case "info", "low", "medium", "high", "critical":
		return s
	default:
		return "info"
	}
}
