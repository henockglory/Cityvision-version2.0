package actions

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/citevision/citevision-v2/rules-engine/internal/evaluator"
)

func TestRunWebhook_ReportsHTTPFailure(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/internal/orgs/org-1/webhook" {
			t.Fatalf("unexpected path %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte(`{"error":"upstream failed"}`))
	}))
	defer srv.Close()

	e := New(nil, srv.URL, "test-key")
	cfg, _ := json.Marshal(map[string]interface{}{
		"url":    "http://example.invalid/hook",
		"preset": "n8n",
	})
	ok := e.runWebhook("org-1", evaluator.RuleDefinition{
		RuleID: "rule-1",
		Name:   "Demo",
	}, map[string]interface{}{
		"camera_id":  "cam-1",
		"event_type": "zone_enter",
		"class_name": "person",
	}, evaluator.Action{Type: "webhook", Config: cfg})
	if ok {
		t.Fatal("expected runWebhook false on HTTP 502")
	}
}

func TestRunWebhook_Success(t *testing.T) {
	var gotPreset string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]interface{}
		_ = json.NewDecoder(r.Body).Decode(&body)
		gotPreset, _ = body["preset"].(string)
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"sent"}`))
	}))
	defer srv.Close()

	e := New(nil, srv.URL, "test-key")
	cfg, _ := json.Marshal(map[string]interface{}{
		"url":    "http://127.0.0.1:5678/webhook/x",
		"preset": "n8n",
	})
	ok := e.runWebhook("org-1", evaluator.RuleDefinition{
		RuleID: "rule-1",
		Name:   "Demo",
	}, map[string]interface{}{
		"camera_id":  "cam-1",
		"event_type": "zone_enter",
	}, evaluator.Action{Type: "webhook", Config: cfg})
	if !ok {
		t.Fatal("expected runWebhook true on HTTP 200")
	}
	if gotPreset != "n8n" {
		t.Fatalf("preset=%q", gotPreset)
	}
}
