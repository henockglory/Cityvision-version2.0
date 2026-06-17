package evaluator

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// ConditionNode represents declarative ET/OU/NON (AND/OR/NOT) trees.
type ConditionNode struct {
	Op            string          `json:"op"`
	Field         string          `json:"field,omitempty"`
	Value         json.RawMessage `json:"value,omitempty"`
	Children      []ConditionNode `json:"children,omitempty"`
	WindowSeconds int             `json:"window_seconds,omitempty"`
	KeyFields     []string        `json:"key_fields,omitempty"`
}

type Action struct {
	Type   string          `json:"type"`
	Config json.RawMessage `json:"config,omitempty"`
}

type TimeWindow struct {
	StartHour int      `json:"start_hour"`
	EndHour   int      `json:"end_hour"`
	Days      []string `json:"days,omitempty"`
}

type RuleDefinition struct {
	RuleID         string                 `json:"rule_id"`
	Name           string                 `json:"name"`
	CameraID       string                 `json:"camera_id,omitempty"`
	Enabled        bool                   `json:"enabled"`
	Priority       int                    `json:"priority"`
	SuppressLower  bool                   `json:"suppress_lower"`
	Condition      ConditionNode          `json:"condition"`
	Actions        []Action               `json:"actions"`
	Window         *TimeWindow            `json:"window,omitempty"`
	DedupKeyFields []string               `json:"dedup_key_fields,omitempty"`
	Evidence       map[string]interface{} `json:"evidence,omitempty"`
	Bindings       map[string]interface{} `json:"bindings,omitempty"`
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
	return nil
}

func Evaluate(def RuleDefinition, payload map[string]interface{}, now time.Time, store SequenceStore) (bool, []Action) {
	if !def.Enabled {
		return false, nil
	}
	payload = normalizePayload(payload)
	if def.Window != nil && !inTimeWindow(*def.Window, now) {
		return false, nil
	}
	if strings.EqualFold(def.Condition.Op, "SEQUENCE") {
		if evalSequence(def.Condition, def, payload, now, store) {
			return true, def.Actions
		}
		return false, nil
	}
	if evalCondition(def.Condition, payload) {
		return true, def.Actions
	}
	return false, nil
}

func evalCondition(node ConditionNode, payload map[string]interface{}) bool {
	switch strings.ToUpper(node.Op) {
	case "ET", "AND":
		if len(node.Children) == 0 {
			return false
		}
		for _, c := range node.Children {
			if !evalCondition(c, payload) {
				return false
			}
		}
		return true
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

func inTimeWindow(w TimeWindow, now time.Time) bool {
	if len(w.Days) > 0 {
		day := strings.ToLower(now.Weekday().String()[:3])
		found := false
		for _, d := range w.Days {
			if strings.EqualFold(d, day) {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	h := now.Hour()
	if w.StartHour <= w.EndHour {
		return h >= w.StartHour && h < w.EndHour
	}
	return h >= w.StartHour || h < w.EndHour
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

func DedupKey(def RuleDefinition, payload map[string]interface{}) string {
	payload = normalizePayload(payload)
	fields := def.DedupKeyFields
	if len(fields) == 0 {
		fields = []string{"camera_id", "event_type", "track_id"}
	}
	parts := make([]string, 0, len(fields))
	for _, f := range fields {
		if v, ok := payload[f]; ok {
			parts = append(parts, fmt.Sprintf("%v", v))
		}
	}
	return strings.Join(parts, "|")
}

func normalizePayload(payload map[string]interface{}) map[string]interface{} {
	out := make(map[string]interface{}, len(payload)+2)
	for k, v := range payload {
		out[k] = v
	}
	if _, ok := out["event"]; !ok {
		if et, ok := out["event_type"].(string); ok {
			out["event"] = et
		}
	}
	if _, ok := out["event_type"]; !ok {
		if ev, ok := out["event"].(string); ok {
			out["event_type"] = ev
		}
	}
	return out
}
