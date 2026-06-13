package rules

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

var ErrNotFound = errors.New("rule not found")

type RuleDefinition struct {
	Condition ConditionNode `json:"condition"`
	Actions   []Action      `json:"actions"`
	Window    *TimeWindow   `json:"window,omitempty"`
}

type ConditionNode struct {
	Op       string          `json:"op"`
	Field    string          `json:"field,omitempty"`
	Value    json.RawMessage `json:"value,omitempty"`
	Children []ConditionNode `json:"children,omitempty"`
}

type Action struct {
	Type   string          `json:"type"`
	Config json.RawMessage `json:"config"`
}

type TimeWindow struct {
	StartHour int      `json:"start_hour"`
	EndHour   int      `json:"end_hour"`
	Days      []string `json:"days,omitempty"`
}

type EvaluateRequest struct {
	Definition  json.RawMessage        `json:"definition,omitempty"`
	EventPayload map[string]interface{} `json:"event_payload"`
}

type EvaluateResponse struct {
	Matched bool     `json:"matched"`
	Actions []Action `json:"actions,omitempty"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) Create(ctx context.Context, orgID uuid.UUID, siteID *uuid.UUID, name, desc string, def json.RawMessage, priority int) (*models.Rule, error) {
	if err := ValidateDefinition(def); err != nil {
		return nil, err
	}
	var d *string
	if desc != "" {
		d = &desc
	}
	var r models.Rule
	err := s.pool.QueryRow(ctx, `
		INSERT INTO rules (org_id, site_id, name, description, definition, priority)
		VALUES ($1,$2,$3,$4,$5,$6)
		RETURNING id, org_id, site_id, name, description, definition, is_enabled, priority, created_at, updated_at`,
		orgID, siteID, name, d, def, priority,
	).Scan(&r.ID, &r.OrgID, &r.SiteID, &r.Name, &r.Description, &r.Definition, &r.IsEnabled, &r.Priority, &r.CreatedAt, &r.UpdatedAt)
	return &r, err
}

func (s *Service) List(ctx context.Context, orgID uuid.UUID) ([]models.Rule, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, site_id, name, description, definition, is_enabled, priority, created_at, updated_at
		FROM rules WHERE org_id = $1 ORDER BY priority DESC, name`, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []models.Rule
	for rows.Next() {
		var r models.Rule
		if err := rows.Scan(&r.ID, &r.OrgID, &r.SiteID, &r.Name, &r.Description, &r.Definition, &r.IsEnabled, &r.Priority, &r.CreatedAt, &r.UpdatedAt); err != nil {
			return nil, err
		}
		list = append(list, r)
	}
	return list, rows.Err()
}

func (s *Service) ListActive(ctx context.Context, orgID uuid.UUID, siteID *uuid.UUID) ([]models.Rule, error) {
	q := `
		SELECT id, org_id, site_id, name, description, definition, is_enabled, priority, created_at, updated_at
		FROM rules WHERE org_id = $1 AND is_enabled = TRUE`
	args := []interface{}{orgID}
	if siteID != nil {
		q += ` AND (site_id IS NULL OR site_id = $2)`
		args = append(args, *siteID)
	}
	q += ` ORDER BY priority DESC, name`

	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []models.Rule
	for rows.Next() {
		var r models.Rule
		if err := rows.Scan(&r.ID, &r.OrgID, &r.SiteID, &r.Name, &r.Description, &r.Definition, &r.IsEnabled, &r.Priority, &r.CreatedAt, &r.UpdatedAt); err != nil {
			return nil, err
		}
		list = append(list, r)
	}
	return list, rows.Err()
}

func (s *Service) Get(ctx context.Context, orgID, id uuid.UUID) (*models.Rule, error) {
	var r models.Rule
	err := s.pool.QueryRow(ctx, `
		SELECT id, org_id, site_id, name, description, definition, is_enabled, priority, created_at, updated_at
		FROM rules WHERE id = $1 AND org_id = $2`, id, orgID,
	).Scan(&r.ID, &r.OrgID, &r.SiteID, &r.Name, &r.Description, &r.Definition, &r.IsEnabled, &r.Priority, &r.CreatedAt, &r.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &r, err
}

func ValidateDefinition(raw json.RawMessage) error {
	var def RuleDefinition
	if err := json.Unmarshal(raw, &def); err != nil {
		return fmt.Errorf("invalid rule definition: %w", err)
	}
	if def.Condition.Op == "" {
		return fmt.Errorf("condition op is required")
	}
	if len(def.Actions) == 0 {
		return fmt.Errorf("at least one action is required")
	}
	for _, a := range def.Actions {
		if a.Type == "" {
			return fmt.Errorf("action type is required")
		}
	}
	return nil
}

func EvaluateDefinition(raw json.RawMessage, eventPayload map[string]interface{}, now time.Time) (EvaluateResponse, error) {
	var def RuleDefinition
	if err := json.Unmarshal(raw, &def); err != nil {
		return EvaluateResponse{}, fmt.Errorf("invalid rule definition: %w", err)
	}
	matched, actions := Evaluate(def, eventPayload, now)
	return EvaluateResponse{Matched: matched, Actions: actions}, nil
}

func Evaluate(def RuleDefinition, eventPayload map[string]interface{}, now time.Time) (bool, []Action) {
	if def.Window != nil && !inTimeWindow(*def.Window, now) {
		return false, nil
	}
	if evalCondition(def.Condition, eventPayload) {
		return true, def.Actions
	}
	return false, nil
}

func evalCondition(node ConditionNode, payload map[string]interface{}) bool {
	switch node.Op {
	case "AND":
		for _, c := range node.Children {
			if !evalCondition(c, payload) {
				return false
			}
		}
		return len(node.Children) > 0
	case "OR":
		for _, c := range node.Children {
			if evalCondition(c, payload) {
				return true
			}
		}
		return false
	case "NOT":
		if len(node.Children) == 1 {
			return !evalCondition(node.Children[0], payload)
		}
		return false
	case "eq":
		v, ok := payload[node.Field]
		if !ok {
			return false
		}
		var expected interface{}
		_ = json.Unmarshal(node.Value, &expected)
		return fmt.Sprintf("%v", v) == fmt.Sprintf("%v", expected)
	default:
		return false
	}
}

func inTimeWindow(w TimeWindow, now time.Time) bool {
	h := now.Hour()
	if w.StartHour <= w.EndHour {
		return h >= w.StartHour && h < w.EndHour
	}
	return h >= w.StartHour || h < w.EndHour
}
