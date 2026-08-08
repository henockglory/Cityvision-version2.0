package demo

import (
	"context"
	"sync/atomic"
	"testing"
	"time"
)

func TestSetFrigateRebuildInvokedByTrigger(t *testing.T) {
	s := &Service{}
	var calls atomic.Int32
	done := make(chan struct{}, 1)
	s.SetFrigateRebuild(func(ctx context.Context) error {
		calls.Add(1)
		select {
		case done <- struct{}{}:
		default:
		}
		return nil
	})
	s.triggerFrigateRebuild(context.Background(), "unit_test")
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("frigate rebuild hook not called")
	}
	if calls.Load() != 1 {
		t.Fatalf("expected 1 call, got %d", calls.Load())
	}
}

func TestTriggerFrigateRebuildNilSafe(t *testing.T) {
	s := &Service{}
	// Must not panic when hook unset.
	s.triggerFrigateRebuild(context.Background(), "nil_hook")
}
