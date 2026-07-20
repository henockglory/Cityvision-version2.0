package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func corsResponse(t *testing.T, allowed []string, origin string) *httptest.ResponseRecorder {
	t.Helper()
	h := CORSWithConfig(allowed)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	if origin != "" {
		req.Header.Set("Origin", origin)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func TestCORS_AllowlistedOriginEchoed(t *testing.T) {
	rec := corsResponse(t, []string{"https://app.example.com"}, "https://app.example.com")
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "https://app.example.com" {
		t.Fatalf("expected origin echoed, got %q", got)
	}
}

func TestCORS_UnlistedOriginRejected(t *testing.T) {
	rec := corsResponse(t, []string{"https://app.example.com"}, "https://evil.example.com")
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Fatalf("expected no ACAO for unlisted origin, got %q", got)
	}
}

func TestCORS_Wildcard(t *testing.T) {
	rec := corsResponse(t, []string{"*"}, "https://anything.example.com")
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "*" {
		t.Fatalf("expected wildcard, got %q", got)
	}
}

func TestCORS_DevDefaultsLocalhost(t *testing.T) {
	rec := corsResponse(t, nil, "http://localhost:5174")
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "http://localhost:5174" {
		t.Fatalf("expected localhost dev origin echoed, got %q", got)
	}
}
