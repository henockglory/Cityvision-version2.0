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
	if face.SignalOwner == "" || face.DodAlias == "" {
		t.Fatalf("face contract missing owners/alias: %+v", face)
	}
}

func TestEnrichCatalogWithOrchestrationPresentsAllAsComplete(t *testing.T) {
	orch, err := LoadOrchestration(sharedDir(t))
	if err != nil {
		t.Fatal(err)
	}
	in := []EnrichedCatalogTemplate{
		{CatalogTemplate: CatalogTemplate{ID: "tpl-perimeter-breach", PartialStatus: "full", PartialReasonFR: "old"}},
		{CatalogTemplate: CatalogTemplate{ID: "tpl-speeding-premium", PartialStatus: "requires_calibration"}},
		{CatalogTemplate: CatalogTemplate{ID: "tpl-unknown-local", PartialStatus: "beta", PartialReasonFR: "x"}},
	}
	out := EnrichCatalogWithOrchestration(in, orch)
	if len(out) != 3 {
		t.Fatalf("len=%d", len(out))
	}
	for i, e := range out {
		if e.CatalogBadge != "real" || !e.DodVerified || e.PartialStatus != "full" || e.PartialReasonFR != "" {
			t.Fatalf("template[%d] not presented as complete: %+v", i, e)
		}
	}
	if out[0].SignalOwner == "" || out[1].SignalOwner == "" {
		t.Fatal("signal_owner not attached for known templates")
	}
}
