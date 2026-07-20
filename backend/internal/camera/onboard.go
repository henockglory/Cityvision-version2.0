package camera

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"github.com/citevision/citevision-v2/backend/internal/models"
)

const onboardProbeTimeout = 10 * time.Second

// StreamStats holds ffprobe results for onboarding.
type StreamStats struct {
	Codec      string  `json:"codec"`
	FPS        float64 `json:"fps"`
	Width      int     `json:"width"`
	Height     int     `json:"height"`
	HasBFrames bool    `json:"has_b_frames"`
}

// ProbeStreamStats runs ffprobe on an RTSP URL.
func ProbeStreamStats(ctx context.Context, rtspURL string) (*StreamStats, error) {
	if rtspURL == "" {
		return nil, fmt.Errorf("empty rtsp url")
	}
	if _, ok := ctx.Deadline(); !ok {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, onboardProbeTimeout)
		defer cancel()
	}
	cmd := exec.CommandContext(ctx, "ffprobe",
		"-rtsp_transport", "tcp",
		"-v", "error",
		"-select_streams", "v:0",
		"-show_entries", "stream=codec_name,r_frame_rate,width,height,has_b_frames",
		"-of", "json",
		rtspURL,
	)
	out, err := cmd.Output()
	if err != nil {
		return nil, err
	}
	var parsed struct {
		Streams []struct {
			CodecName  string `json:"codec_name"`
			RFrameRate string `json:"r_frame_rate"`
			Width      int    `json:"width"`
			Height     int    `json:"height"`
			HasBFrames int    `json:"has_b_frames"`
		} `json:"streams"`
	}
	if err := json.Unmarshal(out, &parsed); err != nil {
		return nil, err
	}
	if len(parsed.Streams) == 0 {
		return nil, fmt.Errorf("no video stream")
	}
	s := parsed.Streams[0]
	fps := parseFrameRate(s.RFrameRate)
	return &StreamStats{
		Codec:      s.CodecName,
		FPS:        fps,
		Width:      s.Width,
		Height:     s.Height,
		HasBFrames: s.HasBFrames > 0,
	}, nil
}

func parseFrameRate(rate string) float64 {
	parts := strings.Split(rate, "/")
	if len(parts) != 2 {
		return 25
	}
	num, _ := strconv.ParseFloat(parts[0], 64)
	den, _ := strconv.ParseFloat(parts[1], 64)
	if den <= 0 {
		return 25
	}
	return num / den
}

func unifiedPipelineEnabled() bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv("UNIFIED_PIPELINE")))
	return v == "" || v == "1" || v == "true" || v == "yes"
}

// OnboardCamera registers go2rtc stream and enriches camera metadata.
// Live preview always uses browser-safe H264 sources (HEVC never exposed to WebRTC).
func OnboardCamera(ctx context.Context, cam *models.Camera, rtspURL string) error {
	if cam == nil || rtspURL == "" {
		return fmt.Errorf("camera or rtsp url missing")
	}
	meta := map[string]interface{}{}
	if len(cam.Metadata) > 0 {
		_ = json.Unmarshal(cam.Metadata, &meta)
	}
	streamName := StreamNameForCamera(cam.ID.String())
	go2 := NewGo2RTCClient()

	stats, probeErr := ProbeStreamStats(ctx, rtspURL)
	if probeErr != nil {
		// Probe failure: still register forced H264 sources so preview can self-heal.
		meta["onboard_probe_error"] = probeErr.Error()
		stats = &StreamStats{Codec: "unknown"}
	} else {
		delete(meta, "onboard_probe_error")
		meta["stream_stats"] = stats
	}

	sources := Go2RTCSourcesForRTSP(rtspURL, stats)
	if len(sources) == 0 {
		sources = []string{ffmpegH264Source(rtspURL)}
	}
	meta["transcode"] = true
	meta["preview_sources"] = sources
	meta["preview_safe"] = true

	if unifiedPipelineEnabled() {
		meta["pipeline_mode"] = "pull"
	}

	_ = go2.UnregisterStream(ctx, streamName)
	if _, err := go2.RegisterStreamSources(ctx, streamName, sources); err != nil {
		meta["onboard_error"] = err.Error()
		meta["stream_ready"] = false
		delete(meta, "go2rtc_src")
		raw, _ := json.Marshal(meta)
		cam.Metadata = raw
		return fmt.Errorf("go2rtc register failed: %w", err)
	}

	meta["go2rtc_src"] = streamName
	meta["stream_ready"] = true
	delete(meta, "onboard_error")
	raw, _ := json.Marshal(meta)
	cam.Metadata = raw
	return nil
}

// EnsureBrowserSafePreview re-registers the stream when go2rtc health is unsafe (HEVC / missing).
// Idempotent — safe to call from preview API and background healer.
func EnsureBrowserSafePreview(ctx context.Context, cam *models.Camera, rtspURL string) (healed bool, err error) {
	if cam == nil || rtspURL == "" {
		return false, fmt.Errorf("camera or rtsp url missing")
	}
	streamName := StreamNameForCamera(cam.ID.String())
	go2 := NewGo2RTCClient()
	health := go2.GetPreviewHealth(ctx, streamName)
	if health.OK && !health.NeedsHeal {
		return false, nil
	}
	if err := OnboardCamera(ctx, cam, rtspURL); err != nil {
		return false, err
	}
	return true, nil
}
