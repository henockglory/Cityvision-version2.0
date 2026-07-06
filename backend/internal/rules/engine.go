package rules

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
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
		FROM rules WHERE org_id = $1 ORDER BY created_at ASC, name ASC`, orgID)
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

func (s *Service) Update(ctx context.Context, orgID, id uuid.UUID, isEnabled *bool, priority *int, name *string, desc *string, def json.RawMessage) (*models.Rule, error) {
	if isEnabled == nil && priority == nil && name == nil && desc == nil && def == nil {
		return s.Get(ctx, orgID, id)
	}
	if def != nil {
		if err := ValidateDefinition(def); err != nil {
			return nil, err
		}
	}
	q := `UPDATE rules SET updated_at = NOW()`
	args := []interface{}{}
	n := 1
	if isEnabled != nil {
		q += `, is_enabled = $` + fmt.Sprintf("%d", n)
		args = append(args, *isEnabled)
		n++
	}
	if priority != nil {
		q += `, priority = $` + fmt.Sprintf("%d", n)
		args = append(args, *priority)
		n++
	}
	if name != nil {
		q += `, name = $` + fmt.Sprintf("%d", n)
		args = append(args, *name)
		n++
	}
	if desc != nil {
		q += `, description = $` + fmt.Sprintf("%d", n)
		args = append(args, *desc)
		n++
	}
	if def != nil {
		q += `, definition = $` + fmt.Sprintf("%d", n)
		args = append(args, def)
		n++
	}
	q += ` WHERE id = $` + fmt.Sprintf("%d", n) + ` AND org_id = $` + fmt.Sprintf("%d", n+1)
	args = append(args, id, orgID)

	var r models.Rule
	err := s.pool.QueryRow(ctx, q+`
		RETURNING id, org_id, site_id, name, description, definition, is_enabled, priority, created_at, updated_at`,
		args...,
	).Scan(&r.ID, &r.OrgID, &r.SiteID, &r.Name, &r.Description, &r.Definition, &r.IsEnabled, &r.Priority, &r.CreatedAt, &r.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &r, err
}

func (s *Service) Delete(ctx context.Context, orgID, id uuid.UUID) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM rules WHERE id = $1 AND org_id = $2`, id, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
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
	return validateDefinitionMap(raw)
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
	switch strings.ToUpper(node.Op) {
	case "ET", "AND":
		for _, c := range node.Children {
			if !evalCondition(c, payload) {
				return false
			}
		}
		return len(node.Children) > 0
	case "OU", "OR":
		for _, c := range node.Children {
			if evalCondition(c, payload) {
				return true
			}
		}
		return false
	case "NON", "NOT":
		if len(node.Children) == 1 {
			return !evalCondition(node.Children[0], payload)
		}
		return false
	case "EQ":
		v, ok := fieldValue(payload, node.Field)
		if !ok {
			return false
		}
		var expected interface{}
		_ = json.Unmarshal(node.Value, &expected)
		return fmt.Sprintf("%v", v) == fmt.Sprintf("%v", expected)
	case "NEQ", "NE":
		v, ok := fieldValue(payload, node.Field)
		if !ok {
			return true
		}
		var expected interface{}
		_ = json.Unmarshal(node.Value, &expected)
		return fmt.Sprintf("%v", v) != fmt.Sprintf("%v", expected)
	case "GT":
		raw, ok := fieldValue(payload, node.Field)
		if !ok {
			return false
		}
		v, ok := toFloat(raw)
		if !ok {
			return false
		}
		var expected float64
		_ = json.Unmarshal(node.Value, &expected)
		return v > expected
	case "GTE", "GE":
		raw, ok := fieldValue(payload, node.Field)
		if !ok {
			return false
		}
		v, ok := toFloat(raw)
		if !ok {
			return false
		}
		var expected float64
		_ = json.Unmarshal(node.Value, &expected)
		return v >= expected
	case "LT":
		raw, ok := fieldValue(payload, node.Field)
		if !ok {
			return false
		}
		v, ok := toFloat(raw)
		if !ok {
			return false
		}
		var expected float64
		_ = json.Unmarshal(node.Value, &expected)
		return v < expected
	case "LTE", "LE":
		raw, ok := fieldValue(payload, node.Field)
		if !ok {
			return false
		}
		v, ok := toFloat(raw)
		if !ok {
			return false
		}
		var expected float64
		_ = json.Unmarshal(node.Value, &expected)
		return v <= expected
	case "CONTAINS":
		v, ok := fieldValue(payload, node.Field)
		if !ok {
			return false
		}
		var expected string
		_ = json.Unmarshal(node.Value, &expected)
		return strings.Contains(fmt.Sprintf("%v", v), expected)
	case "IN_ZONE", "CROSS_LINE":
		v, ok := fieldValue(payload, node.Field)
		if !ok {
			return false
		}
		var expected interface{}
		_ = json.Unmarshal(node.Value, &expected)
		return fmt.Sprintf("%v", v) == fmt.Sprintf("%v", expected)
	case "MATCHES_CLASS":
		v, ok := fieldValue(payload, node.Field)
		if !ok {
			return false
		}
		var expected string
		_ = json.Unmarshal(node.Value, &expected)
		return matchesClass(fmt.Sprintf("%v", v), expected)
	default:
		return false
	}
}

func fieldValue(payload map[string]interface{}, field string) (interface{}, bool) {
	if field == "" {
		return nil, false
	}
	if !strings.Contains(field, ".") {
		v, ok := payload[field]
		return v, ok
	}
	var cur interface{} = payload
	for _, part := range strings.Split(field, ".") {
		m, ok := cur.(map[string]interface{})
		if !ok {
			return nil, false
		}
		cur, ok = m[part]
		if !ok {
			return nil, false
		}
	}
	return cur, true
}

func toFloat(v interface{}) (float64, bool) {
	switch n := v.(type) {
	case float64:
		return n, true
	case float32:
		return float64(n), true
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	default:
		return 0, false
	}
}

func inTimeWindow(w TimeWindow, now time.Time) bool {
	h := now.Hour()
	if w.StartHour <= w.EndHour {
		return h >= w.StartHour && h < w.EndHour
	}
	return h >= w.StartHour || h < w.EndHour
}

func (s *Service) DisableAll(ctx context.Context, orgID uuid.UUID) (int64, error) {
	tag, err := s.pool.Exec(ctx, `UPDATE rules SET is_enabled = FALSE, updated_at = NOW() WHERE org_id = $1 AND is_enabled = TRUE`, orgID)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

// PurgeNonUserRules deletes rules not explicitly created by a user (bindings.origin != "user").
func (s *Service) PurgeNonUserRules(ctx context.Context, orgID uuid.UUID) (int64, error) {
	tag, err := s.pool.Exec(ctx, `
		DELETE FROM rules
		WHERE org_id = $1
		  AND COALESCE(definition->'bindings'->>'origin', '') <> 'user'`, orgID)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

// StampUserOrigin ensures definition.bindings.origin is "user" for API-created rules.
func StampUserOrigin(def json.RawMessage) json.RawMessage {
	if len(def) == 0 {
		def = []byte(`{}`)
	}
	var root map[string]interface{}
	if err := json.Unmarshal(def, &root); err != nil {
		return def
	}
	bindings, _ := root["bindings"].(map[string]interface{})
	if bindings == nil {
		bindings = map[string]interface{}{}
		root["bindings"] = bindings
	}
	if origin, ok := bindings["origin"].(string); !ok || origin == "" {
		bindings["origin"] = "user"
	}
	out, err := json.Marshal(root)
	if err != nil {
		return def
	}
	return out
}
