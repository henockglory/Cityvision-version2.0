package ingest

import (
	"encoding/json"
	"testing"
)

func TestFrigateEvidenceIngestViaGo2RTC(t *testing.T) {
	t.Setenv("EVIDENCE_BACKEND", "frigate")
	if !frigateEvidenceIngestViaGo2RTC() {
		t.Fatal("expected frigate backend to enable go2rtc ingest")
	}
	t.Setenv("EVIDENCE_BACKEND", "")
	t.Setenv("FRIGATE_EVIDENCE", "true")
	if !frigateEvidenceIngestViaGo2RTC() {
		t.Fatal("expected FRIGATE_EVIDENCE=true")
	}
	t.Setenv("FRIGATE_EVIDENCE", "")
	if frigateEvidenceIngestViaGo2RTC() {
		t.Fatal("expected disabled without flags")
	}
	t.Setenv("DEMO_MODE", "1")
	t.Setenv("DEMO_EVIDENCE_BACKEND", "strict_frigate")
	if !frigateEvidenceIngestViaGo2RTC() {
		t.Fatal("expected demo strict_frigate to enable go2rtc ingest")
	}
}

func TestSkipNonDemoLiveCamera(t *testing.T) {
	o := &Orchestrator{}
	demoMeta := json.RawMessage(`{"demo":true,"virtual":true}`)
	if o.skipNonDemoLiveCamera(demoMeta) {
		t.Fatal("demo cameras must never be gated by LIVE_108")
	}
	liveMeta := json.RawMessage(`{"virtual":false}`)
	t.Setenv("LIVE_108_ENABLED", "")
	if !o.skipNonDemoLiveCamera(liveMeta) {
		t.Fatal("live cameras must be skipped when LIVE_108_ENABLED unset")
	}
	t.Setenv("LIVE_108_ENABLED", "1")
	if o.skipNonDemoLiveCamera(liveMeta) {
		t.Fatal("live cameras must ingest when LIVE_108_ENABLED=1")
	}
}

func TestDemoGo2rtcRTSPURL(t *testing.T) {
	t.Setenv("GO2RTC_RTSP_HOST", "127.0.0.1")
	t.Setenv("GO2RTC_RTSP_PORT", "8554")
	meta := json.RawMessage(`{"demo":true,"go2rtc_src":"demo-74d51ead-aaea7c30"}`)
	got := demoGo2rtcRTSPURL(meta)
	want := "rtsp://127.0.0.1:8554/demo-74d51ead-aaea7c30"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestDemoGo2rtcRTSPURLEmptyWithoutStream(t *testing.T) {
	meta := json.RawMessage(`{"demo":true}`)
	if got := demoGo2rtcRTSPURL(meta); got != "" {
		t.Fatalf("expected empty, got %q", got)
	}
}
