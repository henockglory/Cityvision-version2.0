package rules_test

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/citevision/citevision-v2/backend/internal/rules"
)

func TestValidateDefinitionAND(t *testing.T) {
	def := json.RawMessage(`{
		"condition": {
			"op": "AND",
			"children": [
				{"op": "in_zone", "field": "zone_id", "value": "zone-1"},
				{"op": "eq", "field": "class", "value": "person"}
			]
		},
		"actions": [{"type": "alert", "config": {"severity": "high"}}]
	}`)
	if err := rules.ValidateDefinition(def); err != nil {
		t.Fatalf("expected valid definition: %v", err)
	}
}

func TestValidateDefinitionMissingAction(t *testing.T) {
	def := json.RawMessage(`{
		"condition": {"op": "eq", "field": "class", "value": "person"},
		"actions": []
	}`)
	if err := rules.ValidateDefinition(def); err == nil {
		t.Fatal("expected error for empty actions")
	}
}

func TestValidateDefinitionInvalidJSON(t *testing.T) {
	if err := rules.ValidateDefinition(json.RawMessage(`{invalid`)); err == nil {
		t.Fatal("expected JSON error")
	}
}

func TestValidateDefinitionMissingActionType(t *testing.T) {
	def := json.RawMessage(`{
		"condition": {"op": "eq", "field": "class", "value": "person"},
		"actions": [{"type": "", "config": {}}]
	}`)
	if err := rules.ValidateDefinition(def); err == nil {
		t.Fatal("expected error for empty action type")
	}
}

func TestEvaluateDefinitionMatch(t *testing.T) {
	def := json.RawMessage(`{
		"condition": {"op": "eq", "field": "class", "value": "person"},
		"actions": [{"type": "alert", "config": {"severity": "high"}}]
	}`)
	resp, err := rules.EvaluateDefinition(def, map[string]interface{}{"class": "person"}, time.Now())
	if err != nil {
		t.Fatalf("evaluate: %v", err)
	}
	if !resp.Matched || len(resp.Actions) != 1 {
		t.Fatalf("expected match with 1 action, got %+v", resp)
	}
}

func TestEvaluateDefinitionNoMatch(t *testing.T) {
	def := json.RawMessage(`{
		"condition": {"op": "eq", "field": "class", "value": "person"},
		"actions": [{"type": "alert", "config": {}}]
	}`)
	resp, err := rules.EvaluateDefinition(def, map[string]interface{}{"class": "vehicle"}, time.Now())
	if err != nil {
		t.Fatalf("evaluate: %v", err)
	}
	if resp.Matched {
		t.Fatal("expected no match")
	}
}
