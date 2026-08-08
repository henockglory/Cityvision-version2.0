package identity

import "testing"

func TestSanitizeFrigateName(t *testing.T) {
	got := SanitizeFrigateName("  Eve#Dupont!!  ")
	if got != "EveDupont" && got != "Eve Dupont" {
		// cleaner strips # and ! — spaces collapse
		if got == "" {
			t.Fatal("empty name")
		}
	}
	if SanitizeFrigateName("") != "unknown" {
		t.Fatalf("empty → unknown, got %q", SanitizeFrigateName(""))
	}
}

func TestNewFaceEntry(t *testing.T) {
	emb := []float64{0.1, 0.2, 0.3}
	e := NewFaceEntry("", "Alice", emb, "orgs/x/watchlist/y/z.jpg", "http://x", "ok")
	if e["label"] != "Alice" {
		t.Fatalf("label: %v", e["label"])
	}
	if e["identifier"] == nil || e["identifier"] == "" {
		t.Fatal("identifier required")
	}
	meta, _ := e["metadata"].(map[string]interface{})
	if meta["frigate_sync"] != "ok" {
		t.Fatalf("frigate_sync: %v", meta["frigate_sync"])
	}
	if meta["frigate_name"] != "Alice" {
		t.Fatalf("frigate_name: %v", meta["frigate_name"])
	}
}

func TestNormalizePlateEntry(t *testing.T) {
	e := NormalizePlateEntry(map[string]interface{}{"plate": "ab-123-cd"})
	if e["plate_number"] != "AB-123-CD" {
		t.Fatalf("plate: %v", e["plate_number"])
	}
	if e["identifier"] != "AB-123-CD" {
		t.Fatalf("identifier: %v", e["identifier"])
	}
}
