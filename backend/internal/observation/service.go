package observation

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Counter is a unified observation tally for UI display.
type Counter struct {
	ID           string            `json:"id"`
	Kind         string            `json:"kind"`
	LabelFR      string            `json:"label_fr"`
	LabelEN      string            `json:"label_en"`
	LegendFR     string            `json:"legend_fr"`
	LegendEN     string            `json:"legend_en"`
	Count        int64             `json:"count"`
	CountIn      int64             `json:"count_in,omitempty"`
	CountOut     int64             `json:"count_out,omitempty"`
	LastClass    string            `json:"last_class,omitempty"`
	Scope        map[string]string `json:"scope,omitempty"`
	SourceRuleID *uuid.UUID        `json:"source_rule_id,omitempty"`
	UpdatedAt    time.Time         `json:"updated_at"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) ListCounters(ctx context.Context, orgID uuid.UUID, cameraID *uuid.UUID) ([]Counter, error) {
	out := make([]Counter, 0)
	lineRows, err := s.listLineCounters(ctx, orgID, cameraID)
	if err != nil {
		return nil, err
	}
	out = append(out, lineRows...)
	ruleRows, err := s.listRuleCounters(ctx, orgID, cameraID)
	if err != nil {
		return nil, err
	}
	out = append(out, ruleRows...)
	return out, nil
}

func (s *Service) listLineCounters(ctx context.Context, orgID uuid.UUID, cameraID *uuid.UUID) ([]Counter, error) {
	q := `SELECT lc.line_id, lc.class_filter, lc.count_in, lc.count_out, lc.count_total, lc.last_class, lc.updated_at,
		COALESCE(l.behavior_config->>'class_filter', '') AS line_class_cfg
		FROM line_counters lc
		LEFT JOIN lines l ON l.org_id = lc.org_id AND l.camera_id = lc.camera_id AND l.name = lc.line_id
		WHERE lc.org_id = $1`
	args := []interface{}{orgID}
	if cameraID != nil {
		q += ` AND lc.camera_id = $2`
		args = append(args, *cameraID)
	}
	q += ` ORDER BY lc.line_id, lc.class_filter`
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]Counter, 0)
	for rows.Next() {
		var lineID, classFilter, lastClass, lineClassCfg string
		var countIn, countOut, countTotal int64
		var updatedAt time.Time
		if err := rows.Scan(&lineID, &classFilter, &countIn, &countOut, &countTotal, &lastClass, &updatedAt, &lineClassCfg); err != nil {
			return nil, err
		}
		kind := "line"
		if classFilter != "" {
			kind = "line_class"
		}
		classLabel := classFilter
		if classLabel == "" && lineClassCfg != "" && lineClassCfg != "any" {
			classLabel = lineClassCfg
		}
		labelFR := fmt.Sprintf("Ligne · %s", lineID)
		labelEN := fmt.Sprintf("Line · %s", lineID)
		legendFR := fmt.Sprintf("Franchissements cumulés sur la ligne « %s ».", lineID)
		legendEN := fmt.Sprintf("Cumulative crossings on line « %s ».", lineID)
		if classFilter != "" {
			labelFR = fmt.Sprintf("Ligne · %s · %s", lineID, classFilter)
			labelEN = fmt.Sprintf("Line · %s · %s", lineID, classFilter)
			legendFR = fmt.Sprintf("Passages de type « %s » sur la ligne « %s ».", classFilter, lineID)
			legendEN = fmt.Sprintf("Crossings of class « %s » on line « %s ».", classFilter, lineID)
		} else if classLabel != "" {
			legendFR += fmt.Sprintf(" Filtre ligne : %s.", classLabel)
			legendEN += fmt.Sprintf(" Line filter: %s.", classLabel)
		}
		id := fmt.Sprintf("line:%s:%s", lineID, classFilter)
		out = append(out, Counter{
			ID: id, Kind: kind, LabelFR: labelFR, LabelEN: labelEN,
			LegendFR: legendFR, LegendEN: legendEN,
			Count: countTotal, CountIn: countIn, CountOut: countOut, LastClass: lastClass,
			Scope: map[string]string{"line_name": lineID, "class_filter": classFilter},
			UpdatedAt: updatedAt,
		})
	}
	return out, rows.Err()
}

func (s *Service) listRuleCounters(ctx context.Context, orgID uuid.UUID, cameraID *uuid.UUID) ([]Counter, error) {
	q := `SELECT r.id, r.name, r.definition, COALESCE(rc.count, 0), COALESCE(rc.last_event_type, ''),
		COALESCE(rc.last_class, ''), COALESCE(rc.last_zone_id, ''), COALESCE(rc.last_line_id, ''),
		COALESCE(rc.updated_at, r.updated_at)
		FROM rules r
		LEFT JOIN rule_counters rc ON rc.org_id = r.org_id AND rc.rule_id = r.id
		WHERE r.org_id = $1 AND r.is_enabled = TRUE`
	args := []interface{}{orgID}
	if cameraID != nil {
		q += ` AND (r.definition->>'camera_id' = $2 OR r.definition->'bindings'->>'camera_id' = $2)`
		args = append(args, cameraID.String())
	}
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]Counter, 0)
	for rows.Next() {
		var ruleID uuid.UUID
		var name string
		var defRaw []byte
		var count int64
		var lastEvent, lastClass, lastZone, lastLine string
		var updatedAt time.Time
		if err := rows.Scan(&ruleID, &name, &defRaw, &count, &lastEvent, &lastClass, &lastZone, &lastLine, &updatedAt); err != nil {
			return nil, err
		}
		var def map[string]interface{}
		_ = json.Unmarshal(defRaw, &def)
		bindings, _ := def["bindings"].(map[string]interface{})
		if !isObservationRule(def, bindings) {
			continue
		}
		kind := observationKind(bindings)
		labelFR := strBinding(bindings, "observation_label_fr")
		labelEN := strBinding(bindings, "observation_label_en")
		if labelFR == "" {
			labelFR = name
		}
		if labelEN == "" {
			labelEN = name
		}
		legendFR := buildLegendFR(kind, bindings, name)
		legendEN := buildLegendEN(kind, bindings, name)
		scope := map[string]string{}
		if z := strBinding(bindings, "zone_name"); z != "" {
			scope["zone_name"] = z
		}
		if l := strBinding(bindings, "line_name"); l != "" {
			scope["line_name"] = l
		}
		if cf := strBinding(bindings, "class_filter"); cf != "" {
			scope["class_filter"] = cf
		}
		if lastEvent != "" {
			scope["last_event_type"] = lastEvent
		}
		rid := ruleID
		out = append(out, Counter{
			ID:           "rule:" + ruleID.String(),
			Kind:         kind,
			LabelFR:      labelFR,
			LabelEN:      labelEN,
			LegendFR:     legendFR,
			LegendEN:     legendEN,
			Count:        count,
			LastClass:    lastClass,
			Scope:        scope,
			SourceRuleID: &rid,
			UpdatedAt:    updatedAt,
		})
	}
	return out, rows.Err()
}

func isObservationRule(def map[string]interface{}, bindings map[string]interface{}) bool {
	if bindings != nil {
		if v, ok := bindings["observation_mode"].(bool); ok && v {
			return true
		}
	}
	if hasActionType(def, "counter") {
		return true
	}
	return false
}

func hasActionType(def map[string]interface{}, typ string) bool {
	actions, ok := def["actions"].([]interface{})
	if !ok {
		return false
	}
	for _, a := range actions {
		m, ok := a.(map[string]interface{})
		if !ok {
			continue
		}
		if t, _ := m["type"].(string); t == typ {
			return true
		}
	}
	return false
}

func observationKind(bindings map[string]interface{}) string {
	if bindings == nil {
		return "rule"
	}
	k := strBinding(bindings, "observation_kind")
	if k == "" {
		return "rule"
	}
	return k
}

func strBinding(bindings map[string]interface{}, key string) string {
	if bindings == nil {
		return ""
	}
	v, ok := bindings[key]
	if !ok || v == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(v))
}

func buildLegendFR(kind string, bindings map[string]interface{}, name string) string {
	switch kind {
	case "line_cross":
		return fmt.Sprintf("Comptage observation · franchissements ligne (%s).", name)
	case "rule_set_or":
		return fmt.Sprintf("Comptage ensemble OU · %s.", name)
	case "rule_set_n":
		return fmt.Sprintf("Comptage N-sur-M · %s.", name)
	case "event":
		return fmt.Sprintf("Comptage observation · occurrences événement (%s).", name)
	default:
		return fmt.Sprintf("Comptage observation · règle « %s ».", name)
	}
}

func buildLegendEN(kind string, bindings map[string]interface{}, name string) string {
	switch kind {
	case "line_cross":
		return fmt.Sprintf("Observation count · line crossings (%s).", name)
	case "rule_set_or":
		return fmt.Sprintf("OR set count · %s.", name)
	case "rule_set_n":
		return fmt.Sprintf("N-of-M set count · %s.", name)
	case "event":
		return fmt.Sprintf("Observation count · event occurrences (%s).", name)
	default:
		return fmt.Sprintf("Observation count · rule « %s ».", name)
	}
}

// ResetCounters clears tallies. kind/id optional for selective reset.
func (s *Service) ResetCounters(ctx context.Context, orgID uuid.UUID, cameraID *uuid.UUID, kind, id string) error {
	if kind == "rule" || strings.HasPrefix(id, "rule:") {
		ruleIDStr := strings.TrimPrefix(id, "rule:")
		if ruleIDStr == "" && kind == "rule" {
			return fmt.Errorf("rule id required")
		}
		ruleID, err := uuid.Parse(ruleIDStr)
		if err != nil {
			return err
		}
		_, err = s.pool.Exec(ctx, `DELETE FROM rule_counters WHERE org_id = $1 AND rule_id = $2`, orgID, ruleID)
		return err
	}
	if strings.HasPrefix(id, "line:") {
		parts := strings.SplitN(id, ":", 3)
		if len(parts) >= 2 {
			lineID := parts[1]
			classFilter := ""
			if len(parts) >= 3 {
				classFilter = parts[2]
			}
			if cameraID != nil {
				_, err := s.pool.Exec(ctx,
					`DELETE FROM line_counters WHERE org_id = $1 AND camera_id = $2 AND line_id = $3 AND class_filter = $4`,
					orgID, *cameraID, lineID, classFilter)
				return err
			}
		}
	}
	if cameraID != nil {
		if _, err := s.pool.Exec(ctx, `DELETE FROM line_counters WHERE org_id = $1 AND camera_id = $2`, orgID, *cameraID); err != nil {
			return err
		}
		_, err := s.pool.Exec(ctx, `
			DELETE FROM rule_counters rc USING rules r
			WHERE rc.org_id = $1 AND r.id = rc.rule_id AND r.org_id = $1
			AND (r.definition->>'camera_id' = $2 OR r.definition->'bindings'->>'camera_id' = $2)`,
			orgID, cameraID.String())
		return err
	}
	if _, err := s.pool.Exec(ctx, `DELETE FROM line_counters WHERE org_id = $1`, orgID); err != nil {
		return err
	}
	_, err := s.pool.Exec(ctx, `DELETE FROM rule_counters WHERE org_id = $1`, orgID)
	return err
}
