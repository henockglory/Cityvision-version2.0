package demo

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestTranscodeForStreamProducesOutput(t *testing.T) {
	raw := os.Getenv("DEMO_TEST_RAW")
	if raw == "" {
		raw = "/mnt/c/Citevision/data/videos/demo/tmp/e312f375-7442-4089-8022-ed232abc09e8/f28c1338-9091-4d81-a92d-4312844095c5_raw.mp4"
	}
	if st, err := os.Stat(raw); err != nil || st.Size() < 1024 {
		t.Skip("no demo raw fixture")
	}
	out := filepath.Join(os.TempDir(), "citevision-demo-test-stream.mp4")
	defer os.Remove(out)
	if err := TranscodeForStream(t.Context(), raw, out); err != nil {
		t.Fatalf("transcode: %v", err)
	}
	st, err := os.Stat(out)
	if err != nil {
		t.Fatal(err)
	}
	if st.Size() < minOutputBytes {
		t.Fatalf("output too small: %d bytes", st.Size())
	}
}

func TestPickEncoderFallback(t *testing.T) {
	if pickEncoder() == "" {
		t.Fatal("empty encoder")
	}
	if _, err := exec.LookPath("ffmpeg"); err != nil {
		t.Skip("ffmpeg not installed")
	}
}
