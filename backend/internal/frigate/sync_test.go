package frigate

import (
	"encoding/json"
	"testing"
)

func TestSkipFrigateCamera_RealIncluded(t *testing.T) {
	meta := json.RawMessage(`{"go2rtc_src":"cam-abc"}`)
	if skipFrigateCamera(meta) {
		t.Fatal("real camera should be included")
	}
}

func TestSkipFrigateCamera_DemoGo2rtcIncluded(t *testing.T) {
	meta := json.RawMessage(`{"virtual":true,"demo":true,"go2rtc_src":"demo-org1-vid1"}`)
	if skipFrigateCamera(meta) {
		t.Fatal("demo go2rtc camera should be included")
	}
}

func TestSkipFrigateCamera_DemoVideoIDIncluded(t *testing.T) {
	meta := json.RawMessage(`{"virtual":true,"demo":true,"demo_video_id":"aaea7c30-0000-0000-0000-000000000001"}`)
	if skipFrigateCamera(meta) {
		t.Fatal("demo virtual camera with demo_video_id should be included")
	}
}

func TestSkipFrigateCamera_GenericVirtualSkipped(t *testing.T) {
	meta := json.RawMessage(`{"virtual":true}`)
	if !skipFrigateCamera(meta) {
		t.Fatal("generic virtual camera should be skipped")
	}
}

func TestSkipFrigateCamera_BenedicteSkipped(t *testing.T) {
	meta := json.RawMessage(`{"go2rtc_src":"benedicte"}`)
	if !skipFrigateCamera(meta) {
		t.Fatal("benedicte virtual should be skipped")
	}
}
