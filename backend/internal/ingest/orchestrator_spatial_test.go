package ingest

import "testing"

// TestSpatialConfigKeys documents the AI ingest spatial payload contract.
func TestSpatialConfigKeys(t *testing.T) {
	expected := []string{"zones", "lines", "presence_rules"}
	shape := map[string]interface{}{
		"zones":          []interface{}{},
		"lines":          []interface{}{},
		"presence_rules": []interface{}{},
	}
	for _, key := range expected {
		if _, ok := shape[key]; !ok {
			t.Errorf("spatial config must include %q", key)
		}
	}
}
