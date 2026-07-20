package camera

import "testing"

func TestBuildRTSPURL_WithCredentials(t *testing.T) {
	url := BuildRTSPURL("hikvision", "192.168.1.108", 554, 1, "admin", "hids+1234", "", "main")
	want := "rtsp://admin:hids+1234@192.168.1.108:554/Streaming/Channels/101"
	if url != want {
		t.Fatalf("got %q want %q", url, want)
	}
}

func TestBuildRTSPURL_CustomPathWithCredentials(t *testing.T) {
	url := BuildRTSPURL("generic", "127.0.0.1", 8554, 1, "user", "pass", "/benedicte", "main")
	want := "rtsp://user:pass@127.0.0.1:8554/benedicte"
	if url != want {
		t.Fatalf("got %q want %q", url, want)
	}
}

func TestBuildRTSPURL_NoCredentials(t *testing.T) {
	url := BuildRTSPURL("generic", "127.0.0.1", 8554, 1, "", "", "/benedicte", "main")
	want := "rtsp://127.0.0.1:8554/benedicte"
	if url != want {
		t.Fatalf("got %q want %q", url, want)
	}
}
