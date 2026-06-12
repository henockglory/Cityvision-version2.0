package rules_test

import (
	"encoding/json"
	"testing"

	"github.com/citevision/citevision/backend/internal/rules"
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
