package camera

import (
	"strings"
	"testing"
)

func TestGo2RTCSourcesAlwaysForceH264(t *testing.T) {
	rtsp := "rtsp://admin:pass@192.168.1.108:554/live"
	srcs := Go2RTCSourcesForRTSP(rtsp, &StreamStats{Codec: "hevc"})
	if len(srcs) < 1 {
		t.Fatal("expected sources")
	}
	if srcs[0] != "ffmpeg:"+rtsp+"#video=h264#audio=none" {
		t.Fatalf("primary=%q", srcs[0])
	}
	foundAlt := false
	for _, s := range srcs {
		if strings.Contains(s, "/Streaming/Channels/102") {
			foundAlt = true
		}
		if s == rtsp {
			t.Fatal("raw HEVC RTSP must not be registered for preview")
		}
	}
	if !foundAlt {
		t.Fatal("expected Hikvision substream alternate")
	}
}

func TestGo2RTCSourceH264StillTranscodes(t *testing.T) {
	rtsp := "rtsp://admin:pass@192.168.1.108:554/Streaming/Channels/101"
	src := Go2RTCSourceForRTSP(rtsp, &StreamStats{Codec: "h264"})
	if !strings.Contains(src, "ffmpeg:") || !strings.Contains(src, "#video=h264") {
		t.Fatalf("expected forced ffmpeg h264, got %q", src)
	}
}

func TestIsCodecErrorMessage(t *testing.T) {
	cases := []string{
		"Could not find ref with POC 21",
		"[hevc @ 0x123] Error constructing the frame RPS",
		"webrtc/offer: streams: exec/rtsp",
	}
	for _, c := range cases {
		if !IsCodecErrorMessage(c) {
			t.Fatalf("expected codec error: %s", c)
		}
	}
	if IsCodecErrorMessage("connection timeout") {
		t.Fatal("false positive")
	}
}

func TestNeedsPreviewTranscode(t *testing.T) {
	if !NeedsPreviewTranscode(nil) {
		t.Fatal("nil stats need transcode")
	}
	if !NeedsPreviewTranscode(&StreamStats{Codec: "hevc"}) {
		t.Fatal("hevc needs transcode")
	}
	if !NeedsPreviewTranscode(&StreamStats{Codec: "h264", HasBFrames: true}) {
		t.Fatal("b-frames need transcode")
	}
}

func TestInspectPreviewHealthHEVC(t *testing.T) {
	raw := []byte(`{"producers":[{"medias":["video, recvonly, HEVC"]}]}`)
	h := InspectPreviewHealth(raw)
	if !h.NeedsHeal || !h.UnsafeCodec {
		t.Fatalf("expected heal for HEVC: %+v", h)
	}
}

func TestInspectPreviewHealthH264(t *testing.T) {
	raw := []byte(`{"producers":[{"medias":["video, recvonly, H264"],"receivers":[{"codec":{"codec_name":"h264","codec_type":"video"}}]}]}`)
	h := InspectPreviewHealth(raw)
	if !h.OK || h.NeedsHeal {
		t.Fatalf("expected OK: %+v", h)
	}
}
