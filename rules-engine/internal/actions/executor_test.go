package actions

import "testing"

func TestHasEvidencePackage_incomplete(t *testing.T) {
	policy := map[string]interface{}{
		"enabled": true, "clip_seconds": float64(5),
		"images": []interface{}{
			map[string]interface{}{"role": "scene"},
			map[string]interface{}{"role": "subject"},
		},
	}
	payload := map[string]interface{}{
		"package": map[string]interface{}{
			"clip":   map[string]interface{}{"url": "http://clip"},
			"images": []interface{}{map[string]interface{}{"role": "scene", "url": "http://scene"}},
		},
	}
	if hasEvidencePackage(payload, policy) {
		t.Fatal("expected incomplete package (missing subject)")
	}
}

func TestHasEvidencePackage_complete(t *testing.T) {
	policy := map[string]interface{}{
		"enabled": true, "clip_seconds": float64(5),
		"images": []interface{}{
			map[string]interface{}{"role": "scene"},
			map[string]interface{}{"role": "subject"},
		},
	}
	payload := map[string]interface{}{
		"package": map[string]interface{}{
			"clip": map[string]interface{}{"url": "http://clip"},
			"images": []interface{}{
				map[string]interface{}{"role": "scene", "url": "http://scene"},
				map[string]interface{}{"role": "subject", "url": "http://subject"},
			},
		},
	}
	if !hasEvidencePackage(payload, policy) {
		t.Fatal("expected complete package")
	}
}

func TestHasEvidencePackage_bboxQualityBlocks(t *testing.T) {
	policy := map[string]interface{}{
		"enabled": true, "clip_seconds": float64(5),
		"images": []interface{}{
			map[string]interface{}{"role": "scene"},
			map[string]interface{}{"role": "subject"},
		},
	}
	payload := map[string]interface{}{
		"package": map[string]interface{}{
			"clip": map[string]interface{}{"url": "http://clip"},
			"images": []interface{}{
				map[string]interface{}{"role": "scene", "url": "http://scene"},
				map[string]interface{}{"role": "subject", "url": "http://subject"},
			},
			"metadata": map[string]interface{}{"bbox_quality_ok": false},
		},
	}
	if hasEvidencePackage(payload, policy) {
		t.Fatal("expected bbox_quality_ok=false to block package")
	}
}

func TestPolicyRequiresProof_disabled(t *testing.T) {
	policy := map[string]interface{}{"enabled": false}
	if policyRequiresProof(policy) {
		t.Fatal("disabled policy should not require proof")
	}
}

func TestHasEvidencePackage_plateOptional(t *testing.T) {
	policy := map[string]interface{}{
		"enabled": true, "clip_seconds": float64(5),
		"images": []interface{}{
			map[string]interface{}{"role": "scene"},
			map[string]interface{}{"role": "subject"},
			map[string]interface{}{"role": "plate"},
		},
	}
	payload := map[string]interface{}{
		"package": map[string]interface{}{
			"clip": map[string]interface{}{"url": "http://clip"},
			"images": []interface{}{
				map[string]interface{}{"role": "scene", "url": "http://scene"},
				map[string]interface{}{"role": "subject", "url": "http://subject"},
				map[string]interface{}{"role": "plate", "url": "http://plate-blur"},
			},
			"metadata": map[string]interface{}{},
		},
	}
	if !hasEvidencePackage(payload, policy) {
		t.Fatal("plate unreadable must still allow violation package")
	}
	meta := packageMetadata(payload["package"].(map[string]interface{}))
	if meta["identification"] != "unreadable" || meta["plate_status"] != "unreadable" {
		t.Fatalf("want identification=unreadable got %v", meta)
	}
	if meta["violation_status"] != "violation_confirmed" {
		t.Fatalf("want violation_confirmed got %v", meta["violation_status"])
	}
}
