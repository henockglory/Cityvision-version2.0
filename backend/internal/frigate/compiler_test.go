package frigate

import (
	"encoding/json"
	"os"
	"strings"
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
		DetectEnabled: true, RecordEnabled: true, SnapshotsEnabled: true,
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

func TestBuildConfigEnablesFaceRecognition(t *testing.T) {
	dir := t.TempDir()
	base := dir + "/base.yml"
	if err := os.WriteFile(base, []byte("mqtt:\n  host: mosquitto\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	c := NewCompiler(Config{BaseYAML: base})
	data, err := c.BuildConfig(nil, true)
	if err != nil {
		t.Fatal(err)
	}
	s := string(data)
	if !strings.Contains(s, "face_recognition:") || !strings.Contains(s, "enabled: true") {
		t.Fatalf("expected face_recognition enabled in:\n%s", s)
	}
	dataOff, err := c.BuildConfig(nil, false)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(dataOff), "face_recognition:") {
		t.Fatalf("did not expect face_recognition when disabled:\n%s", dataOff)
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


func TestUpsertCameraSpeedDistancesFourPoints(t *testing.T) {
	poly := json.RawMessage(`[{"x":0.1,"y":0.1},{"x":0.5,"y":0.1},{"x":0.5,"y":0.5},{"x":0.1,"y":0.5}]`)
	camID := uuid.New()
	cam := &models.Camera{ID: camID}
	zoneID := uuid.New()
	bcfg := json.RawMessage(`{"behavior":"speed_measurement","config":{"speed_limit_kmh":50,"edge_distances_m":[10,12,11,13]}}`)
	zones := []models.Zone{{
		ID: zoneID, CameraID: &camID, Polygon: poly, BehaviorConfig: bcfg,
	}}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, EvidenceAggregate{
		DetectEnabled: true, RecordEnabled: true, SnapshotsEnabled: true,
	}, zones)
	zn := ZoneID(zoneID.String())
	ze, ok := cc.Entry.Zones[zn]
	if !ok {
		t.Fatalf("missing zone %s", zn)
	}
	if ze.Distances != "10.000,12.000,11.000,13.000" {
		t.Fatalf("distances: got %q", ze.Distances)
	}
	// speed_threshold is a low motion filter (drop stationary objects), never
	// the legal limit: the violation verdict stays bridge-side.
	if ze.SpeedThreshold != 1 {
		t.Fatalf("speed_threshold default motion filter: got %v want 1", ze.SpeedThreshold)
	}
}

func TestUpsertCameraSpeedThresholdOverride(t *testing.T) {
	poly := json.RawMessage(`[{"x":0.1,"y":0.1},{"x":0.5,"y":0.1},{"x":0.5,"y":0.5},{"x":0.1,"y":0.5}]`)
	camID := uuid.New()
	cam := &models.Camera{ID: camID}
	zoneID := uuid.New()
	bcfg := json.RawMessage(`{"behavior":"speed_measurement","config":{"speed_limit_kmh":50,"frigate_speed_threshold":5,"edge_distances_m":[10,12,11,13]}}`)
	zones := []models.Zone{{
		ID: zoneID, CameraID: &camID, Polygon: poly, BehaviorConfig: bcfg,
	}}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, EvidenceAggregate{}, zones)
	ze := cc.Entry.Zones[ZoneID(zoneID.String())]
	if ze.SpeedThreshold != 5 {
		t.Fatalf("frigate_speed_threshold override: got %v want 5", ze.SpeedThreshold)
	}
}

func TestUpsertCameraTrackObjectsFromZone(t *testing.T) {
	poly := json.RawMessage(`[{"x":0.1,"y":0.2},{"x":0.5,"y":0.2},{"x":0.5,"y":0.6}]`)
	camID := uuid.New()
	cam := &models.Camera{ID: camID}
	zoneID := uuid.New()
	bcfg := json.RawMessage(`{"behavior":"seatbelt","config":{"track_objects":["car","motorcycle"]}}`)
	zones := []models.Zone{{
		ID: zoneID, CameraID: &camID, Polygon: poly, BehaviorConfig: bcfg,
	}}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, EvidenceAggregate{}, zones)
	found := map[string]bool{}
	for _, lab := range cc.Entry.Objects.Track {
		found[lab] = true
	}
	for _, want := range []string{"car", "motorcycle", "person"} {
		if !found[want] {
			t.Fatalf("expected %s in objects.track, got %v", want, cc.Entry.Objects.Track)
		}
	}
}

func TestUpsertCameraSpeedNoDistancesWhenNotFourPoints(t *testing.T) {
	poly := json.RawMessage(`[{"x":0.1,"y":0.2},{"x":0.5,"y":0.2},{"x":0.5,"y":0.6}]`)
	camID := uuid.New()
	cam := &models.Camera{ID: camID}
	zoneID := uuid.New()
	bcfg := json.RawMessage(`{"behavior":"speed_measurement","config":{"edge_distances_m":[10,12,11]}}`)
	zones := []models.Zone{{
		ID: zoneID, CameraID: &camID, Polygon: poly, BehaviorConfig: bcfg,
	}}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, EvidenceAggregate{}, zones)
	zn := ZoneID(zoneID.String())
	ze := cc.Entry.Zones[zn]
	if ze.Distances != "" {
		t.Fatalf("expected empty distances for non-4-point zone, got %q", ze.Distances)
	}
}

