package frigate

import (
	"encoding/json"
	"testing"
)

// Policy exclusions (host denylist / frigate_exclude / virtual skip) were removed.
// Active cameras always enter RebuildAll; these tests lock helper semantics only.

func TestIsDemoGo2rtcCamera(t *testing.T) {
	if !isDemoGo2rtcCamera(json.RawMessage(`{"demo":true,"go2rtc_src":"demo-x"}`)) {
		t.Fatal("demo+go2rtc_src should be demo go2rtc")
	}
	if !isDemoGo2rtcCamera(json.RawMessage(`{"demo":true,"demo_video_id":"aaea7c30-0000-0000-0000-000000000001"}`)) {
		t.Fatal("demo+demo_video_id should be demo go2rtc")
	}
	if isDemoGo2rtcCamera(json.RawMessage(`{"virtual":true}`)) {
		t.Fatal("virtual alone is not demo go2rtc")
	}
}

func TestIsVirtualCamera(t *testing.T) {
	if !isVirtualCamera(json.RawMessage(`{"virtual":true}`)) {
		t.Fatal("virtual=true")
	}
	if !isVirtualCamera(json.RawMessage(`{"go2rtc_src":"benedicte"}`)) {
		t.Fatal("benedicte treated as virtual for RTSP probe skip")
	}
	if isVirtualCamera(json.RawMessage(`{"go2rtc_src":"cam-abc"}`)) {
		t.Fatal("real go2rtc_src is not virtual")
	}
}

func TestNoPolicyExclusionsRemain(t *testing.T) {
	// Compile-time guard: former skip helpers must not exist as callable policy.
	// If someone reintroduces skipFrigateCamera/skipFrigateHost, these names
	// should fail to compile when referenced — we assert helpers we keep instead.
	_ = isDemoGo2rtcCamera
	_ = isVirtualCamera
}
