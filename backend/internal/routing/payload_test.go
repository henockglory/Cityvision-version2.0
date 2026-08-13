package routing

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/alerts"
	"github.com/citevision/citevision-v2/backend/internal/models"
)

func TestBuildRoutingWebhookPayload_EvidenceComplete(t *testing.T) {
	orgID := uuid.MustParse("11111111-1111-4111-8111-111111111111")
	alertID := uuid.MustParse("22222222-2222-4222-8222-222222222222")
	ruleName := "Intrusion"
	evSnap := map[string]interface{}{
		"evidence_status": "complete",
		"package": map[string]interface{}{
			"images": []interface{}{
				map[string]interface{}{"role": "scene", "url": "https://example/scene.jpg"},
			},
			"metadata": map[string]interface{}{
				"alert_correlation_id": "corr-abc",
			},
		},
	}
	raw, _ := json.Marshal(evSnap)
	meta, _ := json.Marshal(map[string]interface{}{"alert_correlation_id": "corr-abc"})
	enriched := &alerts.EnrichedAlert{
		Alert: models.Alert{
			ID:        alertID,
			OrgID:     orgID,
			Title:     "Intrusion zone",
			Severity:  "high",
			Status:    "open",
			Metadata:  meta,
			CreatedAt: time.Date(2026, 8, 13, 10, 0, 0, 0, time.UTC),
			UpdatedAt: time.Date(2026, 8, 13, 10, 0, 5, 0, time.UTC),
		},
		CameraID:         "cam-1",
		RuleName:         &ruleName,
		EvidenceSnapshot: raw,
	}
	fields := map[string]string{"event_type": "zone_enter", "plate_number": "", "face_label": ""}
	payload := buildRoutingWebhookPayload(orgID, alertID, enriched, fields, "Critique → webhook", "n8n", WebhookPhaseEvidenceComplete, evSnap)

	if payload["webhook_phase"] != WebhookPhaseEvidenceComplete {
		t.Fatalf("webhook_phase=%v", payload["webhook_phase"])
	}
	if payload["evidence_status"] != "complete" {
		t.Fatalf("evidence_status=%v", payload["evidence_status"])
	}
	if payload["alert_correlation_id"] != "corr-abc" {
		t.Fatalf("alert_correlation_id=%v", payload["alert_correlation_id"])
	}
	if payload["integration_preset"] != "n8n" {
		t.Fatalf("integration_preset=%v", payload["integration_preset"])
	}
	snap, _ := payload["evidence_snapshot"].(map[string]interface{})
	if snap == nil || snap["evidence_status"] != "complete" {
		t.Fatalf("evidence_snapshot incomplete: %v", payload["evidence_snapshot"])
	}
	if payload["status"] != "open" {
		t.Fatalf("status=%v", payload["status"])
	}
}

func TestEvidenceStatusFromSnapshot_PendingDefault(t *testing.T) {
	if got := evidenceStatusFromSnapshot(map[string]interface{}{}); got != "pending" {
		t.Fatalf("got %q", got)
	}
	if got := evidenceStatusFromSnapshot(map[string]interface{}{
		"package": map[string]interface{}{
			"metadata": map[string]interface{}{"evidence_status": "complete"},
		},
	}); got != "complete" {
		t.Fatalf("nested got %q", got)
	}
}
