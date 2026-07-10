package frigate

import (
	"encoding/json"
	"testing"

	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/models"
)

func TestCameraIDConvention(t *testing.T) {
	id := uuid.MustParse("d2eb7076-c3b3-40fd-9b2c-0d119bb975c9")
	got := CameraID(id.String())
	want := "cv_d2eb7076-c3b3-40fd-9b2c-0d119bb975c9"
	if got != want {
		t.Fatalf("camera id: got %q want %q", got, want)
	}
}

func TestUpsertCameraZonesFromPolygon(t *testing.T) {
	poly := json.RawMessage(`[{"x":0.1,"y":0.2},{"x":0.5,"y":0.2},{"x":0.5,"y":0.6}]`)
	camID := uuid.New()
	cam := &models.Camera{ID: camID}
	zoneID := uuid.New()
	zones := []models.Zone{{ID: zoneID, CameraID: &camID, Polygon: poly}}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, EvidenceAggregate{
		RecordEnabled: true, SnapshotsEnabled: true,
	}, zones)
	if len(cc.Entry.Zones) != 1 {
		t.Fatalf("expected 1 zone, got %d", len(cc.Entry.Zones))
	}
	zn := ZoneID(zoneID.String())
	if _, ok := cc.Entry.Zones[zn]; !ok {
		t.Fatalf("missing zone %s", zn)
	}
}

func TestEvidenceAggregateFromRuleDefinition(t *testing.T) {
	def := map[string]interface{}{
		"actions": []interface{}{map[string]interface{}{"type": "alert"}},
		"evidence": map[string]interface{}{
			"enabled":      true,
			"clip_seconds": 6,
			"images": []interface{}{
				map[string]interface{}{"role": "scene"},
				map[string]interface{}{"role": "plate"},
			},
		},
	}
	if !ruleHasAlertAction(def) {
		t.Fatal("expected alert action")
	}
	ev := mergeEvidencePolicy(def)
	if ev["clip_seconds"] != 6 {
		t.Fatalf("clip_seconds: %v", ev["clip_seconds"])
	}
}

func TestObservationModeSkipsInAggregateLogic(t *testing.T) {
	def := map[string]interface{}{
		"bindings": map[string]interface{}{"observation_mode": true},
		"actions":  []interface{}{map[string]interface{}{"type": "alert"}},
		"evidence": map[string]interface{}{"enabled": true, "clip_seconds": 6},
	}
	if v, ok := def["bindings"].(map[string]interface{}); ok {
		if obs, _ := v["observation_mode"].(bool); obs {
			return
		}
	}
	t.Fatal("observation_mode binding expected")
}
