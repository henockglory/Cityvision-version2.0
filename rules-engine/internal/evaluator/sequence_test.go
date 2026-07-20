package evaluator

import (
	"encoding/json"
	"testing"
	"time"
)

func TestEvaluateSequenceTwoSteps(t *testing.T) {
	store := NewMemorySequenceStore()
	def := RuleDefinition{
		RuleID:  "rule-seq-1",
		Enabled: true,
		Condition: ConditionNode{
			Op:            "SEQUENCE",
			WindowSeconds: 120,
			KeyFields:     []string{"camera_id", "track_id"},
			Children: []ConditionNode{
				{Op: "eq", Field: "event_type", Value: json.RawMessage(`"zone_enter"`)},
				{Op: "eq", Field: "event_type", Value: json.RawMessage(`"loitering"`)},
			},
		},
		Actions: []Action{{Type: "alert"}},
	}
	now := time.Date(2026, 6, 15, 10, 0, 0, 0, time.UTC)
	payload := map[string]interface{}{
		"camera_id":  "cam-1",
		"track_id":   7,
		"event_type": "zone_enter",
	}

	ok, _ := Evaluate(def, payload, now, store)
	if ok {
		t.Fatal("expected first step to not complete sequence")
	}

	payload["event_type"] = "loitering"
	ok, actions := Evaluate(def, payload, now.Add(30*time.Second), store)
	if !ok || len(actions) != 1 {
		t.Fatalf("expected sequence completion, ok=%v actions=%d", ok, len(actions))
	}
}

func TestEvaluateSequenceExpires(t *testing.T) {
	store := NewMemorySequenceStore()
	def := RuleDefinition{
		RuleID:  "rule-seq-2",
		Enabled: true,
		Condition: ConditionNode{
			Op:            "SEQUENCE",
			WindowSeconds: 60,
			KeyFields:     []string{"camera_id", "track_id"},
			Children: []ConditionNode{
				{Op: "eq", Field: "event_type", Value: json.RawMessage(`"zone_enter"`)},
				{Op: "eq", Field: "event_type", Value: json.RawMessage(`"loitering"`)},
			},
		},
		Actions: []Action{{Type: "alert"}},
	}
	start := time.Date(2026, 6, 15, 10, 0, 0, 0, time.UTC)
	payload := map[string]interface{}{
		"camera_id":  "cam-1",
		"track_id":   3,
		"event_type": "zone_enter",
	}
	_, _ = Evaluate(def, payload, start, store)

	payload["event_type"] = "loitering"
	ok, _ := Evaluate(def, payload, start.Add(2*time.Minute), store)
	if ok {
		t.Fatal("expected expired sequence to not match")
	}
}
