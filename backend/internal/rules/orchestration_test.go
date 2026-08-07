package rules

import (
	"path/filepath"
	"runtime"
	"testing"
)

func sharedDir(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	// backend/internal/rules → repo/shared
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", "shared"))
}

func TestLoadOrchestrationContract(t *testing.T) {
	orch, err := LoadOrchestration(sharedDir(t))
	if err != nil {
		t.Fatalf("LoadOrchestration: %v", err)
	}
	if orch == nil || len(orch.ByID) < 40 {
		t.Fatalf("expected >=40 templates, got %d", len(orch.ByID))
	}
	speed, ok := orch.ByID["tpl-speeding-premium"]
	if !ok {
		t.Fatal("missing tpl-speeding-premium")
	}
	if speed.SignalOwner != "frigate" || speed.JudgmentOwner != "frigate_speed" {
		t.Fatalf("speeding contract unexpected: %+v", speed)
	}
	if !speed.DodVerified || speed.CatalogBadge != "real" {
		t.Fatalf("speeding should be dod_verified real, got badge=%s verified=%v", speed.CatalogBadge, speed.DodVerified)
	}
	face, ok := orch.ByID["tpl-face-watchlist"]
	if !ok {
		t.Fatal("missing tpl-face-watchlist")
	}
	if face.VlmRole != "clear_face_gate" || face.JudgmentOwner != "insightface" {
		t.Fatalf("face contract unexpected: %+v", face)
	}
	if face.DodVerified || face.CatalogBadge != "partial" {
		t.Fatalf("face must stay partial until DoD")
	}
}

func TestEnrichCatalogWithOrchestrationHonesty(t *testing.T) {
	orch, err := LoadOrchestration(sharedDir(t))
	if err != nil {
		t.Fatal(err)
	}
	in := []EnrichedCatalogTemplate{
		{CatalogTemplate: CatalogTemplate{ID: "tpl-perimeter-breach", PartialStatus: "full"}},
		{CatalogTemplate: CatalogTemplate{ID: "tpl-speeding-premium", PartialStatus: "requires_calibration"}},
	}
	out := EnrichCatalogWithOrchestration(in, orch)
	if len(out) != 2 {
		t.Fatalf("len=%d", len(out))
	}
	if out[0].PartialStatus == "full" && !out[0].DodVerified {
		t.Fatal("perimeter without DoD must not stay full")
	}
	if out[1].PartialStatus != "full" || !out[1].DodVerified {
		t.Fatalf("speeding DoD should force full, got %+v", out[1])
	}
	if out[0].SignalOwner == "" || out[1].SignalOwner == "" {
		t.Fatal("signal_owner not attached")
	}
}
