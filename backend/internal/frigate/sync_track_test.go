package frigate

import (
	"testing"
)

func TestTrackLabelsFromRuleDefinitionClassFilter(t *testing.T) {
	def := map[string]interface{}{
		"bindings": map[string]interface{}{
			"class_filter": "person",
			"track_objects": []interface{}{"backpack", "suitcase"},
		},
	}
	person, labels := trackLabelsFromRuleDefinition(def)
	if !person {
		t.Fatal("expected TrackPerson from class_filter=person")
	}
	found := map[string]bool{}
	for _, lab := range labels {
		found[lab] = true
	}
	if !found["backpack"] || !found["suitcase"] {
		t.Fatalf("expected bag labels, got %v", labels)
	}
}

func TestTrackLabelsFromRuleDefinitionVehicleGroup(t *testing.T) {
	def := map[string]interface{}{
		"bindings": map[string]interface{}{
			"class_filter": "vehicle",
		},
	}
	person, labels := trackLabelsFromRuleDefinition(def)
	if person {
		t.Fatal("vehicle group should not force person")
	}
	found := map[string]bool{}
	for _, lab := range labels {
		found[lab] = true
	}
	for _, want := range []string{"car", "truck", "bus", "motorcycle"} {
		if !found[want] {
			t.Fatalf("expected %s from vehicle group, got %v", want, labels)
		}
	}
}

func TestTrackLabelsFromMatchesClassCondition(t *testing.T) {
	def := map[string]interface{}{
		"condition": map[string]interface{}{
			"op": "and",
			"args": []interface{}{
				map[string]interface{}{
					"op":    "matches_class",
					"value": "motorcycle",
				},
			},
		},
	}
	_, labels := trackLabelsFromRuleDefinition(def)
	found := false
	for _, lab := range labels {
		if lab == "motorcycle" {
			found = true
		}
	}
	if !found {
		t.Fatalf("expected motorcycle from matches_class, got %v", labels)
	}
}

func TestTrackLabelsFromMemberEventTypes(t *testing.T) {
	def := map[string]interface{}{
		"condition": map[string]interface{}{
			"op": "RULE_SET",
			"member_event_types": []interface{}{"face_watchlist_match", "plate_detected"},
			"children": []interface{}{
				map[string]interface{}{"op": "eq", "field": "event_type", "value": "face_watchlist_match"},
				map[string]interface{}{"op": "eq", "field": "event_type", "value": "plate_detected"},
			},
		},
	}
	person, labels := trackLabelsFromRuleDefinition(def)
	if !person {
		t.Fatal("expected TrackPerson from face_watchlist_match member")
	}
	found := map[string]bool{}
	for _, lab := range labels {
		found[lab] = true
	}
	if !found["car"] {
		t.Fatalf("expected car from plate_detected member, got %v", labels)
	}
}
