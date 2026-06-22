package middleware

import (
	"net/http"
	"os"
)

// RequireInternalKey protects service-to-service routes (rules-engine, etc.).
func RequireInternalKey(next http.Handler) http.Handler {
	expected := os.Getenv("INTERNAL_API_KEY")
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if expected == "" || r.Header.Get("X-Internal-Key") != expected {
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(w, r)
	})
}
