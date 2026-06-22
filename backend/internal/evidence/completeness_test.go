package evidence

import (
	"encoding/json"
	"testing"
)

func TestIsComplete_disabledPolicy(t *testing.T) {
	p := Policy{Enabled: false}
	if !IsComplete(json.RawMessage(`{}`), p) {
		t.Fatal("disabled policy should be complete")
	}
}

func TestIsComplete_fullPackage(t *testing.T) {
	p := DefaultPolicy()
	snap := map[string]interface{}{
		"package": map[string]interface{}{
			"clip": map[string]interface{}{"asset_id": "clip-1"},
			"images": []interface{}{
				map[string]interface{}{"role": "scene", "url": "http://x/s"},
				map[string]interface{}{"role": "subject", "asset_id": "sub-1"},
			},
		},
	}
	b, _ := json.Marshal(snap)
	if !IsComplete(b, p) {
		t.Fatal("expected complete")
	}
}

func TestIsComplete_missingClip(t *testing.T) {
	p := DefaultPolicy()
	snap := map[string]interface{}{
		"package": map[string]interface{}{
			"images": []interface{}{
				map[string]interface{}{"role": "scene", "url": "http://x/s"},
				map[string]interface{}{"role": "subject", "asset_id": "sub-1"},
			},
		},
	}
	b, _ := json.Marshal(snap)
	if IsComplete(b, p) {
		t.Fatal("expected incomplete without clip")
	}
}

func TestRequiredSlotCount(t *testing.T) {
	if RequiredSlotCount(DefaultPolicy()) != 3 {
		t.Fatalf("expected 3 slots")
	}
	p := Policy{Enabled: true, ClipSeconds: 0, Images: []map[string]interface{}{{"role": "scene"}}}
	if RequiredSlotCount(p) != 1 {
		t.Fatalf("expected 1 slot")
	}
}
