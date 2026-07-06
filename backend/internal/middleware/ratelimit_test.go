package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRateLimiter_BlocksAfterBurst(t *testing.T) {
	rl := NewRateLimiter(60, 3) // burst of 3
	h := rl.Middleware(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	statuses := make([]int, 0, 5)
	for i := 0; i < 5; i++ {
		req := httptest.NewRequest(http.MethodGet, "/", nil)
		req.RemoteAddr = "203.0.113.5:1234"
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		statuses = append(statuses, rec.Code)
	}
	// First 3 allowed, then limited.
	for i := 0; i < 3; i++ {
		if statuses[i] != http.StatusOK {
			t.Fatalf("request %d expected 200, got %d", i, statuses[i])
		}
	}
	if statuses[3] != http.StatusTooManyRequests || statuses[4] != http.StatusTooManyRequests {
		t.Fatalf("expected 429 after burst, got %v", statuses)
	}
}

func TestRateLimiter_PerIPIsolation(t *testing.T) {
	rl := NewRateLimiter(60, 1)
	h := rl.Middleware(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {}))

	call := func(ip string) int {
		req := httptest.NewRequest(http.MethodGet, "/", nil)
		req.RemoteAddr = ip + ":1000"
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		return rec.Code
	}
	if call("198.51.100.1") != http.StatusOK {
		t.Fatal("first IP first call should pass")
	}
	if call("198.51.100.2") != http.StatusOK {
		t.Fatal("second IP should not be affected by first IP's usage")
	}
}
