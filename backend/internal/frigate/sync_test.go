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

func TestSkipFrigateCamera_ExplicitExclude(t *testing.T) {
	meta := json.RawMessage(`{"frigate_exclude":true}`)
	if !skipFrigateCamera(meta) {
		t.Fatal("frigate_exclude metadata should skip")
	}
}

func TestSkipFrigateHost_108(t *testing.T) {
	if !skipFrigateHost("192.168.1.108") {
		t.Fatal("192.168.1.108 must be excluded from Frigate")
	}
	if !skipFrigateHost("192.168.1.108/32") {
		t.Fatal("CIDR form must be excluded")
	}
	if skipFrigateHost("127.0.0.1") {
		t.Fatal("localhost must not be excluded")
	}
}
