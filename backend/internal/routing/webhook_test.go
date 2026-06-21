package routing

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
)

func TestPostWebhook_CloudEventsRetry(t *testing.T) {
	attempts := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		if attempts < 2 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		if r.Header.Get("X-CiteVision-Delivery-Id") == "" {
			t.Fatal("missing delivery id header")
		}
		var body map[string]interface{}
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body["specversion"] != "1.0" {
			t.Fatalf("expected CloudEvents envelope, got %v", body["specversion"])
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	t.Setenv("WEBHOOK_ALLOW_PRIVATE", "1") // httptest server runs on loopback
	t.Setenv("WEBHOOK_CLOUDEVENTS", "1")
	t.Setenv("WEBHOOK_MAX_ATTEMPTS", "3")
	t.Setenv("WEBHOOK_DLQ_PATH", t.TempDir()+"/dlq.jsonl")

	err := PostWebhook(srv.URL, map[string]interface{}{
		"org_id":   "org-1",
		"alert_id": "alert-1",
		"title":    "test",
	})
	if err != nil {
		t.Fatalf("PostWebhook: %v", err)
	}
	if attempts < 2 {
		t.Fatalf("expected retry, attempts=%d", attempts)
	}
}

func TestPostWebhook_DLQOnFailure(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
	}))
	defer srv.Close()

	dlq := t.TempDir() + "/dlq.jsonl"
	t.Setenv("WEBHOOK_ALLOW_PRIVATE", "1") // httptest server runs on loopback
	t.Setenv("WEBHOOK_MAX_ATTEMPTS", "1")
	t.Setenv("WEBHOOK_DLQ_PATH", dlq)

	err := PostWebhook(srv.URL, map[string]interface{}{"alert_id": "x"})
	if err == nil {
		t.Fatal("expected error")
	}
	if _, statErr := os.Stat(dlq); statErr != nil {
		t.Fatalf("DLQ file missing: %v", statErr)
	}
}