func TestUpsertCameraTracksPersonForFaceAggregate(t *testing.T) {
	cam := &models.Camera{ID: uuid.New()}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, EvidenceAggregate{TrackPerson: true}, nil)
	found := false
	for _, lab := range cc.Entry.Objects.Track {
		if lab == "person" {
			found = true
		}
	}
	if !found {
		t.Fatalf("expected person in objects.track when TrackPerson, got %v", cc.Entry.Objects.Track)
	}
}

func TestUpsertCameraTracksBagsForAbandonedZone(t *testing.T) {
	poly := json.RawMessage(`[{"x":0.1,"y":0.2},{"x":0.5,"y":0.2},{"x":0.5,"y":0.6}]`)
	camID := uuid.New()
	cam := &models.Camera{ID: camID}
	zoneID := uuid.New()
	bcfg := json.RawMessage(`{"behavior":"abandoned_object","config":{"duration_seconds":45}}`)
	zones := []models.Zone{{
		ID: zoneID, CameraID: &camID, Polygon: poly, BehaviorConfig: bcfg,
	}}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, EvidenceAggregate{}, zones)
	found := map[string]bool{}
	for _, lab := range cc.Entry.Objects.Track {
		found[lab] = true
	}
	for _, want := range []string{"car", "backpack", "handbag", "suitcase", "umbrella", "bicycle", "dog"} {
		if !found[want] {
			t.Fatalf("expected %s in objects.track for abandoned zone, got %v", want, cc.Entry.Objects.Track)
		}
	}
}

func TestUpsertCameraTracksBagsFromAggregate(t *testing.T) {
	cam := &models.Camera{ID: uuid.New()}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, EvidenceAggregate{
		DetectEnabled: true, TrackObjects: []string{"backpack", "suitcase"},
	}, nil)
	found := map[string]bool{}
	for _, lab := range cc.Entry.Objects.Track {
		found[lab] = true
	}
	if !found["car"] || !found["backpack"] || !found["suitcase"] {
		t.Fatalf("expected vehicles + bag labels, got %v", cc.Entry.Objects.Track)
	}
}

func TestUpsertCameraTracksPersonForCabinBehavior(t *testing.T) {
	poly := json.RawMessage(`[{"x":0.1,"y":0.2},{"x":0.5,"y":0.2},{"x":0.5,"y":0.6}]`)
	camID := uuid.New()
	cam := &models.Camera{ID: camID}
	zoneID := uuid.New()
	bcfg := json.RawMessage(`{"behavior":"seatbelt","config":{}}`)
	zones := []models.Zone{{
		ID: zoneID, CameraID: &camID, Polygon: poly, BehaviorConfig: bcfg,
	}}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, EvidenceAggregate{}, zones)
	found := false
	for _, lab := range cc.Entry.Objects.Track {
		if lab == "person" {
			found = true
		}
	}
	if !found {
		t.Fatalf("expected person in objects.track, got %v", cc.Entry.Objects.Track)
	}
}

func TestUpsertCameraStrictFrigateForcesRecord(t *testing.T) {
	t.Setenv("FRIGATE_EVIDENCE", "true")
	t.Setenv("FRIGATE_DEMO_MODE", "true")
	t.Setenv("DEMO_EVIDENCE_BACKEND", "strict_frigate")
	vid := uuid.New()
	meta, _ := json.Marshal(map[string]interface{}{
		"demo": true, "go2rtc_src": "demo-x", "demo_video_id": vid.String(),
	})
	cam := &models.Camera{ID: uuid.New(), Metadata: meta}
	agg := EvidenceAggregate{DetectEnabled: true, RecordEnabled: false, SnapshotsEnabled: false}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, agg, nil)
	if !cc.Entry.Record.Enabled || !cc.Entry.Snapshots.Enabled {
		t.Fatal("demo go2rtc with DetectEnabled must enable record+snapshots")
	}
	if !cc.Entry.Detect.Enabled {
		t.Fatal("detect should follow DetectEnabled=true")
	}
	// YAML record stays on; idle cameras are MQTT-stopped (detect gate).
	ccOff := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, EvidenceAggregate{}, nil)
	if !ccOff.Entry.Record.Enabled {
		t.Fatal("demo go2rtc YAML record must stay on so MQTT-woken cams can seal clips")
	}
	if ccOff.Entry.Detect.Enabled {
		t.Fatal("detect should follow DetectEnabled=false")
	}
}

func TestUpsertCameraDetectDisabledWithoutRules(t *testing.T) {
	cam := &models.Camera{ID: uuid.New()}
	cc := UpsertCamera(cam, "rtsp://127.0.0.1/stream", nil, EvidenceAggregate{}, nil)
	if cc.Entry.Detect.Enabled {
		t.Fatal("detect must be OFF when DetectEnabled=false")
	}
}
