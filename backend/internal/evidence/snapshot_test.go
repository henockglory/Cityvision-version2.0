package evidence

import (
	"encoding/json"
	"testing"
)

func TestSnapshotFromPayload_withPackage(t *testing.T) {
	payload := map[string]interface{}{
		"event_type": "zone_presence",
		"class_name": "person",
		"zone_id":    "zone-a",
		"confidence": 0.92,
		"evidence": map[string]interface{}{
			"package": map[string]interface{}{
				"version": 1,
				"clip": map[string]interface{}{
					"url":          "http://localhost:8081/api/v1/orgs/o1/evidence/asset?key=clip.mp4",
					"duration_sec": 6,
					"mime":         "video/mp4",
				},
				"images": []interface{}{
					map[string]interface{}{"role": "scene", "url": "http://localhost/scene.jpg"},
					map[string]interface{}{"role": "subject", "url": "http://localhost/subject.jpg"},
				},
			},
		},
	}

	raw := SnapshotFromPayload(payload)
	var snap map[string]interface{}
	if err := json.Unmarshal(raw, &snap); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if snap["class_name"] != "person" {
		t.Fatalf("expected class_name person, got %v", snap["class_name"])
	}
	pkg, ok := snap["package"].(map[string]interface{})
	if !ok {
		t.Fatal("expected package in snapshot")
	}
	clip, ok := pkg["clip"].(map[string]interface{})
	if !ok || clip["url"] == "" {
		t.Fatal("expected clip url in package")
	}
	images, ok := pkg["images"].([]interface{})
	if !ok || len(images) < 2 {
		t.Fatalf("expected 2 images, got %v", pkg["images"])
	}
	if snap["clip_path"] == "" {
		t.Fatal("expected clip_path alias from package clip url")
	}
}

func TestMergeIntoSnapshot_preservesExisting(t *testing.T) {
	existing := map[string]interface{}{"plate_number": "ABC-123"}
	pkg := &Package{
		Version: 1,
		Clip:    &Clip{URL: "http://example/clip.mp4"},
	}
	raw := MergeIntoSnapshot(existing, pkg, map[string]interface{}{"confidence": 0.8})
	var snap map[string]interface{}
	if err := json.Unmarshal(raw, &snap); err != nil {
		t.Fatal(err)
	}
	if snap["plate_number"] != "ABC-123" {
		t.Fatalf("lost existing field: %v", snap)
	}
	if snap["confidence"] != 0.8 {
		t.Fatalf("expected confidence 0.8, got %v", snap["confidence"])
	}
}

func TestExtractPackageFromPayload_topLevel(t *testing.T) {
	payload := map[string]interface{}{
		"package": map[string]interface{}{
			"version": 1,
			"clip":    map[string]interface{}{"url": "http://x/clip.mp4"},
		},
	}
	pkg := ExtractPackageFromPayload(payload)
	if pkg == nil || pkg.Clip == nil || pkg.Clip.URL == "" {
		t.Fatal("expected package from top-level package key")
	}
}
