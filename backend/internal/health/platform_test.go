package health

import (
	"context"
	"testing"
)

func TestCollectPlatformHealthBackendOk(t *testing.T) {
	ph := CollectPlatformHealth(context.Background(), PlatformDeps{})
	if ph.Status == "" {
		t.Fatal("expected status")
	}
	if ph.Components == nil {
		t.Fatal("expected components map")
	}
	if _, ok := ph.Components["backend"]; !ok {
		t.Fatal("expected backend component")
	}
}
