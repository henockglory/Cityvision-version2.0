package camera

import "testing"

func TestDiscoverySortScore(t *testing.T) {
	if discoverySortScore(DiscoveredDevice{RTSPPort: 8554, HasRTSP: true}) <= discoverySortScore(DiscoveredDevice{Port: 80}) {
		t.Fatal("RTSP devices should sort above HTTP-only")
	}
}

func TestRTSPScanPortsIncludesStandard(t *testing.T) {
	found554 := false
	for _, p := range rtspScanPorts {
		if p == 554 {
			found554 = true
		}
	}
	if !found554 {
		t.Fatal("expected 554 in rtsp scan ports")
	}
}
