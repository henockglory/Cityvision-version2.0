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

func TestPolicyRequiresProof_disabled(t *testing.T) {
	policy := map[string]interface{}{"enabled": false}
	if policyRequiresProof(policy) {
		t.Fatal("disabled policy should not require proof")
	}
}
