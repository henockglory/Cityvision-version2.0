package correlation

import (
	"context"
	"encoding/json"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Rule struct {
	ID         uuid.UUID       `json:"id"`
	OrgID      uuid.UUID       `json:"org_id"`
	Name       string          `json:"name"`
	Definition json.RawMessage `json:"definition"`
	IsEnabled  bool            `json:"is_enabled"`
	CreatedAt  time.Time       `json:"created_at"`
	UpdatedAt  time.Time       `json:"updated_at"`
}

type CorrelationResult struct {
	Matched    bool                   `json:"matched"`
	RuleID     uuid.UUID              `json:"rule_id,omitempty"`
	EventIDs   []uuid.UUID            `json:"event_ids,omitempty"`
	Confidence float64                `json:"confidence"`
	Metadata   map[string]interface{} `json:"metadata,omitempty"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) CreateRule(ctx context.Context, orgID uuid.UUID, name string, def json.RawMessage) (*Rule, error) {
	if def == nil {
		def = json.RawMessage(`{}`)
	}
	var r Rule
	err := s.pool.QueryRow(ctx, `
		INSERT INTO correlation_rules (org_id, name, definition)
		VALUES ($1,$2,$3)
		RETURNING id, org_id, name, definition, is_enabled, created_at, updated_at`,
		orgID, name, def,
	).Scan(&r.ID, &r.OrgID, &r.Name, &r.Definition, &r.IsEnabled, &r.CreatedAt, &r.UpdatedAt)
	return &r, err
}

func (s *Service) ListRules(ctx context.Context, orgID uuid.UUID) ([]Rule, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, name, definition, is_enabled, created_at, updated_at
		FROM correlation_rules WHERE org_id = $1`, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []Rule
	for rows.Next() {
		var r Rule
		if err := rows.Scan(&r.ID, &r.OrgID, &r.Name, &r.Definition, &r.IsEnabled, &r.CreatedAt, &r.UpdatedAt); err != nil {
			return nil, err
		}
		list = append(list, r)
	}
	return list, rows.Err()
}

// Correlate stub: matches events within a time window by event_type pattern.
func (s *Service) Correlate(ctx context.Context, orgID uuid.UUID, eventIDs []uuid.UUID, window time.Duration) ([]CorrelationResult, error) {
	rules, err := s.ListRules(ctx, orgID)
	if err != nil {
		return nil, err
	}
	var results []CorrelationResult
	for _, rule := range rules {
		if !rule.IsEnabled {
			continue
		}
		results = append(results, CorrelationResult{
			Matched:    len(eventIDs) >= 2,
			RuleID:     rule.ID,
			EventIDs:   eventIDs,
			Confidence: 0.5,
			Metadata:   map[string]interface{}{"stub": true, "window_sec": window.Seconds()},
		})
	}
	return results, nil
}
