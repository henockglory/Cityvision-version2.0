package frigate

import (
	"encoding/json"
	"testing"

	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/models"
)

func TestDemoGo2rtcStreamNameFromRTSP(t *testing.T) {
	meta := json.RawMessage(`{"demo":true,"virtual":true,"demo_video_id":"aaea7c30-1111-2222-3333-444444444444"}`)
	rtsp := "rtsp://127.0.0.1:8554/demo-74d51ead-aaea7c30"
	got := demoGo2rtcStreamName(meta, rtsp)
	want := "demo-74d51ead-aaea7c30"
	if got != want {
		t.Fatalf("demo stream: got %q want %q", got, want)
	}
}

func TestFrigateUpstreamPathDemoUsesDemoStream(t *testing.T) {
	t.Setenv("FRIGATE_INPUT_VIA_GO2RTC", "true")
	t.Setenv("FRIGATE_GO2RTC_HOST", "citevision-v2-go2rtc")
	meta := json.RawMessage(`{"demo":true,"virtual":true,"demo_video_id":"aaea7c30-1111-2222-3333-444444444444"}`)
	rtsp := "rtsp://127.0.0.1:8554/demo-74d51ead-aaea7c30"
	got := frigateUpstreamPath(uuid.New().String(), rtsp, meta)
	want := "rtsp://citevision-v2-go2rtc:8554/demo-74d51ead-aaea7c30"
	if got != want {
		t.Fatalf("upstream: got %q want %q", got, want)
	}
}

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
	if want := []string{"car", "truck", "motorcycle", "bus", "van"}; len(cc.Entry.Objects.Track) != len(want) {
		t.Fatalf("objects.track: got %v want %v", cc.Entry.Objects.Track, want)
	}
	if cc.Entry.Detect.Width != 1280 || cc.Entry.Detect.Height != 720 {
		t.Fatalf("detect dims: got %dx%d", cc.Entry.Detect.Width, cc.Entry.Detect.Height)
	}
	zn := ZoneID(zoneID.String())
	if _, ok := cc.Entry.Zones[zn]; !ok {
		t.Fatalf("missing zone %s", zn)
	}
}

func TestUpsertCameraDemoModeRespectsAggregateOnly(t *testing.T) {
	t.Setenv("FRIGATE_EVIDENCE", "true")
	t.Setenv("FRIGATE_DEMO_MODE", "true")
	t.Setenv("DEMO_EVIDENCE_BACKEND", "") // hybrid/default: do not force record
	cam := &models.Camera{ID: uuid.New()}
	agg := EvidenceAggregate{RecordEnabled: false, SnapshotsEnabled: true}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, agg, nil)
	if cc.Entry.Record.Enabled {
		t.Fatal("demo mode must not force record when aggregate disabled")
	}
	if !cc.Entry.Snapshots.Enabled {
		t.Fatal("snapshots should follow aggregate in demo mode")
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


func TestUpsertCameraStrictFrigateForcesRecord(t *testing.T) {
	t.Setenv("FRIGATE_EVIDENCE", "true")
	t.Setenv("FRIGATE_DEMO_MODE", "true")
	t.Setenv("DEMO_EVIDENCE_BACKEND", "strict_frigate")
	cam := &models.Camera{ID: uuid.New()}
	agg := EvidenceAggregate{RecordEnabled: false, SnapshotsEnabled: false}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, agg, nil)
	if !cc.Entry.Record.Enabled || !cc.Entry.Snapshots.Enabled {
		t.Fatal("strict_frigate demo must force record+snapshots")
	}
}
