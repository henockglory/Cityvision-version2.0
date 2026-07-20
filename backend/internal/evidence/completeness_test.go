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

func TestIsComplete_plateOptionalForViolation(t *testing.T) {
	// Tâche 4: plate in policy must NOT block violation_confirmed / IsComplete.
	p := Policy{
		Enabled:     true,
		ClipSeconds: 6,
		Images: []map[string]interface{}{
			{"role": "scene"},
			{"role": "subject"},
			{"role": "plate"},
		},
	}
	snap := map[string]interface{}{
		"package": map[string]interface{}{
			"clip": map[string]interface{}{"asset_id": "clip-1"},
			"images": []interface{}{
				map[string]interface{}{"role": "scene", "url": "http://x/s"},
				map[string]interface{}{"role": "subject", "asset_id": "sub-1"},
				// Degraded / present plate crop but no OCR text → still violation-complete.
				map[string]interface{}{"role": "plate", "asset_id": "plt-blur"},
			},
		},
	}
	b, _ := json.Marshal(snap)
	if !IsComplete(b, p) {
		t.Fatal("missing readable plate must not block violation completeness")
	}
	var m map[string]interface{}
	_ = json.Unmarshal(b, &m)
	if got := PlateStatus(m, p, ""); got != IdentificationUnreadable {
		t.Fatalf("plate_status want unreadable got %s", got)
	}
	if got := ViolationStatusFromSnap(m, p); got != ViolationConfirmed {
		t.Fatalf("violation_status want confirmed got %s", got)
	}
}

func TestPlateStatus_verifiedRequiresNumber(t *testing.T) {
	p := Policy{
		Enabled: true, ClipSeconds: 6,
		Images: []map[string]interface{}{
			{"role": "scene"}, {"role": "subject"}, {"role": "plate"},
		},
	}
	snap := map[string]interface{}{
		"package": map[string]interface{}{
			"clip": map[string]interface{}{"asset_id": "c"},
			"images": []interface{}{
				map[string]interface{}{"role": "scene", "url": "s"},
				map[string]interface{}{"role": "subject", "url": "u"},
				map[string]interface{}{"role": "plate", "url": "p"},
			},
		},
	}
	if PlateStatus(snap, p, "") != IdentificationUnreadable {
		t.Fatal("image without OCR must be unreadable, never verified")
	}
	if PlateStatus(snap, p, "AB-123-CD") != IdentificationVerified {
		t.Fatal("real plate_number must be verified")
	}
	snapNoPlate := map[string]interface{}{
		"package": map[string]interface{}{
			"clip": map[string]interface{}{"asset_id": "c"},
			"images": []interface{}{
				map[string]interface{}{"role": "scene", "url": "s"},
				map[string]interface{}{"role": "subject", "url": "u"},
			},
		},
	}
	if PlateStatus(snapNoPlate, p, "") != IdentificationMissing {
		t.Fatal("no plate crop → missing")
	}
}

func TestAnnotateStatuses(t *testing.T) {
	p := Policy{
		Enabled: true, ClipSeconds: 6,
		Images: []map[string]interface{}{
			{"role": "scene"}, {"role": "subject"}, {"role": "plate"},
		},
	}
	raw, _ := json.Marshal(map[string]interface{}{
		"package": map[string]interface{}{
			"clip": map[string]interface{}{"asset_id": "c"},
			"images": []interface{}{
				map[string]interface{}{"role": "scene", "url": "s"},
				map[string]interface{}{"role": "subject", "url": "u"},
				map[string]interface{}{"role": "plate", "asset_id": "blur"},
			},
			"metadata": map[string]interface{}{},
		},
	})
	out := AnnotateStatuses(raw, p, "")
	var m map[string]interface{}
	_ = json.Unmarshal(out, &m)
	if m["violation_status"] != ViolationConfirmed {
		t.Fatalf("violation_status=%v", m["violation_status"])
	}
	if m["identification"] != IdentificationUnreadable || m["plate_status"] != IdentificationUnreadable {
		t.Fatalf("identification=%v plate_status=%v", m["identification"], m["plate_status"])
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
