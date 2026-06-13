package evaluator

import (
	"encoding/json"
	"testing"
	"time"
)

func TestEvaluateETCondition(t *testing.T) {
	def := RuleDefinition{
		Enabled: true,
		Condition: ConditionNode{
			Op: "ET",
			Children: []ConditionNode{
				{Op: "eq", Field: "event_type", Value: json.RawMessage(`"zone_enter"`)},
				{Op: "eq", Field: "class_name", Value: json.RawMessage(`"person"`)},
			},
		},
		Actions: []Action{{Type: "alert"}},
	}
	payload := map[string]interface{}{
		"event_type":  "zone_enter",
		"class_name":  "person",
		"camera_id":   "cam-1",
		"track_id":    1,
	}
	ok, actions := Evaluate(def, payload, time.Now())
	if !ok || len(actions) != 1 {
		t.Fatalf("expected match, got ok=%v actions=%d", ok, len(actions))
	}
}

func TestEvaluateOUCondition(t *testing.T) {
	def := RuleDefinition{
		Enabled: true,
		Condition: ConditionNode{
			Op: "OU",
			Children: []ConditionNode{
				{Op: "eq", Field: "severity", Value: json.RawMessage(`"critical"`)},
				{Op: "gt", Field: "duration_seconds", Value: json.RawMessage(`120`)},
			},
		},
		Actions: []Action{{Type: "alert"}},
	}
	payload := map[string]interface{}{"duration_seconds": 150.0}
	ok, _ := Evaluate(def, payload, time.Now())
	if !ok {
		t.Fatal("expected OU match on duration")
	}
}

func TestEvaluateNONCondition(t *testing.T) {
	def := RuleDefinition{
		Enabled: true,
		Condition: ConditionNode{
			Op: "NON",
			Children: []ConditionNode{
				{Op: "eq", Field: "class_name", Value: json.RawMessage(`"vehicle"`)},
			},
		},
		Actions: []Action{{Type: "alert"}},
	}
	payload := map[string]interface{}{"class_name": "person"}
	ok, _ := Evaluate(def, payload, time.Now())
	if !ok {
		t.Fatal("expected NON match")
	}
}

func TestTimeWindowBlocks(t *testing.T) {
	def := RuleDefinition{
		Enabled: true,
		Window:  &TimeWindow{StartHour: 22, EndHour: 6},
		Condition: ConditionNode{
			Op: "eq", Field: "event_type", Value: json.RawMessage(`"zone_enter"`),
		},
		Actions: []Action{{Type: "alert"}},
	}
	payload := map[string]interface{}{"event_type": "zone_enter"}
	noon := time.Date(2026, 6, 13, 12, 0, 0, 0, time.UTC)
	ok, _ := Evaluate(def, payload, noon)
	if ok {
		t.Fatal("expected time window to block evaluation at noon")
	}
}

func TestDedupKey(t *testing.T) {
	def := RuleDefinition{DedupKeyFields: []string{"camera_id", "track_id"}}
	payload := map[string]interface{}{"camera_id": "cam-1", "track_id": 42}
	key := DedupKey(def, payload)
	if key != "cam-1|42" {
		t.Fatalf("unexpected dedup key: %s", key)
	}
}
