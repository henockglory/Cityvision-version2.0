package dedup

import (
	"testing"
	"time"
)

func TestAntiDedup(t *testing.T) {
	cache := NewCache(60 * time.Second)
	now := time.Now()
	if cache.IsDuplicate("cam-1|1|zone_enter", now) {
		t.Fatal("first event should not be duplicate")
	}
	if !cache.IsDuplicate("cam-1|1|zone_enter", now.Add(time.Second)) {
		t.Fatal("second event within TTL should be duplicate")
	}
}
