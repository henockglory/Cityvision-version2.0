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
				map[string]interface{}{"role": "plate", "asset_id": "plt-1"},
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

func TestIsComplete_plateOptionalWithoutFailClosed(t *testing.T) {
	// Plate listed in images but NOT in fail_closed → soft identification only.
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
			},
		},
	}
	b, _ := json.Marshal(snap)
	if !IsComplete(b, p) {
		t.Fatal("plate without fail_closed must not block completeness")
	}
}

func TestIsComplete_plateFailClosedHardGate(t *testing.T) {
	p := Policy{
		Enabled:     true,
		ClipSeconds: 6,
		Images: []map[string]interface{}{
			{"role": "scene"},
			{"role": "subject"},
			{"role": "plate"},
		},
		FailClosed: []string{"subject", "plate"},
	}
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
	if IsComplete(b, p) {
		t.Fatal("fail_closed plate without plate image/number must be incomplete")
	}
	snap2 := map[string]interface{}{
		"package": map[string]interface{}{
			"clip": map[string]interface{}{"asset_id": "clip-1"},
			"images": []interface{}{
				map[string]interface{}{"role": "scene", "url": "http://x/s"},
				map[string]interface{}{"role": "subject", "asset_id": "sub-1"},
				map[string]interface{}{"role": "plate", "asset_id": "plt-1"},
			},
		},
	}
	b2, _ := json.Marshal(snap2)
	if !IsComplete(b2, p) {
		t.Fatal("plate image satisfies fail_closed plate")
	}
}

func TestIsComplete_faceReferenceFailClosed(t *testing.T) {
	p := Policy{
		Enabled:     true,
		ClipSeconds: 6,
		Images: []map[string]interface{}{
			{"role": "scene"},
			{"role": "face"},
			{"role": "reference"},
		},
		FailClosed: []string{"face", "reference"},
	}
	snap := map[string]interface{}{
		"package": map[string]interface{}{
			"metadata": map[string]interface{}{"capture_source": "face_identity"},
			"images": []interface{}{
				map[string]interface{}{"role": "face", "asset_id": "f1"},
				map[string]interface{}{"role": "scene", "asset_id": "s1"},
			},
		},
	}
	b, _ := json.Marshal(snap)
	if IsComplete(b, p) {
		t.Fatal("face watchlist without reference must be incomplete when fail_closed")
	}
	snap2 := map[string]interface{}{
		"package": map[string]interface{}{
			"metadata": map[string]interface{}{"capture_source": "face_identity"},
			"images": []interface{}{
				map[string]interface{}{"role": "face", "asset_id": "f1"},
				map[string]interface{}{"role": "scene", "asset_id": "s1"},
				map[string]interface{}{"role": "reference", "asset_id": "r1"},
			},
		},
	}
	b2, _ := json.Marshal(snap2)
	if !IsComplete(b2, p) {
		t.Fatal("face+reference should soft-complete without clip for face_identity")
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
	if RequiredSlotCount(DefaultPolicy()) != 4 {
		t.Fatalf("expected 4 slots (clip+3 images), got %d", RequiredSlotCount(DefaultPolicy()))
	}
	p := Policy{Enabled: true, ClipSeconds: 0, Images: []map[string]interface{}{{"role": "scene"}}}
	if RequiredSlotCount(p) != 1 {
		t.Fatalf("expected 1 slot")
	}
}

